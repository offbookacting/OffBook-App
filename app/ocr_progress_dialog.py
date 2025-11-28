# app/ocr_progress_dialog.py
"""
Progress dialog for OCR operations.
"""
from __future__ import annotations
from typing import Optional
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QProgressBar, QPushButton
)
from pathlib import Path

from core.image_ocr import extract_text_from_image, ImageOCRError


class OCRWorker(QThread):
    """Worker thread for performing OCR."""
    
    finished = pyqtSignal(str)  # Emits extracted text
    error = pyqtSignal(str)  # Emits error message
    progress = pyqtSignal(int, int)  # Emits (current, total)
    
    def __init__(self, image_path: Path, lang: str = "en"):
        super().__init__()
        self.image_path = image_path
        self.lang = lang
    
    def run(self):
        """Run OCR in background thread."""
        try:
            def progress_callback(current: int, total: int):
                self.progress.emit(current, total)
            
            text = extract_text_from_image(
                self.image_path,
                lang=self.lang,
                progress_callback=progress_callback
            )
            self.finished.emit(text)
        except ImageOCRError as e:
            self.error.emit(str(e))
        except Exception as e:
            self.error.emit(f"Unexpected error during OCR: {e}")


class OCRProgressDialog(QDialog):
    """Dialog showing OCR progress."""
    
    def __init__(self, image_path: Path, parent=None):
        super().__init__(parent)
        self.image_path = image_path
        self.extracted_text: str = ""
        self.worker: Optional[OCRWorker] = None
        self._setup_ui()
    
    def _setup_ui(self):
        """Build the UI."""
        self.setWindowTitle("Extracting Text from Image")
        self.setModal(True)
        self.resize(400, 150)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Status label
        self.lbl_status = QLabel(f"Processing: {self.image_path.name}")
        self.lbl_status.setWordWrap(True)
        layout.addWidget(self.lbl_status)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        
        # Cancel button
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self._on_cancel)
        layout.addWidget(self.btn_cancel)
    
    def _on_cancel(self):
        """Handle cancel button click."""
        if self.worker and self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait()
        self.reject()
    
    def start_ocr(self) -> str:
        """
        Start OCR process and return extracted text.
        
        Returns:
            Extracted text, or empty string if cancelled/error
        """
        # Create and start worker thread
        self.worker = OCRWorker(self.image_path)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.error.connect(self._on_error)
        
        self.worker.start()
        
        # Show dialog and wait for completion
        result = self.exec()
        
        if result == QDialog.DialogCode.Accepted:
            return self.extracted_text
        return ""
    
    def _on_progress(self, current: int, total: int):
        """Update progress bar."""
        if total > 0:
            percentage = int((current / total) * 100)
            self.progress_bar.setValue(percentage)
            self.lbl_status.setText(
                f"Processing: {self.image_path.name}\n"
                f"Progress: {percentage}%"
            )
    
    def _on_finished(self, text: str):
        """Handle OCR completion."""
        self.extracted_text = text
        self.accept()
    
    def _on_error(self, error_msg: str):
        """Handle OCR error."""
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.critical(
            self,
            "OCR Error",
            f"Failed to extract text from image:\n\n{error_msg}"
        )
        self.reject()

