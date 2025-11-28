# app/voice_install_dialog.py
"""
Dialog for showing voice installation progress.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QProgressBar, QPushButton
)

from core.voice_installer import VoiceInstaller


class VoiceInstallThread(QThread):
    """Thread for installing voices in the background."""
    progress = pyqtSignal(str, int, int)  # voice_name, current, total
    finished = pyqtSignal(int, int)  # installed_count, total_count
    
    def __init__(self, models_dir: Path, presets_dir: Path):
        super().__init__()
        self.models_dir = models_dir
        self.presets_dir = presets_dir
    
    def run(self):
        """Install voices."""
        def progress_callback(voice_name: str, current: int, total: int):
            self.progress.emit(voice_name, current, total)
        
        installed = VoiceInstaller.install_default_voices(
            self.models_dir,
            self.presets_dir,
            progress_callback
        )
        
        total = len(VoiceInstaller.get_all_voices())
        self.finished.emit(installed, total)


class VoiceInstallDialog(QDialog):
    """Dialog showing voice installation progress."""
    
    def __init__(self, models_dir: Path, presets_dir: Path, parent=None):
        super().__init__(parent)
        self.models_dir = models_dir
        self.presets_dir = presets_dir
        self.install_thread: Optional[VoiceInstallThread] = None
        self._setup_ui()
        self._start_installation()
    
    def _setup_ui(self) -> None:
        """Build the UI."""
        self.setWindowTitle("Installing Voices")
        self.setModal(True)
        self.resize(400, 150)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Message
        self.label = QLabel("Installing default voices...\nThis may take a few minutes.")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setWordWrap(True)
        layout.addWidget(self.label)
        
        # Progress bar
        from core.voice_installer import VoiceInstaller
        total_voices = len(VoiceInstaller.get_all_voices())
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, total_voices)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        
        # Status label
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)
        
        # Cancel button (initially hidden)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self._cancel)
        self.cancel_button.setVisible(False)
        layout.addWidget(self.cancel_button)
    
    def _start_installation(self) -> None:
        """Start the installation process."""
        self.install_thread = VoiceInstallThread(self.models_dir, self.presets_dir)
        self.install_thread.progress.connect(self._on_progress)
        self.install_thread.finished.connect(self._on_finished)
        self.install_thread.start()
    
    def _on_progress(self, voice_name: str, current: int, total: int) -> None:
        """Update progress."""
        self.progress_bar.setValue(current)
        self.status_label.setText(f"Installing {voice_name}... ({current}/{total})")
    
    def _on_finished(self, installed: int, total: int) -> None:
        """Handle installation completion."""
        self.progress_bar.setValue(total)
        if installed == total:
            self.status_label.setText(f"Successfully installed {installed} voice(s)!")
        else:
            self.status_label.setText(f"Installed {installed} of {total} voice(s).")
        
        # Close dialog after a short delay
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(1500, self.accept)
    
    def _cancel(self) -> None:
        """Cancel installation."""
        if self.install_thread and self.install_thread.isRunning():
            self.install_thread.terminate()
            self.install_thread.wait()
        self.reject()

