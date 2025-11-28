# app/file_popout_window.py
"""
Popout window for viewing files (PDFs, text files, and audio files).
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional
import sys
import re

from PyQt6.QtCore import Qt, QTimer, QRect, QSize
from PyQt6.QtWidgets import (
    QMainWindow, QVBoxLayout, QWidget, QTextEdit, QPushButton,
    QMessageBox, QGridLayout
)
from PyQt6.QtGui import QIcon, QPixmap, QPainter
from PyQt6.QtSvg import QSvgRenderer

from app.tabs.pdf_viewer import PDFViewer
from app.tabs.image_viewer import ImageViewer
from app.tabs.audio_player import AudioPlayer
from app.tabs.web_browser import WebBrowser
from app.tabs.watch_tab import WatchTab

_SAVE_ICON_PATH_CANDIDATES = [
    Path(__file__).resolve().parents[2] / "ui" / "code" / "save-svgrepo-com.svg",
    Path(__file__).resolve().parents[2] / "ui" / "Icons" / "save-svgrepo-com.svg",
    Path(__file__).resolve().parents[2] / "UI" / "Icons" / "save-svgrepo-com.svg",
]


def _resolve_first_existing_path(paths: list[Path]) -> Optional[Path]:
    for path in paths:
        if path.exists():
            return path
    return None


SAVE_ICON_PATH = _resolve_first_existing_path(_SAVE_ICON_PATH_CANDIDATES)


def _load_svg_icon(path: Optional[Path], size: QSize) -> QIcon:
    if not path or not path.exists():
        return QIcon()

    renderer = QSvgRenderer(str(path))
    if not renderer.isValid():
        return QIcon()

    pixmap = QPixmap(size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()

    icon = QIcon()
    for mode in (
        QIcon.Mode.Normal,
        QIcon.Mode.Active,
        QIcon.Mode.Disabled,
        QIcon.Mode.Selected,
    ):
        icon.addPixmap(pixmap, mode, QIcon.State.Off)

    return icon


class FilePopoutWindow(QMainWindow):
    """Popout window for viewing files."""
    
    def __init__(self, file_path: Path, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.file_path = Path(file_path)
        self._rtf_editor: Optional[QTextEdit] = None
        self._rtf_save_button: Optional[QPushButton] = None
        self._rtf_original_text: str = ""
        self._rtf_is_dirty: bool = False  # Track if RTF file has unsaved changes
        self._setup_ui()
        self._load_file()
    
    def _setup_ui(self) -> None:
        """Build the UI."""
        self.setWindowTitle(f"{self.file_path.name} - Scene Partner")
        
        # Set default size
        self.resize(480, 300)
        
        # Make window stay on top
        # Manage window flags so the popout behaves well across platforms
        if sys.platform == "darwin":
            # Treat the popout as an auxiliary tool window so it can appear alongside
            # a fullscreen workspace window instead of spawning a separate space.
            self.setWindowFlag(Qt.WindowType.Tool, True)
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
            self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow, True)
        else:
            # Keep popouts on top of the main window on other platforms
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        
        # Position near top-right corner of the primary screen
        QTimer.singleShot(0, self._position_top_right)

        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Content widget (will be set by _load_file)
        self.content_widget: Optional[QWidget] = None
    
    def _load_file(self) -> None:
        """Load the file into the window."""
        if not self.file_path.exists():
            self._show_error(f"File not found:\n{self.file_path}")
            return
        
        if not self.file_path.is_file():
            self._show_error(f"Path is not a file:\n{self.file_path}")
            return
        
        # Remove existing content widget
        if self.content_widget:
            self.centralWidget().layout().removeWidget(self.content_widget)
            self.content_widget.deleteLater()
            self.content_widget = None
        self._rtf_editor = None
        self._rtf_save_button = None
        
        # Load based on file type
        suffix = self.file_path.suffix.lower()
        
        if suffix == ".pdf":
            self._load_pdf()
        elif suffix == ".web":
            self._load_web_file()
        elif suffix in [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg"]:
            self._load_image()
        elif WatchTab.is_video_file(self.file_path):
            self._load_video_file()
        elif AudioPlayer.is_audio_file(self.file_path):
            self._load_audio_file()
        elif suffix in [".txt", ".md", ""] or self._is_text_file():
            self._load_text_file()
        else:
            self._show_error(f"Unsupported file type: {suffix}\n\nSupported types: PDF, web links (.web), images (PNG, JPG, etc.), text files, and audio files (MP3, WAV, OGG, M4A, AAC, FLAC, WMA, Opus, etc.).")
    
    def _load_pdf(self) -> None:
        """Load a PDF file."""
        try:
            pdf_viewer = PDFViewer(self.file_path, self)
            self.content_widget = pdf_viewer
            self.centralWidget().layout().addWidget(pdf_viewer)
        except Exception as e:
            self._show_error(f"Error loading PDF:\n{e}")
    
    def _load_image(self) -> None:
        """Load an image file."""
        try:
            image_viewer = ImageViewer(self.file_path, self)
            self.content_widget = image_viewer
            self.centralWidget().layout().addWidget(image_viewer)
        except Exception as e:
            self._show_error(f"Error loading image:\n{e}")
    
    def _load_video_file(self) -> None:
        """Load a video file using the watch workspace player."""
        try:
            watch_tab = WatchTab(self.file_path, self)
            self.content_widget = watch_tab
            self.centralWidget().layout().addWidget(watch_tab)
        except Exception as e:
            self._show_error(f"Error loading video:\n{e}")
    
    def _load_audio_file(self) -> None:
        """Load an audio file."""
        try:
            audio_player = AudioPlayer(self.file_path, self)
            self.content_widget = audio_player
            self.centralWidget().layout().addWidget(audio_player)
            
            # Adjust window size to fit the audio player content
            # Give it a moment for the layout to calculate sizes
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(100, self._adjust_audio_window_size)
        except Exception as e:
            self._show_error(f"Error loading audio file:\n{e}")
    
    def _load_web_file(self) -> None:
        """Load a web link file."""
        try:
            url = WebBrowser.load_web_file(self.file_path)
            if url:
                web_browser = WebBrowser(url, web_file_path=self.file_path, parent=self)
                self.content_widget = web_browser
                self.centralWidget().layout().addWidget(web_browser)
            else:
                self._show_error("Failed to load URL from web file.")
        except Exception as e:
            self._show_error(f"Error loading web file:\n{e}")
    
    def _adjust_audio_window_size(self) -> None:
        """Adjust window size to fit audio player content."""
        if self.content_widget and isinstance(self.content_widget, AudioPlayer):
            # Use adjustSize to fit the content, then add some padding
            self.adjustSize()
            
            # Get the current size and add a bit of padding
            current_size = self.size()
            self.resize(current_size.width() + 20, current_size.height() + 20)
            
            # Set maximum width to prevent it from being too wide
            self.setMaximumWidth(700)
            
            # Ensure minimum size for usability
            if self.width() < 400:
                self.resize(400, self.height())
            if self.height() < 180:
                self.resize(self.width(), 180)
            
            # Reposition after resizing so it stays fully visible
            QTimer.singleShot(0, self._position_top_right)
    
    def _load_text_file(self) -> None:
        """Load a text file."""
        try:
            content = self.file_path.read_text(encoding="utf-8", errors="replace")
            is_rtf = self.file_path.suffix.lower() == ".rtf"
            display_text = content
            if is_rtf:
                display_text = self._rtf_to_plain_text(content)
                self._rtf_original_text = display_text
            
            text_edit = QTextEdit(self)
            text_edit.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
            text_edit.setFontFamily("Courier Prime")
            text_edit.setFontPointSize(12)
            text_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            text_edit.setStyleSheet("QTextEdit { background-color: white; color: black; }")
            text_edit.blockSignals(True)
            text_edit.setPlainText(display_text)
            text_edit.blockSignals(False)
            text_edit.setReadOnly(not is_rtf)
            
            container = QWidget(self)
            container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            container.setStyleSheet("background-color: white;")

            if is_rtf:
                container_layout = QGridLayout(container)
                container_layout.setContentsMargins(0, 0, 0, 0)
                container_layout.setSpacing(0)
                container_layout.addWidget(text_edit, 0, 0)
            else:
                container_layout = QVBoxLayout(container)
                container_layout.setContentsMargins(0, 0, 0, 0)
                container_layout.setSpacing(0)
                container_layout.addWidget(text_edit)
            
            if is_rtf:
                self._rtf_editor = text_edit
                text_edit.textChanged.connect(self._on_rtf_text_changed)
                save_button = QPushButton()
                save_button.setFlat(True)
                save_button.setCursor(Qt.CursorShape.PointingHandCursor)
                icon = _load_svg_icon(SAVE_ICON_PATH, QSize(20, 20))
                if not icon.isNull():
                    save_button.setIcon(icon)
                    save_button.setIconSize(QSize(20, 20))
                else:
                    save_button.setText("Save")
                save_button.setToolTip("Save changes")
                save_button.setFixedSize(28, 28)
                save_button.setEnabled(False)
                save_button.clicked.connect(self._save_rtf_file)
                self._rtf_save_button = save_button
                container_layout.addWidget(
                    save_button,
                    0,
                    0,
                    Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight,
                )
                self._set_rtf_dirty(False)
            
            self.content_widget = container
            self.centralWidget().layout().addWidget(container)
        except Exception as e:
            self._show_error(f"Error loading text file:\n{e}")

    def _rtf_to_plain_text(self, rtf_content: str) -> str:
        """Convert RTF content to plain text by removing formatting."""
        text = rtf_content

        def remove_nested_group(source: str, start_pattern: str) -> str:
            result = []
            i = 0
            while i < len(source):
                match = re.search(start_pattern, source[i:])
                if not match:
                    result.append(source[i:])
                    break

                result.append(source[i:i + match.start()])
                start_pos = i + match.end() - 1
                brace_count = 0
                j = start_pos
                started = False
                while j < len(source):
                    if source[j] == '{' and (j == 0 or source[j - 1] != '\\'):
                        brace_count += 1
                        started = True
                    elif source[j] == '}' and (j == 0 or source[j - 1] != '\\'):
                        brace_count -= 1
                        if started and brace_count == 0:
                            i = j + 1
                            break
                    j += 1
                else:
                    result.append(source[i:i + match.end()])
                    i = i + match.end()
                    continue
            return ''.join(result)

        text = remove_nested_group(text, r'\\fonttbl')
        text = remove_nested_group(text, r'\\colortbl')
        text = remove_nested_group(text, r'\\stylesheet')

        text = re.sub(r'\\rtf1[^\s{}]*', '', text)
        text = re.sub(r'\\ansi[^\s{}]*', '', text)
        text = re.sub(r'\\deff0[^\s{}]*', '', text)
        text = re.sub(r'\\f\d+', '', text)
        text = re.sub(r'\\fs\d+', '', text)

        text = text.replace('\\par', '\n')
        text = re.sub(r'\\[a-zA-Z]+(?:-?\d+)?\s?', '', text)
        text = text.replace('{', '').replace('}', '')
        text = text.replace('\\', '')
        text = re.sub(r'\n{3,}', '\n\n', text)

        return text.strip()
    
    def _is_text_file(self) -> bool:
        """Check if file appears to be a text file."""
        try:
            # Try to read first 1KB as text
            with open(self.file_path, 'rb') as f:
                chunk = f.read(1024)
                # Check if it's valid UTF-8
                try:
                    chunk.decode('utf-8')
                    return True
                except UnicodeDecodeError:
                    return False
        except Exception:
            return False
    
    def _show_error(self, message: str) -> None:
        """Show an error message in the window."""
        error_widget = QWidget()
        layout = QVBoxLayout(error_widget)
        layout.setContentsMargins(20, 20, 20, 20)
        
        error_label = QTextEdit()
        error_label.setReadOnly(True)
        error_label.setPlainText(message)
        error_label.setFontFamily("Courier Prime")
        error_label.setStyleSheet("QTextEdit { background-color: #ffebee; color: #c62828; }")
        layout.addWidget(error_label)
        
        self.content_widget = error_widget
        self.centralWidget().layout().addWidget(error_widget)
    
    def closeEvent(self, event) -> None:
        """Clean up on close. Check for unsaved RTF changes first."""
        # Check if RTF file has unsaved changes
        if self._has_unsaved_rtf_changes():
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                f"The file '{self.file_path.name}' has unsaved changes.\n\n"
                "Do you want to save your changes before closing?",
                QMessageBox.StandardButton.Save |
                QMessageBox.StandardButton.Discard |
                QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save
            )
            
            if reply == QMessageBox.StandardButton.Cancel:
                # User cancelled - don't close
                event.ignore()
                return
            elif reply == QMessageBox.StandardButton.Save:
                # User wants to save - save the file (don't show success message on close)
                if not self._save_rtf_file(show_success_message=False):
                    # Save failed - don't close
                    event.ignore()
                    return
        
        # Clean up resources
        if self.content_widget:
            # Clean up PDF viewer if it's a PDF
            if isinstance(self.content_widget, PDFViewer):
                # Close the PDF document
                if hasattr(self.content_widget, '_doc') and self.content_widget._doc:
                    try:
                        self.content_widget._doc.close()
                    except Exception:
                        pass
                    self.content_widget._doc = None
            # Clean up audio player if it's an audio file
            elif isinstance(self.content_widget, AudioPlayer):
                # Stop playback and clean up
                if hasattr(self.content_widget, 'player'):
                    try:
                        self.content_widget.player.stop()
                    except Exception:
                        pass
                if hasattr(self.content_widget, 'position_timer'):
                    try:
                        self.content_widget.position_timer.stop()
                    except Exception:
                        pass
        super().closeEvent(event)

    def _position_top_right(self) -> None:
        screen = self.screen()
        if not screen:
            return
        geometry: QRect = screen.availableGeometry()
        window_size = self.size()
        x = geometry.x() + geometry.width() - window_size.width() - 20
        y = geometry.y() + 20
        self.move(max(geometry.x(), x), max(geometry.y(), y))

    def _plain_text_to_rtf(self, plain_text: str) -> str:
        escaped = plain_text.replace('\\', r'\\').replace('{', r'\{').replace('}', r'\}')
        escaped = escaped.replace('\n', r'\par ')
        return r'{\rtf1\ansi\deff0 {\fonttbl {\f0 Courier Prime;}}\f0\fs24 ' + escaped + '}'

    def _save_rtf_file(self, show_success_message: bool = True) -> bool:
        """Save RTF file. Returns True if save was successful, False otherwise.
        
        Args:
            show_success_message: If True, show a success message after saving.
        """
        if not self._rtf_editor:
            return False
        try:
            plain_text = self._rtf_editor.toPlainText()
            rtf_content = self._plain_text_to_rtf(plain_text)
            self.file_path.write_text(rtf_content, encoding="utf-8")
            self._rtf_original_text = plain_text
            self._set_rtf_dirty(False)
            if show_success_message:
                QMessageBox.information(self, "Saved", "RTF file saved successfully.")
            return True
        except Exception as exc:
            QMessageBox.critical(self, "Save Error", f"Failed to save RTF file:\n{exc}")
            return False

    def _on_rtf_text_changed(self) -> None:
        if not self._rtf_editor:
            return
        current_text = self._rtf_editor.toPlainText()
        is_dirty = current_text != self._rtf_original_text
        self._rtf_is_dirty = is_dirty
        self._set_rtf_dirty(is_dirty)

    def _set_rtf_dirty(self, dirty: bool) -> None:
        if not self._rtf_save_button:
            return
        self._rtf_is_dirty = dirty
        self._rtf_save_button.setEnabled(dirty)

        base_style = "QPushButton { background-color: transparent; border: none; padding: 2px; }"
        if dirty:
            glow_style = "QPushButton { background-color: rgba(76, 175, 80, 0.25); border-radius: 14px; padding: 2px; }"
            self._rtf_save_button.setStyleSheet(glow_style)
        else:
            self._rtf_save_button.setStyleSheet(base_style)

        icon = _load_svg_icon(SAVE_ICON_PATH, QSize(20, 20))
        if not icon.isNull():
            self._rtf_save_button.setIcon(icon)
            self._rtf_save_button.setIconSize(QSize(20, 20))
        elif not dirty:
            self._rtf_save_button.setText("Saved")
        else:
            self._rtf_save_button.setText("Save")
    
    def _has_unsaved_rtf_changes(self) -> bool:
        """Check if RTF file has unsaved changes."""
        if not self._rtf_editor or not self.file_path.suffix.lower() == ".rtf":
            return False
        current_text = self._rtf_editor.toPlainText()
        return current_text != self._rtf_original_text

