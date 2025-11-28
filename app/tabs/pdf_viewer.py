# app/tabs/pdf_viewer.py
"""
PDF viewer widget for displaying and editing PDFs.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage, QPainter, QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QLabel,
    QPushButton, QSpinBox, QSlider, QToolBar
)

try:
    import fitz  # PyMuPDF
    _HAVE_PYMUPDF = True
except Exception:
    _HAVE_PYMUPDF = False


class PDFViewer(QWidget):
    """PDF viewer widget with page navigation."""
    
    def __init__(self, pdf_path: Optional[Path] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.pdf_path: Optional[Path] = None
        self._doc = None
        self.current_page = 0
        self.zoom = 1.0
        self._setup_ui()
        if pdf_path:
            self.load_pdf(pdf_path)
    
    def _setup_ui(self) -> None:
        """Build the UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(5, 5, 5, 5)
        
        self.btn_prev = QPushButton("← Previous")
        self.btn_prev.clicked.connect(self._on_prev_page)
        toolbar.addWidget(self.btn_prev)
        
        self.spin_page = QSpinBox()
        self.spin_page.setMinimum(1)
        self.spin_page.setMaximum(1)
        self.spin_page.valueChanged.connect(self._on_page_changed)
        toolbar.addWidget(self.spin_page)
        
        self.lbl_page_count = QLabel("of 1")
        toolbar.addWidget(self.lbl_page_count)
        
        self.btn_next = QPushButton("Next →")
        self.btn_next.clicked.connect(self._on_next_page)
        toolbar.addWidget(self.btn_next)
        
        toolbar.addStretch()
        
        toolbar.addWidget(QLabel("Zoom:"))
        self.slider_zoom = QSlider(Qt.Orientation.Horizontal)
        self.slider_zoom.setMinimum(50)
        self.slider_zoom.setMaximum(400)
        self.slider_zoom.valueChanged.connect(self._on_zoom_changed)
        toolbar.addWidget(self.slider_zoom)
        
        self.zoom = self.slider_zoom.minimum() / 100.0
        self.slider_zoom.setValue(self.slider_zoom.minimum())
        
        layout.addLayout(toolbar)
        
        # Scroll area for PDF
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.label_pdf = QLabel()
        self.label_pdf.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_pdf.setText("No PDF loaded")
        self.scroll.setWidget(self.label_pdf)
        
        layout.addWidget(self.scroll, stretch=1)
    
    def load_pdf(self, pdf_path: Path) -> None:
        """Load a PDF file."""
        if not _HAVE_PYMUPDF:
            self.label_pdf.setText("PyMuPDF is required for PDF viewing. Please install PyMuPDF.")
            return
        
        try:
            if self._doc:
                self._doc.close()
                self._doc = None
            
            pdf_path = Path(pdf_path).expanduser().resolve()
            
            if not pdf_path.exists():
                self.label_pdf.setText(f"PDF file not found:\n{pdf_path}")
                return
            
            if not pdf_path.is_file():
                self.label_pdf.setText(f"Path is not a file:\n{pdf_path}")
                return
            
            self.pdf_path = pdf_path
            self._doc = fitz.open(str(self.pdf_path))
            
            if self._doc.page_count == 0:
                self._doc.close()
                self._doc = None
                self.label_pdf.setText("PDF has no pages")
                return
            
            self.current_page = 0
            self.zoom = self.slider_zoom.minimum() / 100.0
            self.slider_zoom.setValue(self.slider_zoom.minimum())
            self.spin_page.setMaximum(self._doc.page_count)
            self.lbl_page_count.setText(f"of {self._doc.page_count}")
            self._render_page()
        except Exception as e:
            import traceback
            error_msg = f"Error loading PDF:\n{str(e)}\n\n{traceback.format_exc()}"
            self.label_pdf.setText(error_msg)
            if self._doc:
                try:
                    self._doc.close()
                except:
                    pass
                self._doc = None
    
    def _render_page(self) -> None:
        """Render the current page."""
        if not self._doc:
            self.label_pdf.setText("No PDF document loaded")
            return
            
        if self.current_page < 0 or self.current_page >= self._doc.page_count:
            self.label_pdf.setText(f"Invalid page number: {self.current_page}")
            return
        
        try:
            page = self._doc[self.current_page]
            mat = fitz.Matrix(self.zoom, self.zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)

            # Convert pixmap to QImage directly (more reliable)
            img = QImage(
                pix.samples,
                pix.width,
                pix.height,
                pix.stride,
                QImage.Format.Format_RGB888
            )
            
            if img.isNull():
                # Fallback: convert to PNG bytes
                img_data = pix.tobytes("png")
                img = QImage.fromData(img_data, "PNG")
                if img.isNull():
                    raise RuntimeError("Failed to create image from PDF page")
            
            pixmap = QPixmap.fromImage(img)
            self.label_pdf.setPixmap(pixmap)
            
            # Update UI state
            if self.spin_page.value() != self.current_page + 1:
                self.spin_page.blockSignals(True)
                self.spin_page.setValue(self.current_page + 1)
                self.spin_page.blockSignals(False)
            self.btn_prev.setEnabled(self.current_page > 0)
            self.btn_next.setEnabled(self.current_page < self._doc.page_count - 1)
            
        except Exception as e:
            import traceback
            error_msg = f"Error rendering page {self.current_page + 1}:\n{str(e)}\n\n{traceback.format_exc()}"
            self.label_pdf.setText(error_msg)
    
    def _on_prev_page(self) -> None:
        """Go to previous page."""
        if self.current_page > 0:
            self.current_page -= 1
            self._render_page()
    
    def _on_next_page(self) -> None:
        """Go to next page."""
        if self._doc and self.current_page < self._doc.page_count - 1:
            self.current_page += 1
            self._render_page()
    
    def _on_page_changed(self, value: int) -> None:
        """Handle page number change."""
        page = value - 1
        if 0 <= page < (self._doc.page_count if self._doc else 0):
            self.current_page = page
            self._render_page()
    
    def _on_zoom_changed(self, value: int) -> None:
        """Handle zoom change."""
        self.zoom = value / 100.0
        self._render_page()
    
    def closeEvent(self, event) -> None:
        """Clean up on close."""
        if self._doc:
            self._doc.close()
            self._doc = None
        super().closeEvent(event)

