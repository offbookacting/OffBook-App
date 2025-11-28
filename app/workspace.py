# app/workspace.py
"""
Main workspace window with tab-based interface (Files, Rehearse, Read, Edit).
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional, Any

from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QPushButton, QLabel, QMessageBox, QFileDialog, QSplitter,
    QToolButton
)
import json
import re

from core.project_manager import ProjectManager, Project
from core.pdf_parser import PDFParser
from core.nlp_processor import parse_script_text, ScriptParse
from app.config import AppConfig
from app.tabs.files_tab import FilesTab
from app.tabs.rehearse_tab import RehearseTab
from app.tabs.annotate_tab import AnnotateTab
from app.tabs.read_tab import ReadTab
from app.tabs.edit_tab import EditTab
from app.tabs.pdf_viewer import PDFViewer
from app.tabs.image_viewer import ImageViewer
from app.tabs.audio_player import AudioPlayer
from app.tabs.web_browser import WebBrowser
from app.tabs.watch_tab import WatchTab
from core.file_state_manager import FileStateManager


ICONS_DIR = Path(__file__).resolve().parents[1] / "UI" / "Icons"
ICON_COLOR_WHITE = QColor(255, 255, 255)
FOLDER_ICON_PATH = ICONS_DIR / "folder-svgrepo-com.svg"
SIDEBAR_ICON_PATH = ICONS_DIR / "sidebar-svgrepo-com.svg"


def _load_svg_icon(path: Path, size: int = 24, color: Optional[QColor] = None) -> QIcon:
    """Load an SVG icon at the requested size, optionally tinting it."""
    if not path.exists():
        return QIcon()
    
    renderer = QSvgRenderer(str(path))
    if not renderer.isValid():
        return QIcon(str(path))
    
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter)
    painter.end()
    
    if color:
        tinted = QPixmap(pixmap.size())
        tinted.fill(Qt.GlobalColor.transparent)
        painter = QPainter(tinted)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.drawPixmap(0, 0, pixmap)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(tinted.rect(), color)
        painter.end()
        pixmap = tinted
    
    return QIcon(pixmap)


class WorkspaceWindow(QMainWindow):
    """Main workspace window with tab-based interface."""
    
    closed = pyqtSignal()  # emitted when window is closed
    
    def __init__(self, project_manager: ProjectManager, project: Project, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.pm = project_manager
        self.project = project
        self.current_parse: Optional[ScriptParse] = None
        self.current_text: str = ""
        self.current_file_path: Optional[Path] = None
        self.app_config = AppConfig()
        self.audio_view_tab: Optional[AudioPlayer] = None
        self.web_view_tab: Optional[WebBrowser] = None
        self.watch_view_tab: Optional[WatchTab] = None
        self.is_audio_mode: bool = False
        self.is_web_mode: bool = False
        self.is_watch_mode: bool = False
        
        # Initialize file state manager
        # Determine project root for state storage
        project_root = None
        is_referenced = self.project.meta and self.project.meta.get("is_referenced_project", False)
        if is_referenced:
            referenced_path = self.project.meta.get("referenced_folder_path")
            if referenced_path:
                folder_path = Path(referenced_path).expanduser().resolve()
                if folder_path.exists() and folder_path.is_dir():
                    project_root = folder_path
        if project_root is None and self.project.meta and "folder_path" in self.project.meta:
            folder_path = Path(self.project.meta["folder_path"]).expanduser().resolve()
            if folder_path.exists() and folder_path.is_dir():
                project_root = folder_path
        if project_root is None:
            pdf_path = Path(self.project.pdf_path)
            pdf_parent = pdf_path.parent
            if pdf_parent.name == self.project.name and pdf_parent.is_dir():
                project_root = pdf_parent
        if project_root is None and self.pm.library:
            expected_project_folder = self.pm.library._projects_dir / self.project.name
            if expected_project_folder.exists() and expected_project_folder.is_dir():
                project_root = expected_project_folder
        if project_root is None:
            project_root = Path(self.project.pdf_path).parent
        
        self.file_state_manager = FileStateManager(project_root)
        
        self.setWindowTitle(f"Scene Partner - {project.name}")
        self.resize(1400, 900)
        
        self._setup_ui()
        self._load_project()
    
    def _setup_ui(self) -> None:
        """Build the UI."""
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Top toolbar with folder icon toggle button
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(5, 5, 5, 5)
        
        # Folder icon button to toggle files sidebar
        self.btn_toggle_files = QToolButton()
        custom_icon = _load_svg_icon(SIDEBAR_ICON_PATH, size=24, color=ICON_COLOR_WHITE)
        if custom_icon.isNull():
            self.btn_toggle_files.setIcon(self.style().standardIcon(self.style().StandardPixmap.SP_DirIcon))
        else:
            self.btn_toggle_files.setIcon(custom_icon)
        self.btn_toggle_files.setIconSize(QSize(24, 24))
        self.btn_toggle_files.setToolTip("Toggle Files Sidebar")
        self.btn_toggle_files.setCheckable(True)
        self.btn_toggle_files.setChecked(True)  # Start with sidebar visible
        self.btn_toggle_files.clicked.connect(self._toggle_files_sidebar)
        toolbar.addWidget(self.btn_toggle_files)
        
        toolbar.addStretch()
        
        self.lbl_project = QLabel(f"Project: {self.project.name}")
        toolbar.addWidget(self.lbl_project)
        
        main_layout.addLayout(toolbar)
        
        # Main splitter for files sidebar and content area
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.main_splitter, stretch=1)
        
        # Files tab as sidebar
        # Determine the correct project root directory
        # Expected structure: library/projects/project_name/
        project_root = None
        
        # Check if this is a referenced project (external folder)
        is_referenced = self.project.meta and self.project.meta.get("is_referenced_project", False)
        if is_referenced:
            # For referenced projects, use the external folder path directly
            referenced_path = self.project.meta.get("referenced_folder_path")
            if referenced_path:
                folder_path = Path(referenced_path).expanduser().resolve()
                if folder_path.exists() and folder_path.is_dir():
                    project_root = folder_path
        
        # If not a referenced project, check if metadata has folder_path
        if project_root is None and self.project.meta and "folder_path" in self.project.meta:
            folder_path = Path(self.project.meta["folder_path"]).expanduser().resolve()
            if folder_path.exists() and folder_path.is_dir():
                project_root = folder_path
        
        # If not found, check if PDF is in a folder named after the project
        if project_root is None:
            pdf_path = Path(self.project.pdf_path)
            pdf_parent = pdf_path.parent
            if pdf_parent.name == self.project.name and pdf_parent.is_dir():
                project_root = pdf_parent
        
        # If still not found, check if there's a project folder at library/projects/project_name
        if project_root is None and self.pm.library:
            expected_project_folder = self.pm.library._projects_dir / self.project.name
            if expected_project_folder.exists() and expected_project_folder.is_dir():
                project_root = expected_project_folder
        
        # Fallback to PDF's parent directory
        if project_root is None:
            project_root = Path(self.project.pdf_path).parent
        
        library_resources_dir = None
        if self.pm.library:
            library_resources_dir = self.pm.library.resources_dir()
        self.files_tab = FilesTab(project_root, library_resources_dir, is_referenced_project=is_referenced)
        self.files_tab.file_selected.connect(self._on_file_selected)
        self.files_tab.back_to_projects.connect(self._on_back)
        self.main_splitter.addWidget(self.files_tab)
        
        # Content area with tabs
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        
        # File name label above tabs (centered)
        file_name_bar = QHBoxLayout()
        file_name_bar.setContentsMargins(10, 5, 10, 5)
        self.lbl_file_name = QLabel("No file selected")
        self.lbl_file_name.setStyleSheet("font-weight: bold; font-size: 12px;")
        self.lbl_file_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        file_name_bar.addStretch()
        file_name_bar.addWidget(self.lbl_file_name)
        file_name_bar.addStretch()
        content_layout.addLayout(file_name_bar)
        
        # Tabs (DaVinci Resolve style)
        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.TabPosition.North)
        self.tabs.setMovable(False)
        content_layout.addWidget(self.tabs, stretch=1)
        
        # Edit tab (first, on the left)
        self.edit_tab = EditTab()
        self.edit_tab.text_changed.connect(self._on_edit_text_changed)
        self.edit_tab_index = self.tabs.addTab(self.edit_tab, "Edit")
        self.edit_tab_visible = True
        
        # Annotate tab (needs project_root and state manager, so create it after files_tab)
        self.annotate_tab = AnnotateTab(project_root, file_state_manager=self.file_state_manager)
        self.tabs.addTab(self.annotate_tab, "Annotate")
        
        # Read tab (create before rehearse tab so we can pass reference)
        library_presets_dir = None
        if self.pm.library:
            library_presets_dir = self.pm.library.voice_presets_dir()
        self.read_tab = ReadTab(self.app_config, library_presets_dir=library_presets_dir, file_state_manager=self.file_state_manager)
        self.read_tab.set_project(self.pm, self.project)
        self.tabs.addTab(self.read_tab, "Read")
        
        # Rehearse tab (pass read_tab reference)
        self.rehearse_tab = RehearseTab(read_tab=self.read_tab)
        self.rehearse_tab.character_changed.connect(self._on_character_changed)
        self.tabs.addTab(self.rehearse_tab, "Rehearse")
        
        self.main_splitter.addWidget(content_widget)
        
        # Set initial sizes: files sidebar 250px, rest to content
        self.main_splitter.setSizes([250, 1150])
        self.main_splitter.setCollapsible(0, False)  # Don't allow complete collapse via splitter
        
        # Connect tab changes
        self.tabs.currentChanged.connect(self._on_tab_changed)
    
    def _load_project(self) -> None:
        """Load project data."""
        try:
            # Verify PDF exists
            pdf_path = Path(self.project.pdf_path)
            if not pdf_path.exists():
                resolved_pdf = self._resolve_missing_pdf(pdf_path)
                if resolved_pdf and resolved_pdf.exists():
                    try:
                        new_project = self.pm.replace_pdf(self.project.id, resolved_pdf, copy_into_library=False)
                        try:
                            def _meta_updater(meta: dict[str, Any]) -> dict[str, Any]:
                                meta.pop("is_placeholder", None)
                                meta["file_path"] = str(resolved_pdf)
                                return meta

                            new_project = self.pm.update_meta(new_project.id, _meta_updater)
                        except Exception:
                            pass
                        self.project = new_project
                        self.read_tab.set_project(self.pm, self.project)
                        pdf_path = Path(self.project.pdf_path)
                    except Exception:
                        pdf_path = resolved_pdf

                if not pdf_path.exists():
                    self._handle_missing_pdf(pdf_path)
                    return
            
            # Refresh annotate tab file list
            self.annotate_tab.refresh_file_list()
            
            # Extract text from PDF
            try:
                parser = PDFParser(str(pdf_path))
                self.current_text = parser.extract_text(preserve_layout=True, ocr_if_empty=True)
                parser.close()
            except Exception as e:
                error_msg = str(e)
                if "No PDF backend available" in error_msg:
                    QMessageBox.critical(
                        self,
                        "PDF Backend Missing",
                        "PDF processing requires either PyMuPDF or pypdf to be installed.\n\n"
                        "Please install one of these packages:\n\n"
                        "  pip install pymupdf\n"
                        "  or\n"
                        "  pip install pypdf\n\n"
                        "You can also install all dependencies with:\n"
                        "  pip install -r requirements.txt"
                    )
                    self.current_text = ""
                    self.current_parse = None
                else:
                    QMessageBox.warning(
                        self,
                        "PDF Parsing Warning",
                        f"Could not extract text from PDF:\n{e}\n\n"
                        "The PDF viewer may still work, but script parsing features will be unavailable."
                    )
                    self.current_text = ""
                    self.current_parse = None
            
            # Parse script
            if self.current_text:
                self.current_parse = parse_script_text(self.current_text)
            else:
                self.current_parse = None
            
            # Update tabs
            self.rehearse_tab.set_script(self.current_parse, self.current_text)
            self.read_tab.set_script(self.current_parse)
            if self.project.chosen_character:
                self.rehearse_tab.set_character(self.project.chosen_character)
            
            # Ensure project PDF is in Files tab (as a reference, not a copy)
            self._ensure_pdf_in_files_tab(pdf_path)
            
            # Set initial file name (project PDF)
            self.current_file_path = pdf_path
            self.lbl_file_name.setText(pdf_path.name)
            
            # Keep Edit tab visible for PDFs (it will show conversion info)
            if not self.edit_tab_visible:
                self.tabs.insertTab(0, self.edit_tab, "Edit")
                self.edit_tab_visible = True
            
            # Inform the user that PDFs cannot be edited directly
            self.edit_tab.load_file(pdf_path)
            
            # Refresh files tab to show all project files
            self.files_tab._refresh_tree()
            
        except Exception as e:
            import traceback
            error_msg = f"Failed to load project:\n{e}\n\n{traceback.format_exc()}"
            QMessageBox.critical(self, "Error", error_msg)
    
    def _resolve_missing_pdf(self, expected_path: Path) -> Optional[Path]:
        """Attempt to locate a PDF for the project when the stored path is missing."""
        meta = self.project.meta or {}

        # Direct meta hint (e.g., when scanned with an existing PDF)
        meta_file = meta.get("file_path")
        if meta_file:
            candidate = Path(meta_file).expanduser()
            if candidate.exists():
                return candidate

        search_roots: list[Path] = []

        folder_hint = meta.get("folder_path")
        if folder_hint:
            folder_path = Path(folder_hint).expanduser()
            if folder_path.exists():
                search_roots.append(folder_path)

        if expected_path.parent.exists():
            search_roots.append(expected_path.parent)

        if self.pm.library:
            try:
                library_root = self.pm.library.root
                project_dir = (library_root / self.pm.library.PROJECTS_DIR / self.project.name).resolve()
                if project_dir.exists():
                    search_roots.append(project_dir)
            except Exception:
                pass

        seen_roots: set[Path] = set()
        candidates: list[tuple[Path, Path]] = []

        for root in search_roots:
            try:
                resolved_root = root.resolve()
            except Exception:
                continue

            if resolved_root in seen_roots or not resolved_root.is_dir():
                continue

            seen_roots.add(resolved_root)
            try:
                for child in resolved_root.rglob("*.pdf"):
                    if child.is_file():
                        candidates.append((child, resolved_root))
            except Exception:
                continue

        if not candidates:
            return None

        preferred_stems = {expected_path.stem.lower()}
        if self.project.name:
            preferred_stems.add(self.project.name.lower())
        preferred_keywords = ("script", "draft", "screenplay")

        def score(item: tuple[Path, Path]) -> tuple[int, int, str]:
            path, base = item
            stem_lower = path.stem.lower()
            if stem_lower in preferred_stems:
                priority = 0
            elif any(keyword in stem_lower for keyword in preferred_keywords):
                priority = 1
            else:
                priority = 2

            try:
                depth = len(path.resolve().relative_to(base).parts)
            except Exception:
                depth = len(path.parts)

            return (priority, depth, path.name.lower())

        candidates.sort(key=score)
        return candidates[0][0]

    def _handle_missing_pdf(self, missing_path: Path) -> None:
        """Update the UI gracefully when the project PDF cannot be found."""
        meta = self.project.meta or {}
        folder_hint = meta.get("folder_path")
        folder_path = Path(folder_hint).expanduser() if folder_hint else None

        self.current_text = ""
        self.current_parse = None
        self.current_file_path = None

        self.read_tab.set_script(None)
        self.read_tab.lbl_status.setText("No script PDF found for this project yet.")
        self.rehearse_tab.set_script(None, "")

        if hasattr(self.annotate_tab, "pdf_editor") and self.annotate_tab.pdf_editor:
            try:
                self.annotate_tab.pdf_editor.close()
            except Exception:
                pass
            self.annotate_tab.pdf_editor = None
        self.annotate_tab.current_pdf_path = None
        self.annotate_tab.current_image_path = None
        self.annotate_tab.label_pdf.setText(
            "No PDF found for this project.\nAdd a script PDF via the Files tab to begin annotating."
        )

        self.lbl_file_name.setText("No file selected")
        self.edit_tab.show_missing_pdf_message(
            self.project.name,
            expected_path=missing_path,
            project_folder=folder_path if folder_path and folder_path.exists() else None,
        )

        # Ensure the files tree reflects the current state
        self.files_tab._refresh_tree()

    def _ensure_pdf_in_files_tab(self, pdf_path: Path) -> None:
        """Ensure the project's PDF is available in the Files tab."""
        try:
            # Check if PDF is already in the file manager
            existing = self.files_tab.file_manager.find_item_by_path(str(pdf_path.resolve()))
            if not existing:
                # Add it to the root folder as a reference (don't copy)
                try:
                    self.files_tab.file_manager.add_file(
                        pdf_path, 
                        parent_id=self.files_tab.file_manager.get_root().id,
                        name=pdf_path.name,
                        copy_file=False  # Just reference the existing file
                    )
                    self.files_tab._refresh_tree()
                except Exception as e:
                    # If it already exists or other error, that's okay
                    print(f"Note: Could not add PDF reference to Files tab: {e}")
        except Exception as e:
            # Non-critical - just log it
            print(f"Note: Could not add PDF to Files tab: {e}")
    
    def _toggle_files_sidebar(self, checked: bool) -> None:
        """Toggle the files sidebar visibility."""
        if checked:
            # Show sidebar - restore previous size or use default
            sizes = self.main_splitter.sizes()
            if sizes[0] == 0:
                # Was collapsed, restore to default width
                self.main_splitter.setSizes([250, sizes[1] - 250])
            self.files_tab.setVisible(True)
        else:
            # Hide sidebar
            sizes = self.main_splitter.sizes()
            self.files_tab.setVisible(False)
            # Store the content size before hiding
            self.main_splitter.setSizes([0, sum(sizes)])
    
    def _rtf_to_plain_text(self, rtf_content: str) -> str:
        """Convert RTF content to plain text by removing RTF formatting codes."""
        text = rtf_content
        
        # First, remove RTF header groups with nested braces (font tables, color tables, etc.)
        # Handle nested braces by finding matching pairs
        def remove_nested_group(text: str, start_pattern: str) -> str:
            """Remove RTF groups that may contain nested braces."""
            result = []
            i = 0
            while i < len(text):
                # Look for the start pattern
                match = re.search(start_pattern, text[i:])
                if not match:
                    result.append(text[i:])
                    break
                
                # Add text before the match
                result.append(text[i:i + match.start()])
                
                # Find the matching closing brace
                start_pos = i + match.end() - 1  # Position of opening brace
                brace_count = 0
                j = start_pos
                found_start = False
                
                while j < len(text):
                    if text[j] == '{' and (j == 0 or text[j-1] != '\\'):
                        brace_count += 1
                        found_start = True
                    elif text[j] == '}' and (j == 0 or text[j-1] != '\\'):
                        brace_count -= 1
                        if found_start and brace_count == 0:
                            # Found matching closing brace
                            i = j + 1
                            break
                    j += 1
                else:
                    # No matching brace found, skip this match
                    result.append(text[i:i + match.end()])
                    i = i + match.end()
            return ''.join(result)
        
        # Remove font tables (may contain "Times New Roman" or other font names)
        text = remove_nested_group(text, r'\\fonttbl')
        
        # Remove color tables and stylesheets
        text = remove_nested_group(text, r'\\colortbl')
        text = remove_nested_group(text, r'\\stylesheet')
        
        # Remove RTF header commands
        text = re.sub(r'\\rtf1[^\s{}]*', '', text)
        text = re.sub(r'\\ansi[^\s{}]*', '', text)
        text = re.sub(r'\\deff0[^\s{}]*', '', text)
        
        # Remove font and size commands
        text = re.sub(r'\\f\d+', '', text)
        text = re.sub(r'\\fs\d+', '', text)
        
        # Replace line break commands with actual newlines
        text = text.replace('\\par', '\n')
        text = text.replace('\\line', '\n')
        text = text.replace('\\par\n', '\n')
        
        # Remove other RTF control words (commands that start with \)
        # But be careful not to remove escaped characters
        text = re.sub(r'\\([a-z]+)\d*\s?', '', text)
        
        # Handle escaped characters - convert them back
        text = text.replace('\\{', '{PLACEHOLDER_OPEN_BRACE}')
        text = text.replace('\\}', '{PLACEHOLDER_CLOSE_BRACE}')
        text = text.replace('\\\\', '\\')
        
        # Remove unescaped braces (RTF group delimiters)
        text = re.sub(r'[{}]', '', text)
        
        # Restore escaped braces as regular braces
        text = text.replace('{PLACEHOLDER_OPEN_BRACE}', '{')
        text = text.replace('{PLACEHOLDER_CLOSE_BRACE}', '}')
        
        # Clean up multiple spaces (but preserve intentional spacing)
        text = re.sub(r'[ \t]+', ' ', text)
        
        # Clean up multiple newlines (keep at most 2 consecutive)
        text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
        
        # Remove leading/trailing whitespace from each line
        lines = text.split('\n')
        lines = [line.strip() for line in lines]
        text = '\n'.join(lines)
        
        # Trim overall whitespace
        text = text.strip()
        
        return text
    
    def _resolve_web_url(self, file_path: Path) -> Optional[str]:
        """Resolve a URL from supported web link file formats."""
        suffix = file_path.suffix.lower()
        try:
            if suffix in ('.html', '.htm'):
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                match = re.search(r'content="0;\s*url=([^"]+)"', content, re.IGNORECASE)
                if match:
                    return match.group(1).strip()
                return file_path.resolve().as_uri()
            if suffix == '.web':
                data = json.loads(file_path.read_text(encoding="utf-8"))
                url = data.get("url")
                if isinstance(url, str) and url.strip():
                    return url.strip()
                # Some JSON web files may embed HTML
                html = data.get("html")
                if isinstance(html, str):
                    match = re.search(r'content="0;\s*url=([^"]+)"', html, re.IGNORECASE)
                    if match:
                        return match.group(1).strip()
        except Exception as exc:
            print(f"Warning: failed to resolve web URL for {file_path}: {exc}")
        return None
    
    def _get_file_type_display(self, path: Path) -> str:
        """Get a human-readable file type string."""
        if not path.exists():
            return "Unknown"
        
        if path.is_dir():
            return "Folder"
        
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            return "PDF"
        elif suffix in [".txt", ".md", ".rtf"]:
            return "Text File" if suffix != ".rtf" else "Rich Text File"
        elif suffix in [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg"]:
            return "Image"
        elif suffix in [".mp3", ".wav", ".m4a", ".aac"]:
            return "Audio"
        elif suffix in [".mp4", ".mov", ".avi", ".mkv"]:
            return "Video"
        elif suffix in [".html", ".htm", ".web"]:
            return "Web Link"
        elif suffix:
            return f"{suffix[1:].upper()} File"
        else:
            return "File"
    
    
    def _on_tab_changed(self, index: int) -> None:
        """Handle tab change."""
        # Find which tab is at this index
        widget = self.tabs.widget(index)
        if widget == self.annotate_tab:
            # Refresh annotate tab file list when switching to it
            self.annotate_tab.refresh_file_list()
        elif widget == self.read_tab:
            # Update read tab when switching to it
            self.read_tab.set_script(self.current_parse)
    
    def _setup_audio_view(self, audio_path: Path) -> None:
        """Set up audio view mode - remove all tabs and show only View tab with audio player."""
        # Remove all existing tabs
        while self.tabs.count() > 0:
            self.tabs.removeTab(0)
        
        # Create audio player widget
        if self.audio_view_tab:
            # Clean up previous audio player
            self.audio_view_tab.deleteLater()
        
        self.audio_view_tab = AudioPlayer(audio_path, self)
        self.tabs.addTab(self.audio_view_tab, "View")
        
        # Set audio mode flag
        self.is_audio_mode = True
        self.current_file_path = audio_path
        self.lbl_file_name.setText(audio_path.name)
        
        # Switch to the View tab
        self.tabs.setCurrentIndex(0)
    
    def _setup_watch_view(self, video_path: Path) -> None:
        """Set up watch view mode - show a single tab with the video player."""
        while self.tabs.count() > 0:
            self.tabs.removeTab(0)
        
        if self.audio_view_tab:
            self.audio_view_tab.deleteLater()
            self.audio_view_tab = None
            self.is_audio_mode = False
        if self.web_view_tab:
            self.web_view_tab.deleteLater()
            self.web_view_tab = None
            self.is_web_mode = False
        if self.watch_view_tab:
            self.watch_view_tab.deleteLater()
        
        self.watch_view_tab = WatchTab(video_path, self)
        self.tabs.addTab(self.watch_view_tab, "Watch")
        self.tabs.setCurrentIndex(0)
        self.is_watch_mode = True
        self.current_file_path = video_path
        self.lbl_file_name.setText(video_path.name)
    
    def _setup_web_view(self, web_file_path: Path) -> None:
        """Set up web view mode - remove all tabs and show only Browse tab with web browser."""
        print(f"DEBUG _setup_web_view called with: {web_file_path}")
        print(f"DEBUG File exists: {web_file_path.exists()}")
        
        # Remove all existing tabs
        while self.tabs.count() > 0:
            self.tabs.removeTab(0)
        
        # Determine URL to load
        url = self._resolve_web_url(web_file_path) or web_file_path.resolve().as_uri()
        print(f"DEBUG: Final URL to pass to WebBrowser: '{url}'")
        
        # Create web browser widget
        if self.web_view_tab:
            # Clean up previous web browser
            self.web_view_tab.deleteLater()
        
        self.web_view_tab = WebBrowser(url, web_file_path, self)
        self.web_view_tab.open_in_new_tab.connect(self._on_open_in_new_tab)
        self.tabs.addTab(self.web_view_tab, "Browse")
        
        # Update state
        self.is_web_mode = True
        self.current_file_path = web_file_path
        self.lbl_file_name.setText(web_file_path.name)
        
        # Switch to the Browse tab
        self.tabs.setCurrentIndex(0)
    
    def _restore_normal_tabs(self) -> None:
        """Restore normal tabs after exiting audio or web mode."""
        # Remove audio view tab
        if self.audio_view_tab:
            for i in range(self.tabs.count()):
                if self.tabs.widget(i) == self.audio_view_tab:
                    self.tabs.removeTab(i)
                    break
            self.audio_view_tab.deleteLater()
            self.audio_view_tab = None
        
        # Remove web view tab
        if self.web_view_tab:
            for i in range(self.tabs.count()):
                if self.tabs.widget(i) == self.web_view_tab:
                    self.tabs.removeTab(i)
                    break
            self.web_view_tab.deleteLater()
            self.web_view_tab = None
        
        # Remove watch view tab
        if self.watch_view_tab:
            for i in range(self.tabs.count()):
                if self.tabs.widget(i) == self.watch_view_tab:
                    self.tabs.removeTab(i)
                    break
            self.watch_view_tab.deleteLater()
            self.watch_view_tab = None
        
        # Restore normal tabs
        self.tabs.addTab(self.edit_tab, "Edit")
        self.edit_tab_visible = True
        
        # Add other tabs
        self.tabs.addTab(self.annotate_tab, "Annotate")
        self.tabs.addTab(self.read_tab, "Read")
        self.tabs.addTab(self.rehearse_tab, "Rehearse")
        
        # Clear audio, web, and watch mode flags
        self.is_audio_mode = False
        self.is_web_mode = False
        self.is_watch_mode = False
    
    def _on_file_selected(self, file_path: str) -> None:
        """Handle file selection from Files tab - load into all relevant tabs."""
        path = Path(file_path)
        if not path.exists():
            return
        
        # Check if this is an audio or web link file
        is_video = path.is_file() and WatchTab.is_video_file(path)
        is_audio = path.is_file() and AudioPlayer.is_audio_file(path) and not is_video
        is_web_file = path.is_file() and path.suffix.lower() in ('.html', '.htm', '.web')
        
        # Track current file
        self.current_file_path = path
        
        # Update file name label
        self.lbl_file_name.setText(path.name)
        
        # Handle audio files - show only "View" tab with audio player
        if is_audio:
            self._setup_audio_view(path)
            return
        
        # Handle video files - show only "Watch" tab with video player
        if is_video:
            self._setup_watch_view(path)
            return
        
        # Handle web files - show only "Browse" tab with web browser
        if is_web_file:
            self._setup_web_view(path)
            return
        
        # If we were in audio mode, restore normal tabs
        if self.is_audio_mode:
            self._restore_normal_tabs()
        
        # If we were in web mode, restore normal tabs
        if self.is_web_mode:
            self._restore_normal_tabs()
        
        if self.is_watch_mode:
            self._restore_normal_tabs()
        
        # Show/hide tabs based on file type
        is_pdf = path.suffix.lower() == ".pdf"
        is_rtf = path.suffix.lower() == ".rtf"
        is_image = path.suffix.lower() in [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg"]
        is_png = path.suffix.lower() == ".png"
        files_root = self.files_tab.file_manager.files_dir.resolve()
        is_top_level_file = path.is_file() and path.parent.resolve() == files_root
        
        # Handle PNG files and PDF files specially - Edit tab should never be visible
        if is_png or is_pdf:
            # Hide Edit tab for PNG and PDF files
            if self.edit_tab_visible:
                edit_index = None
                for i in range(self.tabs.count()):
                    if self.tabs.widget(i) == self.edit_tab:
                        edit_index = i
                        break
                if edit_index is not None:
                    # If currently on Edit tab, switch away first
                    if self.tabs.currentWidget() == self.edit_tab:
                        # Find Annotate tab index
                        for i in range(self.tabs.count()):
                            if self.tabs.widget(i) == self.annotate_tab:
                                self.tabs.setCurrentIndex(i)
                                break
                    self.tabs.removeTab(edit_index)
                    self.edit_tab_visible = False
            
            # Show Annotate tab as "View" for PNG files, "Annotate" for PDFs, and make it the first tab (leftmost)
            annotate_index = None
            for i in range(self.tabs.count()):
                if self.tabs.widget(i) == self.annotate_tab:
                    annotate_index = i
                    break
            
            tab_name = "View" if is_png else "Annotate"
            if annotate_index is None:
                # Annotate tab not present, add it at position 0 (leftmost)
                self.tabs.insertTab(0, self.annotate_tab, tab_name)
            else:
                # Annotate tab exists, move it to position 0 and rename
                self.tabs.removeTab(annotate_index)
                self.tabs.insertTab(0, self.annotate_tab, tab_name)
            
            # Switch to View/Annotate tab automatically
            self.tabs.setCurrentIndex(0)
        else:
            # For non-PNG, non-PDF files, handle Edit tab visibility normally
            # Handle Edit tab visibility - show for text files (but not PNGs or PDFs)
            if not self.edit_tab_visible:
                # Insert at position 0 (leftmost position)
                self.tabs.insertTab(0, self.edit_tab, "Edit")
                self.edit_tab_visible = True
            
            # For all files (except images which can't be edited as text), load into edit tab
            # IMPORTANT: All tabs should work with the same file
            if not is_image and (path.suffix.lower() in [".txt", ".md", ".rtf", ""] or path.is_file()):
                # RTF files and other text files should always be editable, even if top-level
                # Load text/RTF file into edit tab
                # This same file's text will be used by read/rehearse tabs below
                try:
                    self.edit_tab.load_file(path)
                except Exception as e:
                    print(f"Error loading file in edit tab: {e}")
            
            # Handle Annotate tab visibility - show for PDFs and images, hide for RTF and other text files
            if is_rtf or (not is_pdf and not is_image):
                # Hide Annotate tab for RTF files and non-PDF/image files
                annotate_index = None
                for i in range(self.tabs.count()):
                    if self.tabs.widget(i) == self.annotate_tab:
                        annotate_index = i
                        break
                if annotate_index is not None:
                    # If currently on Annotate tab, switch to Edit tab first
                    if self.tabs.currentWidget() == self.annotate_tab:
                        # Find Edit tab index (should be 0, but check to be safe)
                        for i in range(self.tabs.count()):
                            if self.tabs.widget(i) == self.edit_tab:
                                self.tabs.setCurrentIndex(i)
                                break
                    self.tabs.removeTab(annotate_index)
            elif is_pdf or is_image:
                # Show Annotate tab for PDFs and images (if not already shown)
                annotate_visible = any(self.tabs.widget(i) == self.annotate_tab for i in range(self.tabs.count()))
                if not annotate_visible:
                    # Insert after Edit tab (at index 1, or after Edit if Edit is visible)
                    insert_index = 1 if self.edit_tab_visible else 0
                    # Find Edit tab index to insert after it
                    if self.edit_tab_visible:
                        for i in range(self.tabs.count()):
                            if self.tabs.widget(i) == self.edit_tab:
                                insert_index = i + 1
                                break
                    self.tabs.insertTab(insert_index, self.annotate_tab, "Annotate")
                else:
                    # Tab already exists, make sure it's labeled "Annotate" (not "View")
                    annotate_index = None
                    for i in range(self.tabs.count()):
                        if self.tabs.widget(i) == self.annotate_tab:
                            annotate_index = i
                            break
                    if annotate_index is not None:
                        self.tabs.setTabText(annotate_index, "Annotate")
        
        # Load PDF or image into annotate tab
        if is_pdf or is_image:
            try:
                self.annotate_tab.load_pdf(path)  # load_pdf method now handles both PDFs and images
            except Exception as e:
                print(f"Error loading file in annotate tab: {e}")
        
        # Extract text from the SAME file for read/rehearse tabs
        text = ""
        try:
            if path.suffix.lower() == ".pdf":
                # Extract text from PDF - same file that's loaded in annotate tab
                parser = PDFParser(str(path))
                text = parser.extract_text(preserve_layout=True, ocr_if_empty=True)
                parser.close()
            elif path.suffix.lower() in [".txt", ".md", ".rtf"]:
                # Read text/RTF file - same file that's loaded in edit tab
                if path.suffix.lower() == ".rtf":
                    # For RTF, extract plain text using the same method as edit_tab
                    rtf_content = path.read_text(encoding="utf-8", errors="ignore")
                    text = self._rtf_to_plain_text(rtf_content)
                else:
                    text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            print(f"Error extracting text from file: {e}")
            text = ""
        
        # Parse script if we have text and load into read/rehearse tabs
        # These tabs work with the same file's text content
        if text:
            try:
                script_parse = parse_script_text(text)
                self.current_parse = script_parse
                self.current_text = text
                
                # Load into read tab - same file's text
                self.read_tab.set_script(script_parse)
                
                # Load into rehearse tab - same file's text
                self.rehearse_tab.set_script(script_parse, text)
            except Exception as e:
                print(f"Error parsing script: {e}")
                # Still try to load empty script
                self.current_parse = None
                self.current_text = text
                self.read_tab.set_script(None)
        else:
            # No text extracted, clear the tabs
            self.current_parse = None
            self.current_text = ""
            self.read_tab.set_script(None)
            self.rehearse_tab.set_script(None, "")
    
    def _on_character_changed(self, character: str) -> None:
        """Handle character change from Rehearse tab."""
        # Save character to project
        try:
            self.pm.set_character(self.project.id, character)
            self.project = self.pm.get(self.project.id)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to save character: {e}")
    
    def _on_edit_text_changed(self, text: str) -> None:
        """Handle text change from Edit tab - update other tabs."""
        # Update current text
        self.current_text = text
        
        # Parse script if we have text
        if text:
            try:
                script_parse = parse_script_text(text)
                self.current_parse = script_parse
                
                # Update all tabs with the new text
                self.read_tab.set_script(script_parse)
                self.rehearse_tab.set_script(script_parse, text)
            except Exception as e:
                print(f"Error parsing edited text: {e}")
                # Still update with empty parse
                self.current_parse = None
                self.read_tab.set_script(None)
                self.rehearse_tab.set_script(None, text)
        else:
            # Empty text
            self.current_parse = None
            self.read_tab.set_script(None)
            self.rehearse_tab.set_script(None, "")
    
    def _on_back(self) -> None:
        """Return to project browser."""
        # Stop reading if active
        if self.read_tab.script_reader:
            self.read_tab._on_stop_reading()
        self.close()
        self.closed.emit()
    
    def _on_open_in_new_tab(self, url: str, current_file_path: str):
        """Handle opening a link in a new tab."""
        try:
            import json
            from urllib.parse import urlparse
            
            # Extract name from URL
            try:
                parsed = urlparse(url)
                name = parsed.netloc or url
                # Clean up the name
                name = name.replace('www.', '')
            except:
                name = url
            
            # Truncate if too long
            if len(name) > 50:
                name = name[:50] + "..."
            
            # Create filename
            filename = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in name)
            filename = filename.strip()
            if not filename:
                filename = "link"
            
            # Get the directory where the current file is located
            if current_file_path:
                current_path = Path(current_file_path)
                parent_dir = current_path.parent
            else:
                project_root = Path(self.project.pdf_path).parent
                # Determine the correct files directory path
                # Check if project_root already ends with "files" to avoid nested "files/files"
                if project_root.name == "files":
                    parent_dir = project_root
                else:
                    # Check if "files" subdirectory already exists (expected: library/projects/project_name/files)
                    expected_files_dir = project_root / "files"
                    if expected_files_dir.exists() and expected_files_dir.is_dir():
                        # Use existing "files" directory
                        parent_dir = expected_files_dir
                    else:
                        # Create new "files" directory
                        parent_dir = expected_files_dir
                        parent_dir.mkdir(parents=True, exist_ok=True)
            
            # Ensure parent_dir exists (safety check)
            if not parent_dir.exists():
                parent_dir.mkdir(parents=True, exist_ok=True)
            
            # Ensure unique filename
            base_filename = filename
            counter = 1
            web_file = parent_dir / f"{filename}.web"
            while web_file.exists():
                filename = f"{base_filename}_{counter}"
                web_file = parent_dir / f"{filename}.web"
                counter += 1
            
            # Create JSON content for web link
            link_payload = {"name": name, "url": url}
            web_file.write_text(json.dumps(link_payload, indent=2), encoding="utf-8")
            
            # Refresh files tab
            self.files_tab._save_file_order()
            self.files_tab._refresh_tree()
            
            # Position new link directly after the current file
            reference_path = Path(current_file_path).resolve() if current_file_path else None
            self.files_tab.place_item_after(reference_path, web_file)
            
            # Open the new file
            self._setup_web_view(web_file)
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create new tab:\n{e}")
            import traceback
            traceback.print_exc()
    
    def closeEvent(self, event) -> None:
        """Handle window close."""
        # Stop reading if active
        if self.read_tab.script_reader:
            self.read_tab._on_stop_reading()
        self.closed.emit()
        super().closeEvent(event)

