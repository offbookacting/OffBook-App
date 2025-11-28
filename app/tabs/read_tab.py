# app/tabs/read_tab.py
"""
Read tab - script reading with voice selection and word highlighting.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional, Dict, List, Any
import re

from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QRect
from PyQt6.QtGui import QTextCharFormat, QColor, QTextCursor, QMouseEvent, QKeyEvent, QEnterEvent, QTextBlockFormat
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QMessageBox, QComboBox, QTextEdit, QFileDialog, QScrollArea, QDialog,
    QGroupBox, QSlider, QProgressDialog, QApplication, QCheckBox
)

from core.nlp_processor import ScriptParse, DialogueBlock, blocks_for_character, parse_script_text
from core.pdf_parser import PDFParser
from core.project_manager import ProjectManager, Project
from core.prerender_manager import PrerenderManager
from app.tabs.script_reader import ScriptReader
from app.tabs.voice_selection_dialog import VoiceConfig, VoicePresets
from app.tabs.voice_download_dialog import VoiceDownloadDialog
from app.config import AppConfig
from core.file_state_manager import FileStateManager
import random


class ReadTab(QWidget):
    """Read tab for reading scripts with different voices."""
    
    def __init__(self, app_config: AppConfig, library_presets_dir: Optional[Path] = None, file_state_manager: Optional[FileStateManager] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.app_config = app_config
        self.library_presets_dir = library_presets_dir
        self.file_state_manager = file_state_manager
        self.project_manager: Optional[ProjectManager] = None
        self.current_project: Optional[Project] = None
        self.current_parse: Optional[ScriptParse] = None
        self.script_reader: Optional[ScriptReader] = None
        self.voice_configs: Dict[str, VoiceConfig] = {}
        self.pitch_values: Dict[str, float] = {}  # Store pitch per character
        self.current_highlighted_word: Optional[tuple[int, int]] = None  # (start_pos, end_pos)
        self.current_hovered_word: Optional[tuple[int, int]] = None  # (start_pos, end_pos) for hover
        self.line_offsets: List[int] = []
        self.current_quality: str = "medium"  # Default to medium
        self.word_original_colors: Dict[tuple[int, int], QColor] = {}  # Store original colors of words
        self.prerender_manager: Optional[PrerenderManager] = None
        self.is_prerendered: bool = False  # Track if current script is prerendered
        self.read_words: set[tuple[int, int]] = set()  # Track words that have been read (light blue)
        self.read_character_names: bool = True  # Default to reading character names
        self.playback_speed: float = 1.0  # Playback speed multiplier
        self.current_file_path: Optional[Path] = None  # Track current file for state management
        # Enable keyboard focus so we can receive spacebar events
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._setup_ui()
    
    def set_project(self, project_manager: ProjectManager, project: Project) -> None:
        """Set the project manager and project for saving/loading data."""
        self.project_manager = project_manager
        self.current_project = project
        # Initialize prerender manager
        if project_manager and project_manager.library:
            self.prerender_manager = PrerenderManager(project_manager.library)
        # Load saved voice configs and pitch values
        self._load_voice_configs_from_project()
    
    def _setup_ui(self) -> None:
        """Build the UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Toolbar
        toolbar = QHBoxLayout()
        
        # Voice quality dropdown
        quality_label = QLabel("Quality:")
        toolbar.addWidget(quality_label)
        
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["Low", "Medium", "High"])
        self.quality_combo.setCurrentText("Medium")
        self.quality_combo.setMinimumWidth(120)
        self.quality_combo.currentTextChanged.connect(self._on_quality_changed)
        toolbar.addWidget(self.quality_combo)
        
        # Read character names checkbox
        self.chk_read_character_names = QCheckBox("Read Character Names")
        self.chk_read_character_names.setChecked(True)  # Default to enabled
        self.chk_read_character_names.setToolTip("When enabled, character names will be read aloud")
        toolbar.addWidget(self.chk_read_character_names)
        
        # Speed slider
        speed_label = QLabel("Speed:")
        toolbar.addWidget(speed_label)
        
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setMinimum(50)  # 0.5x speed
        self.speed_slider.setMaximum(200)  # 2.0x speed
        self.speed_slider.setValue(100)  # 1.0x speed (normal)
        self.speed_slider.setMinimumWidth(150)
        self.speed_slider.setToolTip("Adjust playback speed (0.5x to 2.0x)")
        self.speed_slider.valueChanged.connect(self._on_speed_changed)
        toolbar.addWidget(self.speed_slider)
        
        self.speed_label = QLabel("1.00x")
        self.speed_label.setMinimumWidth(50)
        self.speed_label.setMaximumWidth(50)
        toolbar.addWidget(self.speed_label)
        
        toolbar.addStretch()
        
        # Prerender button
        self.btn_prerender = QPushButton("🎙 Prerender")
        self.btn_prerender.clicked.connect(self._on_prerender_clicked)
        self.btn_prerender.setToolTip("Prerender all audio for smooth playback")
        toolbar.addWidget(self.btn_prerender)
        
        # Control buttons
        self.btn_read = QPushButton("▶ Read")
        self.btn_read.clicked.connect(self._on_read_script)
        toolbar.addWidget(self.btn_read)
        
        self.btn_pause = QPushButton("⏸ Pause")
        self.btn_pause.clicked.connect(self._on_pause_reading)
        self.btn_pause.setEnabled(False)
        toolbar.addWidget(self.btn_pause)
        
        self.btn_stop = QPushButton("⏹ Stop")
        self.btn_stop.clicked.connect(self._on_stop_reading)
        self.btn_stop.setEnabled(False)
        toolbar.addWidget(self.btn_stop)
        
        toolbar.addStretch()
        
        layout.addLayout(toolbar)
        
        # Character voice selection (dropdown-based)
        voice_group = QGroupBox("Character Voices")
        voice_layout = QVBoxLayout()
        
        # Scrollable container for character voice dropdowns
        self.voice_widgets: Dict[str, QComboBox] = {}
        self.pitch_sliders: Dict[str, QSlider] = {}
        self.pitch_labels: Dict[str, QLabel] = {}
        self.voice_container = QWidget()
        self.voice_container_layout = QVBoxLayout(self.voice_container)
        self.voice_container_layout.setContentsMargins(5, 5, 5, 5)
        self.voice_container_layout.setSpacing(5)
        
        scroll_area = QScrollArea()
        scroll_area.setWidget(self.voice_container)
        scroll_area.setWidgetResizable(True)
        scroll_area.setMinimumHeight(100)
        scroll_area.setMaximumHeight(200)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setFrameShape(QScrollArea.Shape.Box)
        
        voice_layout.addWidget(scroll_area)
        voice_group.setLayout(voice_layout)
        
        layout.addWidget(voice_group)
        
        # Script text area (clickable)
        self.txt_script = QTextEdit()
        self.txt_script.setReadOnly(True)
        self.txt_script.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)  # Enable word wrapping
        self.txt_script.setFontFamily("Courier Prime")
        self.txt_script.setFontPointSize(12)
        self.txt_script.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)  # Disable horizontal scroll
        # Set white background and black text
        self.txt_script.setStyleSheet("QTextEdit { background-color: white; color: black; }")
        self.txt_script.mousePressEvent = self._on_script_clicked
        self.txt_script.mouseMoveEvent = self._on_script_mouse_move
        self.txt_script.leaveEvent = self._on_script_leave
        self.txt_script.keyPressEvent = self._on_key_press
        self.txt_script.setMouseTracking(True)  # Enable mouse tracking for hover
        layout.addWidget(self.txt_script, stretch=1)
        
        # Status label
        self.lbl_status = QLabel("No script loaded. Load a project to begin.")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setWordWrap(True)
        layout.addWidget(self.lbl_status)
        
    
    def set_script(self, script_parse: Optional[ScriptParse]) -> None:
        """Set the script to read."""
        self.current_parse = script_parse
        if script_parse:
            # Load saved pitch values before auto-assigning voices
            if self.current_project:
                self._load_voice_configs_from_project()
            
            # Display script text with formatting
            lines = script_parse.lines
            self.line_offsets = []
            
            # Build a set of character name lines and dialogue lines for centering
            character_lines = set()
            dialogue_lines = set()
            for block in script_parse.blocks:
                # For non-narrator blocks, character name is on the line before start_line
                # (start_line points to the first dialogue line, character name is at start_line - 1)
                if block.speaker != "NARRATOR" and block.start_line > 0:
                    char_name_line = block.start_line - 1
                    if char_name_line < len(lines):
                        character_lines.add(char_name_line)
                # Dialogue lines are from start_line to end_line
                for line_idx in range(block.start_line, min(block.end_line + 1, len(lines))):
                    dialogue_lines.add(line_idx)
            
            # Set text with formatting
            self.txt_script.clear()
            cursor = self.txt_script.textCursor()
            
            # Set default char format with Courier Prime font
            default_char_format = QTextCharFormat()
            default_char_format.setFontFamily("Courier Prime")
            default_char_format.setFontPointSize(12)
            
            for i, line in enumerate(lines):
                self.line_offsets.append(cursor.position())
                
                # Set alignment based on line type
                block_format = QTextBlockFormat()
                if i in character_lines or i in dialogue_lines:
                    block_format.setAlignment(Qt.AlignmentFlag.AlignCenter)
                else:
                    block_format.setAlignment(Qt.AlignmentFlag.AlignLeft)
                
                cursor.setBlockFormat(block_format)
                
                # Start with default char format (Courier Prime)
                char_format = QTextCharFormat(default_char_format)
                
                # Apply visual differentiation for prerendered blocks - light blue font
                if self.is_prerendered and i in dialogue_lines:
                    char_format.setForeground(QColor("#87CEEB"))  # Light blue (SkyBlue)
                
                cursor.setCharFormat(char_format)
                cursor.insertText(line)
                if i < len(lines) - 1:  # Don't add newline after last line
                    cursor.insertText("\n")
            
            # Auto-assign voice presets
            self._auto_assign_voices()
            
            # Check if prerendered audio is available and valid
            self._check_prerender_status()
            
            num_chars = len(script_parse.characters)
            status_text = f"Script loaded. Found {num_chars} character(s). "
            if self.is_prerendered:
                status_text += "✅ Prerendered audio available. "
            status_text += "Voices auto-assigned. Click 'Read' to start."
            self.lbl_status.setText(status_text)
            self.btn_read.setEnabled(True)
        else:
            self.txt_script.clear()
            self.lbl_status.setText("No script loaded. Load a project to begin.")
            self.btn_read.setEnabled(False)
            self.voice_configs.clear()
            self.pitch_values.clear()
            self._update_voice_widgets()
    
    def _load_voice_configs_from_project(self) -> None:
        """Load voice configs and pitch values from project meta."""
        if not self.current_project or not self.project_manager:
            return
        
        meta = self.current_project.meta or {}
        read_tab_meta = meta.get("read_tab", {})
        
        # Load pitch values
        saved_pitches = read_tab_meta.get("pitch_values", {})
        if saved_pitches:
            self.pitch_values = saved_pitches.copy()
    
    def _save_voice_configs_to_project(self) -> None:
        """Save voice configs and pitch values to project meta."""
        if not self.current_project or not self.project_manager:
            return
        
        try:
            def update_meta(meta: Dict[str, Any]) -> Dict[str, Any]:
                if "read_tab" not in meta:
                    meta["read_tab"] = {}
                meta["read_tab"]["pitch_values"] = self.pitch_values.copy()
                return meta
            
            self.project_manager.update_meta(self.current_project.id, update_meta)
            # Refresh project reference
            self.current_project = self.project_manager.get(self.current_project.id)
        except Exception as e:
            # Non-critical error - just log it
            print(f"Warning: Could not save pitch values to project: {e}")
    
    def _auto_assign_voices(self) -> None:
        """Automatically assign voice presets to characters."""
        if not self.current_parse:
            return
        
        characters = list(self.current_parse.characters.keys())
        if not characters:
            return
        
        default_model = self.app_config.tts_model_path()
        preset_names = VoicePresets.get_preset_names(self.library_presets_dir)
        
        # Preserve existing configs and only add missing ones
        # Don't clear - we want to keep existing assignments
        
        for i, character in enumerate(characters):
            # Skip if already configured
            if character in self.voice_configs:
                existing_config = self.voice_configs[character]
                # Only skip if it has a valid model path
                if existing_config.model_path and existing_config.model_path.strip():
                    continue
            
            # Cycle through presets
            if preset_names:
                preset_name = preset_names[i % len(preset_names)]
                preset = VoicePresets.get_preset(preset_name, default_model, self.library_presets_dir)
                
                # Use preset's model path if available, otherwise use default model
                # Only assign if we have a valid model path
                model_path = preset.model_path or default_model or ""
                
                if model_path and model_path.strip():
                    self.voice_configs[character] = VoiceConfig(
                        model_path=model_path,
                        speaker=preset.speaker or 0,
                        name=preset.name,
                        noise_scale=preset.noise_scale,
                        length_scale=preset.length_scale,
                        noise_w=preset.noise_w,
                        sentence_silence_seconds=preset.sentence_silence_seconds
                    )
            elif default_model and default_model.strip():
                # Fallback to default model
                self.voice_configs[character] = VoiceConfig(
                    model_path=default_model,
                    speaker=0,
                    name="Default",
                    noise_scale=0.667,
                    length_scale=1.0,
                    noise_w=0.8,
                    sentence_silence_seconds=0.0
                )
            else:
                # No presets available, use default model if available
                if default_model and default_model.strip():
                    self.voice_configs[character] = VoiceConfig(
                        model_path=default_model,
                        speaker=0,
                        name="Default",
                        noise_scale=0.667,
                        length_scale=1.0,
                        noise_w=0.8,
                        sentence_silence_seconds=0.0
                    )
        
        # Update voice widgets
        self._update_voice_widgets()
    
    def _update_voice_widgets(self) -> None:
        """Update the character voice dropdown widgets."""
        # Clear existing widgets
        for widget in list(self.voice_widgets.values()):
            widget.setParent(None)
            widget.deleteLater()
        self.voice_widgets.clear()
        
        for widget in list(self.pitch_sliders.values()):
            widget.setParent(None)
            widget.deleteLater()
        self.pitch_sliders.clear()
        
        for widget in list(self.pitch_labels.values()):
            widget.setParent(None)
            widget.deleteLater()
        self.pitch_labels.clear()
        
        # Clear layout
        while self.voice_container_layout.count():
            item = self.voice_container_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                # Clear nested layouts
                while item.layout().count():
                    nested_item = item.layout().takeAt(0)
                    if nested_item.widget():
                        nested_item.widget().deleteLater()
        
        # Get characters from script parse
        if not self.current_parse or not self.current_parse.characters:
            no_voices_label = QLabel("No characters found. Load a script to assign voices.")
            no_voices_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.voice_container_layout.addWidget(no_voices_label)
            return
        
        characters = list(self.current_parse.characters.keys())
        if not characters:
            no_voices_label = QLabel("No characters found. Load a script to assign voices.")
            no_voices_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.voice_container_layout.addWidget(no_voices_label)
            return
        
        # Add dropdowns for each character
        for character in sorted(characters):
            # Get voice config for this character, or create a default one
            voice_config = self.voice_configs.get(character)
            if not voice_config:
                # Create a default empty config
                voice_config = VoiceConfig(
                    model_path="",
                    speaker=0,
                    name="",
                    noise_scale=0.667,
                    length_scale=1.0,
                    noise_w=0.8,
                    sentence_silence_seconds=0.0
                )
            
            # Create horizontal layout for each character
            char_row = QHBoxLayout()
            
            # Character label
            char_label = QLabel(f"{character}:")
            char_label.setMinimumWidth(100)
            char_row.addWidget(char_label)
            
            # Voice combo - only show libritts, lessac, and amy
            voice_combo = QComboBox()
            voice_combo.setMinimumWidth(200)
            voice_combo.addItem("None")
            
            # Filter presets to only show libritts, lessac, and amy
            preset_names = VoicePresets.get_preset_names(self.library_presets_dir)
            filtered_presets = []
            
            # Group by voice name (libritts, lessac, amy)
            voice_groups = {
                "libritts": [],
                "lessac": [],
                "amy": []
            }
            
            for preset_name in preset_names:
                preset_name_lower = preset_name.lower()
                if "libritts" in preset_name_lower:
                    voice_groups["libritts"].append(preset_name)
                elif "lessac" in preset_name_lower:
                    voice_groups["lessac"].append(preset_name)
                elif "amy" in preset_name_lower:
                    voice_groups["amy"].append(preset_name)
            
            # Add one entry per voice group (prefer current quality, or medium, or first available)
            for voice_key, voice_display in [("libritts", "LibriTTS US"), ("lessac", "Lessac"), ("amy", "Amy")]:
                if voice_groups[voice_key]:
                    # Try to find preset with current quality
                    matching_preset = None
                    for preset_name in voice_groups[voice_key]:
                        if self.current_quality in preset_name.lower():
                            matching_preset = preset_name
                            break
                    
                    # If not found, try medium
                    if not matching_preset:
                        for preset_name in voice_groups[voice_key]:
                            if "medium" in preset_name.lower():
                                matching_preset = preset_name
                                break
                    
                    # If still not found, use first available
                    if not matching_preset:
                        matching_preset = voice_groups[voice_key][0]
                    
                    # Add display name with preset name as data
                    voice_combo.addItem(voice_display, matching_preset)
            
            voice_combo.addItem("Custom...")
            
            # Set current selection - match by voice name
            current_voice = None
            default_model = self.app_config.tts_model_path()
            
            # Extract voice name from current config
            voice_name = self._extract_voice_name_from_config(voice_config, preset_names)
            
            if voice_name:
                # Map to display name
                if voice_name == "libritts":
                    current_voice = "LibriTTS US"
                elif voice_name == "lessac":
                    current_voice = "Lessac"
                elif voice_name == "amy":
                    current_voice = "Amy"
            
            if current_voice:
                # Find the combo item with this display name
                for i in range(voice_combo.count()):
                    if voice_combo.itemText(i) == current_voice:
                        voice_combo.setCurrentIndex(i)
                        break
            elif voice_config.model_path and Path(voice_config.model_path).exists() and voice_config.model_path != (default_model or ""):
                voice_combo.setCurrentText("Custom...")
            else:
                voice_combo.setCurrentIndex(0)  # "None"
            
            # Use a lambda that captures the character properly
            def make_voice_changed_handler(char: str):
                def handler(text: str):
                    self._on_voice_changed(char, text)
                return handler
            
            voice_combo.currentTextChanged.connect(make_voice_changed_handler(character))
            
            char_row.addWidget(voice_combo)
            
            # Add dice button for randomizing this character's voice
            btn_random_voice = QPushButton("🎲")
            btn_random_voice.setToolTip(f"Randomize voice for {character}")
            btn_random_voice.setMaximumWidth(30)
            btn_random_voice.clicked.connect(lambda checked, char=character: self._on_randomize_character_voice(char))
            char_row.addWidget(btn_random_voice)
            
            # Add pitch slider
            pitch_label = QLabel("Pitch:")
            pitch_label.setMinimumWidth(50)
            char_row.addWidget(pitch_label)
            
            pitch_slider = QSlider(Qt.Orientation.Horizontal)
            pitch_slider.setRange(50, 200)  # 0.5 to 2.0 in steps of 0.01
            # Get saved pitch or randomize
            if character in self.pitch_values:
                pitch_value = self.pitch_values[character]
            else:
                # Randomize pitch between 0.7 and 1.3 (70-130 on slider)
                pitch_value = random.uniform(0.7, 1.3)
                self.pitch_values[character] = pitch_value
            pitch_slider.setValue(int(pitch_value * 100))
            pitch_slider.setMinimumWidth(150)
            pitch_slider.setMaximumWidth(200)
            
            pitch_value_label = QLabel(f"{pitch_value:.2f}")
            pitch_value_label.setMinimumWidth(50)
            pitch_value_label.setMaximumWidth(50)
            
            def make_pitch_handler(char: str, label: QLabel):
                def handler(value: int):
                    pitch = value / 100.0
                    label.setText(f"{pitch:.2f}")
                    self.pitch_values[char] = pitch
                    self._save_voice_configs_to_project()
                return handler
            
            pitch_slider.valueChanged.connect(make_pitch_handler(character, pitch_value_label))
            
            char_row.addWidget(pitch_slider)
            char_row.addWidget(pitch_value_label)
            
            self.pitch_sliders[character] = pitch_slider
            self.pitch_labels[character] = pitch_value_label
            
            char_row.addStretch()
            
            self.voice_widgets[character] = voice_combo
            self.voice_container_layout.addLayout(char_row)
    
    def _get_custom_presets(self) -> Dict[str, VoiceConfig]:
        """Get custom presets from config."""
        try:
            custom_presets = {}
            config_data = self.app_config._data.get("custom_voice_presets", {})
            for name, preset_data in config_data.items():
                custom_presets[name] = VoiceConfig(
                    model_path=preset_data.get("model_path", ""),
                    speaker=preset_data.get("speaker", 0),
                    name=name,
                    noise_scale=preset_data.get("noise_scale", 0.667),
                    length_scale=preset_data.get("length_scale", 1.0),
                    noise_w=preset_data.get("noise_w", 0.8),
                    sentence_silence_seconds=preset_data.get("sentence_silence_seconds", 0.0)
                )
            return custom_presets
        except Exception:
            return {}
    
    def _on_key_press(self, event: QKeyEvent) -> None:
        """Handle key press events - spacebar to start/stop TTS."""
        if event.key() == Qt.Key.Key_Space:
            # Only handle if script text area has focus
            if self.txt_script.hasFocus() or self.hasFocus():
                if self.script_reader and self.script_reader.is_playing:
                    # Stop if playing
                    self._on_stop_reading()
                elif self.current_parse and self.btn_read.isEnabled():
                    # Start if not playing
                    self._on_read_script()
                event.accept()
                return
        # Call parent handler for other keys
        QTextEdit.keyPressEvent(self.txt_script, event)
    
    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle key press events at widget level - spacebar to start/stop TTS."""
        if event.key() == Qt.Key.Key_Space:
            # Check if spacebar should trigger TTS control
            # Only if the text widget or this widget has focus
            if self.txt_script.hasFocus() or self.hasFocus():
                if self.script_reader and self.script_reader.is_playing:
                    # Stop if playing
                    self._on_stop_reading()
                    event.accept()
                    return
                elif self.current_parse and self.btn_read.isEnabled():
                    # Start if not playing
                    self._on_read_script()
                    event.accept()
                    return
        super().keyPressEvent(event)
    
    def _on_speed_changed(self, value: int) -> None:
        """Handle speed slider change."""
        self.playback_speed = value / 100.0  # Convert to multiplier (50-200 -> 0.5-2.0)
        self.speed_label.setText(f"{self.playback_speed:.2f}x")
        
        # Apply speed to current player if reading
        if self.script_reader and self.script_reader.player:
            self.script_reader.player.setPlaybackRate(self.playback_speed)
    
    def _on_playback_state_changed(self, state) -> None:
        """Handle playback state change - apply speed when audio starts playing."""
        from PyQt6.QtMultimedia import QMediaPlayer
        
        # When audio starts playing, apply the current speed
        if state == QMediaPlayer.PlaybackState.PlayingState:
            if self.script_reader and self.script_reader.player:
                self.script_reader.player.setPlaybackRate(self.playback_speed)
    
    def _on_quality_changed(self, quality: str) -> None:
        """Handle quality dropdown change."""
        self.current_quality = quality.lower()
        
        # Update all voice configs to use the new quality
        # We need to find the matching preset with the new quality
        default_model = self.app_config.tts_model_path()
        preset_names = VoicePresets.get_preset_names(self.library_presets_dir)
        
        for character in list(self.voice_configs.keys()):
            config = self.voice_configs[character]
            # Extract voice name from current config (e.g., "libritts", "lessac", "amy")
            voice_name = self._extract_voice_name_from_config(config, preset_names)
            
            if voice_name:
                # Find preset with matching voice and new quality
                new_preset_name = self._find_preset_by_voice_and_quality(voice_name, self.current_quality, preset_names)
                if new_preset_name:
                    preset = VoicePresets.get_preset(new_preset_name, default_model, self.library_presets_dir)
                    model_path = preset.model_path or default_model or ""
                    if model_path:
                        self.voice_configs[character] = VoiceConfig(
                            model_path=model_path,
                            speaker=preset.speaker or 0,
                            name=preset.name,
                            noise_scale=preset.noise_scale,
                            length_scale=preset.length_scale,
                            noise_w=preset.noise_w,
                            sentence_silence_seconds=preset.sentence_silence_seconds
                        )
        
        # Update voice widgets to reflect changes
        self._update_voice_widgets()
    
    def _extract_voice_name_from_config(self, config: VoiceConfig, preset_names: List[str]) -> Optional[str]:
        """Extract voice name (libritts, lessac, amy) from config."""
        default_model = self.app_config.tts_model_path()
        
        # Check if config matches any preset
        for preset_name in preset_names:
            preset = VoicePresets.get_preset(preset_name, default_model, self.library_presets_dir)
            preset_model = preset.model_path or default_model or ""
            config_model = config.model_path or default_model or ""
            
            if preset_model == config_model:
                # Extract voice name from preset name (e.g., "en_US-libritts-high" -> "libritts")
                preset_name_lower = preset_name.lower()
                if "libritts" in preset_name_lower:
                    return "libritts"
                elif "lessac" in preset_name_lower:
                    return "lessac"
                elif "amy" in preset_name_lower:
                    return "amy"
        
        return None
    
    def _find_preset_by_voice_and_quality(self, voice_name: str, quality: str, preset_names: List[str]) -> Optional[str]:
        """Find a preset by voice name and quality."""
        voice_name_lower = voice_name.lower()
        quality_lower = quality.lower()
        
        for preset_name in preset_names:
            preset_name_lower = preset_name.lower()
            if voice_name_lower in preset_name_lower and quality_lower in preset_name_lower:
                return preset_name
        
        return None
    
    def _on_randomize_character_voice(self, character: str) -> None:
        """Randomize voice for a specific character."""
        if not self.current_parse or not self.current_parse.characters:
            return
        
        if character not in self.current_parse.characters:
            return
        
        # Get default model, try auto-discovery if not set
        default_model = self.app_config.tts_model_path()
        if not default_model or not default_model.strip() or not Path(default_model).exists():
            discovered_model = VoicePresets._find_onnx_model(self.library_presets_dir)
            if discovered_model and Path(discovered_model).exists():
                default_model = discovered_model
                # Save the discovered model as the default for future use
                try:
                    self.app_config.set_tts_model_path(discovered_model)
                except ValueError:
                    # Invalid model path - will be handled by validation
                    pass
        
        # If still no model, try to get from presets
        if not default_model or not default_model.strip():
            preset_names = VoicePresets.get_preset_names(self.library_presets_dir)
            if preset_names:
                preset = VoicePresets.get_preset(preset_names[0], None, self.library_presets_dir)
                if preset.model_path and Path(preset.model_path).exists():
                    default_model = preset.model_path
        
        # If we still don't have a model, show error
        if not default_model or not default_model.strip():
            QMessageBox.warning(
                self,
                "No Voice Model",
                "No voice model found. Please configure a default voice model in settings first."
            )
            return
        
        # Randomize all parameters
        random_config = VoiceConfig(
            model_path=default_model,
            speaker=random.randint(0, 2),  # Random speaker
            name=f"Random - {character}",
            noise_scale=random.uniform(0.3, 0.8),  # Random noise scale
            length_scale=random.uniform(0.7, 1.3),  # Random length scale
            noise_w=random.uniform(0.0, 1.0),  # Random noise_w
            sentence_silence_seconds=random.uniform(0.0, 0.5)  # Random sentence silence
        )
        
        # Assign to this character
        self.voice_configs[character] = random_config
        
        # Update voice widgets to reflect the change
        self._update_voice_widgets()
    
    def _on_voice_changed(self, character: str, voice_text: str) -> None:
        """Handle voice selection change for a character - use selected voice with current quality."""
        # Warn if prerendered audio exists
        if self.is_prerendered:
            reply = QMessageBox.warning(
                self,
                "Prerendered Audio Will Be Reset",
                "Changing voice settings will invalidate prerendered audio.\n\n"
                "Prerendered voices will be reset. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel
            )
            if reply != QMessageBox.StandardButton.Yes:
                # Reset combo box to previous value
                combo = self.voice_widgets.get(character)
                if combo:
                    # Find previous voice config
                    old_config = self.voice_configs.get(character)
                    if old_config:
                        # Try to restore previous selection
                        for i in range(combo.count()):
                            if combo.itemText(i) == old_config.name:
                                combo.setCurrentIndex(i)
                                break
                return
            self.is_prerendered = False
        
        default_model = self.app_config.tts_model_path()
        
        if voice_text == "None":
            # Clear voice config for this character
            if character in self.voice_configs:
                del self.voice_configs[character]
        elif voice_text == "Custom...":
            self._choose_custom_voice(character)
        else:
            # Find the preset name from the combo box data
            combo = self.voice_widgets.get(character)
            if combo:
                current_index = combo.currentIndex()
                preset_name = combo.itemData(current_index)
                
                if preset_name:
                    # Get the preset with current quality
                    voice_name = None
                    if voice_text == "LibriTTS US":
                        voice_name = "libritts"
                    elif voice_text == "Lessac":
                        voice_name = "lessac"
                    elif voice_text == "Amy":
                        voice_name = "amy"
                    
                    if voice_name:
                        preset_names = VoicePresets.get_preset_names(self.library_presets_dir)
                        quality_preset_name = self._find_preset_by_voice_and_quality(voice_name, self.current_quality, preset_names)
                        
                        if quality_preset_name:
                            preset = VoicePresets.get_preset(quality_preset_name, default_model, self.library_presets_dir)
                            model_path = preset.model_path or default_model or ""
                            
                            if model_path:
                                self.voice_configs[character] = VoiceConfig(
                                    model_path=model_path,
                                    speaker=preset.speaker or 0,
                                    name=preset.name,
                                    noise_scale=preset.noise_scale,
                                    length_scale=preset.length_scale,
                                    noise_w=preset.noise_w,
                                    sentence_silence_seconds=preset.sentence_silence_seconds
                                )
                                return
                
                # Fallback: use the preset from data
                if preset_name:
                    preset = VoicePresets.get_preset(preset_name, default_model, self.library_presets_dir)
                    model_path = preset.model_path or default_model or ""
                    
                    if model_path:
                        self.voice_configs[character] = VoiceConfig(
                            model_path=model_path,
                            speaker=preset.speaker or 0,
                            name=preset.name,
                            noise_scale=preset.noise_scale,
                            length_scale=preset.length_scale,
                            noise_w=preset.noise_w,
                            sentence_silence_seconds=preset.sentence_silence_seconds
                        )
            
            # Update visual differentiation after voice change
            if self.current_parse:
                self.set_script(self.current_parse)
    
    def _choose_custom_voice(self, character: str) -> None:
        """Choose custom voice model for a character."""
        # Warn if prerendered audio exists
        if self.is_prerendered:
            reply = QMessageBox.warning(
                self,
                "Prerendered Audio Will Be Reset",
                "Changing voice settings will invalidate prerendered audio.\n\n"
                "Prerendered voices will be reset. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            self.is_prerendered = False
        
        # Start in library presets directory if available, otherwise use empty string
        start_dir = str(self.library_presets_dir) if self.library_presets_dir and self.library_presets_dir.exists() else ""
        path, _ = QFileDialog.getOpenFileName(
            self,
            f"Select Voice Model for {character}",
            start_dir,
            "Piper Models (*.onnx *.onnx.gz);;All Files (*.*)",
        )
        if path:
            self.voice_configs[character] = VoiceConfig(
                model_path=path,
                speaker=0,
                name=f"Custom - {Path(path).name}",
                noise_scale=0.667,
                length_scale=1.0,
                noise_w=0.8,
                sentence_silence_seconds=0.0
            )
            self._update_voice_widgets()
            # Update visual differentiation
            if self.current_parse:
                self.set_script(self.current_parse)
    
    
    def _get_word_at_position(self, pos: int) -> Optional[tuple[int, int]]:
        """Get the word boundaries at the given text position. Returns (start_pos, end_pos) or None."""
        if not self.current_parse:
            return None
        
        text = self.txt_script.toPlainText()
        if pos < 0 or pos >= len(text):
            return None
        
        # Find word boundaries
        # Move backward to find start of word
        start = pos
        while start > 0 and text[start - 1] not in ' \n\t':
            start -= 1
        
        # Move forward to find end of word
        end = pos
        while end < len(text) and text[end] not in ' \n\t':
            end += 1
        
        # Check if we found a valid word (non-whitespace)
        if start < end and text[start:end].strip():
            return (start, end)
        return None
    
    def _find_block_for_position(self, pos: int) -> Optional[int]:
        """Find which dialogue block contains the given text position. Returns block index or None."""
        if not self.current_parse or not self.line_offsets:
            return None
        
        # Get full text to verify position is valid
        full_text = self.txt_script.toPlainText()
        if pos < 0 or pos > len(full_text):
            return None
        
        for i, block in enumerate(self.current_parse.blocks):
            start_line = block.start_line
            end_line = block.end_line
            
            # Make sure line indices are valid
            if start_line >= len(self.line_offsets) or end_line >= len(self.current_parse.lines):
                continue
            
            # Calculate block boundaries
                block_start = self.line_offsets[start_line]
            # For end position, use the offset of the end line plus the length of that line
            if end_line < len(self.line_offsets):
                block_end = self.line_offsets[end_line] + len(self.current_parse.lines[end_line])
            else:
                # If end_line is beyond our offsets, use the end of the text
                block_end = len(full_text)
                
            # Check if position is within this block (inclusive)
                if block_start <= pos <= block_end:
                    return i
        
        return None
    
    def _apply_hover_effect(self, start_pos: int, end_pos: int) -> None:
        """Apply grey background hover effect to a word."""
        if self.current_hovered_word == (start_pos, end_pos):
            return  # Already hovered
        
        # Don't apply hover to currently highlighted word (darker blue)
        if self.current_highlighted_word == (start_pos, end_pos):
            return
        
        # Clear previous hover
        self._clear_hover_effect()
        
        # Apply new hover - only background, preserve text color and font
        cursor = self.txt_script.textCursor()
        cursor.setPosition(start_pos)
        cursor.setPosition(end_pos, QTextCursor.MoveMode.KeepAnchor)
        
        # Get current format to preserve text color and font
        current_format = cursor.charFormat()
        
        fmt = QTextCharFormat()
        fmt.setBackground(QColor("#D3D3D3"))  # Light grey background
        fmt.setForeground(current_format.foreground().color())  # Preserve text color
        fmt.setFontFamily("Courier Prime")  # Preserve Courier Prime font
        fmt.setFontPointSize(12)  # Preserve font size
        cursor.mergeCharFormat(fmt)
        
        self.current_hovered_word = (start_pos, end_pos)
    
    def _clear_hover_effect(self) -> None:
        """Clear the hover effect."""
        if self.current_hovered_word:
            start_pos, end_pos = self.current_hovered_word
            # Don't clear if this is the currently highlighted word
            if self.current_highlighted_word == (start_pos, end_pos):
                self.current_hovered_word = None
                return
            
            cursor = self.txt_script.textCursor()
            cursor.setPosition(start_pos)
            cursor.setPosition(end_pos, QTextCursor.MoveMode.KeepAnchor)
            
            # Get current format to preserve text color and font
            current_format = cursor.charFormat()
            
            fmt = QTextCharFormat()
            fmt.setBackground(QColor())  # Clear background (transparent)
            fmt.setForeground(current_format.foreground().color())  # Preserve text color
            fmt.setFontFamily("Courier Prime")  # Preserve Courier Prime font
            fmt.setFontPointSize(12)  # Preserve font size
            cursor.mergeCharFormat(fmt)
            
            self.current_hovered_word = None
    
    def _on_script_mouse_move(self, event: QMouseEvent) -> None:
        """Handle mouse move over script text - show hover effect."""
        if not self.current_parse:
            QTextEdit.mouseMoveEvent(self.txt_script, event)
            return
        
        cursor = self.txt_script.cursorForPosition(event.position().toPoint())
        pos = cursor.position()
        
        # Find word at this position
        word_bounds = self._get_word_at_position(pos)
        if word_bounds:
            start_pos, end_pos = word_bounds
            # Only apply hover if not the currently highlighted word (darker blue)
            if self.current_highlighted_word != (start_pos, end_pos):
                self._apply_hover_effect(start_pos, end_pos)
            else:
                # Clear hover if we're on the current word
                self._clear_hover_effect()
        else:
            self._clear_hover_effect()
        
        QTextEdit.mouseMoveEvent(self.txt_script, event)
    
    def _on_script_leave(self, event) -> None:
        """Handle mouse leave event - clear hover effect."""
        self._clear_hover_effect()
        if hasattr(QTextEdit, 'leaveEvent'):
            QTextEdit.leaveEvent(self.txt_script, event)
    
    def _on_script_clicked(self, event: QMouseEvent) -> None:
        """Handle click on script text - start reading from clicked word."""
        if not self.current_parse:
            return
        
        try:
            cursor = self.txt_script.cursorForPosition(event.position().toPoint())
            pos = cursor.position()
            
            # Find word at click position
            word_bounds = self._get_word_at_position(pos)
            if not word_bounds:
                return
            
            start_pos, end_pos = word_bounds
            
            # Find which dialogue block contains this word
            block_index = self._find_block_for_position(start_pos)
            if block_index is None:
                # Couldn't find a block - might be clicking on non-dialogue text
                return
            
            # Clear hover effect
            self._clear_hover_effect()
            
            # Stop any current reading completely
            if self.script_reader:
                try:
                    # Disconnect signals first to prevent callbacks during cleanup
                    self.script_reader.progress.disconnect()
                    self.script_reader.word_highlight.disconnect()
                    self.script_reader.finished.disconnect()
                    self.script_reader.error.disconnect()
                except Exception:
                    pass  # Signals might already be disconnected
                
                # Stop and clean up current reader
                self.script_reader.stop_reading()
                self.script_reader.deleteLater()
                self.script_reader = None
            
            # Reset button states
            self.btn_read.setEnabled(True)
            self.btn_pause.setEnabled(False)
            self.btn_stop.setEnabled(False)
            self.btn_pause.setText("⏸ Pause")
            
            # Use QTimer to delay start slightly, ensuring cleanup is complete
            QTimer.singleShot(100, lambda: self._start_reading(start_block=block_index))
        except Exception as e:
            # Handle any errors gracefully
            print(f"Error handling script click: {e}")
            import traceback
            traceback.print_exc()
    
    def _on_read_script(self) -> None:
        """Handle Read button click."""
        if not self.current_parse:
            QMessageBox.warning(
                self,
                "No Script Loaded",
                "No script is currently loaded."
            )
            return
        
        # Get all unique characters from both the characters dict and blocks
        # This ensures we include NARRATOR and any other speakers that might be in blocks
        characters_from_dict = list(self.current_parse.characters.keys())
        characters_from_blocks = list(set(block.speaker for block in self.current_parse.blocks))
        characters = list(set(characters_from_dict + characters_from_blocks))
        
        if not characters:
            QMessageBox.warning(
                self,
                "No Characters Found",
                "No characters were found in the script."
            )
            return
        
        # Get default model
        default_model = self.app_config.tts_model_path()
        default_model_valid = default_model and default_model.strip() and Path(default_model).exists()
        
        # If no default model is configured or doesn't exist, try to auto-discover a .onnx file
        if not default_model_valid:
            discovered_model = VoicePresets._find_onnx_model(self.library_presets_dir)
            if discovered_model and Path(discovered_model).exists():
                default_model = discovered_model
                default_model_valid = True
                # Save the discovered model as the default for future use
                try:
                    self.app_config.set_tts_model_path(discovered_model)
                except ValueError:
                    # Invalid model path - will be handled by validation
                    pass
        
        # If still no model, try to get from presets
        if not default_model_valid:
            preset_names = VoicePresets.get_preset_names(self.library_presets_dir)
            if preset_names:
                preset = VoicePresets.get_preset(preset_names[0], None, self.library_presets_dir)
                if preset.model_path and Path(preset.model_path).exists():
                    default_model = preset.model_path
                    default_model_valid = True
                    # Save as default
                    try:
                        self.app_config.set_tts_model_path(default_model)
                    except ValueError:
                        # Invalid model path - will be handled by validation
                        pass
        
        # NEW SOLUTION: If default model exists (or was auto-discovered), automatically ensure ALL characters have voice configs
        # and skip strict validation - let ScriptReader handle any edge cases
        if default_model_valid:
            preset_names = VoicePresets.get_preset_names(self.library_presets_dir)
            # Ensure every character has a valid voice config
            for i, character in enumerate(characters):
                # Always create/update config for this character with default model
                if preset_names:
                    preset_name = preset_names[i % len(preset_names)]
                    preset = VoicePresets.get_preset(preset_name, default_model, self.library_presets_dir)
                    self.voice_configs[character] = VoiceConfig(
                        model_path=default_model,  # Always use default model
                        speaker=preset.speaker or 0,
                        name=preset.name or f"Default - {character}",
                        noise_scale=preset.noise_scale,
                        length_scale=preset.length_scale,
                        noise_w=preset.noise_w,
                        sentence_silence_seconds=preset.sentence_silence_seconds
                    )
                else:
                    # No presets available, use default model
                    self.voice_configs[character] = VoiceConfig(
                        model_path=default_model,
                        speaker=0,
                        name=f"Default - {character}",
                        noise_scale=0.667,
                        length_scale=1.0,
                        noise_w=0.8,
                        sentence_silence_seconds=0.0
                    )
            
            # Update voice widgets to reflect the auto-assigned voices
            self._update_voice_widgets()
            
            # Skip validation - we've ensured all characters have configs with valid default model
            # Just proceed directly to reading
        else:
            # No default model - use existing auto-assign and validation logic
            if not self.voice_configs or len(self.voice_configs) < len(characters):
                self._auto_assign_voices()
            
            # Validate that all characters have valid voice configs
            missing_models = []
            for character in characters:
                if character not in self.voice_configs:
                    missing_models.append(character)
                else:
                    voice_config = self.voice_configs[character]
                    # Get the actual model path to use (preset's model or default)
                    model_path = voice_config.model_path
                    if not model_path or not model_path.strip():
                        model_path = default_model
                    
                    # Check if we have a valid model path that exists
                    if not model_path or not model_path.strip():
                        missing_models.append(character)
                    else:
                        model_path_obj = Path(model_path)
                        if not model_path_obj.exists():
                            missing_models.append(character)
            
            if missing_models:
                # Try one more time to find a model via auto-discovery
                discovered_model = VoicePresets._find_onnx_model(self.library_presets_dir)
                if discovered_model and Path(discovered_model).exists():
                    # Found a model! Auto-assign it to all missing characters
                    default_model = discovered_model
                    try:
                        self.app_config.set_tts_model_path(default_model)
                    except ValueError:
                        # Invalid model path - will be handled by validation
                        pass
                    # Re-run the auto-assignment logic
                    for i, character in enumerate(characters):
                        if character in missing_models:
                            preset_names = VoicePresets.get_preset_names(self.library_presets_dir)
                            if preset_names:
                                preset_name = preset_names[i % len(preset_names)]
                                preset = VoicePresets.get_preset(preset_name, default_model, self.library_presets_dir)
                                self.voice_configs[character] = VoiceConfig(
                                    model_path=default_model,
                                    speaker=preset.speaker or 0,
                                    name=preset.name or f"Default - {character}",
                                    noise_scale=preset.noise_scale,
                                    length_scale=preset.length_scale,
                                    noise_w=preset.noise_w,
                                    sentence_silence_seconds=preset.sentence_silence_seconds
                                )
                            else:
                                self.voice_configs[character] = VoiceConfig(
                                    model_path=default_model,
                                    speaker=0,
                                    name=f"Default - {character}",
                                    noise_scale=0.667,
                                    length_scale=1.0,
                                    noise_w=0.8,
                                    sentence_silence_seconds=0.0
                                )
                    # Update UI and proceed
                    self._update_voice_widgets()
                    # Continue to start reading
                else:
                    # No model found anywhere - offer file dialog
                    reply = QMessageBox.question(
                        self,
                        "No Voice Model Found",
                        "No voice model files (.onnx) were found automatically.\n\n"
                        "Would you like to browse for a voice model file now?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.Yes
                    )
                    
                    if reply == QMessageBox.StandardButton.Yes:
                        # Open file dialog to select a model
                        start_dir = str(self.library_presets_dir) if self.library_presets_dir and self.library_presets_dir.exists() else ""
                        path, _ = QFileDialog.getOpenFileName(
                            self,
                            "Select Piper Voice Model (.onnx file)",
                            start_dir,
                            "Piper Models (*.onnx *.onnx.gz);;All Files (*.*)",
                        )
                        if path and Path(path).exists():
                            # Use the selected model
                            default_model = path
                            try:
                                self.app_config.set_tts_model_path(default_model)
                            except ValueError as e:
                                QMessageBox.warning(self, "Invalid Model Path", str(e))
                                return
                            # Auto-assign to all characters
                            preset_names = VoicePresets.get_preset_names(self.library_presets_dir)
                            for i, character in enumerate(characters):
                                if character in missing_models:
                                    if preset_names:
                                        preset_name = preset_names[i % len(preset_names)]
                                        preset = VoicePresets.get_preset(preset_name, default_model, self.library_presets_dir)
                                        self.voice_configs[character] = VoiceConfig(
                                            model_path=default_model,
                                            speaker=preset.speaker or 0,
                                            name=preset.name or f"Default - {character}",
                                            noise_scale=preset.noise_scale,
                                            length_scale=preset.length_scale,
                                            noise_w=preset.noise_w,
                                            sentence_silence_seconds=preset.sentence_silence_seconds
                                        )
                                    else:
                                        self.voice_configs[character] = VoiceConfig(
                                            model_path=default_model,
                                            speaker=0,
                                            name=f"Default - {character}",
                                            noise_scale=0.667,
                                            length_scale=1.0,
                                            noise_w=0.8,
                                            sentence_silence_seconds=0.0
                                        )
                            # Update UI and proceed
                            self._update_voice_widgets()
                            # Continue to start reading
                        else:
                            # User cancelled or file doesn't exist
                            QMessageBox.warning(
                                self,
                                "No Model Selected",
                                "No voice model was selected. Please configure a default voice model in settings, "
                                "or select voice models for each character using the dropdown menus."
                            )
                            return
                    else:
                        # User chose not to browse
                        QMessageBox.warning(
                            self,
                            "Missing Voice Models",
                            f"The following characters need voice models selected:\n{', '.join(missing_models)}\n\n"
                            "Please configure a default voice model in settings, or select voice models for each character using the dropdown menus."
                        )
                        return
        
        # Start reading
        self._start_reading()
    
    def _start_reading(self, start_block: int = 0) -> None:
        """Start reading the script."""
        if not self.current_parse:
            return
        
        # Stop any existing reading
        if self.script_reader:
            # Disconnect playback state signal before stopping
            try:
                if self.script_reader.player:
                    self.script_reader.player.playbackStateChanged.disconnect(self._on_playback_state_changed)
            except Exception:
                pass
            self.script_reader.stop_reading()
            self.script_reader.deleteLater()
        
        # Resolve voice configs with default model before passing to ScriptReader
        default_model = self.app_config.tts_model_path()
        
        # Ensure default model is valid, try auto-discovery if needed
        if not default_model or not default_model.strip() or not Path(default_model).exists():
            discovered_model = VoicePresets._find_onnx_model(self.library_presets_dir)
            if discovered_model and Path(discovered_model).exists():
                default_model = discovered_model
                try:
                    self.app_config.set_tts_model_path(default_model)
                except ValueError:
                    # Invalid model path - will be handled by validation
                    pass
            else:
                # Try to get from presets
                preset_names = VoicePresets.get_preset_names(self.library_presets_dir)
                if preset_names:
                    preset = VoicePresets.get_preset(preset_names[0], None, self.library_presets_dir)
                    if preset.model_path and Path(preset.model_path).exists():
                        default_model = preset.model_path
                        try:
                            self.app_config.set_tts_model_path(default_model)
                        except ValueError:
                            # Invalid model path - will be handled by validation
                            pass
        
        resolved_voice_configs = {}
        for character, voice_config in self.voice_configs.items():
            # Create a new config with resolved model path
            model_path = voice_config.model_path
            if not model_path or not model_path.strip() or not Path(model_path).exists():
                model_path = default_model or ""
            
            # If still no valid model path, try auto-discovery one more time
            if not model_path or not model_path.strip() or not Path(model_path).exists():
                discovered_model = VoicePresets._find_onnx_model(self.library_presets_dir)
                if discovered_model and Path(discovered_model).exists():
                    model_path = discovered_model
                    try:
                        self.app_config.set_tts_model_path(model_path)
                    except ValueError:
                        # Invalid model path - will be handled by validation
                        pass
            
            resolved_voice_configs[character] = VoiceConfig(
                model_path=model_path,
                speaker=voice_config.speaker,
                name=voice_config.name,
                noise_scale=voice_config.noise_scale,
                length_scale=voice_config.length_scale,
                noise_w=voice_config.noise_w,
                sentence_silence_seconds=voice_config.sentence_silence_seconds
            )
        
        # Create new reader with prerender manager if available
        self.script_reader = ScriptReader(
            self.current_parse, 
            resolved_voice_configs, 
            self,
            self.txt_script,
            start_block,
            default_model_path=default_model,
            prerender_manager=self.prerender_manager if self.is_prerendered else None,
            project=self.current_project if self.is_prerendered else None,
            read_character_names=self.chk_read_character_names.isChecked()
        )
        self.script_reader.progress.connect(self._on_reading_progress)
        self.script_reader.word_highlight.connect(self._on_word_highlight)
        self.script_reader.finished.connect(self._on_reading_finished)
        self.script_reader.error.connect(self._on_reading_error)
        
        # Connect to playback state to apply speed when audio starts
        try:
            if self.script_reader.player:
                self.script_reader.player.playbackStateChanged.connect(self._on_playback_state_changed)
        except Exception:
            pass
        
        # Prepare and start
        if self.script_reader.prepare_reading():
            self.btn_read.setEnabled(False)
            self.btn_pause.setEnabled(True)
            self.btn_stop.setEnabled(True)
            self.lbl_status.setText("Reading script...")
            # Apply playback speed (will also be applied when playback starts)
            if self.script_reader.player:
                self.script_reader.player.setPlaybackRate(self.playback_speed)
            self.script_reader.start_reading()
        else:
            QMessageBox.warning(
                self,
                "Preparation Failed",
                "Failed to prepare script for reading."
            )
    
    def _on_pause_reading(self) -> None:
        """Pause or resume reading."""
        if not self.script_reader:
            return
        
        if self.script_reader.is_paused:
            self.script_reader.resume_reading()
            # Apply playback speed when resuming
            if self.script_reader.player:
                self.script_reader.player.setPlaybackRate(self.playback_speed)
            self.btn_pause.setText("⏸ Pause")
            self.lbl_status.setText("Reading...")
        else:
            self.script_reader.pause_reading()
            self.btn_pause.setText("▶ Resume")
            self.lbl_status.setText("Paused")
    
    def _on_stop_reading(self) -> None:
        """Stop reading."""
        if self.script_reader:
            # Disconnect playback state signal before stopping
            try:
                if self.script_reader.player:
                    self.script_reader.player.playbackStateChanged.disconnect(self._on_playback_state_changed)
            except Exception:
                pass
            self.script_reader.stop_reading()
            self.script_reader.deleteLater()
            self.script_reader = None
        
        # Change current word to light blue if it exists
        if self.current_highlighted_word:
            start_pos, end_pos = self.current_highlighted_word
            cursor = self.txt_script.textCursor()
            cursor.setPosition(start_pos)
            cursor.setPosition(end_pos, QTextCursor.MoveMode.KeepAnchor)
            fmt = QTextCharFormat()
            fmt.setForeground(QColor("#87CEEB"))  # Light blue for read words
            fmt.setFontFamily("Courier Prime")  # Preserve Courier Prime font
            fmt.setFontPointSize(12)  # Preserve font size
            cursor.mergeCharFormat(fmt)
            self.read_words.add((start_pos, end_pos))
        
        # Clear current highlighting reference
        self._clear_word_highlight()
        self._clear_hover_effect()
        # Keep read_words and word_original_colors - we want to keep the highlighting
        
        self.btn_read.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_stop.setEnabled(False)
        self.btn_pause.setText("⏸ Pause")
        
        if self.current_parse:
            self.lbl_status.setText("Reading stopped.")
        else:
            self.lbl_status.setText("No script loaded. Load a project to begin.")
    
    def _on_reading_progress(self, message: str) -> None:
        """Handle reading progress update."""
        self.lbl_status.setText(f"Reading: {message}")
    
    def _on_word_highlight(self, start_pos: int, end_pos: int) -> None:
        """Handle word highlighting - darker blue for current word, light blue for previous word."""
        # Clear hover if it's on this word
        if self.current_hovered_word == (start_pos, end_pos):
            self._clear_hover_effect()
        
        cursor = self.txt_script.textCursor()
        
        # Change previous word to light blue (read)
        if self.current_highlighted_word:
            prev_start, prev_end = self.current_highlighted_word
            # Only change to light blue if it's not already in read_words
            if (prev_start, prev_end) not in self.read_words:
                cursor.setPosition(prev_start)
                cursor.setPosition(prev_end, QTextCursor.MoveMode.KeepAnchor)
                fmt = QTextCharFormat()
                fmt.setForeground(QColor("#87CEEB"))  # Light blue (SkyBlue) for read words
                fmt.setFontFamily("Courier Prime")  # Preserve Courier Prime font
                fmt.setFontPointSize(12)  # Preserve font size
                cursor.mergeCharFormat(fmt)
                self.read_words.add((prev_start, prev_end))
        
        # Store original color of current word if not already stored
        cursor.setPosition(start_pos)
        current_format = cursor.charFormat()
        current_color = current_format.foreground().color()
        
        # Only store original color if it's not a blue variant
        if current_color != QColor("#0000FF") and current_color != QColor("#87CEEB"):
            self.word_original_colors[(start_pos, end_pos)] = current_color
        
        # Apply darker blue to current word (being read)
        cursor.setPosition(start_pos)
        cursor.setPosition(end_pos, QTextCursor.MoveMode.KeepAnchor)
        
        fmt = QTextCharFormat()
        fmt.setForeground(QColor("#0000FF"))  # Darker blue for current word
        fmt.setFontFamily("Courier Prime")  # Preserve Courier Prime font
        fmt.setFontPointSize(12)  # Preserve font size
        cursor.mergeCharFormat(fmt)
        
        # Check if we need to scroll before setting cursor
        needs_scroll = self._should_scroll_to_position(start_pos)
        
        # Set cursor
        cursor.setPosition(start_pos)
        self.txt_script.setTextCursor(cursor)
        
        # Only scroll if word is near viewport edges (less aggressive scrolling)
        if needs_scroll:
            self.txt_script.ensureCursorVisible()
        
        self.current_highlighted_word = (start_pos, end_pos)
    
    def _should_scroll_to_position(self, pos: int) -> bool:
        """Check if we should scroll to the given position."""
        # Save current cursor
        old_cursor = self.txt_script.textCursor()
        
        # Check position
        temp_cursor = self.txt_script.textCursor()
        temp_cursor.setPosition(pos)
        self.txt_script.setTextCursor(temp_cursor)
        rect = self.txt_script.cursorRect()
            
        # Get viewport dimensions
        viewport = self.txt_script.viewport().rect()
        margin = 150  # Scroll margin in pixels - larger margin means less frequent scrolling
        
        # Check if word is near top or bottom edge
        word_top = rect.top()
        word_bottom = rect.bottom()
        viewport_top = viewport.top()
        viewport_bottom = viewport.bottom()
        
        # Restore old cursor
        self.txt_script.setTextCursor(old_cursor)
        
        # Only scroll if word is outside the viewport or very close to edges
        return (word_top < viewport_top + margin or 
                word_bottom > viewport_bottom - margin or
                word_top < viewport_top or 
                word_bottom > viewport_bottom)
    
    def _clear_word_highlight(self) -> None:
        """Clear current word highlighting reference."""
        # Just clear the current highlighted word reference
        # Colors are preserved - read words stay light blue
        self.current_highlighted_word = None
    
    def _on_reading_finished(self) -> None:
        """Handle reading finished."""
        # Change current word to light blue if it exists
        if self.current_highlighted_word:
            start_pos, end_pos = self.current_highlighted_word
            cursor = self.txt_script.textCursor()
            cursor.setPosition(start_pos)
            cursor.setPosition(end_pos, QTextCursor.MoveMode.KeepAnchor)
            fmt = QTextCharFormat()
            fmt.setForeground(QColor("#87CEEB"))  # Light blue for read words
            fmt.setFontFamily("Courier Prime")  # Preserve Courier Prime font
            fmt.setFontPointSize(12)  # Preserve font size
            cursor.mergeCharFormat(fmt)
            self.read_words.add((start_pos, end_pos))
        
        # Clear current highlighting reference
        self._clear_word_highlight()
        self._clear_hover_effect()
        # Keep read_words and word_original_colors - we want to keep the highlighting
        
        if self.script_reader:
            self.script_reader.deleteLater()
            self.script_reader = None
        
        self.btn_read.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_stop.setEnabled(False)
        self.btn_pause.setText("⏸ Pause")
        
        if self.current_parse:
            self.lbl_status.setText("Reading complete. Click 'Read' to read again.")
        else:
            self.lbl_status.setText("No script loaded. Load a project to begin.")
    
    def _check_prerender_status(self) -> None:
        """Check if prerendered audio is available and valid."""
        if not self.prerender_manager or not self.current_project or not self.current_parse:
            self.is_prerendered = False
            return
        
        self.is_prerendered = self.prerender_manager.is_prerender_valid(
            self.current_project,
            self.current_parse,
            self.voice_configs
        )
    
    def _on_prerender_clicked(self) -> None:
        """Handle prerender button click."""
        if not self.current_parse or not self.current_project or not self.prerender_manager:
            QMessageBox.warning(
                self,
                "Cannot Prerender",
                "No script or project loaded."
            )
            return
        
        # Check if voices are configured
        if not self.voice_configs:
            QMessageBox.warning(
                self,
                "No Voices Configured",
                "Please configure voices for all characters before prerendering."
            )
            return
        
        # Get default model
        default_model = self.app_config.tts_model_path()
        if not default_model or not default_model.strip() or not Path(default_model).exists():
            discovered_model = VoicePresets._find_onnx_model(self.library_presets_dir)
            if discovered_model and Path(discovered_model).exists():
                default_model = discovered_model
            else:
                QMessageBox.warning(
                    self,
                    "No Voice Model",
                    "No voice model found. Please configure a default voice model first."
                )
                return
        
        # Create progress dialog
        progress = QProgressDialog("Prerendering audio...", "Cancel", 0, 100, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        
        def progress_callback(block_index: int, total_blocks: int, message: str) -> bool:
            """Update progress dialog."""
            if progress.wasCanceled():
                return False
            progress.setMaximum(total_blocks)
            progress.setValue(block_index)
            progress.setLabelText(message)
            QApplication.processEvents()  # Allow UI to update
            return True
        
        try:
            # Prerender all blocks
            success = self.prerender_manager.prerender_all_blocks(
                self.current_project,
                self.current_parse,
                self.voice_configs,
                default_model,
                progress_callback
            )
            
            if success:
                self.is_prerendered = True
                # Update visual differentiation
                if self.current_parse:
                    self.set_script(self.current_parse)
                QMessageBox.information(
                    self,
                    "Prerendering Complete",
                    "All audio has been prerendered successfully!\n\n"
                    "Reading will now be smooth and fast."
                )
            else:
                QMessageBox.warning(
                    self,
                    "Prerendering Failed",
                    "Failed to prerender audio. Please check your voice settings."
                )
        except Exception as e:
            QMessageBox.warning(
                self,
                "Prerendering Error",
                f"An error occurred while prerendering:\n\n{e}"
            )
        finally:
            progress.close()
    
    def _on_reading_error(self, error: str) -> None:
        """Handle reading error."""
        # Change current word to light blue if it exists
        if self.current_highlighted_word:
            start_pos, end_pos = self.current_highlighted_word
            cursor = self.txt_script.textCursor()
            cursor.setPosition(start_pos)
            cursor.setPosition(end_pos, QTextCursor.MoveMode.KeepAnchor)
            fmt = QTextCharFormat()
            fmt.setForeground(QColor("#87CEEB"))  # Light blue for read words
            fmt.setFontFamily("Courier Prime")  # Preserve Courier Prime font
            fmt.setFontPointSize(12)  # Preserve font size
            cursor.mergeCharFormat(fmt)
            self.read_words.add((start_pos, end_pos))
        
        # Clear current highlighting reference
        self._clear_word_highlight()
        self._clear_hover_effect()
        # Keep read_words and word_original_colors - we want to keep the highlighting
        
        # Format error message for better readability
        formatted_error = error.replace('\n\n', '\n').strip()
        
        QMessageBox.warning(
            self,
            "Reading Error",
            f"An error occurred while reading:\n\n{formatted_error}"
        )
        
        if self.script_reader:
            self.script_reader.deleteLater()
            self.script_reader = None
        
        self.btn_read.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_stop.setEnabled(False)
        self.btn_pause.setText("⏸ Pause")
        
        if self.current_parse:
            self.lbl_status.setText(f"Error: {error}")
        else:
            self.lbl_status.setText("No script loaded. Load a project to begin.")
