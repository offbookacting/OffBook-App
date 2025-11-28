# app/tabs/voice_settings_dialog.py
"""
Voice settings dialog for adjusting voices and saving presets.
"""
from __future__ import annotations
from pathlib import Path
from typing import Dict, Optional, List
import json

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QTableWidget, QTableWidgetItem, QFileDialog,
    QMessageBox, QGroupBox, QHeaderView, QSpinBox, QLineEdit, QInputDialog,
    QWidget, QTextEdit, QDoubleSpinBox, QSlider, QFormLayout, QDialogButtonBox,
    QScrollArea
)
import random
import subprocess
import platform

from app.tabs.voice_selection_dialog import VoiceConfig, VoicePresets, create_piper_onnx_json
from app.tabs.voice_download_dialog import VoiceDownloadDialog
from app.config import AppConfig


class VoiceSettingsDialog(QDialog):
    """Dialog for adjusting voices and managing presets."""
    
    def __init__(self, app_config: AppConfig, library_presets_dir: Optional[Path] = None, parent=None):
        super().__init__(parent)
        self.app_config = app_config
        self.library_presets_dir = library_presets_dir
        self.custom_presets: Dict[str, VoiceConfig] = {}
        self._load_custom_presets()
        self._setup_ui()
        self._populate_presets()
    
    def _setup_ui(self) -> None:
        """Build the UI."""
        self.setWindowTitle("Voice Settings & Presets")
        self.resize(800, 600)
        
        layout = QVBoxLayout(self)
        
        # Test text box at the top
        test_group = QGroupBox("Test Voice")
        test_layout = QVBoxLayout()
        test_label = QLabel("Test text (what the voice will say when 'Test' is clicked):")
        test_layout.addWidget(test_label)
        self.test_text_edit = QTextEdit()
        self.test_text_edit.setPlainText("this is how this voice sounds")
        self.test_text_edit.setMaximumHeight(60)
        test_layout.addWidget(self.test_text_edit)
        test_group.setLayout(test_layout)
        layout.addWidget(test_group)
        
        # Presets table
        presets_group = QGroupBox("Voice Presets")
        presets_layout = QVBoxLayout()
        
        # Info about library presets
        if self.library_presets_dir:
            info_layout = QHBoxLayout()
            info_label = QLabel(
                f"Library presets directory: {self.library_presets_dir}\n"
                "Place JSON preset files here to use them across all projects."
            )
            info_label.setWordWrap(True)
            info_layout.addWidget(info_label)
            btn_open_dir = QPushButton("Open Directory")
            btn_open_dir.clicked.connect(self._open_library_presets_dir)
            info_layout.addWidget(btn_open_dir)
            presets_layout.addLayout(info_layout)
        
        self.table_presets = QTableWidget()
        self.table_presets.setColumnCount(2)
        self.table_presets.setHorizontalHeaderLabels(["Name", "Actions"])
        self.table_presets.horizontalHeader().setStretchLastSection(True)
        self.table_presets.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        presets_layout.addWidget(self.table_presets)
        
        # Add preset buttons
        btn_layout = QHBoxLayout()
        btn_download = QPushButton("📥 Download Official Voices")
        btn_download.clicked.connect(self._download_voices)
        btn_layout.addWidget(btn_download)
        
        btn_add = QPushButton("Add Custom Preset")
        btn_add.clicked.connect(self._add_custom_preset)
        btn_layout.addWidget(btn_add)
        
        btn_random = QPushButton("Create Random Preset")
        btn_random.clicked.connect(self._create_random_preset)
        btn_layout.addWidget(btn_random)
        
        btn_layout.addStretch()
        presets_layout.addLayout(btn_layout)
        
        presets_group.setLayout(presets_layout)
        layout.addWidget(presets_group, stretch=1)
        
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
    
    def _load_custom_presets(self) -> None:
        """Load custom presets from library presets directory."""
        self.custom_presets = {}
        if self.library_presets_dir and self.library_presets_dir.exists():
            library_presets = VoicePresets.load_library_presets(self.library_presets_dir)
            self.custom_presets = library_presets
    
    def _save_custom_presets(self) -> None:
        """Save custom presets to library presets directory as .onnx.json files (Piper format)."""
        if not self.library_presets_dir:
            return
        
        # Ensure directory exists
        self.library_presets_dir.mkdir(parents=True, exist_ok=True)
        
        # Save each preset as a .onnx.json file in Piper format
        for name, preset in self.custom_presets.items():
            # Create a safe filename from the preset name
            safe_name = name.replace(" ", "_").replace("-", "_").lower()
            # Remove any invalid filename characters
            safe_name = "".join(c for c in safe_name if c.isalnum() or c in ('_', '-'))
            
            # IMPORTANT: Always use .onnx.json extension (Piper format)
            preset_file = self.library_presets_dir / f"{safe_name}.onnx.json"
            
            # Remove any legacy .json file FIRST (before creating new one)
            legacy_file = self.library_presets_dir / f"{safe_name}.json"
            if legacy_file.exists() and not legacy_file.name.endswith(".onnx.json"):
                try:
                    legacy_file.unlink()
                except Exception:
                    pass
            
            # Create Piper-compatible .onnx.json format
            preset_data = create_piper_onnx_json(
                model_path=preset.model_path or "",
                speaker=preset.speaker or 0,
                noise_scale=preset.noise_scale,
                length_scale=preset.length_scale,
                noise_w=preset.noise_w,
                sentence_silence_seconds=preset.sentence_silence_seconds,
                name=preset.name or name
            )
            
            # Write the .onnx.json file
            preset_file.write_text(json.dumps(preset_data, indent=2), encoding="utf-8")
            
            # Double-check: remove any .json file that might have been created (safety check)
            if legacy_file.exists() and legacy_file != preset_file:
                try:
                    legacy_file.unlink()
                except Exception:
                    pass
    
    def _populate_presets(self) -> None:
        """Populate the presets table."""
        # Combine built-in and library presets - treat all the same
        all_presets = {}
        
        default_model = self.app_config.tts_model_path()
        
        # Add built-in presets
        for preset_name in VoicePresets.BUILTIN_PRESETS.keys():
            preset = VoicePresets.get_preset(preset_name, default_model, self.library_presets_dir)
            all_presets[preset_name] = preset
        
        # Add library presets (these are the custom presets saved to library)
        if self.library_presets_dir:
            library_presets = VoicePresets.load_library_presets(self.library_presets_dir)
            for preset_name, preset in library_presets.items():
                all_presets[preset_name] = preset
        
        self.table_presets.setRowCount(len(all_presets))
        
        for i, (name, preset) in enumerate(all_presets.items()):
            # Name - all presets are editable
            # Store original name in data role for tracking changes
            name_item = QTableWidgetItem(name)
            name_item.setFlags(name_item.flags() | Qt.ItemFlag.ItemIsEditable)
            name_item.setData(Qt.ItemDataRole.UserRole, name)  # Store original name
            self.table_presets.setItem(i, 0, name_item)
            
            # Actions - all presets get all buttons
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(2, 2, 2, 2)
            actions_layout.setSpacing(2)
            
            # Delete button (all presets)
            btn_delete = QPushButton("🗑")
            btn_delete.setToolTip("Delete")
            btn_delete.setMaximumWidth(30)
            btn_delete.clicked.connect(lambda checked, n=name: self._delete_preset(n))
            actions_layout.addWidget(btn_delete)
            
            # Rename button (all presets)
            btn_rename = QPushButton("✏")
            btn_rename.setToolTip("Rename")
            btn_rename.setMaximumWidth(30)
            btn_rename.clicked.connect(lambda checked, n=name: self._rename_preset(n))
            actions_layout.addWidget(btn_rename)
            
            # Edit button (all presets)
            btn_edit = QPushButton("⚙")
            btn_edit.setToolTip("Edit")
            btn_edit.setMaximumWidth(30)
            btn_edit.clicked.connect(lambda checked, n=name, p=preset: self._edit_preset(n, p))
            actions_layout.addWidget(btn_edit)
            
            # Test button (all presets)
            btn_test = QPushButton("▶")
            btn_test.setToolTip("Test")
            btn_test.setMaximumWidth(30)
            btn_test.clicked.connect(lambda checked, n=name, p=preset: self._test_preset(n, p))
            actions_layout.addWidget(btn_test)
            
            actions_layout.addStretch()
            
            self.table_presets.setCellWidget(i, 1, actions_widget)
    
    def _add_custom_preset(self) -> None:
        """Add a new custom preset."""
        name, ok = QInputDialog.getText(
            self,
            "New Preset",
            "Enter preset name:"
        )
        if not ok or not name.strip():
            return
        
        # Check if name already exists in built-in or library presets
        preset_names = VoicePresets.get_preset_names(self.library_presets_dir)
        if name in preset_names:
            QMessageBox.warning(self, "Error", "Preset name already exists.")
            return
        
        # Try to find a model: use default, or try auto-discovery
        default_model = self.app_config.tts_model_path()
        model_path = default_model or ""
        
        # If no default model, try auto-discovery
        if not model_path or not Path(model_path).exists():
            discovered_model = VoicePresets._find_onnx_model(self.library_presets_dir)
            if discovered_model and Path(discovered_model).exists():
                model_path = discovered_model
                # Optionally save as default
                if not default_model:
                    reply = QMessageBox.question(
                        self,
                        "Model Found",
                        f"Found a voice model: {discovered_model}\n\n"
                        "Would you like to set this as the default model for all presets?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                    )
                    if reply == QMessageBox.StandardButton.Yes:
                        try:
                            self.app_config.set_tts_model_path(discovered_model)
                        except ValueError as e:
                            QMessageBox.warning(self, "Invalid Model Path", str(e))
        
        new_preset = VoiceConfig(
            model_path=model_path,
            speaker=0,
            name=name,
            noise_scale=0.667,
            length_scale=1.0,
            noise_w=0.8,
            sentence_silence_seconds=0.0
        )
        
        # Open edit dialog immediately
        edited_preset = self._edit_voice_config_dialog(new_preset, name, is_new=True)
        if edited_preset:
            self.custom_presets[edited_preset.name] = edited_preset
            self._save_custom_presets()
            self._populate_presets()
    
    def _create_random_preset(self) -> None:
        """Create a random preset with randomized parameters."""
        name, ok = QInputDialog.getText(
            self,
            "Random Preset",
            "Enter preset name:"
        )
        if not ok or not name.strip():
            return
        
        # Check if name already exists
        preset_names = VoicePresets.get_preset_names(self.library_presets_dir)
        if name in preset_names:
            QMessageBox.warning(self, "Error", "Preset name already exists.")
            return
        
        # Try to find a model: use default, or try auto-discovery
        default_model = self.app_config.tts_model_path()
        model_path = default_model or ""
        
        # If no default model, try auto-discovery
        if not model_path or not Path(model_path).exists():
            discovered_model = VoicePresets._find_onnx_model(self.library_presets_dir)
            if discovered_model and Path(discovered_model).exists():
                model_path = discovered_model
                # Optionally save as default
                if not default_model:
                    reply = QMessageBox.question(
                        self,
                        "Model Found",
                        f"Found a voice model: {discovered_model}\n\n"
                        "Would you like to set this as the default model for all presets?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                    )
                    if reply == QMessageBox.StandardButton.Yes:
                        try:
                            self.app_config.set_tts_model_path(discovered_model)
                        except ValueError as e:
                            QMessageBox.warning(self, "Invalid Model Path", str(e))
        
        # Randomize all parameters
        random_preset = VoiceConfig(
            model_path=model_path,
            speaker=random.randint(0, 2),  # Random speaker 0-2
            name=name,
            noise_scale=random.uniform(0.3, 0.8),  # Random noise scale
            length_scale=random.uniform(0.7, 1.3),  # Random length scale
            noise_w=random.uniform(0.0, 1.0),  # Random noise_w
            sentence_silence_seconds=random.uniform(0.0, 0.5)  # Random sentence silence
        )
        
        # Open edit dialog with randomized values
        edited_preset = self._edit_voice_config_dialog(random_preset, name, is_new=True)
        if edited_preset:
            self.custom_presets[edited_preset.name] = edited_preset
            self._save_custom_presets()
            self._populate_presets()
    
    def _edit_voice_config_dialog(self, preset: VoiceConfig, initial_name: str, is_new: bool = False) -> Optional[VoiceConfig]:
        """Comprehensive dialog for editing all voice parameters."""
        dialog = QDialog(self)
        dialog.setWindowTitle(f"{'Create' if is_new else 'Edit'} Voice Preset: {initial_name}")
        dialog.resize(600, 700)
        
        layout = QVBoxLayout(dialog)
        
        # Scroll area for parameters
        scroll = QWidget()
        scroll_layout = QVBoxLayout(scroll)
        
        form_layout = QFormLayout()
        
        # Name
        name_edit = QLineEdit(initial_name)
        form_layout.addRow("Name:", name_edit)
        
        # Model path
        model_edit = QLineEdit(preset.model_path or "")
        model_btn = QPushButton("Browse...")
        model_layout = QHBoxLayout()
        model_layout.addWidget(model_edit)
        model_layout.addWidget(model_btn)
        model_widget = QWidget()
        model_widget.setLayout(model_layout)
        form_layout.addRow("Model Path:", model_widget)
        
        def browse_model():
            start_dir = str(self.library_presets_dir) if self.library_presets_dir and self.library_presets_dir.exists() else ""
            path, _ = QFileDialog.getOpenFileName(
                dialog,
                "Select Voice Model",
                start_dir,
                "Piper Models (*.onnx *.onnx.gz);;All Files (*.*)",
            )
            if path:
                model_edit.setText(path)
        
        model_btn.clicked.connect(browse_model)
        
        # Speaker ID
        speaker_spin = QSpinBox()
        speaker_spin.setRange(0, 100)
        speaker_spin.setValue(preset.speaker or 0)
        form_layout.addRow("Speaker ID:", speaker_spin)
        
        # Noise Scale
        noise_scale_slider = QSlider(Qt.Orientation.Horizontal)
        noise_scale_slider.setRange(30, 80)  # 0.3 to 0.8 in steps of 0.01
        noise_scale_slider.setValue(int(preset.noise_scale * 100))
        noise_scale_label = QLabel(f"{preset.noise_scale:.2f}")
        noise_scale_slider.valueChanged.connect(
            lambda v: noise_scale_label.setText(f"{v / 100.0:.2f}")
        )
        noise_scale_layout = QHBoxLayout()
        noise_scale_layout.addWidget(noise_scale_slider)
        noise_scale_layout.addWidget(noise_scale_label)
        noise_scale_widget = QWidget()
        noise_scale_widget.setLayout(noise_scale_layout)
        form_layout.addRow("Noise Scale (variability):", noise_scale_widget)
        
        # Length Scale
        length_scale_slider = QSlider(Qt.Orientation.Horizontal)
        length_scale_slider.setRange(50, 200)  # 0.5 to 2.0 in steps of 0.01
        length_scale_slider.setValue(int(preset.length_scale * 100))
        length_scale_label = QLabel(f"{preset.length_scale:.2f}")
        length_scale_slider.valueChanged.connect(
            lambda v: length_scale_label.setText(f"{v / 100.0:.2f}")
        )
        length_scale_layout = QHBoxLayout()
        length_scale_layout.addWidget(length_scale_slider)
        length_scale_layout.addWidget(length_scale_label)
        length_scale_widget = QWidget()
        length_scale_widget.setLayout(length_scale_layout)
        form_layout.addRow("Length Scale (speed):", length_scale_widget)
        
        # Noise W
        noise_w_slider = QSlider(Qt.Orientation.Horizontal)
        noise_w_slider.setRange(0, 100)  # 0.0 to 1.0 in steps of 0.01
        noise_w_slider.setValue(int(preset.noise_w * 100))
        noise_w_label = QLabel(f"{preset.noise_w:.2f}")
        noise_w_slider.valueChanged.connect(
            lambda v: noise_w_label.setText(f"{v / 100.0:.2f}")
        )
        noise_w_layout = QHBoxLayout()
        noise_w_layout.addWidget(noise_w_slider)
        noise_w_layout.addWidget(noise_w_label)
        noise_w_widget = QWidget()
        noise_w_widget.setLayout(noise_w_layout)
        form_layout.addRow("Noise W (phoneme variation):", noise_w_widget)
        
        # Sentence Silence Seconds
        sentence_silence_spin = QDoubleSpinBox()
        sentence_silence_spin.setRange(0.0, 2.0)
        sentence_silence_spin.setSingleStep(0.1)
        sentence_silence_spin.setDecimals(2)
        sentence_silence_spin.setValue(preset.sentence_silence_seconds)
        form_layout.addRow("Sentence Silence (seconds):", sentence_silence_spin)
        
        scroll_layout.addLayout(form_layout)
        scroll_layout.addStretch()
        
        scroll_area = QScrollArea()
        scroll_area.setWidget(scroll)
        scroll_area.setWidgetResizable(True)
        layout.addWidget(scroll_area)
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_name = name_edit.text().strip()
            if not new_name:
                QMessageBox.warning(self, "Error", "Name cannot be empty.")
                return None
            
            return VoiceConfig(
                model_path=model_edit.text().strip(),
                speaker=speaker_spin.value(),
                name=new_name,
                noise_scale=noise_scale_slider.value() / 100.0,
                length_scale=length_scale_slider.value() / 100.0,
                noise_w=noise_w_slider.value() / 100.0,
                sentence_silence_seconds=sentence_silence_spin.value()
            )
        
        return None
    
    def _rename_preset(self, name: str) -> None:
        """Rename a preset."""
        # Get the preset (from built-in or library)
        default_model = self.app_config.tts_model_path()
        preset = VoicePresets.get_preset(name, default_model, self.library_presets_dir)
        
        new_name, ok = QInputDialog.getText(
            self,
            "Rename Preset",
            f"Enter new name for '{name}':",
            text=name
        )
        if not ok or not new_name.strip() or new_name == name:
            return
        
        # Check if name already exists
        preset_names = VoicePresets.get_preset_names(self.library_presets_dir)
        if new_name in preset_names:
            QMessageBox.warning(self, "Error", "Preset name already exists.")
            return
        
        # Add to custom presets (or update if already exists)
        self.custom_presets[new_name] = VoiceConfig(
            model_path=preset.model_path or default_model or "",
            speaker=preset.speaker or 0,
            name=new_name,
            noise_scale=preset.noise_scale,
            length_scale=preset.length_scale,
            noise_w=preset.noise_w,
            sentence_silence_seconds=preset.sentence_silence_seconds
        )
        
        # If it was a library preset, delete the old one
        if name in self.custom_presets:
            del self.custom_presets[name]
        
        # Rename the file if it exists in library
        if self.library_presets_dir:
            for preset_file in self.library_presets_dir.glob("*.onnx.json"):
                try:
                    data = json.loads(preset_file.read_text(encoding="utf-8"))
                    preset_file_name = preset_file.stem.replace(".onnx", "")
                    custom_name = data.get("_custom", {}).get("name", data.get("name", preset_file_name))
                    if preset_file_name == name or custom_name == name:
                        # Create new filename
                        safe_name = new_name.replace(" ", "_").replace("-", "_").lower()
                        safe_name = "".join(c for c in safe_name if c.isalnum() or c in ('_', '-'))
                        new_file = self.library_presets_dir / f"{safe_name}.onnx.json"
                        preset_file.rename(new_file)
                        break
                except Exception:
                    continue
        
        self._save_custom_presets()
        self._populate_presets()
    
    def _edit_preset(self, name: str, preset: VoiceConfig) -> None:
        """Edit a preset using comprehensive dialog."""
        # Get the current preset (from built-in or library)
        default_model = self.app_config.tts_model_path()
        current_preset = VoicePresets.get_preset(name, default_model, self.library_presets_dir)
        
        edited_preset = self._edit_voice_config_dialog(current_preset, name, is_new=False)
        if edited_preset:
            new_name = edited_preset.name
            if not new_name:
                QMessageBox.warning(self, "Error", "Name cannot be empty.")
                return
            
            # Check if name already exists (and it's not the same name)
            preset_names = VoicePresets.get_preset_names(self.library_presets_dir)
            if new_name in preset_names and new_name != name:
                QMessageBox.warning(self, "Error", "Preset name already exists.")
                return
            
            # Update the preset (save as library preset)
            self.custom_presets[new_name] = edited_preset
            
            # If name changed, delete old entry
            if new_name != name:
                if name in self.custom_presets:
                    del self.custom_presets[name]
                # Rename the file if it exists in library
                if self.library_presets_dir:
                    for preset_file in self.library_presets_dir.glob("*.onnx.json"):
                        try:
                            data = json.loads(preset_file.read_text(encoding="utf-8"))
                            preset_file_name = preset_file.stem.replace(".onnx", "")
                            custom_name = data.get("_custom", {}).get("name", data.get("name", preset_file_name))
                            if preset_file_name == name or custom_name == name:
                                # Create new filename
                                safe_name = new_name.replace(" ", "_").replace("-", "_").lower()
                                safe_name = "".join(c for c in safe_name if c.isalnum() or c in ('_', '-'))
                                new_file = self.library_presets_dir / f"{safe_name}.onnx.json"
                                preset_file.rename(new_file)
                                break
                        except Exception:
                            continue
            
            self._save_custom_presets()
            self._populate_presets()
    
    def _delete_preset(self, name: str) -> None:
        """Delete a preset."""
        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Delete preset '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # Delete the preset file from library directory if it exists
            if self.library_presets_dir:
                # Find the file with this preset name
                for preset_file in self.library_presets_dir.glob("*.onnx.json"):
                    try:
                        data = json.loads(preset_file.read_text(encoding="utf-8"))
                        preset_file_name = preset_file.stem.replace(".onnx", "")
                        custom_name = data.get("_custom", {}).get("name", data.get("name", preset_file_name))
                        # Check if this is the preset we want to delete
                        if preset_file_name == name or custom_name == name:
                            preset_file.unlink()
                            break
                    except Exception:
                        continue
                # Also check legacy .json files
                for preset_file in self.library_presets_dir.glob("*.json"):
                    if preset_file.name.endswith(".onnx.json"):
                        continue
                    try:
                        data = json.loads(preset_file.read_text(encoding="utf-8"))
                        preset_file_name = preset_file.stem
                        if preset_file_name == name or data.get("name") == name:
                            preset_file.unlink()
                            break
                    except Exception:
                        continue
            
            # Remove from custom presets if it exists
            if name in self.custom_presets:
                del self.custom_presets[name]
            
            self._populate_presets()
    
    def _test_preset(self, name: str, preset: VoiceConfig) -> None:
        """Test a voice preset."""
        from core.tts import PiperTTS, PiperTTSError
        
        default_model = self.app_config.tts_model_path()
        
        # Use the in-memory version if it exists (might have unsaved changes)
        # Otherwise resolve from library or built-in
        if name in self.custom_presets:
            resolved_preset = self.custom_presets[name]
        else:
            resolved_preset = VoicePresets.get_preset(name, default_model, self.library_presets_dir)
            # If that doesn't work, use the passed preset
            if not resolved_preset.model_path or not resolved_preset.model_path.strip():
                resolved_preset = preset
        
        # Try to resolve model path: use preset's model, then default model, then try auto-discovery
        model_path = None
        if resolved_preset.model_path and resolved_preset.model_path.strip():
            model_path_str = resolved_preset.model_path.strip()
            if Path(model_path_str).exists():
                model_path = model_path_str
        
        if not model_path:
            if default_model and default_model.strip():
                default_model_str = default_model.strip()
                if Path(default_model_str).exists():
                    model_path = default_model_str
        
        if not model_path:
            # Try auto-discovery as last resort
            discovered_model = VoicePresets._find_onnx_model(self.library_presets_dir)
            if discovered_model:
                discovered_model_str = str(discovered_model).strip()
                if Path(discovered_model_str).exists():
                    model_path = discovered_model_str
        
        if not model_path or not model_path.strip():
            # Build a helpful error message
            error_msg = f"Preset '{name}' has no voice model configured.\n\n"
            
            # Check what's available
            checks = []
            if not resolved_preset.model_path or not resolved_preset.model_path.strip():
                checks.append("• Preset has no model path set")
            elif not Path(resolved_preset.model_path.strip()).exists():
                checks.append(f"• Preset's model path doesn't exist: {resolved_preset.model_path}")
            
            if not default_model or not default_model.strip():
                checks.append("• No default model configured in settings")
            elif not Path(default_model.strip()).exists():
                checks.append(f"• Default model path doesn't exist: {default_model}")
            
            discovered = VoicePresets._find_onnx_model(self.library_presets_dir)
            if not discovered:
                checks.append("• No .onnx model files found in standard locations")
            
            if checks:
                error_msg += "Issues found:\n" + "\n".join(checks) + "\n\n"
            
            error_msg += "Solutions:\n"
            error_msg += "• Edit this preset and set a model path\n"
            error_msg += "• Configure a default model in application settings\n"
            error_msg += "• Place a .onnx model file in a standard location"
            
            QMessageBox.warning(
                self,
                "No Model Available",
                error_msg
            )
            return
        
        if not Path(model_path).exists():
            QMessageBox.warning(
                self,
                "Model Not Found",
                f"Voice model file not found:\n{model_path}\n\n"
                "Please check that the model path is correct or configure a default model in settings."
            )
            return
        
        # Use the resolved preset's speaker ID
        speaker_id = resolved_preset.speaker or preset.speaker or 0
        
        try:
            # Find config file (same directory as model, with .onnx.json extension)
            config_path = None
            model_path_obj = Path(model_path)
            if model_path_obj.exists():
                config_path_obj = model_path_obj.with_suffix('.onnx.json')
                if config_path_obj.exists():
                    config_path = str(config_path_obj)
            
            # Create TTS engine with the preset
            tts = PiperTTS(
                model_path=model_path,
                config_path=config_path,
                speaker=speaker_id,
                noise_scale=resolved_preset.noise_scale,
                length_scale=resolved_preset.length_scale,
                noise_w=resolved_preset.noise_w,
                sentence_silence_seconds=resolved_preset.sentence_silence_seconds
            )
            
            if not tts.is_available():
                QMessageBox.warning(
                    self,
                    "TTS Not Available",
                    "Text-to-speech engine is not available.\n\n"
                    "Please ensure Piper is properly installed."
                )
                return
            
            # Generate test audio using text from test text box
            test_text = self.test_text_edit.toPlainText().strip()
            if not test_text:
                test_text = "this is how this voice sounds"
            audio_path = tts.synthesize(test_text)
            
            if not audio_path or not audio_path.exists():
                QMessageBox.warning(
                    self,
                    "Synthesis Failed",
                    "Failed to generate audio for the test."
                )
                return
            
            # Play the audio
            from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
            from PyQt6.QtCore import QUrl
            import os
            
            # Play using QMediaPlayer
            player = QMediaPlayer(self)
            audio_output = QAudioOutput(self)
            player.setAudioOutput(audio_output)
            player.setSource(QUrl.fromLocalFile(str(audio_path)))
            
            # Clean up after playback
            def cleanup():
                try:
                    if audio_path.exists():
                        audio_path.unlink()
                except:
                    pass
            
            # Connect to finished signal to clean up
            player.mediaStatusChanged.connect(
                lambda status: cleanup() if status == QMediaPlayer.MediaStatus.EndOfMedia else None
            )
            
            player.play()
            
            # Don't show message box - just play silently
            # The audio will play in the background
            
        except PiperTTSError as e:
            QMessageBox.warning(
                self,
                "TTS Error",
                f"Error testing voice preset:\n{e}"
            )
        except Exception as e:
            QMessageBox.warning(
                self,
                "Error",
                f"Unexpected error testing voice preset:\n{e}"
            )
    
    def accept(self) -> None:
        """Save changes and accept."""
        # Save any edited preset names from the table
        for i in range(self.table_presets.rowCount()):
            name_item = self.table_presets.item(i, 0)
            if not name_item:
                continue
            
            new_name = name_item.text().strip()
            original_name = name_item.data(Qt.ItemDataRole.UserRole)  # Get original name
            
            if not new_name:
                continue
            
            # If name changed, rename the preset
            if original_name and new_name != original_name:
                # Get the preset
                default_model = self.app_config.tts_model_path()
                preset = VoicePresets.get_preset(original_name, default_model, self.library_presets_dir)
                
                # Check if new name already exists
                preset_names = VoicePresets.get_preset_names(self.library_presets_dir)
                if new_name in preset_names:
                    QMessageBox.warning(self, "Error", f"Preset name '{new_name}' already exists.")
                    return
                
                # Add with new name
                self.custom_presets[new_name] = VoiceConfig(
                    model_path=preset.model_path or default_model or "",
                    speaker=preset.speaker or 0,
                    name=new_name,
                    noise_scale=preset.noise_scale,
                    length_scale=preset.length_scale,
                    noise_w=preset.noise_w,
                    sentence_silence_seconds=preset.sentence_silence_seconds
                )
                
                # Delete old one if it was in custom presets
                if original_name in self.custom_presets:
                    del self.custom_presets[original_name]
                
                # Rename file if it exists
                if self.library_presets_dir:
                    for preset_file in self.library_presets_dir.glob("*.onnx.json"):
                        try:
                            data = json.loads(preset_file.read_text(encoding="utf-8"))
                            preset_file_name = preset_file.stem.replace(".onnx", "")
                            custom_name = data.get("_custom", {}).get("name", data.get("name", preset_file_name))
                            if preset_file_name == original_name or custom_name == original_name:
                                safe_name = new_name.replace(" ", "_").replace("-", "_").lower()
                                safe_name = "".join(c for c in safe_name if c.isalnum() or c in ('_', '-'))
                                new_file = self.library_presets_dir / f"{safe_name}.onnx.json"
                                preset_file.rename(new_file)
                                break
                        except Exception:
                            continue
        
        self._save_custom_presets()
        # Refresh presets table
        self._populate_presets()
        super().accept()
    
    def _download_voices(self) -> None:
        """Open the voice download dialog."""
        dialog = VoiceDownloadDialog(library_presets_dir=self.library_presets_dir, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Reload presets after download
            self._load_custom_presets()
            self._populate_presets()
    
    def _open_library_presets_dir(self) -> None:
        """Open the library presets directory in the file manager."""
        if not self.library_presets_dir:
            return
        
        try:
            if platform.system() == "Darwin":  # macOS
                subprocess.run(["open", str(self.library_presets_dir)])
            elif platform.system() == "Windows":
                subprocess.run(["explorer", str(self.library_presets_dir)])
            else:  # Linux
                subprocess.run(["xdg-open", str(self.library_presets_dir)])
        except Exception as e:
            QMessageBox.warning(
                self,
                "Error",
                f"Could not open directory:\n{e}\n\nDirectory: {self.library_presets_dir}"
            )
    
    def get_custom_presets(self) -> Dict[str, VoiceConfig]:
        """Get custom presets."""
        return self.custom_presets.copy()

