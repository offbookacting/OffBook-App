# app/tabs/files_tab.py
"""
Files tab - hierarchical file organization with drag-and-drop (Scrivener-style).
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional, Dict
import json
import re
import html

from PyQt6.QtCore import Qt, QMimeData, pyqtSignal, QPoint, QSize
from PyQt6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent, QIcon, QPainter, QColor, QPixmap, QPen, QBrush, QFont
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QPushButton, QMenu, QFileDialog, QInputDialog, QMessageBox,
    QSplitter, QLabel, QToolButton, QDialog, QGridLayout, QScrollArea,
    QAbstractItemView
)

from core.file_manager import FileManager, FileItem, FileItemType
from app.dialogs.add_link_dialog import AddLinkDialog
from app.utils import reveal_in_finder


class FileTree(QTreeWidget):
    """Custom tree to handle drag/drop for the file manager."""

    def __init__(self, file_manager: FileManager, owner: "FilesTab"):
        super().__init__()
        self._file_manager = file_manager
        self._owner = owner
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(False)  # We'll draw our own custom indicator
        # Don't set drag-drop mode here - let FilesTab set it to InternalMove for reordering
        
        # Track drop indicator position
        self._drop_indicator_y: Optional[int] = None
        self._drop_indicator_item: Optional[QTreeWidgetItem] = None
        self._drop_indicator_position: Optional[str] = None  # 'above', 'below', or 'on'

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        try:
            if event.mimeData().hasUrls() or event.source() == self:
                event.acceptProposedAction()
                self._update_drop_indicator(event.position().toPoint())
                return
        except Exception as e:
            print(f"Error in dragEnterEvent: {e}")
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        try:
            if event.mimeData().hasUrls() or event.source() == self:
                event.acceptProposedAction()
                self._update_drop_indicator(event.position().toPoint())
                return
        except Exception as e:
            print(f"Error in dragMoveEvent: {e}")
        super().dragMoveEvent(event)
    
    def dragLeaveEvent(self, event) -> None:
        """Clear drop indicator when drag leaves."""
        try:
            self._drop_indicator_y = None
            self._drop_indicator_item = None
            self._drop_indicator_position = None
            self.update()
        except Exception as e:
            print(f"Error in dragLeaveEvent: {e}")
        super().dragLeaveEvent(event)
    
    def _update_drop_indicator(self, pos: QPoint) -> None:
        """Update the drop indicator position based on mouse position."""
        try:
            item = self.itemAt(pos)
            
            if item is None:
                # No item at position - show indicator at bottom of last item or viewport
                self._drop_indicator_item = None
                self._drop_indicator_position = None
                # Find the last top-level item
                top_level_count = self.topLevelItemCount()
                if top_level_count > 0:
                    last_item = self.topLevelItem(top_level_count - 1)
                    if last_item:
                        try:
                            last_rect = self.visualItemRect(last_item)
                            if last_rect.isValid():
                                self._drop_indicator_y = last_rect.y() + last_rect.height()
                            else:
                                # Invalid rect, use viewport height
                                viewport = self.viewport()
                                if viewport:
                                    self._drop_indicator_y = viewport.height()
                                else:
                                    self._drop_indicator_y = 0
                        except Exception:
                            # If visualItemRect fails, use viewport height
                            viewport = self.viewport()
                            if viewport:
                                self._drop_indicator_y = viewport.height()
                            else:
                                self._drop_indicator_y = 0
                    else:
                        self._drop_indicator_y = 0
                else:
                    # No items, show at top
                    self._drop_indicator_y = 0
            else:
                self._drop_indicator_item = item
                try:
                    item_rect = self.visualItemRect(item)
                    if item_rect.isValid():
                        item_center_y = item_rect.y() + item_rect.height() // 2
                        
                        # Determine if we're above or below the item center
                        if pos.y() < item_center_y:
                            # Drop above this item
                            self._drop_indicator_y = item_rect.y()
                            self._drop_indicator_position = 'above'
                        else:
                            # Drop below this item
                            self._drop_indicator_y = item_rect.y() + item_rect.height()
                            self._drop_indicator_position = 'below'
                    else:
                        # Invalid rect, don't show indicator
                        self._drop_indicator_y = None
                        self._drop_indicator_item = None
                        self._drop_indicator_position = None
                except Exception:
                    # If visualItemRect fails, don't show indicator
                    self._drop_indicator_y = None
                    self._drop_indicator_item = None
                    self._drop_indicator_position = None
            
            self.update()  # Trigger repaint
        except Exception as e:
            print(f"Error in _update_drop_indicator: {e}")
            # Clear indicator on error
            self._drop_indicator_y = None
            self._drop_indicator_item = None
            self._drop_indicator_position = None
    
    def paintEvent(self, event) -> None:
        """Override paint event to draw custom blue drop indicator."""
        super().paintEvent(event)
        
        # Draw blue drop indicator line if we're dragging
        if self._drop_indicator_y is not None:
            try:
                viewport = self.viewport()
                if not viewport:
                    return
                
                painter = QPainter(viewport)
                if not painter.isActive():
                    return
                
                # Use a bright blue color similar to highlighting
                blue_color = QColor("#2196F3")  # Material Design blue
                painter.setPen(blue_color)
                painter.setBrush(blue_color)
                
                # Draw a 3-pixel thick line for better visibility
                viewport_width = viewport.width()
                y = self._drop_indicator_y
                
                # Ensure y is within viewport bounds
                if 0 <= y <= viewport.height():
                    # Draw multiple lines for a thicker indicator
                    for offset in range(3):
                        line_y = y + offset
                        if 0 <= line_y <= viewport.height():
                            painter.drawLine(0, line_y, viewport_width, line_y)
                
                painter.end()
            except Exception as e:
                print(f"Error in paintEvent: {e}")

    def dropEvent(self, event: QDropEvent) -> None:
        try:
            # Clear drop indicator
            self._drop_indicator_y = None
            self._drop_indicator_item = None
            self._drop_indicator_position = None
            self.update()
            
            # External files dropped from Finder/Explorer
            if event.mimeData() and event.mimeData().hasUrls():
                try:
                    target_item = self.itemAt(event.position().toPoint())
                    target_path = None
                    if target_item:
                        target_path = self._owner._get_path_from_tree_item(target_item)
                        # If dropping on a file, use its parent directory
                        if target_path and target_path.is_file():
                            target_path = target_path.parent
                    if not target_path:
                        # Drop on empty area - use files directory
                        target_path = self._owner.file_manager.files_dir
                    
                    if target_path:
                        self._owner.handle_external_drop(event.mimeData().urls(), target_path)
                    event.acceptProposedAction()
                    return
                except Exception as e:
                    print(f"Error handling external drop: {e}")
                    event.ignore()
                    return

            # Internal move within the tree
            try:
                target_item = self.itemAt(event.position().toPoint())
                target_path = None
                if target_item:
                    target_path = self._owner._get_path_from_tree_item(target_item)
                    # If dropping on a file, use its parent directory
                    if target_path and target_path.is_file():
                        target_path = target_path.parent
                if not target_path:
                    target_path = self._owner.file_manager.files_dir

                if target_path:
                    for selected_item in self.selectedItems():
                        if selected_item:
                            source_path = self._owner._get_path_from_tree_item(selected_item)
                            if source_path and target_path and source_path != target_path:
                                self._owner.handle_internal_move(source_path, target_path)

                event.acceptProposedAction()
                # Save order after reordering
                self._owner._save_file_order()
                self._owner.refresh_tree()
            except Exception as e:
                print(f"Error handling internal move: {e}")
                event.ignore()
        except Exception as e:
            print(f"Error in dropEvent: {e}")
            event.ignore()


ICONS_DIR = Path(__file__).resolve().parents[2] / "UI" / "Icons"
ICON_COLOR_WHITE = QColor(255, 255, 255)
FOLDER_ICON_FILENAME = "folder-svgrepo-com.svg"
AUDIO_ICON_FILENAME = "microphone-alt-svgrepo-com.svg"
RTF_BUTTON_ICON_FILENAME = "memo-pencil-svgrepo-com.svg"
RTF_FILE_ICON_FILENAME = "memo-pencil-svgrepo-com.svg"
PDF_ICON_FILENAME = "memo-check-svgrepo-com.svg"
IMAGE_ICON_FILENAME = "photo-svgrepo-com.svg"
INTERNET_ICON_FILENAME = "globe-alt-svgrepo-com.svg"
VIDEO_ICON_FILENAME = "camcorder-svgrepo-com.svg"
REFRESH_ICON_FILENAME = "refresh-cw-svgrepo-com.svg"

SVG_ICON_TINTS: Dict[str, QColor] = {
    FOLDER_ICON_FILENAME: ICON_COLOR_WHITE,
    AUDIO_ICON_FILENAME: ICON_COLOR_WHITE,
    RTF_BUTTON_ICON_FILENAME: ICON_COLOR_WHITE,
    RTF_FILE_ICON_FILENAME: ICON_COLOR_WHITE,
    PDF_ICON_FILENAME: ICON_COLOR_WHITE,
    IMAGE_ICON_FILENAME: ICON_COLOR_WHITE,
    INTERNET_ICON_FILENAME: ICON_COLOR_WHITE,
    VIDEO_ICON_FILENAME: ICON_COLOR_WHITE,
    REFRESH_ICON_FILENAME: ICON_COLOR_WHITE,
}

ICON_TOOLBUTTON_STYLE = """
QToolButton {
    background-color: palette(button);
    border: 1px solid palette(mid);
    border-radius: 8px;
    padding: 4px;
}
QToolButton:hover {
    background-color: palette(midlight);
}
QToolButton:pressed {
    background-color: palette(dark);
}
"""


class FilesTab(QWidget):
    """Files tab with hierarchical file organization."""
    
    file_selected = pyqtSignal(str)  # emits file path
    back_to_projects = pyqtSignal()  # emitted when back button is clicked
    
    def __init__(self, project_root: Path, library_resources_dir: Optional[Path] = None, is_referenced_project: bool = False, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.project_root = project_root
        self.library_resources_dir = library_resources_dir
        self.is_referenced_project = is_referenced_project
        self.file_manager = FileManager(project_root, use_root_as_files_dir=is_referenced_project)
        
        # Custom icon storage (already hidden with . prefix)
        self.custom_icons_file = self.project_root / ".custom_icons.json"
        self.custom_icons = self._load_custom_icons()
        self._icon_cache: dict[tuple[str, int, Optional[str]], QIcon] = {}
        
        self._setup_ui()
        self._refresh_tree()
    
    def _setup_ui(self) -> None:
        """Build the UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Top section with back button
        top_section = QVBoxLayout()
        top_section.setContentsMargins(5, 5, 5, 5)
        top_section.setSpacing(5)
        
        # Back to Projects button
        btn_back = QPushButton("← Back to Projects")
        btn_back.clicked.connect(self.back_to_projects.emit)
        top_section.addWidget(btn_back)
        
        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)
        
        btn_add_file = QPushButton("Add File…")
        btn_add_file.setIcon(self.style().standardIcon(self.style().StandardPixmap.SP_FileIcon))
        btn_add_file.clicked.connect(self._on_add_file)
        toolbar.addWidget(btn_add_file)
        
        # Add text file button (icon only)
        btn_add_text_file = QToolButton()
        btn_add_text_file.setStyleSheet(ICON_TOOLBUTTON_STYLE)
        btn_add_text_file.setIconSize(QSize(18, 18))
        btn_add_text_file.setIcon(self._create_plus_paper_icon())
        btn_add_text_file.setToolTip("New Rich Text File")
        btn_add_text_file.clicked.connect(self._on_add_text_file)
        toolbar.addWidget(btn_add_text_file)
        
        # Add folder button (icon only)
        btn_add_folder = QToolButton()
        btn_add_folder.setStyleSheet(ICON_TOOLBUTTON_STYLE)
        btn_add_folder.setIconSize(QSize(18, 18))
        btn_add_folder.setIcon(self._create_plus_folder_icon())
        btn_add_folder.setToolTip("New Folder")
        btn_add_folder.clicked.connect(self._on_add_folder)
        toolbar.addWidget(btn_add_folder)
        
        # Add link button (icon only)
        btn_add_link = QToolButton()
        btn_add_link.setStyleSheet(ICON_TOOLBUTTON_STYLE)
        btn_add_link.setIconSize(QSize(18, 18))
        btn_add_link.setIcon(self._create_plus_internet_icon())
        btn_add_link.setToolTip("Add Link")
        btn_add_link.clicked.connect(self._on_add_link)
        toolbar.addWidget(btn_add_link)
        
        toolbar.addStretch()
        
        # Refresh button (icon only)
        btn_refresh = QToolButton()
        btn_refresh.setStyleSheet(ICON_TOOLBUTTON_STYLE)
        btn_refresh.setIconSize(QSize(18, 18))
        btn_refresh.setIcon(self._icon_from_entry(REFRESH_ICON_FILENAME))
        btn_refresh.setToolTip("Refresh")
        btn_refresh.clicked.connect(self._refresh_tree)
        toolbar.addWidget(btn_refresh)
        
        top_section.addLayout(toolbar)
        layout.addLayout(top_section)
        
        # File tree (no preview in sidebar - just the tree)
        self.tree = FileTree(self.file_manager, self)
        self.tree.setHeaderHidden(True)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.tree.itemSelectionChanged.connect(self._on_selection_changed)
        # Enable drag and drop for reordering (only for top-level items)
        # Use InternalMove mode for reordering within the same level
        self.tree.setDragDropMode(QTreeWidget.DragDropMode.InternalMove)
        # Connect to model's rowsMoved signal for drag-and-drop reordering
        self.tree.model().rowsMoved.connect(self._on_files_reordered)
        # Ensure all items are visible
        self.tree.setRootIsDecorated(True)
        self.tree.setItemsExpandable(True)
        # Make sure the tree shows all items
        self.tree.setUniformRowHeights(False)
        self.tree.setStyleSheet("""
            QTreeWidget::item {
                padding: 5px;
            }
            QTreeWidget::item:hover {
                background-color: #D3D3D3;
            }
        """)
        
        layout.addWidget(self.tree, stretch=1)
        
        # Enable drag and drop
        self.setAcceptDrops(True)
    
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Handle drag enter event."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
    
    def dropEvent(self, event: QDropEvent) -> None:
        """Handle drop event."""
        if not event.mimeData().hasUrls():
            return
        
        # Determine drop target
        item = self.tree.itemAt(event.position().toPoint())
        target_path = self.file_manager.files_dir
        if item:
            item_path = self._get_path_from_tree_item(item)
            if item_path:
                if item_path.is_dir():
                    target_path = item_path
                else:
                    target_path = item_path.parent
        
        # Add dropped files
        import shutil
        for url in event.mimeData().urls():
            source_path = Path(url.toLocalFile())
            if source_path.exists():
                try:
                    dest_path = target_path / source_path.name
                    # If destination exists, append a number
                    if dest_path.exists():
                        base = dest_path.stem
                        suffix = dest_path.suffix
                        counter = 1
                        while dest_path.exists():
                            dest_path = target_path / f"{base}_{counter}{suffix}"
                            counter += 1
                    
                    if source_path.is_file():
                        shutil.copy2(source_path, dest_path)
                    elif source_path.is_dir():
                        shutil.copytree(source_path, dest_path, dirs_exist_ok=True)
                except Exception as e:
                    QMessageBox.warning(self, "Error", f"Failed to add file: {e}")
        
        self._refresh_tree()
        event.acceptProposedAction()
    
    def refresh_tree(self) -> None:
        """Public helper for the tree to trigger a refresh."""
        self._refresh_tree()
    
    def _load_custom_icons(self) -> dict:
        """Load custom icon preferences from JSON file."""
        if self.custom_icons_file.exists():
            try:
                return json.loads(self.custom_icons_file.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}
    
    def _save_custom_icons(self) -> None:
        """Save custom icon preferences to JSON file."""
        try:
            self.custom_icons_file.write_text(
                json.dumps(self.custom_icons, indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            print(f"Error saving custom icons: {e}")
    
    def _get_icon_for_file(self, file_path: Path) -> QIcon:
        """Get icon for a file based on its type and custom preferences."""
        # Check if there's a custom icon for this specific file
        file_key = str(file_path.resolve())
        if file_key in self.custom_icons:
            icon_char = self.custom_icons[file_key]
            if icon_char == "":  # No icon
                return QIcon()
            return self._create_text_icon(icon_char)
        
        # Default icons based on file type
        if file_path.is_dir():
            return self._icon_from_entry(FOLDER_ICON_FILENAME)
        
        suffix = file_path.suffix.lower()
        
        image_suffixes = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".tif", ".webp", ".heic", ".heif"}
        audio_suffixes = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac", ".aif", ".aiff"}
        video_suffixes = {".mp4", ".m4v", ".mov", ".avi", ".mkv", ".mpg", ".mpeg", ".wmv", ".webm", ".flv"}
        internet_suffixes = {".html", ".htm", ".web"}
        
        icon_map = {
            ".pdf": PDF_ICON_FILENAME,
            ".rtf": RTF_FILE_ICON_FILENAME,
        }
        
        icon_entry = icon_map.get(suffix)
        if icon_entry:
            return self._icon_from_entry(icon_entry)
        
        if suffix in image_suffixes:
            return self._icon_from_entry(IMAGE_ICON_FILENAME)
        if suffix in video_suffixes:
            return self._icon_from_entry(VIDEO_ICON_FILENAME)
        if suffix in audio_suffixes:
            return self._icon_from_entry(AUDIO_ICON_FILENAME)
        if suffix in internet_suffixes:
            return self._icon_from_entry(INTERNET_ICON_FILENAME)
        
        return self._icon_from_entry("📄")  # Default to document icon
    
    def _is_web_link(self, file_path: Path) -> bool:
        """Check if the file should open in the browser workspace."""
        if not file_path or not file_path.exists() or not file_path.is_file():
            return False
        suffix = file_path.suffix.lower()
        if suffix not in ('.html', '.htm', '.web'):
            return False
        _, url = self._extract_web_metadata(file_path)
        return url is not None or suffix == '.web'

    def _sanitize_display_name(self, value: Optional[str], fallback: str) -> str:
        if not isinstance(value, str):
            return fallback
        text = html.unescape(value)
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text or fallback

    def _extract_web_metadata(self, file_path: Path) -> tuple[str, Optional[str]]:
        """Extract (name, url) metadata from supported web link files."""
        suffix = file_path.suffix.lower()
        if suffix == '.web':
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
                raw_name = data.get("name") or file_path.stem
                name = self._sanitize_display_name(raw_name, file_path.stem)
                url = data.get("url")
                if isinstance(url, str):
                    url = url.strip() or None
                else:
                    url = None
                return name, url
            except Exception:
                return file_path.stem, None
        if suffix in ('.html', '.htm'):
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                title_match = re.search(r'<title>(.*?)</title>', content, re.IGNORECASE | re.DOTALL)
                raw_title = title_match.group(1) if title_match else file_path.stem
                name = self._sanitize_display_name(raw_title, file_path.stem)
                url_match = re.search(r'content="0;\s*url=([^"]+)"', content, re.IGNORECASE)
                url = url_match.group(1).strip() if url_match else None
                return name, url
            except Exception:
                return file_path.stem, None
        return file_path.stem, None
    
    def _create_text_icon(self, text: str, size: int = 16) -> QIcon:
        """Create an icon from text (emoji)."""
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Use a font that supports emoji
        font = QFont("Apple Color Emoji", size - 4)
        painter.setFont(font)
        
        # Draw text centered
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, text)
        painter.end()
        
        return QIcon(pixmap)
    
    def _load_svg_icon(self, path: Path, size: int = 16, color: Optional[QColor] = None) -> QIcon:
        """Load an SVG icon, optionally tinting it to the given color."""
        if not path.exists():
            return QIcon()
        
        color_key = color.name() if color else None
        cache_key = (str(path.resolve()), size, color_key)
        cached_icon = self._icon_cache.get(cache_key)
        if cached_icon:
            return cached_icon
        
        renderer = QSvgRenderer(str(path))
        if not renderer.isValid():
            icon = QIcon(str(path))
            self._icon_cache[cache_key] = icon
            return icon
        
        dpr = self.devicePixelRatioF() if hasattr(self, "devicePixelRatioF") else 1.0
        pixmap = QPixmap(int(size * dpr), int(size * dpr))
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
        
        pixmap.setDevicePixelRatio(dpr)
        icon = QIcon(pixmap)
        self._icon_cache[cache_key] = icon
        return icon
    
    def _icon_from_entry(self, entry) -> QIcon:
        """Resolve an icon entry which may be an emoji, filename, or QIcon."""
        if isinstance(entry, QIcon):
            return entry
        
        if isinstance(entry, str):
            icon_str = entry.strip()
            lower = icon_str.lower()
            if lower.endswith(('.png', '.jpg', '.jpeg', '.svg', '.ico', '.bmp', '.gif')):
                icon_path = Path(icon_str)
                if not icon_path.is_absolute():
                    icon_path = ICONS_DIR / icon_str
                if icon_path.exists():
                    if icon_path.suffix.lower() == ".svg":
                        tint_color = SVG_ICON_TINTS.get(icon_path.name)
                        return self._load_svg_icon(icon_path, size=16, color=tint_color)
                    return QIcon(str(icon_path))
            if icon_str:
                return self._create_text_icon(icon_str)
        
        return self._create_text_icon("📄")

    def _refresh_tree(self) -> None:
        """Refresh the file tree."""
        self.tree.clear()
        
        # First, scan project folder and add any files not in file_manager
        self._sync_project_files()
        
        # Use the files directory instead of project root
        files_dir = self.file_manager.files_dir
        
        if not files_dir.exists():
            files_dir.mkdir(parents=True, exist_ok=True)
            return
        
        # Load file order from JSON
        file_order = self._load_file_order()
        
        # Get all items in the files directory
        all_items = []
        try:
            for item in files_dir.iterdir():
                # Skip hidden files and excluded items (including macOS Icon files)
                excluded_names = {'.ds_store', 'icon\r', 'icon\n', 'icon', '.custom_icons.json', 'file_order.json', '.file_order.json'}
                if item.name.startswith('.') or item.name.lower() in excluded_names:
                    continue
                # Skip .json files (never show them in files tab)
                if item.is_file() and item.suffix.lower() == '.json':
                    continue
                # Ensure we include all files and directories, including PDFs
                if item.exists():
                    all_items.append(item)
        except Exception as e:
            print(f"Error reading files directory {files_dir}: {e}")
            import traceback
            traceback.print_exc()
            return
        
        # Separate directories and files - ensure we capture all files including PDFs
        directories = [item for item in all_items if item.is_dir()]
        files = [item for item in all_items if item.is_file() and item.exists()]
        
        # Sort items according to saved order
        if file_order:
            order_map = {name: idx for idx, name in enumerate(file_order)}
            # Sort directories
            directories.sort(key=lambda x: (order_map.get(x.name, 9999), x.name.lower()))
            # Sort files
            files.sort(key=lambda x: (order_map.get(x.name, 9999), x.name.lower()))
        else:
            # Default sort: directories first, then files, both alphabetically
            directories.sort(key=lambda x: x.name.lower())
            files.sort(key=lambda x: x.name.lower())
        
        # Combine: directories first, then files
        items = directories + files
        
        # Add items to tree (no root item - directly add to tree)
        added_dirs = 0
        added_files = 0
        for item_path in items:
            try:
                # Verify the item still exists
                if not item_path.exists():
                    print(f"Skipping non-existent item: {item_path}")
                    continue
                
                # Try to find corresponding FileManager item
                file_item = self.file_manager.find_item_by_path(str(item_path.resolve()))
                item_id = file_item.id if file_item else None
                
                # Get display name for web links
                display_name = item_path.name
                if self._is_web_link(item_path):
                    display_name, _ = self._extract_web_metadata(item_path)
                
                # Create tree item as top-level item (no parent)
                tree_item = QTreeWidgetItem([display_name])
                tree_item.setData(0, Qt.ItemDataRole.UserRole, item_id)
                tree_item.setData(0, Qt.ItemDataRole.UserRole + 1, str(item_path.resolve()))
                
                # Set icon
                icon = self._get_icon_for_file(item_path)
                tree_item.setIcon(0, icon)
                
                # Ensure item is enabled and selectable
                tree_item.setFlags(
                    Qt.ItemFlag.ItemIsEnabled | 
                    Qt.ItemFlag.ItemIsSelectable | 
                    Qt.ItemFlag.ItemIsDragEnabled |
                    Qt.ItemFlag.ItemIsDropEnabled
                )
                
                # If it's a directory, recursively add children
                if item_path.is_dir():
                    self._build_tree_from_filesystem(item_path, tree_item)
                    added_dirs += 1
                else:
                    # It's a file
                    added_files += 1
                
                # Add as top-level item to the tree (for both files and directories)
                self.tree.addTopLevelItem(tree_item)
                print(f"✓ Added: {item_path.name} ({'dir' if item_path.is_dir() else 'file'})")
            except Exception as e:
                print(f"✗ Error adding item {item_path} to tree: {e}")
                import traceback
                traceback.print_exc()
                continue
        
        print(f"Summary: Added {added_dirs} directories and {added_files} files to tree")
        print(f"Tree now has {self.tree.topLevelItemCount()} top-level items")
        
        # Expand all by default, but folders remain collapsible
        self.tree.expandAll()
        
        # Force update of the tree widget
        self.tree.update()
        self.tree.repaint()
    
    def _build_tree_from_filesystem(self, directory: Path, parent_item: QTreeWidgetItem) -> None:
        """Recursively build tree items from the file system."""
        if not directory.exists() or not directory.is_dir():
            return
        
        # Exclude certain directories and files
        EXCLUDED_NAMES = {
            '.rehearsal', 'file_structure.json', '.file_structure.json',  # FileManager's internal files
            '.custom_icons.json', 'file_order.json', '.file_order.json',  # FilesTab's internal files
            '.git', '.ds_store', '__pycache__', '.pyc', 'icon\r', 'icon'  # System files
        }
        
        try:
            # Get all items in the directory, sorted (folders first, then files)
            items = []
            for item in directory.iterdir():
                # Skip hidden files and excluded items (case-insensitive)
                if item.name.startswith('.') or item.name.lower() in EXCLUDED_NAMES:
                    continue
                # Skip .json files (never show them in files tab)
                if item.is_file() and item.suffix.lower() == '.json':
                    continue
                
                items.append(item)
            
            # Sort: directories first, then files, both alphabetically
            items.sort(key=lambda x: (not x.is_dir(), x.name.lower()))
            
            for item_path in items:
                # Try to find corresponding FileManager item
                file_item = self.file_manager.find_item_by_path(str(item_path.resolve()))
                item_id = file_item.id if file_item else None
                
                # Create tree item
                tree_item = QTreeWidgetItem(parent_item, [item_path.name])
                tree_item.setData(0, Qt.ItemDataRole.UserRole, item_id)
                tree_item.setData(0, Qt.ItemDataRole.UserRole + 1, str(item_path.resolve()))
                
                # Set icon
                icon = self._get_icon_for_file(item_path)
                tree_item.setIcon(0, icon)
                
                # Set icon based on type
                if item_path.is_dir():
                    # Recursively add children
                    self._build_tree_from_filesystem(item_path, tree_item)
                elif item_path.is_file():
                    # File - no children to add
                    pass
                    
        except PermissionError:
            # Skip directories we can't read
            pass
        except Exception as e:
            # Skip items that cause errors
            import traceback
            print(f"Error building tree for {directory}: {e}\n{traceback.format_exc()}")
    
    def _sync_project_files(self) -> None:
        """Sync files from files directory into file_manager."""
        try:
            # Get root item - this points to the files directory
            root = self.file_manager.get_root()
            
            # Scan the files directory
            files_dir = self.file_manager.files_dir
            if not files_dir.exists():
                files_dir.mkdir(parents=True, exist_ok=True)
                return
            
            # Exclude certain directories and files
            EXCLUDED_NAMES = {
                '.rehearsal', 'file_structure.json', '.file_structure.json',  # FileManager's internal files
                '.git', '.ds_store', '__pycache__', '.pyc', 'icon\r', 'icon'  # System files
            }
            
            # Process all files and directories directly in the files directory
            items_to_process = []
            try:
                for item in files_dir.iterdir():
                    items_to_process.append((item, root.id))
            except PermissionError:
                pass
            
            processed_paths = set()
            
            while items_to_process:
                current_path, parent_id = items_to_process.pop(0)
                
                # Skip if already processed
                path_str = str(current_path.resolve())
                if path_str in processed_paths:
                    continue
                processed_paths.add(path_str)
                
                # Skip hidden files and excluded directories (case-insensitive)
                if current_path.name.startswith('.') or current_path.name.lower() in EXCLUDED_NAMES:
                    continue
                # Skip .json files (never show them in files tab)
                if current_path.is_file() and current_path.suffix.lower() == '.json':
                    continue
                
                try:
                    if current_path.is_file():
                        # Check if already in file_manager
                        existing = self.file_manager.find_item_by_path(path_str)
                        if not existing:
                            # Add to file_manager as a reference (don't copy)
                            self.file_manager.add_file(
                                current_path,
                                parent_id=parent_id,
                                copy_file=False
                            )
                    elif current_path.is_dir():
                        # Check if folder already exists in file_manager
                        existing = None
                        parent_item = self.file_manager.get_item(parent_id)
                        if parent_item:
                            for child_id in parent_item.children:
                                child = self.file_manager.get_item(child_id)
                                if child and child.name == current_path.name and child.type == FileItemType.FOLDER:
                                    # Check if it's the same path
                                    if Path(child.path).resolve() == current_path.resolve():
                                        existing = child
                                        break
                        
                        if not existing:
                            # Create folder in file_manager that references the actual folder
                            import time
                            import uuid
                            folder_id = str(uuid.uuid4())
                            folder_item = FileItem(
                                id=folder_id,
                                name=current_path.name,
                                type=FileItemType.FOLDER,
                                path=str(current_path.resolve()),
                                parent_id=parent_id,
                                created_at=time.time(),
                                updated_at=time.time(),
                            )
                            self.file_manager._items[folder_id] = folder_item
                            parent_item.children.append(folder_id)
                            parent_item.updated_at = time.time()
                            self.file_manager._save()
                        else:
                            folder_id = existing.id
                        
                        # Add all items in this directory to processing queue
                        try:
                            for item in current_path.iterdir():
                                items_to_process.append((item, folder_id))
                        except PermissionError:
                            pass  # Skip directories we can't read
                            
                except Exception as e:
                    # Skip files that can't be added
                    continue
                    
        except Exception as e:
            # Non-critical - just log
            import traceback
            print(f"Error syncing project files: {e}\n{traceback.format_exc()}")
    
    def _build_tree_item(self, file_item: FileItem, parent: Optional[QTreeWidgetItem]) -> QTreeWidgetItem:
        """Build a tree item from a FileItem."""
        item = QTreeWidgetItem(parent, [file_item.name])
        item.setData(0, Qt.ItemDataRole.UserRole, file_item.id)
        
        # Set icon based on type
        icon_name = {
            FileItemType.FOLDER: "folder",
            FileItemType.PDF: "pdf",
            FileItemType.TEXT: "text",
            FileItemType.IMAGE: "image",
            FileItemType.AUDIO: "audio",
            FileItemType.VIDEO: "video",
        }.get(file_item.type, "file")
        
        # Add children
        for child_id in file_item.children:
            child = self.file_manager.get_item(child_id)
            if child:
                self._build_tree_item(child, item)
        
        return item
    
    def _on_add_file(self) -> None:
        """Add a file to the hierarchy."""
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select Files to Add", "", "All Files (*.*)"
        )
        
        item = self.tree.currentItem()
        target_path = self.file_manager.files_dir
        if item:
            item_path = self._get_path_from_tree_item(item)
            if item_path:
                if item_path.is_dir():
                    target_path = item_path
                else:
                    target_path = item_path.parent
        
        import shutil
        for file_path in files:
            try:
                source = Path(file_path)
                dest = target_path / source.name
                # If destination exists, append a number
                if dest.exists():
                    base = dest.stem
                    suffix = dest.suffix
                    counter = 1
                    while dest.exists():
                        dest = target_path / f"{base}_{counter}{suffix}"
                        counter += 1
                shutil.copy2(source, dest)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to add file: {e}")
        
        # Save order after adding files
        self._save_file_order()
        self._refresh_tree()
    
    def _create_plus_paper_icon(self) -> QIcon:
        """Create an icon with a paper/document and plus sign."""
        base_icon = self._icon_from_entry(RTF_BUTTON_ICON_FILENAME)
        pixmap = base_icon.pixmap(16, 16)
        
        # Create a new pixmap with plus overlay
        result = QPixmap(16, 16)
        result.fill(Qt.GlobalColor.transparent)
        painter = QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw the base icon
        painter.drawPixmap(0, 0, pixmap)
        
        # Draw a small plus sign in the corner
        painter.setPen(QPen(QColor(0, 0, 0), 1.5))
        painter.setBrush(QBrush(QColor(255, 255, 255)))
        # Draw white circle background for plus
        painter.drawEllipse(10, 2, 6, 6)
        # Draw plus sign
        painter.setPen(QPen(QColor(0, 0, 0), 1.5))
        center_x, center_y = 13, 5
        painter.drawLine(center_x - 2, center_y, center_x + 2, center_y)
        painter.drawLine(center_x, center_y - 2, center_x, center_y + 2)
        
        painter.end()
        return QIcon(result)
    
    def _create_plus_folder_icon(self) -> QIcon:
        """Create an icon with a folder and plus sign."""
        # Get custom folder icon
        base_icon = self._icon_from_entry(FOLDER_ICON_FILENAME)
        pixmap = base_icon.pixmap(16, 16)
        
        # Create a new pixmap with plus overlay
        result = QPixmap(16, 16)
        result.fill(Qt.GlobalColor.transparent)
        painter = QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw the base icon
        painter.drawPixmap(0, 0, pixmap)
        
        # Draw a small plus sign in the corner
        painter.setPen(QPen(QColor(0, 0, 0), 1.5))
        painter.setBrush(QBrush(QColor(255, 255, 255)))
        # Draw white circle background for plus
        painter.drawEllipse(10, 2, 6, 6)
        # Draw plus sign
        painter.setPen(QPen(QColor(0, 0, 0), 1.5))
        center_x, center_y = 13, 5
        painter.drawLine(center_x - 2, center_y, center_x + 2, center_y)
        painter.drawLine(center_x, center_y - 2, center_x, center_y + 2)
        
        painter.end()
        return QIcon(result)
    
    def _create_plus_internet_icon(self) -> QIcon:
        """Create an icon with a globe/internet symbol and plus sign."""
        base_icon = self._icon_from_entry(INTERNET_ICON_FILENAME)
        pixmap = base_icon.pixmap(16, 16)
        
        result = QPixmap(16, 16)
        result.fill(Qt.GlobalColor.transparent)
        painter = QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.drawPixmap(0, 0, pixmap)
        
        # Draw a small plus sign in the corner
        painter.setPen(QPen(QColor(0, 0, 0), 1.5))
        painter.setBrush(QBrush(QColor(255, 255, 255)))
        painter.drawEllipse(10, 2, 6, 6)
        painter.setPen(QPen(QColor(0, 0, 0), 1.5))
        center_x, center_y = 13, 5
        painter.drawLine(center_x - 2, center_y, center_x + 2, center_y)
        painter.drawLine(center_x, center_y - 2, center_x, center_y + 2)
        
        painter.end()
        return QIcon(result)
    
    def _on_add_text_file(self) -> None:
        """Create a new rich text file."""
        name, ok = QInputDialog.getText(self, "New Rich Text File", "File name:")
        if not ok or not name.strip():
            return
        
        # Ensure .rtf extension if not provided
        file_name = name.strip()
        if not file_name.endswith('.rtf'):
            file_name += '.rtf'
        
        item = self.tree.currentItem()
        target_path = self.file_manager.files_dir
        if item:
            item_path = self._get_path_from_tree_item(item)
            if item_path:
                if item_path.is_dir():
                    target_path = item_path
                else:
                    target_path = item_path.parent
        
        try:
            new_file = target_path / file_name
            if new_file.exists():
                QMessageBox.warning(self, "Error", f"A file named '{file_name}' already exists.")
                return
            # Create empty RTF file with basic RTF header
            rtf_content = "{\\rtf1\\ansi\\deff0 {\\fonttbl {\\f0 Times New Roman;}}\\f0\\fs24 }"
            new_file.write_text(rtf_content, encoding='utf-8')
            # Save order after adding file
            self._save_file_order()
            self._refresh_tree()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to create rich text file: {e}")
    
    def _on_add_folder(self) -> None:
        """Create a new folder."""
        name, ok = QInputDialog.getText(self, "New Folder", "Folder name:")
        if not ok or not name.strip():
            return
        
        item = self.tree.currentItem()
        target_path = self.file_manager.files_dir
        if item:
            item_path = self._get_path_from_tree_item(item)
            if item_path:
                if item_path.is_dir():
                    target_path = item_path
                else:
                    target_path = item_path.parent
        
        try:
            new_folder = target_path / name.strip()
            if new_folder.exists():
                QMessageBox.warning(self, "Error", f"A folder named '{name.strip()}' already exists.")
                return
            new_folder.mkdir(parents=True, exist_ok=True)
            # Save order after adding folder
            self._save_file_order()
            self._refresh_tree()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to create folder: {e}")
    
    def _on_add_link(self) -> None:
        """Open dialog to add a web link."""
        dialog = AddLinkDialog(self.project_root, self.library_resources_dir, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Refresh tree to show new link
            self._save_file_order()
            self._refresh_tree()
            
            # If a file was added from resources, open it automatically
            if hasattr(dialog, 'added_file_path') and dialog.added_file_path:
                # Emit signal to open the file
                self.file_selected.emit(str(dialog.added_file_path.resolve()))
    
    def _on_context_menu(self, position) -> None:
        """Show context menu for tree item."""
        item = self.tree.itemAt(position)
        if not item:
            return
        
        # Check if this is the actual root folder (files_dir) - which shouldn't appear in the tree
        # Since the root folder doesn't appear in the tree, all items should be deletable/renamable
        file_path = self._get_path_from_tree_item(item)
        # Only disable operations if this is actually the files_dir itself
        # (which shouldn't happen, but just to be safe)
        is_actually_root = file_path and file_path.resolve() == self.file_manager.files_dir.resolve()
        
        # Check if this is a web link file
        is_web_link = file_path and file_path.is_file() and self._is_web_link(file_path)
        is_file = file_path and file_path.is_file()
        
        menu = QMenu(self)
        
        # Add "Open in Browser" option for web link files
        if is_web_link:
            act_open_browser = menu.addAction("Open in Browser")
            act_open_browser.triggered.connect(lambda: self._on_open_web_link(item))
            
            # Add "Add to Resources" option for web link files if library resources dir exists
            if self.library_resources_dir and self.library_resources_dir.exists():
                act_add_to_resources = menu.addAction("Add to Resources")
                act_add_to_resources.triggered.connect(lambda: self._on_add_to_resources(item))
            
            menu.addSeparator()
        
        # Add "Change Icon" option
        act_change_icon = menu.addAction("Change Icon...")
        act_change_icon.triggered.connect(lambda: self._on_change_icon(item, file_path))
        menu.addSeparator()
        
        # Add "Duplicate" option for files (all files are duplicatable)
        if is_file:
            duplicate_text = "Duplicate" if is_web_link else "Duplicate File"
            act_duplicate = menu.addAction(duplicate_text)
            if is_web_link:
                act_duplicate.triggered.connect(lambda: self._on_duplicate_web_file(item))
            else:
                act_duplicate.triggered.connect(lambda: self._on_duplicate_file(item))
            menu.addSeparator()
        
        # Add "View File Location" option for all files and folders (no exceptions)
        if file_path:
            act_view_location = menu.addAction("View File Location")
            act_view_location.triggered.connect(lambda: self._on_view_file_location(item))
            menu.addSeparator()
        
        act_rename = menu.addAction("Rename")
        act_rename.setEnabled(not is_actually_root)
        act_rename.triggered.connect(lambda: self._on_rename_item(item))
        
        act_delete = menu.addAction("Delete")
        act_delete.setEnabled(not is_actually_root)
        act_delete.triggered.connect(lambda: self._on_delete_item(item))
        
        menu.exec(self.tree.mapToGlobal(position))
    
    def _on_open_web_link(self, item: QTreeWidgetItem) -> None:
        """Open web link in default browser."""
        file_path = self._get_path_from_tree_item(item)
        if not file_path or not file_path.exists():
            return
        
        try:
            _, url = self._extract_web_metadata(file_path)
            if url:
                import webbrowser
                webbrowser.open(url)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to open link: {e}")
    
    def _on_add_to_resources(self, item: QTreeWidgetItem) -> None:
        """Add web link to library resources."""
        file_path = self._get_path_from_tree_item(item)
        if not file_path or not file_path.exists():
            return
        
        if not self.library_resources_dir or not self.library_resources_dir.exists():
            QMessageBox.warning(self, "Error", "Library resources directory not available.")
            return
        
        try:
            import shutil
            
            # Copy file to resources directory
            dest_path = self.library_resources_dir / file_path.name
            
            # Handle name conflicts
            if dest_path.exists():
                base_name = dest_path.stem
                counter = 1
                while dest_path.exists():
                    dest_path = self.library_resources_dir / f"{base_name}_{counter}{file_path.suffix}"
                    counter += 1
            
            shutil.copy2(file_path, dest_path)
            
            # Get link name for success message
            link_name, _ = self._extract_web_metadata(file_path)
            
            QMessageBox.information(
                self,
                "Success",
                f"'{link_name}' has been added to library resources.\n\n"
                "This link is now available across all projects."
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to add to resources:\n{e}")
    
    def _on_view_file_location(self, item: QTreeWidgetItem) -> None:
        """View file location in Finder (macOS) or Explorer (Windows)."""
        file_path = self._get_path_from_tree_item(item)
        if not file_path or not file_path.exists():
            QMessageBox.warning(
                self,
                "File Not Found",
                f"The file or folder does not exist:\n{file_path}"
            )
            return
        
        try:
            reveal_in_finder(file_path)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to reveal file location:\n{e}")
    
    def _on_rename_item(self, item: QTreeWidgetItem) -> None:
        """Rename an item."""
        item_id = item.data(0, Qt.ItemDataRole.UserRole)
        file_path = self._get_path_from_tree_item(item)
        
        if not file_path or not file_path.exists():
            return
        
        # Check if this is a web link file - handle rename while preserving extension
        is_web_link = self._is_web_link(file_path)
        
        if is_web_link:
            _, url = self._extract_web_metadata(file_path)
            current_base_name = file_path.stem
            suffix = file_path.suffix
            suffix_lower = suffix.lower()
            name, ok = QInputDialog.getText(
                self, "Rename Link", "New name (without extension):", text=current_base_name
            )
            if not ok:
                return
            new_base = name.strip()
            if not new_base or new_base == current_base_name:
                return
            if "/" in new_base or "\\" in new_base:
                QMessageBox.warning(self, "Error", "Name cannot contain path separators.")
                return
            if "." in new_base:
                QMessageBox.warning(self, "Error", "Please enter a name without an extension.")
                return
            
            new_filename = f"{new_base}{suffix}"
            new_path = file_path.with_name(new_filename)
            if new_path.exists():
                QMessageBox.warning(self, "Error", f"A file named '{new_filename}' already exists.")
                return
            
            try:
                if suffix_lower == '.web':
                    data = json.loads(file_path.read_text(encoding="utf-8"))
                    data["name"] = new_base
                    file_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
                elif suffix_lower in ('.html', '.htm'):
                    import re
                    content = file_path.read_text(encoding="utf-8")
                    escaped_name = html.escape(new_base)
                    new_content = re.sub(
                        r'<title>.*?</title>',
                        f'<title>{escaped_name}</title>',
                        content,
                        flags=re.IGNORECASE | re.DOTALL
                    )
                    if url:
                        new_content = re.sub(
                            r'<p>Redirecting to <a href="[^"]+">.*?</a>...</p>',
                            f'<p>Redirecting to <a href="{html.escape(url)}">{escaped_name}</a>...</p>',
                            new_content,
                            flags=re.IGNORECASE | re.DOTALL
                        )
                    file_path.write_text(new_content, encoding="utf-8")
                file_path.rename(new_path)
                self._refresh_tree()
                return
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to rename link: {e}")
                return
        
        # Regular file or folder rename
        current_name = item.text(0)
        name, ok = QInputDialog.getText(
            self, "Rename", "New name:", text=current_name
        )
        if not ok or not name.strip() or name.strip() == current_name:
            return
        
        try:
            # If item is in FileManager, use FileManager's rename
            if item_id:
                file_item = self.file_manager.get_item(item_id)
                if file_item:
                    self.file_manager.rename_item(item_id, name.strip())
                    self._refresh_tree()
                    return
            
            # Otherwise, rename directly in file system
            new_path = file_path.parent / name.strip()
            if new_path.exists():
                QMessageBox.warning(self, "Error", f"A file or folder named '{name.strip()}' already exists.")
                return
            
            file_path.rename(new_path)
            self._refresh_tree()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to rename: {e}")
    
    def _on_delete_item(self, item: QTreeWidgetItem) -> None:
        """Delete an item."""
        item_id = item.data(0, Qt.ItemDataRole.UserRole)
        file_path = self._get_path_from_tree_item(item)
        
        if not file_path or not file_path.exists():
            return
        
        item_name = item.text(0)
        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Are you sure you want to delete '{item_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                # If item is in FileManager, use FileManager's delete
                if item_id:
                    file_item = self.file_manager.get_item(item_id)
                    if file_item:
                        self.file_manager.delete_item(item_id, remove_files=True)
                        self._refresh_tree()
                        return
                
                # Otherwise, delete directly from file system
                import shutil
                if file_path.is_dir():
                    shutil.rmtree(file_path, ignore_errors=True)
                else:
                    file_path.unlink(missing_ok=True)
                self._refresh_tree()
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to delete: {e}")
    
    def _on_duplicate_file(self, item: QTreeWidgetItem) -> None:
        """Duplicate a file."""
        item_id = item.data(0, Qt.ItemDataRole.UserRole)
        file_path = self._get_path_from_tree_item(item)
        
        if not file_path or not file_path.exists() or not file_path.is_file():
            return
        
        try:
            # Get parent folder
            parent_path = file_path.parent
            
            # Generate a unique name for the duplicate
            original_name = file_path.name
            stem = file_path.stem
            suffix = file_path.suffix
            
            # Try "filename_copy.ext" first
            duplicate_name = f"{stem}_copy{suffix}"
            duplicate_path = parent_path / duplicate_name
            
            # If that exists, try numbered versions
            counter = 2
            while duplicate_path.exists():
                duplicate_name = f"{stem} ({counter}){suffix}"
                duplicate_path = parent_path / duplicate_name
                counter += 1
                # Safety limit
                if counter > 1000:
                    QMessageBox.warning(self, "Error", "Too many duplicate files. Please clean up existing duplicates.")
                    return
            
            # Copy the file
            import shutil
            shutil.copy2(str(file_path), str(duplicate_path))
            
            # Add to file manager if the original item is in the file manager
            if item_id:
                file_item = self.file_manager.get_item(item_id)
                if file_item:
                    # Add the duplicate to the same parent
                    # Use copy_file=True so it properly handles the path, but the file is already copied
                    # The add_file method will check if source and dest are the same and skip copying
                    self.file_manager.add_file(
                        duplicate_path,
                        parent_id=file_item.parent_id,
                        name=duplicate_name,
                        copy_file=True
                    )
            else:
                # If not in file manager, we still need to add it
                # Find the parent item in the tree to get its parent_id
                parent_item = item.parent()
                if parent_item:
                    parent_item_id = parent_item.data(0, Qt.ItemDataRole.UserRole)
                    if parent_item_id:
                        self.file_manager.add_file(
                            duplicate_path,
                            parent_id=parent_item_id,
                            name=duplicate_name,
                            copy_file=True
                        )
                else:
                    # Top-level item, add to root
                    self.file_manager.add_file(
                        duplicate_path,
                        parent_id=self.file_manager.get_root().id,
                        name=duplicate_name,
                        copy_file=True
                    )
            
            # Refresh the tree
            self._refresh_tree()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to duplicate file: {e}")
    
    def _on_duplicate_web_file(self, item: QTreeWidgetItem) -> None:
        """Duplicate a web link file (.web/.html)."""
        file_path = self._get_path_from_tree_item(item)
        
        if not file_path or not file_path.exists() or not file_path.is_file():
            return
        
        try:
            parent_path = file_path.parent
            stem = file_path.stem
            suffix = file_path.suffix
            display_name, url = self._extract_web_metadata(file_path)
            
            # Generate unique filename
            duplicate_name = f"{stem}_copy{suffix}"
            duplicate_path = parent_path / duplicate_name
            counter = 2
            while duplicate_path.exists():
                duplicate_name = f"{stem}_{counter}{suffix}"
                duplicate_path = parent_path / duplicate_name
                counter += 1
                if counter > 1000:
                    QMessageBox.warning(self, "Error", "Too many duplicate files. Please clean up existing duplicates.")
                    return
            
            new_display_name = f"{display_name} (Copy)" if counter == 2 else f"{display_name} ({counter-1})"
            
            if suffix.lower() == '.web':
                data = json.loads(file_path.read_text(encoding="utf-8"))
                data["name"] = new_display_name
                duplicate_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            else:
                import re
                content = file_path.read_text(encoding="utf-8")
                new_content = re.sub(
                    r'<title>.*?</title>',
                    f'<title>{new_display_name}</title>',
                    content,
                    flags=re.IGNORECASE | re.DOTALL
                )
                if url:
                    new_content = re.sub(
                        r'<p>Redirecting to <a href="[^"]+">.*?</a>...</p>',
                        f'<p>Redirecting to <a href="{url}">{new_display_name}</a>...</p>',
                        new_content,
                        flags=re.IGNORECASE | re.DOTALL
                    )
                duplicate_path.write_text(new_content, encoding="utf-8")
            
            self._save_file_order()
            self._refresh_tree()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to duplicate link: {e}")
    
    # ----- Drag/drop helpers -----

    def handle_external_drop(self, urls, target_path: Optional[Path]) -> None:
        """Process files dropped from the OS onto the tree."""
        if not target_path:
            target_path = self.file_manager.files_dir
        elif not target_path.is_dir():
            target_path = target_path.parent if target_path.parent else self.file_manager.files_dir
        
        import shutil
        for url in urls:
            source_path = Path(url.toLocalFile())
            if not source_path.exists():
                continue
            try:
                dest_path = target_path / source_path.name
                # If destination exists, append a number
                if dest_path.exists():
                    base = dest_path.stem
                    suffix = dest_path.suffix
                    counter = 1
                    while dest_path.exists():
                        dest_path = target_path / f"{base}_{counter}{suffix}"
                        counter += 1
                
                if source_path.is_file():
                    shutil.copy2(source_path, dest_path)
                elif source_path.is_dir():
                    shutil.copytree(source_path, dest_path, dirs_exist_ok=True)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to add file: {e}")
        self._refresh_tree()

    def handle_internal_move(self, source_path: Path, target_path: Path) -> None:
        """Process internal tree re-parenting."""
        if not source_path or not target_path:
            return
        
        # Ensure target is a directory
        if not target_path.is_dir():
            target_path = target_path.parent if target_path.parent else self.file_manager.files_dir
        
        # Prevent moving into own descendant
        try:
            if source_path.is_dir():
                target_resolved = target_path.resolve()
                source_resolved = source_path.resolve()
                # Check if target is within source
                try:
                    target_resolved.relative_to(source_resolved)
                    QMessageBox.warning(self, "Invalid Move", "Cannot move a folder into itself.")
                    return
                except ValueError:
                    pass  # Target is not within source, which is good
        except Exception:
            pass  # If we can't check, proceed anyway
        
        try:
            import shutil
            dest_path = target_path / source_path.name
            if dest_path.exists() and dest_path.resolve() != source_path.resolve():
                QMessageBox.warning(self, "Error", f"A file or folder named '{source_path.name}' already exists in the destination.")
                return
            
            if source_path.resolve() != dest_path.resolve():
                shutil.move(str(source_path), str(dest_path))
                # Save order after moving (only if moving within top level)
                if source_path.parent == self.file_manager.files_dir and dest_path.parent == self.file_manager.files_dir:
                    self._save_file_order()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to move item: {e}")

    def _on_selection_changed(self) -> None:
        """Handle selection change - emit signal when a file is selected."""
        selected_items = self.tree.selectedItems()
        if selected_items:
            item = selected_items[0]
            file_path = self._get_path_from_tree_item(item)
            if file_path and file_path.is_file():
                self.file_selected.emit(str(file_path.resolve()))
    
    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """Handle double-click on item - open in popout window."""
        # Get file path from tree item
        file_path = self._get_path_from_tree_item(item)
        if file_path and file_path.is_file():
            # For files, open in popout window
            from app.file_popout_window import FilePopoutWindow
            popout = FilePopoutWindow(file_path, self)
            popout.show()
            popout.raise_()
            popout.activateWindow()
            
            # Also emit signal for backward compatibility (in case other code listens to it)
            self.file_selected.emit(str(file_path.resolve()))
    
    def _on_change_icon(self, item: QTreeWidgetItem, file_path: Path) -> None:
        """Show icon picker dialog to change file/folder icon."""
        if not file_path:
            return
        
        # Create icon picker dialog
        dialog = IconPickerDialog(file_path, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected_icon = dialog.selected_icon
            file_key = str(file_path.resolve())
            
            if selected_icon is None:
                # Remove custom icon (use default)
                if file_key in self.custom_icons:
                    del self.custom_icons[file_key]
            else:
                # Save custom icon
                self.custom_icons[file_key] = selected_icon
            
            self._save_custom_icons()
            self._refresh_tree()
    
    def _get_path_from_tree_item(self, item: QTreeWidgetItem) -> Optional[Path]:
        """Get the file system path for a tree item by reconstructing from tree hierarchy."""
        path_data = item.data(0, Qt.ItemDataRole.UserRole + 1)
        if path_data:
            return Path(path_data)
        
        # Build path by walking up the tree
        path_parts = []
        current = item
        
        # Walk up to root (no root item now, items are directly in tree)
        while current:
            path_parts.insert(0, current.text(0))
            current = current.parent()
        
        if path_parts:
            # Start from files_dir instead of project_root
            return self.file_manager.files_dir / Path(*path_parts)
        return None
    
    def _find_tree_item_by_path(self, target_path: Path) -> Optional[QTreeWidgetItem]:
        """Find a tree item corresponding to the given path."""
        if not target_path:
            return None
        target = str(target_path.resolve())
        
        def _search(item: QTreeWidgetItem) -> Optional[QTreeWidgetItem]:
            if item.data(0, Qt.ItemDataRole.UserRole + 1) == target:
                return item
            for i in range(item.childCount()):
                result = _search(item.child(i))
                if result:
                    return result
            return None
        
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            result = _search(item)
            if result:
                return result
        return None
    
    def place_item_after(self, reference_path: Optional[Path], target_path: Path) -> None:
        """Move target path directly below reference path in the tree."""
        target_item = self._find_tree_item_by_path(target_path)
        if not target_item:
            return
        
        reference_item = self._find_tree_item_by_path(reference_path) if reference_path else None
        parent_item = target_item.parent()
        
        # Detach target item from current position
        if parent_item:
            row = parent_item.indexOfChild(target_item)
            parent_item.takeChild(row)
        else:
            row = self.tree.indexOfTopLevelItem(target_item)
            if row != -1:
                self.tree.takeTopLevelItem(row)
        
        inserted = False
        if reference_item and reference_item.parent() == parent_item:
            if parent_item:
                ref_index = parent_item.indexOfChild(reference_item)
                parent_item.insertChild(ref_index + 1, target_item)
            else:
                ref_index = self.tree.indexOfTopLevelItem(reference_item)
                self.tree.insertTopLevelItem(ref_index + 1, target_item)
                self._save_file_order()
            inserted = True
        
        if not inserted:
            if parent_item:
                parent_item.addChild(target_item)
            else:
                self.tree.addTopLevelItem(target_item)
                self._save_file_order()
        
        # Ensure ancestors are expanded before selecting
        ancestor = target_item.parent()
        while ancestor:
            self.tree.expandItem(ancestor)
            ancestor = ancestor.parent()
        
        self.tree.setCurrentItem(target_item)
        self.tree.scrollToItem(target_item, QAbstractItemView.ScrollHint.PositionAtCenter)
    
    def _on_files_reordered(self, parent, start, end, destination, row) -> None:
        """Handle file reordering via drag and drop."""
        # Only save order for top-level items (direct children of tree, not nested)
        if parent.isValid():
            return  # Only handle top-level reordering
        
        # Save the new order
        self._save_file_order()
    
    def _load_file_order(self) -> list[str]:
        """Load file order from JSON file in project folder."""
        # Use hidden filename for referenced projects
        order_filename = ".file_order.json" if self.is_referenced_project else "file_order.json"
        preferred_order_file = self.project_root / order_filename
        alternate_order_file = self.project_root / (".file_order.json" if not self.is_referenced_project else "file_order.json")
        
        # Check both hidden and non-hidden versions for backward compatibility
        order_files = [preferred_order_file, alternate_order_file]
        
        for order_file in order_files:
            try:
                if order_file.exists():
                    with open(order_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        # For referenced projects, migrate non-hidden files to hidden versions
                        if self.is_referenced_project and order_file != preferred_order_file:
                            try:
                                import shutil
                                shutil.move(str(order_file), str(preferred_order_file))
                            except Exception:
                                pass  # If migration fails, continue using existing file
                        return data.get('file_names', [])
            except Exception:
                continue
        
        return []
    
    def _save_file_order(self) -> None:
        """Save file order to JSON file in project folder."""
        try:
            # Get current order of top-level file names from the tree widget
            file_names = []
            for i in range(self.tree.topLevelItemCount()):
                item = self.tree.topLevelItem(i)
                if item:
                    file_names.append(item.text(0))
            
            # Use hidden filename for referenced projects
            order_filename = ".file_order.json" if self.is_referenced_project else "file_order.json"
            order_file = self.project_root / order_filename
            
            with open(order_file, 'w', encoding='utf-8') as f:
                json.dump({'file_names': file_names}, f, indent=2)
        except Exception as e:
            # Non-critical error, just log it
            print(f"Failed to save file order: {e}")


class IconPickerDialog(QDialog):
    """Dialog for selecting a custom icon for a file or folder."""
    
    def __init__(self, file_path: Path, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.selected_icon: Optional[str] = None
        self._setup_ui()
    
    def _setup_ui(self):
        """Build the UI."""
        self.setWindowTitle(f"Change Icon: {self.file_path.name}")
        self.setModal(True)
        self.resize(500, 400)
        
        layout = QVBoxLayout(self)
        
        # Info label
        info = QLabel(f"Select an icon for: {self.file_path.name}")
        info.setWordWrap(True)
        layout.addWidget(info)
        
        # Icon grid in scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        grid = QGridLayout(scroll_widget)
        grid.setSpacing(10)
        
        # Emoji icon options organized by category
        icon_categories = {
            "Documents": ["📄", "📃", "📝", "📋", "📑", "📰", "📓", "📔", "📕", "📖", "📗", "📘", "📙", "📚"],
            "Theater": ["🎭", "🎬", "🎪", "🎨", "🎤", "🎧", "🎵", "🎶", "🎼", "🎹", "🎸", "🎺", "🎻", "🥁"],
            "Media": ["🖼️", "🎞️", "📷", "📸", "📹", "📺", "📻", "📱", "💻", "🖥️", "⌨️", "🖱️", "🖨️", "📀"],
            "Objects": ["📦", "📁", "🗂️", "🗃️", "🗄️", "📇", "🗳️", "🗑️", "📌", "📍", "✂️", "🔍", "🔎", "🔑"],
            "Symbols": ["⭐", "🌟", "✨", "💎", "🔥", "💧", "🌈", "☀️", "🌙", "⚡", "🎯", "🏆", "🎖️", "🏅"],
            "Flags": ["🚩", "🏁", "🏳️", "🏴", "🎌", "🚪", "🔔", "🔕", "📢", "📣", "💬", "💭", "🗨️", "🗯️"],
        }
        
        row = 0
        for category, icons in icon_categories.items():
            # Category label
            cat_label = QLabel(f"<b>{category}</b>")
            grid.addWidget(cat_label, row, 0, 1, 7)
            row += 1
            
            col = 0
            for icon in icons:
                btn = QPushButton(icon)
                btn.setFixedSize(50, 50)
                btn.setStyleSheet("""
                    QPushButton {
                        font-size: 24px;
                        border: 2px solid #ccc;
                        border-radius: 5px;
                        background: white;
                    }
                    QPushButton:hover {
                        border: 2px solid #2196F3;
                        background: #E3F2FD;
                    }
                """)
                btn.clicked.connect(lambda checked, i=icon: self._select_icon(i))
                grid.addWidget(btn, row, col)
                
                col += 1
                if col >= 7:
                    col = 0
                    row += 1
            
            if col > 0:
                row += 1
        
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll, stretch=1)
        
        # No icon button (remove custom icon)
        no_icon_btn = QPushButton("No Icon (Use Default)")
        no_icon_btn.clicked.connect(lambda: self._select_icon(None))
        layout.addWidget(no_icon_btn)
        
        # Cancel button
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(cancel_btn)
    
    def _select_icon(self, icon: Optional[str]):
        """Select an icon and close dialog."""
        self.selected_icon = icon
        self.accept()

