# app/tabs/image_viewer.py
"""
Image viewer widget for displaying images (PNG, JPG, etc.).
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QLabel,
    QPushButton, QSlider
)


class ImageViewer(QWidget):
    """Image viewer widget with zoom controls."""
    
    def __init__(self, image_path: Optional[Path] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.image_path: Optional[Path] = None
        self.original_pixmap: Optional[QPixmap] = None
        self.zoom = 1.0
        self._setup_ui()
        if image_path:
            self.load_image(image_path)
    
    def _setup_ui(self) -> None:
        """Build the UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(5, 5, 5, 5)
        
        toolbar.addStretch()
        
        toolbar.addWidget(QLabel("Zoom:"))
        self.slider_zoom = QSlider(Qt.Orientation.Horizontal)
        self.slider_zoom.setMinimum(25)
        self.slider_zoom.setMaximum(400)
        self.slider_zoom.valueChanged.connect(self._on_zoom_changed)
        toolbar.addWidget(self.slider_zoom)
        
        self.zoom = self.slider_zoom.minimum() / 100.0
        self.slider_zoom.setValue(self.slider_zoom.minimum())
        
        self.btn_fit = QPushButton("Fit to Window")
        self.btn_fit.clicked.connect(self._fit_to_window)
        toolbar.addWidget(self.btn_fit)
        
        layout.addLayout(toolbar)
        
        # Scroll area for image
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.label_image = QLabel()
        self.label_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label_image.setText("No image loaded")
        self.scroll.setWidget(self.label_image)
        
        layout.addWidget(self.scroll, stretch=1)
    
    def load_image(self, image_path: Path) -> None:
        """Load an image file."""
        try:
            image_path = Path(image_path).expanduser().resolve()
            
            if not image_path.exists():
                self.label_image.setText(f"Image file not found:\n{image_path}")
                return
            
            if not image_path.is_file():
                self.label_image.setText(f"Path is not a file:\n{image_path}")
                return
            
            self.image_path = image_path
            
            # Load image
            pixmap = QPixmap(str(self.image_path))
            if pixmap.isNull():
                self.label_image.setText(f"Failed to load image:\n{image_path}\n\nUnsupported format or corrupted file.")
                return
            
            self.original_pixmap = pixmap
            self.zoom = self.slider_zoom.minimum() / 100.0
            self.slider_zoom.setValue(self.slider_zoom.minimum())
            self._render_image()
        except Exception as e:
            import traceback
            error_msg = f"Error loading image:\n{str(e)}\n\n{traceback.format_exc()}"
            self.label_image.setText(error_msg)
    
    def _render_image(self) -> None:
        """Render the image with current zoom."""
        if not self.original_pixmap:
            self.label_image.setText("No image loaded")
            return
        
        try:
            # Scale the pixmap
            scaled_pixmap = self.original_pixmap.scaled(
                int(self.original_pixmap.width() * self.zoom),
                int(self.original_pixmap.height() * self.zoom),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            
            self.label_image.setPixmap(scaled_pixmap)
        except Exception as e:
            import traceback
            error_msg = f"Error rendering image:\n{str(e)}\n\n{traceback.format_exc()}"
            self.label_image.setText(error_msg)
    
    def _on_zoom_changed(self, value: int) -> None:
        """Handle zoom change."""
        self.zoom = value / 100.0
        self._render_image()
    
    def _fit_to_window(self) -> None:
        """Fit image to window size."""
        if not self.original_pixmap or not self.scroll:
            return
        
        # Get available size in scroll area
        scroll_size = self.scroll.viewport().size()
        img_size = self.original_pixmap.size()
        
        # Calculate zoom to fit
        zoom_x = scroll_size.width() / img_size.width()
        zoom_y = scroll_size.height() / img_size.height()
        self.zoom = min(zoom_x, zoom_y) * 0.95  # 95% to leave some margin
        
        # Update slider
        self.slider_zoom.blockSignals(True)
        self.slider_zoom.setValue(int(self.zoom * 100))
        self.slider_zoom.blockSignals(False)
        
        self._render_image()

