# app/tabs/annotate_tab.py
"""
Annotate tab - PDF annotation and editing.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional, List

from PyQt6.QtCore import Qt, QSize, pyqtSignal, QPointF, QTimer
from PyQt6.QtGui import QPixmap, QImage, QPainter, QColor, QMouseEvent
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QLabel,
    QPushButton, QSpinBox, QSlider, QGroupBox,
    QColorDialog, QMessageBox, QFileDialog, QFrame
)

try:
    import fitz  # PyMuPDF
    _HAVE_PYMUPDF = True
except Exception:
    _HAVE_PYMUPDF = False

from core.pdf_editor import PDFEditor, PDFEditorError
from core.file_state_manager import FileStateManager


class AnnotateTab(QWidget):
    """Annotate tab for PDF annotation."""
    
    def __init__(self, project_root: Path, file_state_manager: Optional[FileStateManager] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.project_root = project_root
        self.file_state_manager = file_state_manager
        self.pdf_editor: Optional[PDFEditor] = None
        self.current_pdf_path: Optional[Path] = None
        self.current_image_path: Optional[Path] = None
        self.original_pixmap: Optional[QPixmap] = None
        self.is_image_mode: bool = False
        self.annotation_mode: str = "none"  # "none", "highlight", "note"
        self.highlight_color = (1.0, 1.0, 0.0)  # Yellow
        self._zoom_change_timer: Optional[QTimer] = None
        self._page_change_timer: Optional[QTimer] = None
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Build the UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Top toolbar
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(5, 5, 5, 5)
        
        toolbar.addStretch()
        
        # Annotation mode buttons
        self.btn_highlight = QPushButton("Highlight")
        self.btn_highlight.setCheckable(True)
        self.btn_highlight.clicked.connect(lambda: self._set_annotation_mode("highlight"))
        toolbar.addWidget(self.btn_highlight)
        
        self.btn_note = QPushButton("Add Note")
        self.btn_note.setCheckable(True)
        self.btn_note.clicked.connect(lambda: self._set_annotation_mode("note"))
        toolbar.addWidget(self.btn_note)
        
        self.btn_color = QPushButton("Color")
        self.btn_color.clicked.connect(self._choose_color)
        toolbar.addWidget(self.btn_color)
        
        # Add separator (vertical line)
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        toolbar.addWidget(separator)
        
        self.btn_save = QPushButton("Save Annotations")
        self.btn_save.clicked.connect(self._save_annotations)
        toolbar.addWidget(self.btn_save)
        
        layout.addLayout(toolbar)
        
        # Navigation toolbar
        nav_toolbar = QHBoxLayout()
        nav_toolbar.setContentsMargins(5, 5, 5, 5)
        
        self.btn_prev = QPushButton("← Previous")
        self.btn_prev.clicked.connect(self._on_prev_page)
        nav_toolbar.addWidget(self.btn_prev)
        
        self.spin_page = QSpinBox()
        self.spin_page.setMinimum(1)
        self.spin_page.setMaximum(1)
        self.spin_page.valueChanged.connect(self._on_page_changed)
        # Create timer for debouncing page saves
        self._page_change_timer = QTimer()
        self._page_change_timer.setSingleShot(True)
        self._page_change_timer.timeout.connect(self._save_page_number)
        nav_toolbar.addWidget(self.spin_page)
        
        self.lbl_page_count = QLabel("of 1")
        nav_toolbar.addWidget(self.lbl_page_count)
        
        self.btn_next = QPushButton("Next →")
        self.btn_next.clicked.connect(self._on_next_page)
        nav_toolbar.addWidget(self.btn_next)
        
        nav_toolbar.addStretch()
        
        nav_toolbar.addWidget(QLabel("Zoom:"))
        self.slider_zoom = QSlider(Qt.Orientation.Horizontal)
        self.slider_zoom.setMinimum(50)
        self.slider_zoom.setMaximum(400)
        self.slider_zoom.valueChanged.connect(self._on_zoom_changed)
        # Create timer for debouncing zoom saves
        self._zoom_change_timer = QTimer()
        self._zoom_change_timer.setSingleShot(True)
        self._zoom_change_timer.timeout.connect(self._save_zoom_level)
        nav_toolbar.addWidget(self.slider_zoom)
        
        layout.addLayout(nav_toolbar)
        
        # PDF display area
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.label_pdf = QLabel()
        self.label_pdf.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_pdf.setText("Select a PDF or image file to view")
        self.label_pdf.setMouseTracking(True)
        self.label_pdf.mousePressEvent = self._on_pdf_clicked
        self.scroll.setWidget(self.label_pdf)
        
        layout.addWidget(self.scroll, stretch=1)
        
        self.current_page = 0
        self.zoom = self.slider_zoom.minimum() / 100.0
        self.slider_zoom.setValue(self.slider_zoom.minimum())
        self._drag_start: Optional[QPointF] = None
    
    def _load_pdf(self, pdf_path: Path) -> None:
        """Load a PDF file for annotation."""
        if not _HAVE_PYMUPDF:
            self.label_pdf.setText("PyMuPDF is required for PDF annotation")
            return
        
        try:
            # Clear image mode
            self.is_image_mode = False
            self.current_image_path = None
            self.original_pixmap = None
            
            if self.pdf_editor:
                self.pdf_editor.close()
            
            self.pdf_editor = PDFEditor(pdf_path)
            self.current_pdf_path = pdf_path
            
            # Load saved state (zoom and page) if available
            if self.file_state_manager:
                saved_page = self.file_state_manager.get_page_number(pdf_path, default=0)
                saved_zoom = self.file_state_manager.get_zoom_level(pdf_path, default=self.slider_zoom.minimum() / 100.0)
                self.current_page = max(0, min(saved_page, self.pdf_editor.num_pages() - 1))
                self.zoom = saved_zoom
                # Update slider to match saved zoom
                zoom_percent = int(self.zoom * 100)
                zoom_percent = max(self.slider_zoom.minimum(), min(self.slider_zoom.maximum(), zoom_percent))
                self.slider_zoom.blockSignals(True)
                self.slider_zoom.setValue(zoom_percent)
                self.slider_zoom.blockSignals(False)
            else:
                self.current_page = 0
                self.zoom = self.slider_zoom.minimum() / 100.0
                self.slider_zoom.setValue(self.slider_zoom.minimum())
            
            # Show annotation buttons for PDFs
            self.btn_highlight.setVisible(True)
            self.btn_note.setVisible(True)
            self.btn_color.setVisible(True)
            self.btn_save.setVisible(True)
            
            # Enable page navigation for PDFs
            self.spin_page.setEnabled(True)
            
            if self.pdf_editor.num_pages() > 0:
                self.spin_page.setMaximum(self.pdf_editor.num_pages())
                self.lbl_page_count.setText(f"of {self.pdf_editor.num_pages()}")
                # Update spin box to match saved page
                self.spin_page.blockSignals(True)
                self.spin_page.setValue(self.current_page + 1)
                self.spin_page.blockSignals(False)
                self._render_page()
            else:
                self.label_pdf.setText("PDF has no pages")
        except PDFEditorError as e:
            self.label_pdf.setText(f"Error loading PDF: {e}")
        except Exception as e:
            self.label_pdf.setText(f"Error: {e}")
    
    def _render_page(self) -> None:
        """Render the current page."""
        if self.is_image_mode:
            self._render_image()
            return
        
        if not self.pdf_editor or not self.pdf_editor._doc:
            return
        
        try:
            page = self.pdf_editor._doc[self.current_page]
            mat = fitz.Matrix(self.zoom, self.zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            
            # Convert to QImage
            img = QImage(
                pix.samples,
                pix.width,
                pix.height,
                pix.stride,
                QImage.Format.Format_RGB888
            )
            
            if img.isNull():
                img_data = pix.tobytes("png")
                img = QImage.fromData(img_data, "PNG")
            
            pixmap = QPixmap.fromImage(img)
            self.label_pdf.setPixmap(pixmap)
            
            # Update UI
            if self.spin_page.value() != self.current_page + 1:
                self.spin_page.blockSignals(True)
                self.spin_page.setValue(self.current_page + 1)
                self.spin_page.blockSignals(False)
            self.btn_prev.setEnabled(self.current_page > 0)
            self.btn_next.setEnabled(self.current_page < self.pdf_editor.num_pages() - 1)
        except Exception as e:
            self.label_pdf.setText(f"Error rendering page: {e}")
    
    def _on_prev_page(self) -> None:
        """Go to previous page."""
        if self.current_page > 0:
            self.current_page -= 1
            self.spin_page.blockSignals(True)
            self.spin_page.setValue(self.current_page + 1)
            self.spin_page.blockSignals(False)
            self._render_page()
            # Save page number
            if self.file_state_manager and self.current_pdf_path:
                self._page_change_timer.stop()
                self._page_change_timer.start(500)
    
    def _on_next_page(self) -> None:
        """Go to next page."""
        if self.pdf_editor and self.current_page < self.pdf_editor.num_pages() - 1:
            self.current_page += 1
            self.spin_page.blockSignals(True)
            self.spin_page.setValue(self.current_page + 1)
            self.spin_page.blockSignals(False)
            self._render_page()
            # Save page number
            if self.file_state_manager and self.current_pdf_path:
                self._page_change_timer.stop()
                self._page_change_timer.start(500)
    
    def _on_page_changed(self, value: int) -> None:
        """Handle page number change."""
        page = value - 1
        if self.pdf_editor and 0 <= page < self.pdf_editor.num_pages():
            self.current_page = page
            self._render_page()
            # Save page number after a short delay (debounce)
            if self.file_state_manager and self.current_pdf_path:
                self._page_change_timer.stop()
                self._page_change_timer.start(500)  # Wait 500ms before saving
    
    def _save_page_number(self) -> None:
        """Save page number to state manager."""
        if self.file_state_manager and self.current_pdf_path:
            self.file_state_manager.set_page_number(self.current_pdf_path, self.current_page)
    
    def _on_zoom_changed(self, value: int) -> None:
        """Handle zoom change."""
        self.zoom = value / 100.0
        if self.is_image_mode:
            self._render_image()
        else:
            self._render_page()
        # Save zoom level after a short delay (debounce)
        if self.file_state_manager and self.current_pdf_path:
            self._zoom_change_timer.stop()
            self._zoom_change_timer.start(500)  # Wait 500ms before saving
    
    def _save_zoom_level(self) -> None:
        """Save zoom level to state manager."""
        if self.file_state_manager and self.current_pdf_path:
            self.file_state_manager.set_zoom_level(self.current_pdf_path, self.zoom)
    
    def _set_annotation_mode(self, mode: str) -> None:
        """Set annotation mode."""
        if mode == self.annotation_mode:
            # Toggle off
            self.annotation_mode = "none"
            self.btn_highlight.setChecked(False)
            self.btn_note.setChecked(False)
        else:
            self.annotation_mode = mode
            self.btn_highlight.setChecked(mode == "highlight")
            self.btn_note.setChecked(mode == "note")
    
    def _choose_color(self) -> None:
        """Choose highlight color."""
        color = QColorDialog.getColor()
        if color.isValid():
            self.highlight_color = (color.red() / 255.0, color.green() / 255.0, color.blue() / 255.0)
            # Update button color
            self.btn_color.setStyleSheet(f"background-color: {color.name()}")
    
    def _on_pdf_clicked(self, event: QMouseEvent) -> None:
        """Handle mouse click on PDF for annotations."""
        # Don't handle clicks for images (no annotation support)
        if self.is_image_mode:
            return
        
        if not self.pdf_editor or not self.pdf_editor._doc or self.annotation_mode == "none":
            return
        
        # Get click position relative to PDF image
        pixmap = self.label_pdf.pixmap()
        if not pixmap:
            return
        
        # Calculate PDF coordinates from click position
        label_size = self.label_pdf.size()
        pixmap_size = pixmap.size()
        
        # Account for centering
        x_offset = (label_size.width() - pixmap_size.width()) / 2
        y_offset = (label_size.height() - pixmap_size.height()) / 2
        
        click_x = event.position().x() - x_offset
        click_y = event.position().y() - y_offset
        
        if click_x < 0 or click_y < 0 or click_x > pixmap_size.width() or click_y > pixmap_size.height():
            return
        
        # Convert to PDF coordinates
        page = self.pdf_editor._doc[self.current_page]
        page_rect = page.rect
        pdf_x = (click_x / pixmap_size.width()) * page_rect.width
        pdf_y = (click_y / pixmap_size.height()) * page_rect.height
        
        try:
            if self.annotation_mode == "highlight":
                # Create a small highlight rectangle
                rect = (pdf_x - 20, pdf_y - 5, pdf_x + 20, pdf_y + 5)
                self.pdf_editor.add_highlight(self.current_page, rect, self.highlight_color)
                self._render_page()
            elif self.annotation_mode == "note":
                # Add a note at the click position
                from PyQt6.QtWidgets import QInputDialog
                text, ok = QInputDialog.getText(self, "Add Note", "Note text:")
                if ok and text:
                    self.pdf_editor.add_text_note(self.current_page, (pdf_x, pdf_y), text, self.highlight_color)
                    self._render_page()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to add annotation: {e}")
    
    def _save_annotations(self) -> None:
        """Save PDF with annotations."""
        if not self.pdf_editor:
            QMessageBox.warning(self, "No PDF", "No PDF loaded to save.")
            return
        
        try:
            self.pdf_editor.save()
            QMessageBox.information(self, "Saved", "Annotations saved successfully.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save annotations: {e}")
    
    def refresh_file_list(self) -> None:
        """Refresh the PDF file list (no-op since dropdown removed)."""
        pass
    
    def load_pdf(self, pdf_path: Path) -> None:
        """Load a specific PDF file (public method for external use)."""
        if not pdf_path.exists():
            return
        # Check if it's an image file
        if pdf_path.suffix.lower() in [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg"]:
            self._load_image(pdf_path)
        else:
            self._load_pdf(pdf_path)
    
    def _load_image(self, image_path: Path) -> None:
        """Load an image file for viewing."""
        try:
            # Close PDF editor if open
            if self.pdf_editor:
                self.pdf_editor.close()
                self.pdf_editor = None
            
            self.current_image_path = image_path
            self.current_pdf_path = None
            self.is_image_mode = True
            
            # Load image
            pixmap = QPixmap(str(image_path))
            if pixmap.isNull():
                self.label_pdf.setText(f"Failed to load image:\n{image_path}")
                return
            
            self.original_pixmap = pixmap
            self.current_page = 0
            
            # Load saved zoom level for images if available
            if self.file_state_manager:
                saved_zoom = self.file_state_manager.get_zoom_level(image_path, default=self.slider_zoom.minimum() / 100.0)
                self.zoom = saved_zoom
                zoom_percent = int(self.zoom * 100)
                zoom_percent = max(self.slider_zoom.minimum(), min(self.slider_zoom.maximum(), zoom_percent))
                self.slider_zoom.blockSignals(True)
                self.slider_zoom.setValue(zoom_percent)
                self.slider_zoom.blockSignals(False)
            else:
                self.zoom = self.slider_zoom.minimum() / 100.0
                self.slider_zoom.setValue(self.slider_zoom.minimum())
            
            # Hide page navigation for images (single page)
            self.btn_prev.setEnabled(False)
            self.btn_next.setEnabled(False)
            self.spin_page.setEnabled(False)
            self.spin_page.setMaximum(1)
            self.lbl_page_count.setText("of 1")
            
            # Hide annotation buttons for images
            self.btn_highlight.setVisible(False)
            self.btn_note.setVisible(False)
            self.btn_color.setVisible(False)
            self.btn_save.setVisible(False)
            
            self._render_image()
        except Exception as e:
            self.label_pdf.setText(f"Error loading image: {e}")
    
    def _render_image(self) -> None:
        """Render the image with current zoom."""
        if not self.original_pixmap:
            return
        
        try:
            # Scale the pixmap
            scaled_pixmap = self.original_pixmap.scaled(
                int(self.original_pixmap.width() * self.zoom),
                int(self.original_pixmap.height() * self.zoom),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            
            self.label_pdf.setPixmap(scaled_pixmap)
            
            # Update UI
            if self.spin_page.value() != 1:
                self.spin_page.blockSignals(True)
                self.spin_page.setValue(1)
                self.spin_page.blockSignals(False)
            
            # Save zoom level for images
            if self.file_state_manager and self.current_image_path:
                self._zoom_change_timer.stop()
                self._zoom_change_timer.start(500)
        except Exception as e:
            self.label_pdf.setText(f"Error rendering image: {e}")
    
    def closeEvent(self, event) -> None:
        """Clean up on close."""
        if self.pdf_editor:
            self.pdf_editor.close()
        super().closeEvent(event)

