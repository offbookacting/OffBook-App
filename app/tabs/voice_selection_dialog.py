# app/tabs/voice_selection_dialog.py
"""
Voice selection dialog for assigning voices to characters.
"""
from __future__ import annotations
from pathlib import Path
from typing import Dict, Optional, List
from dataclasses import dataclass
import json

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QTableWidget, QTableWidgetItem, QFileDialog,
    QMessageBox, QGroupBox, QHeaderView
)

from core.tts import PiperTTS, PiperTTSError


def create_piper_onnx_json(
    model_path: str,
    speaker: int = 0,
    noise_scale: float = 0.667,
    length_scale: float = 1.0,
    noise_w: float = 0.8,
    sentence_silence_seconds: float = 0.0,
    name: str = "",
    language: str = "en",
    sample_rate: int = 22050
) -> dict:
    """
    Create a Piper-compatible .onnx.json configuration file structure.
    This references an existing .onnx model file and includes voice parameters.
    """
    # Try to find the corresponding .onnx.json file if the model exists
    model_path_obj = Path(model_path) if model_path else None
    base_config = {}
    
    if model_path_obj and model_path_obj.exists():
        # Try to load existing .onnx.json config if it exists
        onnx_json_path = model_path_obj.with_suffix('.onnx.json')
        if onnx_json_path.exists():
            try:
                base_config = json.loads(onnx_json_path.read_text(encoding="utf-8"))
                # Use existing language and sample_rate if available
                language = base_config.get("language", language)
                sample_rate = base_config.get("audio", {}).get("sample_rate", sample_rate)
            except Exception:
                pass
    
    # Create Piper-compatible .onnx.json structure
    # This is a simplified version that includes our custom parameters
    piper_config = {
        "dataset": base_config.get("dataset", "custom"),
        "audio": {
            "sample_rate": sample_rate,
            "quality": base_config.get("audio", {}).get("quality", "high")
        },
        "espeak": {
            "voice": base_config.get("espeak", {}).get("voice", language)
        },
        "inference": {
            "noise_scale": noise_scale,
            "length_scale": length_scale,
            "noise_w": noise_w,
            "sentence_silence_seconds": sentence_silence_seconds
        },
        "language": language,
        "piper_version": base_config.get("piper_version", "1.0.0"),
        "num_speakers": base_config.get("num_speakers", 1),
        "speaker_id_map": base_config.get("speaker_id_map", {"0": speaker}),
        "model_path": model_path,
        "speaker": speaker,
        "name": name,
        # Custom fields for our application
        "_custom": {
            "noise_scale": noise_scale,
            "length_scale": length_scale,
            "noise_w": noise_w,
            "sentence_silence_seconds": sentence_silence_seconds,
            "name": name
        }
    }
    
    return piper_config


@dataclass
class VoiceConfig:
    """Configuration for a voice."""
    model_path: str
    speaker: Optional[int] = None
    name: str = ""  # Display name for the voice
    # Piper TTS parameters
    noise_scale: float = 0.667  # Controls voice variability (0.3-0.8 typical)
    length_scale: float = 1.0  # Speech rate (<1.0 faster, >1.0 slower)
    noise_w: float = 0.8  # Phoneme length variation (0.0-1.0)
    sentence_silence_seconds: float = 0.0  # Pause between sentences (0.0+)


class VoicePresets:
    """Voice presets loaded from downloaded voices."""
    
    # No built-in presets - all voices come from downloaded files
    BUILTIN_PRESETS = {}
    
    @staticmethod
    def _find_onnx_model(library_presets_dir: Optional[Path] = None) -> Optional[str]:
        """Try to find a .onnx model file in common locations."""
        import os
        from pathlib import Path
        
        # Directories to exclude from search (venv, node_modules, etc.)
        exclude_dirs = {".venv", "venv", "env", ".env", "__pycache__", "node_modules", 
                       ".git", ".svn", "site-packages", "dist", "build"}
        
        def should_exclude_path(path: Path) -> bool:
            """Check if a path should be excluded from search."""
            path_str = str(path)
            parts = path.parts
            
            # Check if any part of the path matches exclude patterns
            for part in parts:
                if part in exclude_dirs:
                    return True
                # Also exclude paths containing site-packages (Python packages)
                if "site-packages" in part:
                    return True
            
            # Additional checks: exclude if path contains venv indicators
            if any(excluded in path_str for excluded in [".venv", "venv", "site-packages", "__pycache__"]):
                return True
            
            return False
        
        # Common locations to search for Piper models
        search_paths = [
            Path.home() / ".local" / "share" / "piper" / "voices",
            Path.home() / "piper" / "voices",
            Path("/usr/local/share/piper/voices"),
            Path("/opt/piper/voices"),
            Path.home() / "Documents" / "piper" / "voices",
            Path.home() / "Downloads",
            Path.home() / "Desktop",
        ]
        
        # Add library presets directory if provided
        if library_presets_dir and library_presets_dir.exists():
            search_paths.insert(0, library_presets_dir)  # Check this first
        
        # Only add current working directory if it's not a venv
        cwd = Path.cwd()
        if not should_exclude_path(cwd):
            search_paths.append(cwd)
        
        # Search for .onnx or .onnx.gz files
        for search_path in search_paths:
            if not search_path.exists():
                continue
            try:
                # Look for .onnx files (not .onnx.gz first, as .onnx is usually preferred)
                for model_file in search_path.rglob("*.onnx"):
                    # Skip if path should be excluded
                    if should_exclude_path(model_file):
                        continue
                    # Skip if it's a gzipped file (has .gz extension)
                    if model_file.name.endswith(".gz"):
                        continue
                    # Skip demo/test files from onnxruntime or other test files
                    if any(excluded in model_file.name.lower() for excluded in ["logreg_iris", "test", "demo", "sample", "example"]):
                        continue
                    # Also check the full path for excluded patterns
                    if any(excluded in str(model_file) for excluded in ["logreg_iris", "datasets", "onnxruntime/datasets"]):
                        continue
                    if model_file.is_file():
                        # Basic validation: check if file is reasonably sized (Piper models are usually >1MB)
                        try:
                            size_mb = model_file.stat().st_size / (1024 * 1024)
                            if size_mb < 0.1:  # Skip files smaller than 100KB (likely not Piper models)
                                continue
                        except OSError:
                            continue
                        return str(model_file)
                # Fall back to .onnx.gz if no .onnx found
                for model_file in search_path.rglob("*.onnx.gz"):
                    if should_exclude_path(model_file):
                        continue
                    if model_file.is_file():
                        try:
                            size_mb = model_file.stat().st_size / (1024 * 1024)
                            if size_mb < 0.1:
                                continue
                        except OSError:
                            continue
                        return str(model_file)
            except (PermissionError, OSError):
                continue
        
        return None
    
    @staticmethod
    def load_library_presets(library_presets_dir: Optional[Path] = None) -> Dict[str, VoiceConfig]:
        """Load presets from library presets directory (supports both .json and .onnx.json formats)."""
        library_presets = {}
        if library_presets_dir and library_presets_dir.exists():
            # Load .onnx.json files (Piper format)
            for preset_file in library_presets_dir.glob("*.onnx.json"):
                try:
                    data = json.loads(preset_file.read_text(encoding="utf-8"))
                    preset_name = preset_file.stem.replace(".onnx", "")  # Remove .onnx from stem
                    
                    # Extract parameters from Piper format or custom fields
                    custom = data.get("_custom", {})
                    inference = data.get("inference", {})
                    
                    library_presets[preset_name] = VoiceConfig(
                        model_path=data.get("model_path", ""),
                        speaker=data.get("speaker", 0),
                        name=custom.get("name", data.get("name", preset_name)),
                        noise_scale=inference.get("noise_scale", custom.get("noise_scale", 0.667)),
                        length_scale=inference.get("length_scale", custom.get("length_scale", 1.0)),
                        noise_w=inference.get("noise_w", custom.get("noise_w", 0.8)),
                        sentence_silence_seconds=inference.get("sentence_silence_seconds", custom.get("sentence_silence_seconds", 0.0))
                    )
                except Exception:
                    # Skip invalid preset files
                    continue
            
            # Also load legacy .json files for backward compatibility
            for preset_file in library_presets_dir.glob("*.json"):
                # Skip .onnx.json files we already processed
                if preset_file.name.endswith(".onnx.json"):
                    continue
                try:
                    data = json.loads(preset_file.read_text(encoding="utf-8"))
                    preset_name = preset_file.stem
                    library_presets[preset_name] = VoiceConfig(
                        model_path=data.get("model_path", ""),
                        speaker=data.get("speaker", 0),
                        name=data.get("name", preset_name),
                        noise_scale=data.get("noise_scale", 0.667),
                        length_scale=data.get("length_scale", 1.0),
                        noise_w=data.get("noise_w", 0.8),
                        sentence_silence_seconds=data.get("sentence_silence_seconds", 0.0)
                    )
                except Exception:
                    # Skip invalid preset files
                    continue
        return library_presets
    
    @staticmethod
    def get_preset_names(library_presets_dir: Optional[Path] = None) -> List[str]:
        """Get list of preset names (built-in + library presets)."""
        names = list(VoicePresets.BUILTIN_PRESETS.keys())
        if library_presets_dir:
            library_presets = VoicePresets.load_library_presets(library_presets_dir)
            names.extend(library_presets.keys())
        return names
    
    @staticmethod
    def get_preset(preset_name: str, default_model_path: Optional[str] = None, 
                   library_presets_dir: Optional[Path] = None) -> VoiceConfig:
        """Get a preset from downloaded voices."""
        # Check library presets (downloaded voices)
        if library_presets_dir:
            library_presets = VoicePresets.load_library_presets(library_presets_dir)
            if preset_name in library_presets:
                preset = library_presets[preset_name]
                if not preset.model_path:
                    # Try default model first
                    if default_model_path and Path(default_model_path).exists():
                        return VoiceConfig(
                            model_path=default_model_path,
                            speaker=preset.speaker,
                            name=preset.name,
                            noise_scale=preset.noise_scale,
                            length_scale=preset.length_scale,
                            noise_w=preset.noise_w,
                            sentence_silence_seconds=preset.sentence_silence_seconds
                        )
                    # If no default model, try to auto-discover .onnx file
                    discovered_model = VoicePresets._find_onnx_model(library_presets_dir)
                    if discovered_model:
                        return VoiceConfig(
                            model_path=discovered_model,
                            speaker=preset.speaker,
                            name=preset.name,
                            noise_scale=preset.noise_scale,
                            length_scale=preset.length_scale,
                            noise_w=preset.noise_w,
                            sentence_silence_seconds=preset.sentence_silence_seconds
                        )
                return preset
        
        # Fallback: return a default config with auto-discovered model if available
        fallback_model = default_model_path
        if not fallback_model or not Path(fallback_model).exists():
            fallback_model = VoicePresets._find_onnx_model(library_presets_dir) or ""
        
        return VoiceConfig(
            model_path=fallback_model,
            speaker=0,
            name=preset_name,
            noise_scale=0.667,
            length_scale=1.0,
            noise_w=0.8,
            sentence_silence_seconds=0.0
        )


class VoiceSelectionDialog(QDialog):
    """Dialog for selecting voices for each character."""
    
    def __init__(self, characters: List[str], default_model_path: Optional[str] = None, 
                 library_presets_dir: Optional[Path] = None, parent=None):
        super().__init__(parent)
        self.characters = characters
        self.default_model_path = default_model_path
        self.library_presets_dir = library_presets_dir
        self.voice_configs: Dict[str, VoiceConfig] = {}
        self._setup_ui()
        self._load_default_voices()
    
    def _setup_ui(self) -> None:
        """Build the UI."""
        self.setWindowTitle("Select Voices for Characters")
        self.resize(800, 600)
        
        layout = QVBoxLayout(self)
        
        # Instructions
        instructions = QLabel(
            "Assign a voice to each character. You can use presets or select custom voice models.\n"
            "Note: You'll need to have Piper voice models installed."
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)
        
        # Default model selection
        model_group = QGroupBox("Default Voice Model")
        model_layout = QHBoxLayout()
        self.lbl_model = QLabel("Model:")
        model_layout.addWidget(self.lbl_model)
        self.btn_choose_model = QPushButton("Choose Model...")
        self.btn_choose_model.clicked.connect(self._choose_default_model)
        model_layout.addWidget(self.btn_choose_model)
        self.lbl_model_path = QLabel("No model selected")
        self.lbl_model_path.setWordWrap(True)
        model_layout.addWidget(self.lbl_model_path, stretch=1)
        model_group.setLayout(model_layout)
        layout.addWidget(model_group)
        
        if self.default_model_path:
            self.lbl_model_path.setText(self.default_model_path)
        
        # Character-voice table
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Character", "Voice Preset", "Custom Model", "Selected Voice"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setRowCount(len(self.characters))
        
        # Populate table
        for i, character in enumerate(self.characters):
            # Character name
            char_item = QTableWidgetItem(character)
            char_item.setFlags(char_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(i, 0, char_item)
            
            # Preset combo
            preset_combo = QComboBox()
            preset_combo.addItem("None")
            preset_combo.addItems(VoicePresets.get_preset_names(self.library_presets_dir))
            preset_combo.currentTextChanged.connect(
                lambda text, idx=i: self._on_preset_changed(idx, text)
            )
            self.table.setCellWidget(i, 1, preset_combo)
            
            # Custom model button
            custom_btn = QPushButton("Choose...")
            custom_btn.clicked.connect(lambda checked, idx=i: self._choose_custom_model(idx))
            self.table.setCellWidget(i, 2, custom_btn)
            
            # Selected voice label
            voice_label = QLabel("None")
            voice_label.setWordWrap(True)
            self.table.setCellWidget(i, 3, voice_label)
        
        layout.addWidget(self.table, stretch=1)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_ok = QPushButton("OK")
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_ok)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)
    
    def _load_default_voices(self) -> None:
        """Load default voice configurations."""
        # Initialize with default model if available
        if self.default_model_path:
            for character in self.characters:
                self.voice_configs[character] = VoiceConfig(
                    model_path=self.default_model_path,
                    speaker=0,
                    name=f"Default - {character}",
                    noise_scale=0.667,
                    length_scale=1.0,
                    noise_w=0.8,
                    sentence_silence_seconds=0.0
                )
    
    def _choose_default_model(self) -> None:
        """Choose default voice model."""
        # Start in library presets directory if available, otherwise use empty string
        start_dir = str(self.library_presets_dir) if self.library_presets_dir and self.library_presets_dir.exists() else ""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Piper Voice Model",
            start_dir,
            "Piper Models (*.onnx *.onnx.gz);;All Files (*.*)",
        )
        if path:
            self.default_model_path = path
            self.lbl_model_path.setText(path)
            # Update all characters that don't have custom models
            for i, character in enumerate(self.characters):
                if character not in self.voice_configs or \
                   self.voice_configs[character].model_path == "":
                    self.voice_configs[character] = VoiceConfig(
                        model_path=path,
                        speaker=0,
                        name=f"Default - {character}"
                    )
    
    def _on_preset_changed(self, row: int, preset_name: str) -> None:
        """Handle preset selection change."""
        character = self.characters[row]
        if preset_name == "None":
            # Use default model if available
            if self.default_model_path:
                self.voice_configs[character] = VoiceConfig(
                    model_path=self.default_model_path,
                    speaker=0,
                    name=f"Default - {character}",
                    noise_scale=0.667,
                    length_scale=1.0,
                    noise_w=0.8,
                    sentence_silence_seconds=0.0
                )
                self._update_voice_label(row, "Default (Speaker 0)")
            else:
                self.voice_configs[character] = VoiceConfig(
                    model_path="",
                    speaker=None,
                    name=""
                )
                self._update_voice_label(row, "None")
        else:
            preset = VoicePresets.get_preset(preset_name, self.default_model_path, self.library_presets_dir)
            # Use default model path if preset doesn't have one
            model_path = preset.model_path or self.default_model_path or ""
            if not model_path:
                QMessageBox.warning(
                    self,
                    "No Model Selected",
                    "Please select a default voice model first, or choose a custom model for this character."
                )
                # Reset combo to None
                preset_combo = self.table.cellWidget(row, 1)
                if preset_combo:
                    preset_combo.setCurrentIndex(0)
                return
            
            self.voice_configs[character] = VoiceConfig(
                model_path=model_path,
                speaker=preset.speaker,
                name=preset.name,
                noise_scale=preset.noise_scale,
                length_scale=preset.length_scale,
                noise_w=preset.noise_w,
                sentence_silence_seconds=preset.sentence_silence_seconds
            )
            self._update_voice_label(row, preset.name)
    
    def _choose_custom_model(self, row: int) -> None:
        """Choose custom voice model for a character."""
        character = self.characters[row]
        # Start in library presets directory if available, otherwise use empty string
        start_dir = str(self.library_presets_dir) if self.library_presets_dir and self.library_presets_dir.exists() else ""
        path, _ = QFileDialog.getOpenFileName(
            self,
            f"Select Voice Model for {character}",
            start_dir,
            "Piper Models (*.onnx *.onnx.gz);;All Files (*.*)",
        )
        if path:
            # Reset preset combo to "None"
            preset_combo = self.table.cellWidget(row, 1)
            if preset_combo:
                preset_combo.setCurrentIndex(0)
            
            # Set custom model
            self.voice_configs[character] = VoiceConfig(
                model_path=path,
                speaker=0,
                name=f"Custom - {Path(path).name}",
                noise_scale=0.667,
                length_scale=1.0,
                noise_w=0.8,
                sentence_silence_seconds=0.0
            )
            self._update_voice_label(row, f"Custom - {Path(path).name}")
    
    def _update_voice_label(self, row: int, voice_name: str) -> None:
        """Update the voice label for a character."""
        voice_label = self.table.cellWidget(row, 3)
        if voice_label:
            voice_label.setText(voice_name)
    
    def get_voice_configs(self) -> Dict[str, VoiceConfig]:
        """Get voice configurations for all characters."""
        return self.voice_configs.copy()
    
    def accept(self) -> None:
        """Validate and accept the dialog."""
        # Check that all characters have valid voice configs
        missing = []
        for character in self.characters:
            if character not in self.voice_configs or \
               not self.voice_configs[character].model_path:
                missing.append(character)
        
        if missing:
            QMessageBox.warning(
                self,
                "Missing Voices",
                f"The following characters don't have voice models selected:\n"
                f"{', '.join(missing)}\n\n"
                f"Please select a voice model for each character."
            )
            return
        
        super().accept()

