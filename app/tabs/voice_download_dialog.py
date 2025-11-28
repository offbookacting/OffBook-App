# app/tabs/voice_download_dialog.py
"""
Dialog for downloading official Piper TTS voices from Hugging Face.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional, Dict, List
import json
import re

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QTreeWidget, QTreeWidgetItem, QMessageBox,
    QGroupBox, QProgressBar, QTextEdit, QLineEdit, QFileDialog,
    QHeaderView
)
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.tabs.voice_selection_dialog import VoiceConfig, create_piper_onnx_json


class VoiceDownloadThread(QThread):
    """Thread for downloading voice files."""
    progress = pyqtSignal(str, int, int)  # message, current, total
    finished = pyqtSignal(bool, str)  # success, message
    file_downloaded = pyqtSignal(str)  # filename
    
    def __init__(self, voice_urls: Dict[str, str], download_dir: Path):
        super().__init__()
        self.voice_urls = voice_urls
        self.download_dir = download_dir
        self.cancelled = False
    
    def cancel(self):
        self.cancelled = True
    
    def run(self):
        """Download voice files."""
        try:
            # Create session with retry strategy
            session = requests.Session()
            retry_strategy = Retry(
                total=3,
                backoff_factor=1,
                status_forcelist=[429, 500, 502, 503, 504],
            )
            adapter = HTTPAdapter(max_retries=retry_strategy)
            session.mount("http://", adapter)
            session.mount("https://", adapter)
            
            total_files = len(self.voice_urls)
            current = 0
            
            for filename, url in self.voice_urls.items():
                if self.cancelled:
                    self.finished.emit(False, "Download cancelled")
                    return
                
                self.progress.emit(f"Downloading {filename}...", current, total_files)
                
                try:
                    # Follow redirects (Hugging Face uses redirects to CDN)
                    response = session.get(url, stream=True, timeout=30, allow_redirects=True)
                    response.raise_for_status()
                    
                    file_path = self.download_dir / filename
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    total_size = int(response.headers.get('content-length', 0))
                    downloaded = 0
                    
                    with open(file_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            if self.cancelled:
                                if file_path.exists():
                                    file_path.unlink()
                                self.finished.emit(False, "Download cancelled")
                                return
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                if total_size > 0:
                                    percent = int((downloaded / total_size) * 100)
                                    self.progress.emit(
                                        f"Downloading {filename}... {percent}%",
                                        current,
                                        total_files
                                    )
                    
                    self.file_downloaded.emit(filename)
                    current += 1
                    
                except Exception as e:
                    self.finished.emit(False, f"Error downloading {filename}: {str(e)}")
                    return
            
            self.finished.emit(True, f"Successfully downloaded {total_files} file(s)")
            
        except Exception as e:
            self.finished.emit(False, f"Download error: {str(e)}")


class VoiceDownloadDialog(QDialog):
    """Dialog for downloading Piper TTS voices from Hugging Face."""
    
    # Popular voices to show by default
    POPULAR_VOICES = {
        "English (US) - Amy (Low)": {
            "language": "en",
            "region": "en_US",
            "voice": "amy",
            "quality": "low"
        },
        "English (US) - Amy (Medium)": {
            "language": "en",
            "region": "en_US",
            "voice": "amy",
            "quality": "medium"
        },
        "English (US) - Amy (High)": {
            "language": "en",
            "region": "en_US",
            "voice": "amy",
            "quality": "high"
        },
        "English (US) - Lessac (Low)": {
            "language": "en",
            "region": "en_US",
            "voice": "lessac",
            "quality": "low"
        },
        "English (US) - Lessac (Medium)": {
            "language": "en",
            "region": "en_US",
            "voice": "lessac",
            "quality": "medium"
        },
        "English (US) - Lessac (High)": {
            "language": "en",
            "region": "en_US",
            "voice": "lessac",
            "quality": "high"
        },
        "English (US) - LibriTTS (Low)": {
            "language": "en",
            "region": "en_US",
            "voice": "libritts",
            "quality": "low"
        },
        "English (US) - LibriTTS (Medium)": {
            "language": "en",
            "region": "en_US",
            "voice": "libritts",
            "quality": "medium"
        },
        "English (US) - LibriTTS (High)": {
            "language": "en",
            "region": "en_US",
            "voice": "libritts",
            "quality": "high"
        },
    }
    
    HUGGINGFACE_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
    
    def __init__(self, library_presets_dir: Optional[Path] = None, parent=None):
        super().__init__(parent)
        self.library_presets_dir = library_presets_dir
        self.download_dir = None
        self.download_thread: Optional[VoiceDownloadThread] = None
        self._setup_ui()
        self._populate_voices()
    
    def _setup_ui(self) -> None:
        """Build the UI."""
        self.setWindowTitle("Download Piper TTS Voices")
        self.resize(700, 600)
        
        layout = QVBoxLayout(self)
        
        # Instructions
        instructions = QLabel(
            "Select voices to download from the official Piper TTS repository.\n"
            "Each voice includes both the model file (.onnx) and configuration (.onnx.json)."
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        
        # Download directory selection
        dir_group = QGroupBox("Download Location")
        dir_layout = QHBoxLayout()
        dir_label = QLabel("Directory:")
        dir_layout.addWidget(dir_label)
        self.dir_edit = QLineEdit()
        if self.library_presets_dir:
            # Default to a models subdirectory in library presets
            default_dir = self.library_presets_dir.parent / "models"
            self.dir_edit.setText(str(default_dir))
            self.download_dir = default_dir
        else:
            default_dir = Path.home() / "piper" / "voices"
            self.dir_edit.setText(str(default_dir))
            self.download_dir = default_dir
        dir_layout.addWidget(self.dir_edit)
        btn_browse = QPushButton("Browse...")
        btn_browse.clicked.connect(self._browse_directory)
        dir_layout.addWidget(btn_browse)
        dir_group.setLayout(dir_layout)
        layout.addWidget(dir_group)
        
        # Voice selection
        voice_group = QGroupBox("Available Voices")
        voice_layout = QVBoxLayout()
        
        # Search/filter
        search_layout = QHBoxLayout()
        search_label = QLabel("Search:")
        search_layout.addWidget(search_label)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Filter voices...")
        self.search_edit.textChanged.connect(self._filter_voices)
        search_layout.addWidget(self.search_edit)
        voice_layout.addLayout(search_layout)
        
        # Voice list
        self.voice_list = QTreeWidget()
        self.voice_list.setHeaderLabels(["Voice", "Quality", "Size"])
        self.voice_list.setRootIsDecorated(False)
        self.voice_list.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.voice_list.header().setStretchLastSection(False)
        self.voice_list.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.voice_list.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.voice_list.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        voice_layout.addWidget(self.voice_list)
        voice_group.setLayout(voice_layout)
        layout.addWidget(voice_group, stretch=1)
        
        # Progress
        progress_group = QGroupBox("Download Progress")
        progress_layout = QVBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        progress_layout.addWidget(self.progress_bar)
        self.progress_label = QLabel("")
        self.progress_label.setVisible(False)
        progress_layout.addWidget(self.progress_label)
        progress_group.setLayout(progress_layout)
        layout.addWidget(progress_group)
        
        # Buttons
        btn_layout = QHBoxLayout()
        self.btn_download = QPushButton("Download Selected")
        self.btn_download.clicked.connect(self._start_download)
        btn_layout.addWidget(self.btn_download)
        self.btn_cancel = QPushButton("Cancel Download")
        self.btn_cancel.clicked.connect(self._cancel_download)
        self.btn_cancel.setEnabled(False)
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addStretch()
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)
    
    def _browse_directory(self) -> None:
        """Browse for download directory."""
        current_dir = self.dir_edit.text()
        dir_path = QFileDialog.getExistingDirectory(
            self,
            "Select Download Directory",
            current_dir
        )
        if dir_path:
            self.dir_edit.setText(dir_path)
            self.download_dir = Path(dir_path)
    
    def _populate_voices(self) -> None:
        """Populate the voice list with available voices."""
        self.voice_list.clear()
        
        # Auto-select all libritts, lessac, and amy voices
        for voice_name, voice_info in self.POPULAR_VOICES.items():
            item = QTreeWidgetItem(self.voice_list)
            item.setText(0, voice_name)
            item.setText(1, voice_info["quality"].title())
            item.setText(2, "~10-50 MB")  # Approximate size
            item.setData(0, Qt.ItemDataRole.UserRole, voice_info)
            # Auto-check all voices for libritts, lessac, and amy
            item.setCheckState(0, Qt.CheckState.Checked)
    
    def _filter_voices(self, text: str) -> None:
        """Filter voices based on search text."""
        text_lower = text.lower()
        for i in range(self.voice_list.topLevelItemCount()):
            item = self.voice_list.topLevelItem(i)
            voice_name = item.text(0).lower()
            if text_lower in voice_name:
                item.setHidden(False)
            else:
                item.setHidden(True)
    
    def _get_voice_urls(self, voice_info: Dict) -> Dict[str, str]:
        """Get download URLs for a voice."""
        lang = voice_info["language"]
        region = voice_info["region"]
        voice = voice_info["voice"]
        quality = voice_info["quality"]
        
        # Construct file names
        base_name = f"{region}-{voice}-{quality}"
        onnx_file = f"{base_name}.onnx"
        json_file = f"{base_name}.onnx.json"
        
        # Construct URLs
        onnx_url = f"{self.HUGGINGFACE_BASE}/{lang}/{region}/{voice}/{quality}/{onnx_file}"
        json_url = f"{self.HUGGINGFACE_BASE}/{lang}/{region}/{voice}/{quality}/{json_file}"
        
        return {
            onnx_file: onnx_url,
            json_file: json_url
        }
    
    def _start_download(self) -> None:
        """Start downloading selected voices."""
        # Get download directory
        dir_text = self.dir_edit.text().strip()
        if not dir_text:
            QMessageBox.warning(self, "No Directory", "Please select a download directory.")
            return
        
        self.download_dir = Path(dir_text)
        try:
            self.download_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            QMessageBox.warning(self, "Directory Error", f"Cannot create directory: {str(e)}")
            return
        
        # Get selected voices
        selected_voices = []
        for i in range(self.voice_list.topLevelItemCount()):
            item = self.voice_list.topLevelItem(i)
            if item.checkState(0) == Qt.CheckState.Checked:
                voice_info = item.data(0, Qt.ItemDataRole.UserRole)
                selected_voices.append(voice_info)
        
        if not selected_voices:
            QMessageBox.warning(self, "No Selection", "Please select at least one voice to download.")
            return
        
        # Collect all files to download
        all_urls = {}
        for voice_info in selected_voices:
            urls = self._get_voice_urls(voice_info)
            all_urls.update(urls)
        
        # Start download thread
        self.download_thread = VoiceDownloadThread(all_urls, self.download_dir)
        self.download_thread.progress.connect(self._on_download_progress)
        self.download_thread.finished.connect(self._on_download_finished)
        self.download_thread.file_downloaded.connect(self._on_file_downloaded)
        
        self.progress_bar.setVisible(True)
        self.progress_label.setVisible(True)
        self.progress_bar.setMaximum(len(all_urls))
        self.progress_bar.setValue(0)
        self.btn_download.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        
        self.download_thread.start()
    
    def _cancel_download(self) -> None:
        """Cancel the download."""
        if self.download_thread and self.download_thread.isRunning():
            self.download_thread.cancel()
            self.btn_cancel.setEnabled(False)
    
    def _on_download_progress(self, message: str, current: int, total: int) -> None:
        """Update download progress."""
        self.progress_label.setText(message)
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
    
    def _on_file_downloaded(self, filename: str) -> None:
        """Handle file download completion."""
        pass  # Could show individual file completion
    
    def _on_download_finished(self, success: bool, message: str) -> None:
        """Handle download completion."""
        self.btn_download.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        
        if success:
            # Update presets if we have a library presets directory
            preset_count = 0
            if self.library_presets_dir and self.download_dir:
                preset_count = self._update_presets_from_downloads()
            
            msg = message
            if preset_count > 0:
                msg += f"\n\n{preset_count} preset(s) have been created and are ready to use."
            QMessageBox.information(self, "Download Complete", msg)
        else:
            QMessageBox.warning(self, "Download Error", message)
    
    def _update_presets_from_downloads(self) -> int:
        """Update presets to use downloaded models. Returns number of presets created."""
        if not self.download_dir or not self.download_dir.exists():
            return 0
        
        if not self.library_presets_dir:
            return 0
        
        # Ensure library presets directory exists
        self.library_presets_dir.mkdir(parents=True, exist_ok=True)
        
        preset_count = 0
        
        # Find all downloaded .onnx.json files
        for json_file in self.download_dir.rglob("*.onnx.json"):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                
                # Get the corresponding .onnx file
                onnx_file = json_file.with_suffix('')  # Remove .json
                if not onnx_file.exists():
                    # Try finding .onnx file in same directory
                    onnx_file = json_file.parent / json_file.stem.replace('.onnx', '') + '.onnx'
                    if not onnx_file.exists():
                        continue
                
                # Update the model_path in the JSON to point to the actual .onnx file
                data["model_path"] = str(onnx_file.absolute())
                
                # Create a preset name from the filename
                preset_name = json_file.stem.replace('.onnx', '').replace('_', ' ').replace('-', ' ').title()
                
                # Save to library presets directory
                preset_file = self.library_presets_dir / json_file.name
                preset_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
                preset_count += 1
                    
            except Exception as e:
                # Skip invalid files
                continue
        
        return preset_count

