# app/tabs/rehearse_tab.py
"""
Rehearse tab - script view with character highlighting and rehearsal tools.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional, List, Dict
from functools import partial
import re

from PyQt6.QtCore import Qt, pyqtSignal, QEvent, QTimer, QSize
from PyQt6.QtGui import QTextCharFormat, QColor, QTextCursor, QTextBlockFormat, QIcon, QPixmap, QPainter
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QComboBox,
    QPushButton, QLabel, QSplitter, QScrollArea, QFrame, QDialog, QCheckBox,
    QRadioButton, QButtonGroup, QMainWindow, QSlider, QGroupBox, QMessageBox
)

from core.nlp_processor import ScriptParse, blocks_for_character, list_characters
from app.config import AppConfig
from app.tabs.character_color_dialog import CharacterColorDialog, NO_HIGHLIGHT
from app.tabs.script_reader import ScriptReader
from app.tabs.voice_selection_dialog import VoiceConfig, VoicePresets


ICONS_DIR = Path(__file__).resolve().parents[2] / "UI" / "Icons"
ICON_COLOR_WHITE = QColor(255, 255, 255)
MAXIMIZE_ICON_FILENAME = "maximize-svgrepo-com.svg"
EXIT_FULLSCREEN_ICON_FILENAME = "compress-wide-svgrepo-com.svg"


def _load_svg_icon(filename: str, size: int) -> QIcon:
    path = ICONS_DIR / filename
    if not path.exists():
        return QIcon()
    
    renderer = QSvgRenderer(str(path))
    if not renderer.isValid():
        return QIcon(str(path))
    
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter)
    painter.end()
    
    tinted = QPixmap(pixmap.size())
    tinted.fill(Qt.GlobalColor.transparent)
    painter = QPainter(tinted)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.drawPixmap(0, 0, pixmap)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(tinted.rect(), ICON_COLOR_WHITE)
    painter.end()
    
    return QIcon(tinted)


class RehearseTab(QWidget):
    """Rehearse tab for script rehearsal with character highlighting."""
    
    character_changed = pyqtSignal(str)  # emits character name
    
    def __init__(self, parent: Optional[QWidget] = None, read_tab=None):
        super().__init__(parent)
        self.current_parse: Optional[ScriptParse] = None
        self.current_character: Optional[str] = None
        self.line_offsets: List[int] = []
        self.app_config = AppConfig()
        self.character_color_buttons: Dict[str, QPushButton] = {}
        self.character_visibility_checkboxes: Dict[str, QCheckBox] = {}
        self.character_hieroglyphs_checkboxes: Dict[str, QCheckBox] = {}
        self.character_rehearse_radios: Dict[str, QRadioButton] = {}
        self.character_voice_combos: Dict[str, QComboBox] = {}
        self.character_voice_labels: Dict[str, QLabel] = {}
        self.rehearse_voice_configs: Dict[str, VoiceConfig] = {}
        self.rehearse_button_group: Optional[QButtonGroup] = None
        self.original_text: str = ""  # Store original text for hieroglyph transformation
        self.fullscreen_window: Optional[RehearseFullscreenWindow] = None
        self.read_tab = read_tab  # Reference to ReadTab for TTS controls
        self.script_reader: Optional[ScriptReader] = None
        self.current_highlighted_word: Optional[tuple[int, int]] = None
        self.current_highlighted_line: Optional[int] = None  # Track which line is currently highlighted in gray
        self.current_line_highlight_range: Optional[tuple[int, int]] = None  # Store the highlight range for the current line
        self.waiting_at_character_line: bool = False  # Track if we're waiting at character's line
        self.character_line_highlight_range: Optional[tuple[int, int]] = None  # Store highlight range
        self.should_skip_current_block: bool = False  # Flag to skip current block (character's line)
        self.playback_speed: float = 1.0  # Playback speed multiplier
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)  # Enable keyboard focus for spacebar
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Build the UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Top toolbar with alignment buttons and fullscreen button
        top_toolbar = QHBoxLayout()
        
        # Alignment section label
        alignment_label = QLabel("Alignment:")
        top_toolbar.addWidget(alignment_label)
        
        # Load saved alignment options
        alignment_options = self.app_config.rehearse_alignment_options()
        
        # Character names alignment button
        self.btn_align_character_names = QPushButton(f"Character Names: {alignment_options['character_names'].title()}")
        self.btn_align_character_names.setToolTip("Click to cycle alignment: Left → Center → Right")
        self.btn_align_character_names.clicked.connect(partial(self._on_alignment_clicked, "character_names"))
        top_toolbar.addWidget(self.btn_align_character_names)
        
        # Dialogue alignment button
        self.btn_align_dialogue = QPushButton(f"Dialogue: {alignment_options['dialogue'].title()}")
        self.btn_align_dialogue.setToolTip("Click to cycle alignment: Left → Center → Right")
        self.btn_align_dialogue.clicked.connect(partial(self._on_alignment_clicked, "dialogue"))
        top_toolbar.addWidget(self.btn_align_dialogue)
        
        # Narrator alignment button
        self.btn_align_narrator = QPushButton(f"Narrator: {alignment_options['narrator'].title()}")
        self.btn_align_narrator.setToolTip("Click to cycle alignment: Left → Center → Right")
        self.btn_align_narrator.clicked.connect(partial(self._on_alignment_clicked, "narrator"))
        top_toolbar.addWidget(self.btn_align_narrator)
        
        # Everything else alignment button
        self.btn_align_everything_else = QPushButton(f"Everything Else: {alignment_options['everything_else'].title()}")
        self.btn_align_everything_else.setToolTip("Click to cycle alignment: Left → Center → Right")
        self.btn_align_everything_else.clicked.connect(partial(self._on_alignment_clicked, "everything_else"))
        top_toolbar.addWidget(self.btn_align_everything_else)
        
        top_toolbar.addStretch()
        
        self.btn_fullscreen = QPushButton("Fullscreen")
        self.btn_fullscreen.setToolTip("Enter fullscreen rehearsal mode")
        fullscreen_icon = _load_svg_icon(MAXIMIZE_ICON_FILENAME, 18)
        if not fullscreen_icon.isNull():
            self.btn_fullscreen.setIcon(fullscreen_icon)
            self.btn_fullscreen.setIconSize(QSize(18, 18))
        self.btn_fullscreen.setAccessibleName("Enter Fullscreen")
        self.btn_fullscreen.clicked.connect(self._on_fullscreen_clicked)
        top_toolbar.addWidget(self.btn_fullscreen)
        
        layout.addLayout(top_toolbar)
        
        # Rehearse TTS Controls section (above Highlight Options)
        rehearse_controls_label = QLabel("Rehearse Controls:")
        rehearse_controls_label.setStyleSheet("font-weight: bold; font-size: 12pt;")
        layout.addWidget(rehearse_controls_label)
        
        # TTS Controls Group Box
        tts_group = QGroupBox("TTS Controls")
        tts_layout = QVBoxLayout()
        
        # Top toolbar with quality, read character names, and control buttons
        tts_toolbar = QHBoxLayout()
        
        # Quality dropdown (references read tab)
        quality_label = QLabel("Quality:")
        tts_toolbar.addWidget(quality_label)
        
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["Low", "Medium", "High"])
        self.quality_combo.setCurrentText("Medium")
        self.quality_combo.setMinimumWidth(120)
        if self.read_tab:
            # Sync with read tab's quality
            self.quality_combo.setCurrentText(self.read_tab.quality_combo.currentText())
            self.quality_combo.currentTextChanged.connect(self._on_quality_changed)
        tts_toolbar.addWidget(self.quality_combo)
        
        # Read character names checkbox (references read tab)
        self.chk_read_character_names = QCheckBox("Read Character Names")
        self.chk_read_character_names.setToolTip("When enabled, character names will be read aloud before their dialogue")
        if self.read_tab:
            self.chk_read_character_names.setChecked(self.read_tab.chk_read_character_names.isChecked())
            # Sync bidirectionally
            self.chk_read_character_names.stateChanged.connect(self._on_read_character_names_changed)
            self.read_tab.chk_read_character_names.stateChanged.connect(
                lambda state: self.chk_read_character_names.setChecked(state == Qt.CheckState.Checked.value)
            )
        else:
            self.chk_read_character_names.setChecked(True)
        tts_toolbar.addWidget(self.chk_read_character_names)
        
        tts_toolbar.addStretch()
        
        # Control buttons
        self.btn_rehearse = QPushButton("▶ Rehearse")
        self.btn_rehearse.clicked.connect(self._on_rehearse_clicked)
        tts_toolbar.addWidget(self.btn_rehearse)
        
        self.btn_next_line = QPushButton("Next Line")
        self.btn_next_line.clicked.connect(self._on_next_line_clicked)
        self.btn_next_line.setEnabled(False)
        tts_toolbar.addWidget(self.btn_next_line)
        
        self.btn_pause = QPushButton("⏸ Pause")
        self.btn_pause.clicked.connect(self._on_pause_rehearsing)
        self.btn_pause.setEnabled(False)
        tts_toolbar.addWidget(self.btn_pause)
        
        self.btn_stop = QPushButton("⏹ Stop")
        self.btn_stop.clicked.connect(self._on_stop_rehearsing)
        self.btn_stop.setEnabled(False)
        tts_toolbar.addWidget(self.btn_stop)
        
        tts_layout.addLayout(tts_toolbar)
        
        # Speed slider row
        speed_row = QHBoxLayout()
        speed_label = QLabel("Speed:")
        speed_row.addWidget(speed_label)
        
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setMinimum(50)  # 0.5x speed
        self.speed_slider.setMaximum(200)  # 2.0x speed
        self.speed_slider.setValue(100)  # 1.0x speed (normal)
        self.speed_slider.setMinimumWidth(150)
        self.speed_slider.setToolTip("Adjust playback speed (0.5x to 2.0x)")
        self.speed_slider.valueChanged.connect(self._on_speed_changed)
        speed_row.addWidget(self.speed_slider)
        
        self.speed_label = QLabel("1.00x")
        self.speed_label.setMinimumWidth(50)
        self.speed_label.setMaximumWidth(50)
        speed_row.addWidget(self.speed_label)
        
        speed_row.addStretch()
        tts_layout.addLayout(speed_row)
        
        # Note about using read tab's voice controls
        note_label = QLabel("Note: Voice selection and pitch controls are in the 'Read' tab.")
        note_label.setStyleSheet("color: #666; font-style: italic;")
        tts_layout.addWidget(note_label)
        
        tts_group.setLayout(tts_layout)
        layout.addWidget(tts_group)
        
        # Character colors section
        colors_label = QLabel("Highlight Options:")
        colors_label.setStyleSheet("font-weight: bold; font-size: 12pt;")
        layout.addWidget(colors_label)
        
        # Scrollable area for character color selectors
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setMaximumHeight(150)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.colors_widget = QWidget()
        self.colors_layout = QVBoxLayout(self.colors_widget)
        self.colors_layout.setContentsMargins(5, 5, 5, 5)
        self.colors_layout.setSpacing(5)
        
        # Enable highlighting toggle (inside scrollable area)
        enable_highlighting_row = QHBoxLayout()
        enable_highlighting_row.setSpacing(10)
        enable_highlighting_label = QLabel("Enable Highlighting")
        enable_highlighting_row.addWidget(enable_highlighting_label)
        
        # Load saved highlighting options
        highlighting_options = self.app_config.rehearse_highlighting_options()
        
        self.btn_enable_highlighting = QCheckBox()
        self.btn_enable_highlighting.setChecked(highlighting_options.get("enable_highlighting", True))
        self.btn_enable_highlighting.setToolTip("Toggle character highlighting on/off")
        self.btn_enable_highlighting.stateChanged.connect(self._on_enable_highlighting_toggled)
        enable_highlighting_row.addWidget(self.btn_enable_highlighting)
        enable_highlighting_row.addStretch()
        self.colors_layout.addLayout(enable_highlighting_row)
        
        # Highlight character names checkbox (inside scrollable area)
        highlight_names_row = QHBoxLayout()
        highlight_names_row.setSpacing(10)
        highlight_names_label = QLabel("Highlight Character Names")
        highlight_names_row.addWidget(highlight_names_label)
        
        self.btn_highlight_names = QCheckBox()
        self.btn_highlight_names.setChecked(highlighting_options.get("highlight_character_names", False))
        self.btn_highlight_names.setToolTip("Highlight character names with the same color as their dialogue")
        self.btn_highlight_names.stateChanged.connect(self._on_highlight_names_toggled)
        highlight_names_row.addWidget(self.btn_highlight_names)
        highlight_names_row.addStretch()
        self.colors_layout.addLayout(highlight_names_row)
        
        # Highlight parentheticals checkbox (inside scrollable area)
        highlight_parentheticals_row = QHBoxLayout()
        highlight_parentheticals_row.setSpacing(10)
        highlight_parentheticals_label = QLabel("Highlight Parentheticals")
        highlight_parentheticals_row.addWidget(highlight_parentheticals_label)
        
        self.btn_highlight_parentheticals = QCheckBox()
        self.btn_highlight_parentheticals.setChecked(highlighting_options.get("highlight_parentheticals", False))
        self.btn_highlight_parentheticals.setToolTip("Remove highlighting from text in brackets/parentheses")
        self.btn_highlight_parentheticals.stateChanged.connect(self._on_highlight_parentheticals_toggled)
        highlight_parentheticals_row.addWidget(self.btn_highlight_parentheticals)
        highlight_parentheticals_row.addStretch()
        self.colors_layout.addLayout(highlight_parentheticals_row)
        
        # Smoosh hieroglyphs checkbox (inside scrollable area)
        smoosh_hieroglyphs_row = QHBoxLayout()
        smoosh_hieroglyphs_row.setSpacing(10)
        smoosh_hieroglyphs_label = QLabel("smoosh hyrohlyphs")
        smoosh_hieroglyphs_row.addWidget(smoosh_hieroglyphs_label)
        
        self.btn_smoosh_hieroglyphs = QCheckBox()
        self.btn_smoosh_hieroglyphs.setChecked(highlighting_options.get("smoosh_hieroglyphs", False))
        self.btn_smoosh_hieroglyphs.setToolTip("Remove letter spacing in hieroglyphs mode - place characters and punctuation one after another")
        self.btn_smoosh_hieroglyphs.stateChanged.connect(self._on_smoosh_hieroglyphs_toggled)
        smoosh_hieroglyphs_row.addWidget(self.btn_smoosh_hieroglyphs)
        smoosh_hieroglyphs_row.addStretch()
        self.colors_layout.addLayout(smoosh_hieroglyphs_row)
        
        scroll_area.setWidget(self.colors_widget)
        layout.addWidget(scroll_area)
        
        # Script text area - formatted like read tab
        self.txt_script = QTextEdit()
        self.txt_script.setReadOnly(True)
        self.txt_script.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)  # Enable word wrapping
        self.txt_script.setFontFamily("Courier Prime")
        self.txt_script.setFontPointSize(12)
        self.txt_script.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)  # Disable horizontal scroll
        # Set white background and black text
        self.txt_script.setStyleSheet("QTextEdit { background-color: white; color: black; }")
        # Install event filter for spacebar handling
        self.txt_script.installEventFilter(self)
        layout.addWidget(self.txt_script, stretch=1)
    
    def set_script(self, script_parse: Optional[ScriptParse], script_text: str = "") -> None:
        """Set the script content."""
        self.current_parse = script_parse
        
        if script_parse:
            lines = script_parse.lines
            # Get characters and create color selectors
            characters = list_characters(script_parse, sort_by_freq=True)
            self._update_character_color_selectors(characters)
            
            # Display script text with formatting (same as read tab)
            self.line_offsets = []
            
            # Build sets of line types
            character_lines = set()
            dialogue_lines = set()
            narrator_lines = set()
            for block in script_parse.blocks:
                if block.speaker == "NARRATOR":
                    # Narrator dialogue lines
                    for line_idx in range(block.start_line, min(block.end_line + 1, len(lines))):
                        narrator_lines.add(line_idx)
                else:
                    # For non-narrator blocks, character name is on the line before start_line
                    if block.start_line > 0:
                        char_name_line = block.start_line - 1
                        if char_name_line < len(lines):
                            character_lines.add(char_name_line)
                    # Dialogue lines are from start_line to end_line
                    for line_idx in range(block.start_line, min(block.end_line + 1, len(lines))):
                        dialogue_lines.add(line_idx)
            
            # Store original text
            self.original_text = "\n".join(lines)
            
            # Get alignment options
            alignment_options = self.app_config.rehearse_alignment_options()
            
            # Set text with formatting
            self.txt_script.clear()
            cursor = self.txt_script.textCursor()
            
            for i, line in enumerate(lines):
                self.line_offsets.append(cursor.position())
                
                # Set alignment based on line type
                block_format = QTextBlockFormat()
                if i in character_lines:
                    alignment_flag = self._get_alignment_flag(alignment_options["character_names"])
                elif i in dialogue_lines:
                    alignment_flag = self._get_alignment_flag(alignment_options["dialogue"])
                elif i in narrator_lines:
                    alignment_flag = self._get_alignment_flag(alignment_options["narrator"])
                else:
                    alignment_flag = self._get_alignment_flag(alignment_options["everything_else"])
                
                block_format.setAlignment(alignment_flag)
                cursor.setBlockFormat(block_format)
                cursor.insertText(line)
                if i < len(lines) - 1:  # Don't add newline after last line
                    cursor.insertText("\n")
            
            # Apply all character highlights
            self._apply_all_highlights()
            
            # Update fullscreen window if it exists
            if self.fullscreen_window and self.fullscreen_window.isVisible():
                self.fullscreen_window._update_script_content()
        else:
            lines = script_text.splitlines() if script_text else []
            self._clear_character_color_selectors()
            
            # Build line offsets and set text (plain text mode)
            self.line_offsets = []
            buf = []
            offset = 0
            for line in lines:
                self.line_offsets.append(offset)
                buf.append(line)
                offset += len(line) + 1  # +1 for newline
            
            text = "\n".join(buf)
            self.txt_script.clear()
            self.txt_script.setPlainText(text)
    
    def set_character(self, character: str) -> None:
        """Set the selected character (for compatibility)."""
        self.current_character = character
        # Update the radio button selection
        if character:
            char_upper = character.upper().strip()
            if char_upper in self.character_rehearse_radios:
                self.character_rehearse_radios[char_upper].setChecked(True)
            # Highlighting is now done via color selectors, but we can still emit the signal
            self.character_changed.emit(character)
    
    def _on_rehearse_character_toggled(self, character: str, checked: bool) -> None:
        """Handle rehearse character radio button toggle."""
        if checked:
            # Hide previous character's "your voice" label and show their dropdown
            if self.current_character:
                prev_char_upper = self.current_character.upper().strip()
                if prev_char_upper in self.character_voice_labels and prev_char_upper in self.character_voice_combos:
                    self.character_voice_labels[prev_char_upper].hide()
                    self.character_voice_combos[prev_char_upper].show()
            
            self.current_character = character
            char_upper = character.upper().strip()
            
            # Show "your voice" label and hide dropdown for selected character
            if char_upper in self.character_voice_labels and char_upper in self.character_voice_combos:
                self.character_voice_combos[char_upper].hide()
                self.character_voice_labels[char_upper].show()
            
            self.character_changed.emit(character)
        else:
            # When unchecked, restore dropdown and hide label
            char_upper = character.upper().strip()
            if char_upper in self.character_voice_labels and char_upper in self.character_voice_combos:
                self.character_voice_labels[char_upper].hide()
                self.character_voice_combos[char_upper].show()
    
    def _update_character_color_selectors(self, characters: List[str]) -> None:
        """Update the character color selector UI."""
        # Clear existing selectors
        self._clear_character_color_selectors()
        
        # Create button group for radio buttons (only one can be selected)
        self.rehearse_button_group = QButtonGroup(self)
        
        # Create a selector for each character
        for char in characters:
            char_upper = char.upper().strip()
            row = QHBoxLayout()
            row.setSpacing(10)
            
            # Rehearse toggle (radio button) - leftmost
            rehearse_radio = QRadioButton()
            rehearse_radio.setToolTip("Select this character to rehearse as")
            rehearse_radio.toggled.connect(partial(self._on_rehearse_character_toggled, char))
            
            self.character_rehearse_radios[char_upper] = rehearse_radio
            self.rehearse_button_group.addButton(rehearse_radio)
            row.addWidget(rehearse_radio)
            
            # Character name label
            label = QLabel(char)
            label.setMinimumWidth(150)
            row.addWidget(label)
            
            # Color button
            btn = QPushButton()
            btn.setFixedSize(100, 30)
            btn.setToolTip("Click to change color")
            
            # Get current color from config
            current_color = self.app_config.get_character_color(char)
            self._update_color_button(btn, current_color)
            
            # Connect button click - use partial to avoid closure issues
            btn.clicked.connect(partial(self._on_color_button_clicked, char))
            
            self.character_color_buttons[char_upper] = btn
            row.addWidget(btn)
            
            # Visibility toggle
            visibility_label = QLabel("Visibility")
            row.addWidget(visibility_label)
            
            visibility_checkbox = QCheckBox()
            visibility_checkbox.setChecked(True)  # Default to visible
            visibility_checkbox.setToolTip("Toggle visibility of this character's lines")
            visibility_checkbox.stateChanged.connect(partial(self._on_visibility_changed, char))
            
            self.character_visibility_checkboxes[char_upper] = visibility_checkbox
            row.addWidget(visibility_checkbox)
            
            # Hieroglyphs toggle
            hieroglyphs_label = QLabel("Hieroglyphs")
            row.addWidget(hieroglyphs_label)
            
            hieroglyphs_checkbox = QCheckBox()
            hieroglyphs_checkbox.setChecked(False)  # Default to off
            hieroglyphs_checkbox.setToolTip("Show only first letter of each word and punctuation")
            hieroglyphs_checkbox.stateChanged.connect(partial(self._on_hieroglyphs_changed, char))
            
            self.character_hieroglyphs_checkboxes[char_upper] = hieroglyphs_checkbox
            row.addWidget(hieroglyphs_checkbox)
            
            # Voice selection dropdown
            voice_combo = QComboBox()
            voice_combo.setMinimumWidth(150)
            voice_combo.addItem("None")
            
            # Get available voice presets
            library_presets_dir = self.read_tab.library_presets_dir if self.read_tab else None
            preset_names = VoicePresets.get_preset_names(library_presets_dir) if library_presets_dir else []
            
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
            
            # Add one entry per voice group (prefer medium quality, or first available)
            for voice_key, voice_display in [("libritts", "LibriTTS US"), ("lessac", "Lessac"), ("amy", "Amy")]:
                if voice_groups[voice_key]:
                    # Try to find preset with medium quality
                    matching_preset = None
                    for preset_name in voice_groups[voice_key]:
                        if "medium" in preset_name.lower():
                            matching_preset = preset_name
                            break
                    
                    # If not found, use first available
                    if not matching_preset:
                        matching_preset = voice_groups[voice_key][0]
                    
                    # Add display name with preset name as data
                    voice_combo.addItem(voice_display, matching_preset)
            
            voice_combo.addItem("Custom...")
            
            # Set current selection based on existing voice config
            voice_config = None
            if char in self.rehearse_voice_configs:
                voice_config = self.rehearse_voice_configs[char]
            elif self.read_tab and char in self.read_tab.voice_configs:
                voice_config = self.read_tab.voice_configs[char]
            
            if voice_config:
                # Extract voice name from config
                voice_name = None
                default_model = self.read_tab.app_config.tts_model_path() if self.read_tab else None
                for preset_name in preset_names:
                    try:
                        preset = VoicePresets.get_preset(preset_name, default_model, library_presets_dir)
                        if (preset.model_path == voice_config.model_path and 
                            preset.speaker == voice_config.speaker):
                            preset_name_lower = preset_name.lower()
                            if "libritts" in preset_name_lower:
                                voice_name = "LibriTTS US"
                            elif "lessac" in preset_name_lower:
                                voice_name = "Lessac"
                            elif "amy" in preset_name_lower:
                                voice_name = "Amy"
                            break
                    except Exception:
                        continue
                
                if voice_name:
                    for i in range(voice_combo.count()):
                        if voice_combo.itemText(i) == voice_name:
                            voice_combo.setCurrentIndex(i)
                            break
                elif voice_config.model_path and Path(voice_config.model_path).exists() and voice_config.model_path != (default_model or ""):
                    voice_combo.setCurrentText("Custom...")
            
            # Connect voice change handler
            voice_combo.currentTextChanged.connect(partial(self._on_rehearse_voice_changed, char))
            
            self.character_voice_combos[char_upper] = voice_combo
            row.addWidget(voice_combo)
            
            # "Your voice" label (initially hidden)
            your_voice_label = QLabel("your voice")
            your_voice_label.setMinimumWidth(150)
            your_voice_label.setStyleSheet("font-style: italic; color: #666;")
            your_voice_label.hide()
            self.character_voice_labels[char_upper] = your_voice_label
            row.addWidget(your_voice_label)
            
            # If this character is currently selected, show "your voice" and hide dropdown
            if self.current_character and self.current_character.upper().strip() == char_upper:
                voice_combo.hide()
                your_voice_label.show()
            
            row.addStretch()
            
            self.colors_layout.addLayout(row)
        
        # Add stretch at the end
        self.colors_layout.addStretch()
    
    def _clear_character_color_selectors(self) -> None:
        """Clear all character color selectors."""
        # Remove widgets from layout, but preserve the first four items (checkboxes)
        # Count how many items to preserve (the four checkbox rows: enable highlighting, highlight names, highlight parentheticals, smoosh hieroglyphs)
        items_to_preserve = 4
        total_items = self.colors_layout.count()
        
        # Remove items from the end, working backwards, skipping the preserved items
        for i in range(total_items - 1, items_to_preserve - 1, -1):
            item = self.colors_layout.takeAt(i)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())
        
        self.character_color_buttons.clear()
        self.character_visibility_checkboxes.clear()
        self.character_hieroglyphs_checkboxes.clear()
        self.character_rehearse_radios.clear()
        self.character_voice_combos.clear()
        self.character_voice_labels.clear()
        if self.rehearse_button_group:
            # Remove all buttons from group before clearing
            for button in self.rehearse_button_group.buttons():
                self.rehearse_button_group.removeButton(button)
            self.rehearse_button_group = None
    
    def _clear_layout(self, layout) -> None:
        """Recursively clear a layout."""
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())
    
    def _update_color_button(self, btn: QPushButton, color: Optional[str]) -> None:
        """Update a color button's appearance."""
        if color is None or color == NO_HIGHLIGHT:
            btn.setText("")
            btn.setStyleSheet("""
                QPushButton {
                    background-color: white;
                    border: 2px solid #ccc;
                    border-radius: 3px;
                }
                QPushButton:hover {
                    border-color: #999;
                    background-color: #f5f5f5;
                }
            """)
            btn.setToolTip("No Highlight - Click to change color")
        else:
            btn.setText("")
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color};
                    border: 2px solid #999;
                    border-radius: 3px;
                }}
                QPushButton:hover {{
                    border-color: #333;
                    border-width: 3px;
                }}
            """)
            btn.setToolTip(f"Color: {color} - Click to change")
    
    def _on_rehearse_voice_changed(self, character: str, voice_text: str) -> None:
        """Handle voice selection change for a character."""
        if not self.read_tab:
            return
        
        char_upper = character.upper().strip()
        voice_combo = self.character_voice_combos.get(char_upper)
        if not voice_combo:
            return
        
        library_presets_dir = self.read_tab.library_presets_dir
        default_model = self.read_tab.app_config.tts_model_path()
        
        if voice_text == "None":
            # Remove voice config
            if character in self.rehearse_voice_configs:
                del self.rehearse_voice_configs[character]
        elif voice_text == "Custom...":
            # Open file dialog for custom model
            from PyQt6.QtWidgets import QFileDialog
            start_dir = str(library_presets_dir) if library_presets_dir and library_presets_dir.exists() else ""
            path, _ = QFileDialog.getOpenFileName(
                self,
                f"Select Voice Model for {character}",
                start_dir,
                "Piper Models (*.onnx *.onnx.gz);;All Files (*.*)",
            )
            if path:
                self.rehearse_voice_configs[character] = VoiceConfig(
                    model_path=path,
                    speaker=0,
                    name=f"Custom - {Path(path).name}",
                    noise_scale=0.667,
                    length_scale=1.0,
                    noise_w=0.8,
                    sentence_silence_seconds=0.0
                )
        else:
            # Get preset name from combo data
            preset_name = voice_combo.currentData()
            if preset_name:
                try:
                    preset = VoicePresets.get_preset(preset_name, default_model, library_presets_dir)
                    self.rehearse_voice_configs[character] = preset
                except Exception as e:
                    QMessageBox.warning(
                        self,
                        "Voice Error",
                        f"Failed to load voice preset: {e}"
                    )
    
    def _on_enable_highlighting_toggled(self, state: int) -> None:
        """Handle enable highlighting toggle."""
        # Save setting
        checked = state == Qt.CheckState.Checked.value
        self.app_config.set_rehearse_highlighting_option("enable_highlighting", checked)
        # Reapply all highlights (or remove them if disabled)
        self._apply_all_highlights()
        # Update fullscreen window if it exists
        if self.fullscreen_window and self.fullscreen_window.isVisible():
            self.fullscreen_window._update_script_content()
    
    def _on_highlight_names_toggled(self, state: int) -> None:
        """Handle highlight character names toggle."""
        # Save setting
        checked = state == Qt.CheckState.Checked.value
        self.app_config.set_rehearse_highlighting_option("highlight_character_names", checked)
        # Reapply all highlights to update character name highlighting
        self._apply_all_highlights()
        # Update fullscreen window if it exists
        if self.fullscreen_window and self.fullscreen_window.isVisible():
            self.fullscreen_window._update_script_content()
    
    def _on_highlight_parentheticals_toggled(self, state: int) -> None:
        """Handle highlight parentheticals toggle."""
        # Save setting
        checked = state == Qt.CheckState.Checked.value
        self.app_config.set_rehearse_highlighting_option("highlight_parentheticals", checked)
        # Reapply all highlights to update parenthetical highlighting
        self._apply_all_highlights()
        # Update fullscreen window if it exists
        if self.fullscreen_window and self.fullscreen_window.isVisible():
            self.fullscreen_window._update_script_content()
    
    def _on_smoosh_hieroglyphs_toggled(self, state: int) -> None:
        """Handle smoosh hieroglyphs toggle."""
        # Save setting
        checked = state == Qt.CheckState.Checked.value
        self.app_config.set_rehearse_highlighting_option("smoosh_hieroglyphs", checked)
        # Reapply all highlights to update hieroglyph formatting
        self._apply_all_highlights()
        # Update fullscreen window if it exists
        if self.fullscreen_window and self.fullscreen_window.isVisible():
            self.fullscreen_window._update_script_content()
    
    def _unhighlight_parentheticals(self, cursor: QTextCursor, lines: List[str]) -> None:
        """Remove highlighting from text in brackets/parentheses."""
        # Format to remove background color (white background, normal weight)
        unhighlight_fmt = QTextCharFormat()
        unhighlight_fmt.setBackground(QColor("white"))
        unhighlight_fmt.setFontWeight(400)
        unhighlight_fmt.setForeground(QColor("black"))
        
        # Process each line to find parentheticals
        for line_idx, line in enumerate(lines):
            if line_idx >= len(self.line_offsets):
                continue
            
            line_start_pos = self.line_offsets[line_idx]
            
            # Find all text in parentheses (text) or brackets [text]
            # Match parentheses: (anything inside)
            paren_pattern = r'\([^)]*\)'
            paren_matches = list(re.finditer(paren_pattern, line))
            
            # Match brackets: [anything inside]
            bracket_pattern = r'\[[^\]]*\]'
            bracket_matches = list(re.finditer(bracket_pattern, line))
            
            # Combine all matches
            all_matches = paren_matches + bracket_matches
            
            for match in all_matches:
                # Calculate the absolute position in the document
                parenthetical_start = line_start_pos + match.start()
                parenthetical_end = line_start_pos + match.end()
                
                # Apply unhighlight format to this range
                cursor.setPosition(parenthetical_start)
                cursor.setPosition(parenthetical_end, QTextCursor.MoveMode.KeepAnchor)
                cursor.mergeCharFormat(unhighlight_fmt)
    
    def _on_color_button_clicked(self, character: str, checked: bool = False) -> None:
        """Handle color button click - open color picker dialog."""
        current_color = self.app_config.get_character_color(character)
        
        dialog = CharacterColorDialog(current_color=current_color, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected_color = dialog.get_selected_color()
            
            # Save to config
            self.app_config.set_character_color(character, selected_color)
            
            # Update button appearance
            char_upper = character.upper().strip()
            if char_upper in self.character_color_buttons:
                btn = self.character_color_buttons[char_upper]
                self._update_color_button(btn, selected_color)
            
            # Reapply all highlights
            self._apply_all_highlights()
            # Update fullscreen window if it exists
            if self.fullscreen_window and self.fullscreen_window.isVisible():
                self.fullscreen_window._update_script_content()
    
    def _on_visibility_changed(self, character: str, state: int) -> None:
        """Handle visibility checkbox change."""
        # Reapply all highlights to update visibility
        self._apply_all_highlights()
        # Update fullscreen window if it exists
        if self.fullscreen_window and self.fullscreen_window.isVisible():
            self.fullscreen_window._update_script_content()
            self.fullscreen_window._copy_character_controls()
    
    def _on_hieroglyphs_changed(self, character: str, state: int) -> None:
        """Handle hieroglyphs checkbox change."""
        # Reapply all highlights to update hieroglyph transformation
        self._apply_all_highlights()
        # Update fullscreen window if it exists
        if self.fullscreen_window and self.fullscreen_window.isVisible():
            self.fullscreen_window._update_script_content()
            self.fullscreen_window._copy_character_controls()
    
    def _is_character_visible(self, character: str) -> bool:
        """Check if a character is visible."""
        char_upper = character.upper().strip()
        if char_upper in self.character_visibility_checkboxes:
            return self.character_visibility_checkboxes[char_upper].isChecked()
        return True  # Default to visible
    
    def _is_hieroglyphs_enabled(self, character: str) -> bool:
        """Check if hieroglyphs mode is enabled for a character."""
        char_upper = character.upper().strip()
        if char_upper in self.character_hieroglyphs_checkboxes:
            return self.character_hieroglyphs_checkboxes[char_upper].isChecked()
        return False  # Default to off
    
    def _apply_hieroglyph_formatting(self, cursor: QTextCursor, start_pos: int, end_pos: int, highlight_color: str, base_format: Optional[QTextCharFormat] = None) -> None:
        """Apply formatting to make non-first letters invisible by matching highlight color."""
        # Check if smoosh hieroglyphs is enabled
        smoosh_enabled = self.btn_smoosh_hieroglyphs.isChecked()
        
        # Get the text in this range
        cursor.setPosition(start_pos)
        cursor.setPosition(end_pos, QTextCursor.MoveMode.KeepAnchor)
        text = cursor.selectedText()
        
        # Get the formatting to preserve - use provided format or get from cursor
        if base_format is not None:
            current_format = base_format
        else:
            cursor.setPosition(start_pos)
            current_format = cursor.charFormat()
        
        # If smoosh is enabled, build text with only visible characters with spaces between them
        if smoosh_enabled:
            # Build new text with only first letters and punctuation, with spaces between visible characters
            visible_chars = []
            in_word = False
            
            for char in text:
                if char == '\n':
                    # Preserve newlines
                    visible_chars.append('\n')
                    in_word = False
                elif char.isspace():
                    # Skip all whitespace (spaces, tabs, etc.) except newlines
                    in_word = False
                elif char.isalpha():
                    if not in_word:
                        # First letter of word - keep it
                        visible_chars.append(char)
                        in_word = True
                    # Subsequent letters are skipped
                else:
                    # Punctuation or other non-whitespace character - keep it
                    visible_chars.append(char)
                    in_word = False
            
            # Build text with spaces between visible characters (but not before/after newlines)
            new_text_parts = []
            for i, char in enumerate(visible_chars):
                if char == '\n':
                    new_text_parts.append('\n')
                else:
                    # Add space before this character if it's not the first and previous wasn't newline
                    if i > 0 and visible_chars[i-1] != '\n':
                        new_text_parts.append(' ')
                    new_text_parts.append(char)
            
            new_text = ''.join(new_text_parts)
            
            # Replace the text in the document
            cursor.setPosition(start_pos)
            cursor.setPosition(end_pos, QTextCursor.MoveMode.KeepAnchor)
            cursor.removeSelectedText()
            
            # Prepare format for insertion - use the base format to preserve all highlighting
            format_to_apply = QTextCharFormat(current_format)
            # Ensure foreground is visible (black) if character is visible
            # The base_format should already have the correct foreground, but ensure it's not white
            fg_color = current_format.foreground().color()
            bg_color = current_format.background().color()
            # Only override if foreground is white or matches background (invisible)
            if fg_color == QColor("white") or (bg_color.isValid() and fg_color == bg_color):
                format_to_apply.setForeground(QColor("black"))
            
            # Insert text with the format (this preserves background color and all other formatting)
            cursor.insertText(new_text, format_to_apply)
            
            # Update end position and text for any remaining formatting
            end_pos = start_pos + len(new_text)
            text = new_text
        
        # Apply hieroglyph formatting (make non-first letters invisible)
        # Process character by character
        pos = start_pos
        i = 0
        in_word = False
        
        while i < len(text):
            char = text[i]
            
            if char.isalpha():
                if not in_word:
                    # First letter of word - keep visible (don't change color)
                    in_word = True
                    pos += 1
                else:
                    # Subsequent letters in word - make invisible
                    fmt = QTextCharFormat()
                    fmt.setForeground(QColor(highlight_color))
                    cursor.setPosition(pos)
                    cursor.setPosition(pos + 1, QTextCursor.MoveMode.KeepAnchor)
                    cursor.mergeCharFormat(fmt)
                    pos += 1
            else:
                # Non-letter character (punctuation, space, etc.) - keep visible
                in_word = False
                pos += 1
            
            i += 1
    
    def _apply_all_highlights(self) -> None:
        """Apply highlights for all characters based on their configured colors."""
        if not self.current_parse or not self.original_text:
            return
        
        # If highlighting is disabled, just show plain text
        if not self.btn_enable_highlighting.isChecked():
            # Restore original text with alignment but no highlighting
            cursor = self.txt_script.textCursor()
            cursor.beginEditBlock()
            cursor.select(QTextCursor.SelectionType.Document)
            cursor.removeSelectedText()
            
            lines = self.original_text.splitlines()
            self.line_offsets = []
            
            # Build sets of line types
            character_lines = set()
            dialogue_lines = set()
            narrator_lines = set()
            for block in self.current_parse.blocks:
                if block.speaker == "NARRATOR":
                    # Narrator dialogue lines
                    for line_idx in range(block.start_line, min(block.end_line + 1, len(lines))):
                        narrator_lines.add(line_idx)
                else:
                    if block.start_line > 0:
                        char_name_line = block.start_line - 1
                        if char_name_line < len(lines):
                            character_lines.add(char_name_line)
                    for line_idx in range(block.start_line, min(block.end_line + 1, len(lines))):
                        dialogue_lines.add(line_idx)
            
            # Get alignment options
            alignment_options = self.app_config.rehearse_alignment_options()
            
            # Insert text with alignment only
            for i, line in enumerate(lines):
                self.line_offsets.append(cursor.position())
                
                block_format = QTextBlockFormat()
                if i in character_lines:
                    alignment_flag = self._get_alignment_flag(alignment_options["character_names"])
                elif i in dialogue_lines:
                    alignment_flag = self._get_alignment_flag(alignment_options["dialogue"])
                elif i in narrator_lines:
                    alignment_flag = self._get_alignment_flag(alignment_options["narrator"])
                else:
                    alignment_flag = self._get_alignment_flag(alignment_options["everything_else"])
                
                block_format.setAlignment(alignment_flag)
                cursor.setBlockFormat(block_format)
                cursor.insertText(line)
                if i < len(lines) - 1:
                    cursor.insertText("\n")
            
            cursor.endEditBlock()
            return
        
        # First, restore original text with alignment
        cursor = self.txt_script.textCursor()
        cursor.beginEditBlock()
        cursor.select(QTextCursor.SelectionType.Document)
        cursor.removeSelectedText()
        
        # Rebuild line offsets and restore text with alignment
        lines = self.original_text.splitlines()
        self.line_offsets = []
        
        # Build sets of line types
        character_lines = set()
        dialogue_lines = set()
        narrator_lines = set()
        for block in self.current_parse.blocks:
            if block.speaker == "NARRATOR":
                # Narrator dialogue lines
                for line_idx in range(block.start_line, min(block.end_line + 1, len(lines))):
                    narrator_lines.add(line_idx)
            else:
                # For non-narrator blocks, character name is on the line before start_line
                if block.start_line > 0:
                    char_name_line = block.start_line - 1
                    if char_name_line < len(lines):
                        character_lines.add(char_name_line)
                # Dialogue lines are from start_line to end_line
                for line_idx in range(block.start_line, min(block.end_line + 1, len(lines))):
                    dialogue_lines.add(line_idx)
        
        # Get alignment options
        alignment_options = self.app_config.rehearse_alignment_options()
        
        # Insert text with alignment
        for i, line in enumerate(lines):
            self.line_offsets.append(cursor.position())
            
            # Set alignment based on line type
            block_format = QTextBlockFormat()
            if i in character_lines:
                alignment_flag = self._get_alignment_flag(alignment_options["character_names"])
            elif i in dialogue_lines:
                alignment_flag = self._get_alignment_flag(alignment_options["dialogue"])
            elif i in narrator_lines:
                alignment_flag = self._get_alignment_flag(alignment_options["narrator"])
            else:
                alignment_flag = self._get_alignment_flag(alignment_options["everything_else"])
            
            block_format.setAlignment(alignment_flag)
            cursor.setBlockFormat(block_format)
            cursor.insertText(line)
            if i < len(lines) - 1:  # Don't add newline after last line
                cursor.insertText("\n")
        
        cursor.endEditBlock()
        
        # Get all character colors from config
        character_colors = self.app_config.character_colors()
        
        # Get all characters from the script
        from core.nlp_processor import list_characters
        all_characters = list_characters(self.current_parse, sort_by_freq=False)
        
        # Build character, dialogue, and narrator line sets once (for alignment preservation)
        character_lines_set = set()
        dialogue_lines_set = set()
        narrator_lines_set = set()
        for block in self.current_parse.blocks:
            if block.speaker == "NARRATOR":
                # Narrator dialogue lines
                for line_idx in range(block.start_line, min(block.end_line + 1, len(lines))):
                    narrator_lines_set.add(line_idx)
            else:
                if block.start_line > 0:
                    char_name_line = block.start_line - 1
                    if char_name_line < len(lines):
                        character_lines_set.add(char_name_line)
                for line_idx in range(block.start_line, min(block.end_line + 1, len(lines))):
                    dialogue_lines_set.add(line_idx)
        
        # Now apply formatting (colors, visibility, hieroglyphs)
        cursor = self.txt_script.textCursor()
        cursor.beginEditBlock()
        
        # Collect blocks that need space removal (for smoosh hieroglyphs)
        # Process these in reverse order to avoid position shifts
        smoosh_blocks = []
        
        for character in all_characters:
            # Get blocks for character
            blocks = blocks_for_character(self.current_parse, character)
            if not blocks:
                continue
            
            # Check visibility
            is_visible = self._is_character_visible(character)
            
            # Get color for this character
            color = character_colors.get(character.upper().strip())
            
            # Check if hieroglyphs is enabled
            hieroglyphs_enabled = self._is_hieroglyphs_enabled(character)
            
            # Determine highlight color (use white if no color assigned)
            highlight_color = color if (color and color != NO_HIGHLIGHT) else "white"
            
            # Prepare highlight format
            fmt = QTextCharFormat()
            
            if color and color != NO_HIGHLIGHT:
                # Character has a color - apply background highlight
                fmt.setBackground(QColor(color))
                fmt.setFontWeight(600)
                
                # If not visible, set text color to match highlight color (makes it invisible)
                if not is_visible:
                    fmt.setForeground(QColor(color))
                else:
                    # Visible: use default black text
                    fmt.setForeground(QColor("black"))
            else:
                # Character has no color assigned
                if not is_visible:
                    # Hide by making text white (matches white background)
                    fmt.setForeground(QColor("white"))
                else:
                    # Visible: use default black text (no background highlight)
                    fmt.setForeground(QColor("black"))
            
            # Apply formatting to each block
            for block in blocks:
                start_line = max(0, block.start_line)
                end_line = max(start_line, block.end_line)
                
                if start_line >= len(self.line_offsets):
                    continue
                
                start_pos = self.line_offsets[start_line]
                if end_line < len(self.line_offsets):
                    end_pos = self.line_offsets[end_line] + len(lines[end_line])
                else:
                    end_pos = len(self.original_text)
                
                # Apply base formatting (color, visibility) to dialogue
                cursor.setPosition(start_pos)
                cursor.setPosition(end_pos, QTextCursor.MoveMode.KeepAnchor)
                cursor.mergeCharFormat(fmt)
                
                # Apply character name highlighting if enabled
                if self.btn_highlight_names.isChecked() and block.speaker != "NARRATOR" and block.start_line > 0:
                    char_name_line = block.start_line - 1
                    if char_name_line < len(self.line_offsets):
                        char_name_start_pos = self.line_offsets[char_name_line]
                        char_name_end_pos = char_name_start_pos + len(lines[char_name_line])
                        
                        cursor.setPosition(char_name_start_pos)
                        cursor.setPosition(char_name_end_pos, QTextCursor.MoveMode.KeepAnchor)
                        cursor.mergeCharFormat(fmt)
                
                # Preserve alignment for all line types
                # Ensure all lines in this range maintain their proper alignment
                alignment_options = self.app_config.rehearse_alignment_options()
                for line_idx in range(start_line, end_line + 1):
                    if line_idx < len(self.line_offsets):
                        line_start_pos = self.line_offsets[line_idx]
                        cursor.setPosition(line_start_pos)
                        block = cursor.block()
                        block_format = block.blockFormat()
                        
                        # Determine proper alignment based on line type
                        if line_idx in character_lines_set:
                            proper_alignment = self._get_alignment_flag(alignment_options["character_names"])
                        elif line_idx in dialogue_lines_set:
                            proper_alignment = self._get_alignment_flag(alignment_options["dialogue"])
                        elif line_idx in narrator_lines_set:
                            proper_alignment = self._get_alignment_flag(alignment_options["narrator"])
                        else:
                            proper_alignment = self._get_alignment_flag(alignment_options["everything_else"])
                        
                        # Apply alignment if different
                        if block_format.alignment() != proper_alignment:
                            block_format.setAlignment(proper_alignment)
                            cursor.setBlockFormat(block_format)
                
                # Collect blocks that need space removal (for smoosh hieroglyphs)
                if hieroglyphs_enabled and is_visible and self.btn_smoosh_hieroglyphs.isChecked():
                    # Store format so we can preserve highlighting when smooshing
                    smoosh_blocks.append((start_pos, end_pos, highlight_color, fmt))
                # Apply hieroglyph formatting if enabled (make non-first letters invisible)
                elif hieroglyphs_enabled and is_visible:
                    self._apply_hieroglyph_formatting(cursor, start_pos, end_pos, highlight_color, fmt)
        
        # Apply space removal in reverse order (to avoid position shifts)
        for start_pos, end_pos, highlight_color, fmt in reversed(smoosh_blocks):
            self._apply_hieroglyph_formatting(cursor, start_pos, end_pos, highlight_color, fmt)
        
        # Unhighlight parentheticals if toggle is enabled
        if self.btn_highlight_parentheticals.isChecked():
            self._unhighlight_parentheticals(cursor, lines)
        
        cursor.endEditBlock()
    
    def _on_alignment_clicked(self, option_name: str) -> None:
        """Handle alignment button click - cycle through alignment options."""
        alignment_options = self.app_config.rehearse_alignment_options()
        current_alignment = alignment_options[option_name]
        
        # Cycle: left -> center -> right -> left
        if current_alignment == "left":
            new_alignment = "center"
        elif current_alignment == "center":
            new_alignment = "right"
        else:  # right
            new_alignment = "left"
        
        # Save new alignment
        self.app_config.set_rehearse_alignment_option(option_name, new_alignment)
        
        # Update button text
        if option_name == "character_names":
            self.btn_align_character_names.setText(f"Character Names: {new_alignment.title()}")
        elif option_name == "dialogue":
            self.btn_align_dialogue.setText(f"Dialogue: {new_alignment.title()}")
        elif option_name == "narrator":
            self.btn_align_narrator.setText(f"Narrator: {new_alignment.title()}")
        elif option_name == "everything_else":
            self.btn_align_everything_else.setText(f"Everything Else: {new_alignment.title()}")
        
        # Reapply alignment to script
        if self.current_parse:
            self._apply_alignment()
            # Update fullscreen window if it exists
            if self.fullscreen_window and self.fullscreen_window.isVisible():
                self.fullscreen_window._update_script_content()
    
    def _get_alignment_flag(self, alignment_str: str) -> Qt.AlignmentFlag:
        """Convert alignment string to Qt alignment flag."""
        if alignment_str == "center":
            return Qt.AlignmentFlag.AlignCenter
        elif alignment_str == "right":
            return Qt.AlignmentFlag.AlignRight
        else:  # left
            return Qt.AlignmentFlag.AlignLeft
    
    def _apply_alignment(self) -> None:
        """Apply alignment settings to the script text."""
        if not self.current_parse or not self.original_text:
            return
        
        lines = self.original_text.splitlines()
        if not lines:
            return
        
        # Get alignment options
        alignment_options = self.app_config.rehearse_alignment_options()
        
        # Build sets of line types
        character_lines = set()
        dialogue_lines = set()
        narrator_lines = set()
        
        for block in self.current_parse.blocks:
            if block.speaker == "NARRATOR":
                # Narrator dialogue lines
                for line_idx in range(block.start_line, min(block.end_line + 1, len(lines))):
                    narrator_lines.add(line_idx)
            else:
                # Character name is on the line before start_line
                if block.start_line > 0:
                    char_name_line = block.start_line - 1
                    if char_name_line < len(lines):
                        character_lines.add(char_name_line)
                # Character dialogue lines
                for line_idx in range(block.start_line, min(block.end_line + 1, len(lines))):
                    dialogue_lines.add(line_idx)
        
        # Apply alignment to each line
        cursor = self.txt_script.textCursor()
        cursor.beginEditBlock()
        
        for i, line in enumerate(lines):
            if i >= len(self.line_offsets):
                continue
            
            line_start_pos = self.line_offsets[i]
            cursor.setPosition(line_start_pos)
            block = cursor.block()
            block_format = block.blockFormat()
            
            # Determine alignment based on line type
            if i in character_lines:
                alignment_flag = self._get_alignment_flag(alignment_options["character_names"])
            elif i in dialogue_lines:
                alignment_flag = self._get_alignment_flag(alignment_options["dialogue"])
            elif i in narrator_lines:
                alignment_flag = self._get_alignment_flag(alignment_options["narrator"])
            else:
                alignment_flag = self._get_alignment_flag(alignment_options["everything_else"])
            
            # Apply alignment if different
            if block_format.alignment() != alignment_flag:
                block_format.setAlignment(alignment_flag)
                cursor.setBlockFormat(block_format)
        
        cursor.endEditBlock()
    
    def _on_quality_changed(self, quality: str) -> None:
        """Handle quality dropdown change - sync with read tab."""
        if self.read_tab:
            self.read_tab.quality_combo.setCurrentText(quality)
            self.read_tab._on_quality_changed(quality)
    
    def _on_read_character_names_changed(self, state: int) -> None:
        """Handle read character names checkbox change - sync with read tab."""
        if self.read_tab:
            self.read_tab.chk_read_character_names.setChecked(state == Qt.CheckState.Checked.value)
    
    def _on_speed_changed(self, value: int) -> None:
        """Handle speed slider change."""
        self.playback_speed = value / 100.0  # Convert to multiplier (50-200 -> 0.5-2.0)
        self.speed_label.setText(f"{self.playback_speed:.2f}x")
        
        # Apply speed to current player if reading
        if self.script_reader and self.script_reader.player:
            self.script_reader.player.setPlaybackRate(self.playback_speed)
    
    def _on_rehearse_clicked(self) -> None:
        """Handle Rehearse button click - start reading all lines except selected character's."""
        if not self.current_parse:
            QMessageBox.warning(
                self,
                "No Script Loaded",
                "No script is currently loaded."
            )
            return
        
        if not self.current_character:
            QMessageBox.warning(
                self,
                "No Character Selected",
                "Please select a character to rehearse as using the radio buttons."
            )
            return
        
        if not self.read_tab:
            QMessageBox.warning(
                self,
                "Read Tab Not Available",
                "Read tab is not available. Please ensure the Read tab is loaded."
            )
            return
        
        # Get voice configs from read tab
        if not self.read_tab.voice_configs:
            QMessageBox.warning(
                self,
                "No Voices Configured",
                "Please configure voices in the 'Read' tab first."
            )
            return
        
        
        # Use the full script parse (we'll pause at character's lines instead of filtering)
        # This allows us to stop at the character's lines and wait for user input
        
        # Get voice configs - use rehearse overrides if available, otherwise use read_tab configs
        base_voice_configs = self.read_tab.voice_configs.copy()
        # Merge rehearse voice configs (overrides)
        voice_configs = {**base_voice_configs, **self.rehearse_voice_configs}
        
        default_model = self.read_tab.app_config.tts_model_path()
        library_presets_dir = self.read_tab.library_presets_dir
        
        # Resolve voice configs (same logic as read tab)
        from app.tabs.voice_selection_dialog import VoicePresets
        resolved_voice_configs = {}
        for character, voice_config in voice_configs.items():
            model_path = voice_config.model_path
            if not model_path or not model_path.strip() or not Path(model_path).exists():
                model_path = default_model or ""
            
            if not model_path or not model_path.strip() or not Path(model_path).exists():
                discovered_model = VoicePresets._find_onnx_model(library_presets_dir)
                if discovered_model and Path(discovered_model).exists():
                    model_path = discovered_model
            
            resolved_voice_configs[character] = voice_config
        
        # Stop any existing reading
        if self.script_reader:
            self.script_reader.stop_reading()
            self.script_reader.deleteLater()
        
        # Create script reader with full parse (we'll pause at character's lines)
        self.script_reader = ScriptReader(
            self.current_parse,  # Use full parse, not filtered
            resolved_voice_configs,
            self,
            self.txt_script,
            start_block=0,
            default_model_path=default_model,
            read_character_names=self.chk_read_character_names.isChecked()
        )
        
        # Apply playback speed
        if self.script_reader.player:
            self.script_reader.player.setPlaybackRate(self.playback_speed)
        self.script_reader.progress.connect(self._on_reading_progress)
        self.script_reader.word_highlight.connect(self._on_word_highlight)
        self.script_reader.finished.connect(self._on_reading_finished)
        self.script_reader.error.connect(self._on_reading_error)
        
        # Don't connect to player signals directly - ScriptReader already handles them
        # Instead, we'll check in _on_reading_progress which is called at the start of _read_next_block
        # Connect to playback state to apply speed when audio starts (this is safe)
        try:
            if self.script_reader.player:
                self.script_reader.player.playbackStateChanged.connect(self._on_playback_state_changed)
        except Exception:
            pass
        
        # Prepare and start
        if self.script_reader.prepare_reading():
            # Clear any previous line highlighting
            self._clear_line_highlight()
            self.btn_rehearse.setEnabled(False)
            self.btn_pause.setEnabled(True)
            self.btn_stop.setEnabled(True)
            self.btn_next_line.setEnabled(False)
            self.waiting_at_character_line = False
            self.should_skip_current_block = False
            self.script_reader.start_reading()
        else:
            QMessageBox.warning(
                self,
                "Preparation Failed",
                "Failed to prepare script for reading."
            )
    
    def _on_pause_rehearsing(self) -> None:
        """Pause or resume rehearsing."""
        if not self.script_reader:
            return
        
        if self.script_reader.is_paused:
            self.script_reader.resume_reading()
            self.btn_pause.setText("⏸ Pause")
        else:
            self.script_reader.pause_reading()
            self.btn_pause.setText("▶ Resume")
    
    def _on_next_line_clicked(self) -> None:
        """Handle Next Line button click - continue past character's line."""
        if not self.script_reader or not self.waiting_at_character_line:
            return
        
        try:
            # Store reference to avoid issues with lambda closure
            reader = self.script_reader
            
            # Validate reader object and its attributes before accessing
            if not hasattr(reader, 'blocks_to_read') or not reader.blocks_to_read:
                # Reader is in invalid state, finish reading
                self._on_reading_finished()
                return
            
            if not hasattr(reader, 'current_block_index'):
                # Reader is in invalid state, finish reading
                self._on_reading_finished()
                return
            
            # Check bounds before incrementing
            if reader.current_block_index + 1 >= len(reader.blocks_to_read):
                # No more blocks to read
                self._on_reading_finished()
                return
            
            # Clear waiting state first
            self.waiting_at_character_line = False
            self.btn_next_line.setEnabled(False)
            self.btn_pause.setEnabled(True)
            self.should_skip_current_block = False
            
            # Clear the yellow highlight (preserve original formatting)
            self._clear_character_line_highlight()
            # Clear the gray line highlight as well
            self._clear_line_highlight()
            
            # Move to next block (skip the character's line)
            reader.current_block_index += 1
            
            # Make sure we're playing and not paused
            reader.is_paused = False
            reader.is_playing = True
            
            # Apply playback speed
            if hasattr(reader, 'player') and reader.player:
                try:
                    reader.player.setPlaybackRate(self.playback_speed)
                except (RuntimeError, AttributeError, Exception):
                    pass  # Player might be in invalid state or deleted
            
            # Continue reading - read next block
            # Use QTimer to ensure the UI updates before continuing
            QTimer.singleShot(50, lambda: self._continue_reading_next_block())
        except RuntimeError as e:
            # RuntimeError often indicates object has been deleted
            print(f"RuntimeError in _on_next_line_clicked (object deleted?): {e}")
            import traceback
            traceback.print_exc()
            # Reset state on error
            self.script_reader = None
            self.waiting_at_character_line = False
            self.btn_next_line.setEnabled(False)
            self.btn_pause.setEnabled(True)
            self._on_reading_finished()
        except Exception as e:
            print(f"Error in _on_next_line_clicked: {e}")
            import traceback
            traceback.print_exc()
            # Reset state on error
            self.waiting_at_character_line = False
            self.btn_next_line.setEnabled(False)
            self.btn_pause.setEnabled(True)
    
    def _continue_reading_next_block(self) -> None:
        """Continue reading the next block after skipping character's line."""
        if not self.script_reader:
            return
        
        try:
            reader = self.script_reader
            
            # Check if reader is still valid
            if not hasattr(reader, 'blocks_to_read') or not reader.blocks_to_read:
                self._on_reading_finished()
                return
            
            if not hasattr(reader, 'current_block_index'):
                self._on_reading_finished()
                return
            
            # Check bounds
            if reader.current_block_index >= len(reader.blocks_to_read):
                self._on_reading_finished()
                return
            
            # Make sure we're in the right state
            reader.is_paused = False
            reader.is_playing = True
            
            # Apply playback speed
            if hasattr(reader, 'player') and reader.player:
                try:
                    reader.player.setPlaybackRate(self.playback_speed)
                except (RuntimeError, AttributeError, Exception):
                    pass  # Player might be in invalid state or deleted
            
            # Use QTimer to call _read_next_block safely
            # This ensures any pending operations complete first
            QTimer.singleShot(100, lambda: self._safe_read_next_block())
        except RuntimeError as e:
            # RuntimeError often indicates object has been deleted
            print(f"RuntimeError in _continue_reading_next_block (object deleted?): {e}")
            import traceback
            traceback.print_exc()
            # Reset state on error
            self.script_reader = None
            self.waiting_at_character_line = False
            self.btn_next_line.setEnabled(False)
            self.btn_pause.setEnabled(True)
            self._on_reading_finished()
        except Exception as e:
            print(f"Error in _continue_reading_next_block: {e}")
            import traceback
            traceback.print_exc()
            # Reset state on error
            if self.script_reader:
                try:
                    self.script_reader.stop_reading()
                except Exception:
                    pass
            self.waiting_at_character_line = False
            self.btn_next_line.setEnabled(False)
            self.btn_pause.setEnabled(True)
    
    def _safe_read_next_block(self) -> None:
        """Safely call _read_next_block with error handling."""
        if not self.script_reader:
            return
        
        try:
            reader = self.script_reader
            
            # Double-check validity - ensure reader hasn't been deleted
            if not hasattr(reader, 'blocks_to_read') or not reader.blocks_to_read:
                return
            
            if not hasattr(reader, 'current_block_index'):
                return
            
            if reader.current_block_index >= len(reader.blocks_to_read):
                self._on_reading_finished()
                return
            
            # Ensure player exists and is valid
            if not hasattr(reader, 'player') or not reader.player:
                return
            
            # Ensure we're in playing state BEFORE calling _read_next_block
            # This is critical - _read_next_block checks is_playing at the start
            reader.is_paused = False
            reader.is_playing = True
            
            # Verify the block exists before calling
            if reader.current_block_index < len(reader.blocks_to_read):
                # Call the method - this will emit progress signal which we handle
                # The progress handler will check if it's the character's line and pause if needed
                reader._read_next_block()
        except RuntimeError as e:
            # RuntimeError often indicates object has been deleted
            print(f"RuntimeError in _safe_read_next_block (object deleted?): {e}")
            self.script_reader = None
            self.waiting_at_character_line = False
            self.btn_next_line.setEnabled(False)
            self.btn_pause.setEnabled(True)
        except Exception as e:
            print(f"Error in _safe_read_next_block: {e}")
            import traceback
            traceback.print_exc()
            # On error, stop reading
            if self.script_reader:
                try:
                    self.script_reader.stop_reading()
                except Exception:
                    pass
            self.waiting_at_character_line = False
            self.btn_next_line.setEnabled(False)
            self.btn_pause.setEnabled(True)
    
    def _on_stop_rehearsing(self) -> None:
        """Stop rehearsing."""
        if self.script_reader:
            try:
                # Disconnect our signal handlers first
                try:
                    if self.script_reader.player:
                        self.script_reader.player.playbackStateChanged.disconnect(self._on_playback_state_changed)
                except Exception:
                    pass
                
                self.script_reader.stop_reading()
                self.script_reader.deleteLater()
            except Exception:
                pass
            finally:
                self.script_reader = None
        
        # Clear word highlighting
        self._clear_word_highlight()
        
        self.btn_rehearse.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_stop.setEnabled(False)
        self.btn_next_line.setEnabled(False)
        self.btn_pause.setText("⏸ Pause")
        self.waiting_at_character_line = False
    
    def _on_reading_progress(self, message: str) -> None:
        """Handle reading progress update - check if we need to pause at character's line."""
        if not self.script_reader or not self.current_character:
            return
        
        try:
            reader = self.script_reader
            
            # Check if reader is still valid
            if not hasattr(reader, 'blocks_to_read') or not reader.blocks_to_read:
                return
            
            # Clear the previous line's gray highlight when starting a new block
            self._clear_line_highlight()
            
            # Check if the current block is the selected character's block
            # This is called at the start of _read_next_block, after the is_playing check
            # So we need to stop synthesis before it happens
            if reader.current_block_index < len(reader.blocks_to_read):
                block, _ = reader.blocks_to_read[reader.current_block_index]
                
                # If this is the character's line, stop immediately and wait
                if block.speaker.upper().strip() == self.current_character.upper().strip():
                    # CRITICAL: Set is_playing to False to prevent synthesis from continuing
                    # This will cause _read_next_block to return early after progress signal
                    reader.is_playing = False
                    reader.is_paused = True
                    self.should_skip_current_block = True
                    
                    # Stop any current playback immediately (safely)
                    try:
                        if hasattr(reader, 'player') and reader.player:
                            try:
                                if reader.player.playbackState() != reader.player.PlaybackState.StoppedState:
                                    reader.player.stop()
                            except (RuntimeError, AttributeError):
                                pass
                    except Exception:
                        pass
                    
                    # Stop word highlighting timer if running
                    try:
                        if hasattr(reader, 'current_word_timer') and reader.current_word_timer:
                            try:
                                reader.current_word_timer.stop()
                                reader.current_word_timer = None
                            except Exception:
                                pass
                    except Exception:
                        pass
                    
                    # Set waiting state
                    self.waiting_at_character_line = True
                    self.btn_next_line.setEnabled(True)  # Enable the button
                    self.btn_pause.setEnabled(False)  # Disable pause button while waiting
                    
                    # Highlight the character's line to show it's waiting
                    self._highlight_character_line(block)
                    
                    # Use QTimer to ensure we've stopped everything
                    QTimer.singleShot(50, self._ensure_block_stopped)
                    return
        except Exception as e:
            print(f"Error in _on_reading_progress: {e}")
            import traceback
            traceback.print_exc()
    
    def _ensure_block_stopped(self) -> None:
        """Ensure the current block is fully stopped if it's the character's line."""
        if not self.script_reader or not self.waiting_at_character_line:
            return
        
        try:
            # Stop the player if it's trying to play
            if hasattr(self.script_reader, 'player') and self.script_reader.player:
                try:
                    if self.script_reader.player.playbackState() != self.script_reader.player.PlaybackState.StoppedState:
                        self.script_reader.player.stop()
                except (RuntimeError, AttributeError):
                    pass  # Player might be in invalid state or deleted
            
            # Make sure we're paused
            if hasattr(self.script_reader, 'is_paused'):
                self.script_reader.is_paused = True
            if hasattr(self.script_reader, 'is_playing'):
                self.script_reader.is_playing = False
            
            # Ensure the button is enabled
            if self.waiting_at_character_line:
                self.btn_next_line.setEnabled(True)
                self.btn_pause.setEnabled(False)
        except (RuntimeError, AttributeError) as e:
            # Object might have been deleted
            print(f"Error in _ensure_block_stopped: {e}")
            self.script_reader = None
            self.waiting_at_character_line = False
            self.btn_next_line.setEnabled(False)
            self.btn_pause.setEnabled(True)
    
    
    def _on_playback_state_changed(self, state) -> None:
        """Handle playback state change - apply speed when audio starts playing."""
        from PyQt6.QtMultimedia import QMediaPlayer
        
        # When audio starts playing, apply the current speed
        if state == QMediaPlayer.PlaybackState.PlayingState:
            if self.script_reader and self.script_reader.player:
                self.script_reader.player.setPlaybackRate(self.playback_speed)
    
    def _on_word_highlight(self, start_pos: int, end_pos: int) -> None:
        """Handle line highlighting during rehearsal - highlight the entire line in gray."""
        try:
            # Basic validation - quick checks first
            if not hasattr(self, 'txt_script') or not self.txt_script:
                return
            if not hasattr(self, 'current_parse') or not self.current_parse:
                return
            if not hasattr(self, 'line_offsets') or not self.line_offsets or len(self.line_offsets) == 0:
                return
            
            # Get document and validate
            try:
                document = self.txt_script.document()
                if not document:
                    return
                doc_length = document.characterCount()
                if doc_length == 0 or start_pos < 0 or start_pos >= doc_length:
                    return
            except (RuntimeError, AttributeError):
                return
            
            # Find which line this word is on
            current_line = None
            for i, line_start_pos in enumerate(self.line_offsets):
                if i + 1 < len(self.line_offsets):
                    line_end_pos = self.line_offsets[i + 1]
                else:
                    line_end_pos = doc_length
                
                if line_start_pos <= start_pos < line_end_pos:
                    current_line = i
                    break
            
            if current_line is None:
                return
            
            # Get current highlighted line
            current_highlighted_line = getattr(self, 'current_highlighted_line', None)
            
            # Only update if we've moved to a different line
            if current_highlighted_line != current_line:
                # Clear previous line if needed
                if current_highlighted_line is not None:
                    self._clear_line_highlight()
                
                # Highlight current line
                try:
                    cursor = self.txt_script.textCursor()
                    cursor.beginEditBlock()
                    
                    line_start_pos = self.line_offsets[current_line]
                    if current_line + 1 < len(self.line_offsets):
                        line_end_pos = self.line_offsets[current_line + 1]
                    else:
                        line_end_pos = doc_length
                    
                    # Validate positions
                    if line_start_pos >= 0 and line_end_pos <= doc_length and line_start_pos < line_end_pos:
                        cursor.setPosition(line_start_pos)
                        cursor.setPosition(line_end_pos, QTextCursor.MoveMode.KeepAnchor)
                        fmt = QTextCharFormat()
                        fmt.setBackground(QColor("#D3D3D3"))
                        cursor.mergeCharFormat(fmt)
                        
                        # Store state
                        self.current_line_highlight_range = (line_start_pos, line_end_pos)
                        self.current_highlighted_line = current_line
                    
                    cursor.endEditBlock()
                except (RuntimeError, AttributeError):
                    try:
                        cursor.endEditBlock()
                    except:
                        pass
                    return
            
            # Scroll to position (only if we need to)
            try:
                cursor = self.txt_script.textCursor()
                if cursor.position() != start_pos:
                    cursor.setPosition(start_pos)
                    self.txt_script.setTextCursor(cursor)
                    self.txt_script.ensureCursorVisible()
            except (RuntimeError, AttributeError):
                pass
            
            self.current_highlighted_word = (start_pos, end_pos)
        except (RuntimeError, AttributeError):
            pass
        except Exception as e:
            print(f"Error in _on_word_highlight: {e}")
            import traceback
            traceback.print_exc()
    
    def _clear_line_highlight(self) -> None:
        """Clear the gray highlight from the current line."""
        try:
            current_line_highlight_range = getattr(self, 'current_line_highlight_range', None)
            if not current_line_highlight_range:
                self.current_line_highlight_range = None
                self.current_highlighted_line = None
                self.current_highlighted_word = None
                return
            
            start_pos, end_pos = current_line_highlight_range
            
            # Validate positions - check widget exists and is valid
            if not hasattr(self, 'txt_script') or not self.txt_script:
                self.current_line_highlight_range = None
                self.current_highlighted_line = None
                self.current_highlighted_word = None
                return
            
            try:
                # Check if widget is still valid
                if not self.txt_script.isVisible() and not self.txt_script.isEnabled():
                    self.current_line_highlight_range = None
                    self.current_highlighted_line = None
                    self.current_highlighted_word = None
                    return
            except (RuntimeError, AttributeError):
                # Widget has been deleted
                self.current_line_highlight_range = None
                self.current_highlighted_line = None
                self.current_highlighted_word = None
                return
            
            try:
                document = self.txt_script.document()
                if not document:
                    self.current_line_highlight_range = None
                    self.current_highlighted_line = None
                    self.current_highlighted_word = None
                    return
                doc_length = document.characterCount()
                if start_pos < 0 or end_pos > doc_length or start_pos >= end_pos:
                    self.current_line_highlight_range = None
                    self.current_highlighted_line = None
                    self.current_highlighted_word = None
                    return
                
                # Use beginEditBlock for atomic operation
                cursor = self.txt_script.textCursor()
                cursor.beginEditBlock()
                
                try:
                    # Get the original format before clearing
                    cursor.setPosition(start_pos)
                    original_format = cursor.charFormat()
                    
                    # Clear only the background, preserve text color and other formatting
                    fmt = QTextCharFormat()
                    fmt.setBackground(QColor())  # Clear background
                    fmt.setForeground(original_format.foreground().color())  # Preserve text color
                    fmt.setFontFamily(original_format.fontFamily())  # Preserve font
                    fmt.setFontPointSize(original_format.fontPointSize())  # Preserve font size
                    
                    cursor.setPosition(start_pos)
                    cursor.setPosition(end_pos, QTextCursor.MoveMode.KeepAnchor)
                    cursor.mergeCharFormat(fmt)
                finally:
                    # Always end the edit block
                    cursor.endEditBlock()
                
                self.current_line_highlight_range = None
            except (RuntimeError, AttributeError):
                # Widget or document is invalid
                self.current_line_highlight_range = None
                self.current_highlighted_line = None
                self.current_highlighted_word = None
                return
            
            self.current_highlighted_line = None
            self.current_highlighted_word = None
        except (RuntimeError, AttributeError) as e:
            # Widget or object has been deleted - this is expected and safe to ignore
            # Reset state
            self.current_line_highlight_range = None
            self.current_highlighted_line = None
            self.current_highlighted_word = None
        except Exception as e:
            # Log other errors but don't crash
            print(f"Error in _clear_line_highlight: {e}")
            import traceback
            traceback.print_exc()
            # Reset state on error
            self.current_line_highlight_range = None
            self.current_highlighted_line = None
            self.current_highlighted_word = None
    
    def _clear_word_highlight(self) -> None:
        """Clear current word and line highlighting."""
        self._clear_line_highlight()
    
    def _on_reading_finished(self) -> None:
        """Handle reading finished."""
        self._clear_word_highlight()
        
        if self.script_reader:
            self.script_reader.deleteLater()
            self.script_reader = None
        
        self.btn_rehearse.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_stop.setEnabled(False)
        self.btn_next_line.setEnabled(False)
        self.btn_pause.setText("⏸ Pause")
        self.waiting_at_character_line = False
    
    def _on_reading_error(self, error: str) -> None:
        """Handle reading error."""
        self._clear_word_highlight()
        
        QMessageBox.warning(
            self,
            "Reading Error",
            f"An error occurred while reading:\n\n{error}"
        )
        
        if self.script_reader:
            self.script_reader.deleteLater()
            self.script_reader = None
        
        self.btn_rehearse.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_stop.setEnabled(False)
        self.btn_next_line.setEnabled(False)
        self.btn_pause.setText("⏸ Pause")
        self.waiting_at_character_line = False
    
    def _highlight_character_line(self, block) -> None:
        """Highlight the character's line to show it's waiting for user input."""
        if not self.current_parse or not self.line_offsets:
            return
        
        cursor = self.txt_script.textCursor()
        cursor.beginEditBlock()
        
        # Highlight the block's lines
        start_line = max(0, block.start_line)
        end_line = max(start_line, block.end_line)
        
        if start_line < len(self.line_offsets):
            start_pos = self.line_offsets[start_line]
            lines = self.current_parse.lines
            if end_line < len(self.line_offsets):
                end_pos = self.line_offsets[end_line] + len(lines[end_line])
            else:
                end_pos = len(self.original_text)
            
            # Store the highlight range for clearing later
            self.character_line_highlight_range = (start_pos, end_pos)
            
            # Apply yellow background to indicate waiting
            cursor.setPosition(start_pos)
            cursor.setPosition(end_pos, QTextCursor.MoveMode.KeepAnchor)
            fmt = QTextCharFormat()
            fmt.setBackground(QColor("#FFFF99"))  # Light yellow
            cursor.mergeCharFormat(fmt)
            
            # Scroll to the line
            cursor.setPosition(start_pos)
            self.txt_script.setTextCursor(cursor)
            self.txt_script.ensureCursorVisible()
        
        cursor.endEditBlock()
    
    def _clear_character_line_highlight(self) -> None:
        """Clear the yellow highlight from the character's line."""
        if hasattr(self, 'character_line_highlight_range') and self.character_line_highlight_range:
            start_pos, end_pos = self.character_line_highlight_range
            cursor = self.txt_script.textCursor()
            cursor.beginEditBlock()
            
            # Get the original format before clearing
            cursor.setPosition(start_pos)
            original_format = cursor.charFormat()
            
            # Clear only the background, preserve text color and other formatting
            fmt = QTextCharFormat()
            fmt.setBackground(QColor())  # Clear background
            fmt.setForeground(original_format.foreground().color())  # Preserve text color
            fmt.setFontFamily(original_format.fontFamily())  # Preserve font
            fmt.setFontPointSize(original_format.fontPointSize())  # Preserve font size
            
            cursor.setPosition(start_pos)
            cursor.setPosition(end_pos, QTextCursor.MoveMode.KeepAnchor)
            cursor.mergeCharFormat(fmt)
            
            cursor.endEditBlock()
            self.character_line_highlight_range = None
    
    def eventFilter(self, obj, event) -> bool:
        """Filter events to catch spacebar for next line."""
        if obj == self.txt_script and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Space:
                if self.waiting_at_character_line:
                    self._on_next_line_clicked()
                    return True
        return super().eventFilter(obj, event)
    
    def keyPressEvent(self, event) -> None:
        """Handle key press events - spacebar for next line."""
        if event.key() == Qt.Key.Key_Space:
            if self.waiting_at_character_line:
                self._on_next_line_clicked()
                event.accept()
                return
        super().keyPressEvent(event)
    
    def _on_fullscreen_clicked(self) -> None:
        """Handle fullscreen button click."""
        if self.fullscreen_window is None or not self.fullscreen_window.isVisible():
            # Create and show fullscreen window
            self.fullscreen_window = RehearseFullscreenWindow(self)
            self.fullscreen_window.showFullScreen()
        else:
            # Close fullscreen window
            self.fullscreen_window.close()
            self.fullscreen_window = None


class RehearseFullscreenWindow(QMainWindow):
    """Fullscreen window for rehearsal mode with toolbar at bottom."""
    
    def __init__(self, rehearse_tab: RehearseTab, parent=None):
        super().__init__(parent)
        self.rehearse_tab = rehearse_tab
        self.setWindowTitle("Rehearse - Fullscreen")
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Build the fullscreen UI."""
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Script text area (takes up most of the screen)
        self.txt_script = QTextEdit()
        self.txt_script.setReadOnly(True)
        self.txt_script.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.txt_script.setFontFamily("Courier Prime")
        self.font_size = 12
        self.txt_script.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.txt_script.setStyleSheet("QTextEdit { background-color: white; color: black; }")
        # Install event filter on text edit to catch escape key
        self.txt_script.installEventFilter(self)
        
        # Fullscreen rehearse toolbar at the bottom
        self.fullscreen_rehearse_toolbar = QWidget()
        self.fullscreen_rehearse_toolbar.setStyleSheet("""
            QWidget {
                background-color: #3d3d3d;
                border-top: 1px solid #555;
            }
            QLabel {
                color: white;
            }
        """)
        toolbar_layout = QVBoxLayout(self.fullscreen_rehearse_toolbar)
        toolbar_layout.setContentsMargins(5, 5, 5, 5)
        toolbar_layout.setSpacing(5)
        
        # Font size control container (can be hidden when collapsed)
        self.font_size_container = QWidget()
        font_size_layout = QHBoxLayout(self.font_size_container)
        font_size_layout.setContentsMargins(0, 0, 0, 0)
        font_size_layout.setSpacing(5)
        font_size_label = QLabel("Font Size:")
        font_size_layout.addWidget(font_size_label)
        
        self.font_size_slider = QSlider(Qt.Orientation.Horizontal)
        self.font_size_slider.setMinimum(8)
        self.font_size_slider.setMaximum(48)
        self.font_size_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.font_size_slider.setTickInterval(4)
        self.font_size_slider.valueChanged.connect(self._on_font_size_changed)
        font_size_layout.addWidget(self.font_size_slider)
        
        midpoint = (self.font_size_slider.minimum() + self.font_size_slider.maximum()) // 2
        if self.font_size < midpoint:
            self.font_size = midpoint
        self.font_size_slider.blockSignals(True)
        self.font_size_slider.setValue(self.font_size)
        self.font_size_slider.blockSignals(False)
        
        self.txt_script.setFontPointSize(self.font_size)
        
        self.font_size_display = QLabel(str(self.font_size))
        self.font_size_display.setMinimumWidth(30)
        font_size_layout.addWidget(self.font_size_display)
        
        font_size_layout.addStretch()
        toolbar_layout.addWidget(self.font_size_container)
        
        # Buttons row
        buttons_layout = QHBoxLayout()
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.addStretch()
        
        # Collapse toolbar button
        self.btn_collapse_toolbar = QPushButton("▼")
        self.btn_collapse_toolbar.setToolTip("Collapse Toolbar")
        self.btn_collapse_toolbar.setStyleSheet("""
            QPushButton {
                background-color: #555;
                color: white;
                font-weight: bold;
                font-size: 12px;
                padding: 4px 8px;
                border-radius: 3px;
                border: 1px solid #777;
                min-width: 24px;
                max-width: 24px;
                min-height: 24px;
                max-height: 24px;
            }
            QPushButton:hover {
                background-color: #666;
                border-color: #888;
            }
        """)
        self.btn_collapse_toolbar.clicked.connect(self._toggle_toolbar)
        buttons_layout.addWidget(self.btn_collapse_toolbar)
        
        # Exit fullscreen button
        self.btn_exit_fullscreen = QPushButton()
        self.btn_exit_fullscreen.setToolTip("Exit Fullscreen (Esc)")
        self.btn_exit_fullscreen.setStyleSheet("""
            QPushButton {
                background-color: #555;
                color: white;
                font-weight: bold;
                font-size: 14px;
                padding: 4px 8px;
                border-radius: 3px;
                border: 1px solid #777;
                min-width: 28px;
                max-width: 28px;
                min-height: 28px;
                max-height: 28px;
            }
            QPushButton:hover {
                background-color: #666;
                border-color: #888;
            }
        """)
        exit_icon = _load_svg_icon(EXIT_FULLSCREEN_ICON_FILENAME, 18)
        if not exit_icon.isNull():
            self.btn_exit_fullscreen.setIcon(exit_icon)
            self.btn_exit_fullscreen.setIconSize(QSize(18, 18))
        self.btn_exit_fullscreen.setAccessibleName("Exit Fullscreen")
        self.btn_exit_fullscreen.clicked.connect(self.close)
        buttons_layout.addWidget(self.btn_exit_fullscreen)
        
        toolbar_layout.addLayout(buttons_layout)
        
        # Track toolbar collapsed state - start collapsed
        self.toolbar_collapsed = True
        # Hide font size controls initially
        self.font_size_container.hide()
        # Set button to expand icon initially
        self.btn_collapse_toolbar.setText("▲")
        self.btn_collapse_toolbar.setToolTip("Expand Toolbar")
        
        # Use splitter to make toolbar resizable
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.addWidget(self.txt_script)
        self.splitter.addWidget(self.fullscreen_rehearse_toolbar)
        # Set initial sizes: script takes most space, toolbar gets minimal height
        self.splitter.setSizes([1000, 40])
        self.splitter.setCollapsible(0, False)  # Don't allow script area to collapse
        self.splitter.setCollapsible(1, False)  # Don't allow toolbar to collapse completely
        
        layout.addWidget(self.splitter)
        
        # Update script content
        self._update_script_content()
    
    def _copy_character_controls(self) -> None:
        """Copy character controls from the main rehearse tab."""
        # Clear existing controls
        while self.colors_layout.count():
            item = self.colors_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())
        
        if not self.rehearse_tab.current_parse:
            return
        
        from core.nlp_processor import list_characters
        characters = list_characters(self.rehearse_tab.current_parse, sort_by_freq=True)
        
        # Create button group for radio buttons
        button_group = QButtonGroup(self)
        
        for char in characters:
            char_upper = char.upper().strip()
            row = QHBoxLayout()
            row.setSpacing(10)
            
            # Rehearse toggle (radio button)
            rehearse_radio = QRadioButton()
            rehearse_radio.setToolTip("Select this character to rehearse as")
            # Sync with main tab's radio button
            if char_upper in self.rehearse_tab.character_rehearse_radios:
                rehearse_radio.setChecked(self.rehearse_tab.character_rehearse_radios[char_upper].isChecked())
            rehearse_radio.toggled.connect(partial(self._on_rehearse_toggled, char))
            button_group.addButton(rehearse_radio)
            row.addWidget(rehearse_radio)
            
            # Character name
            label = QLabel(char)
            label.setMinimumWidth(150)
            row.addWidget(label)
            
            # Color button (read-only display)
            btn = QPushButton()
            btn.setFixedSize(100, 30)
            current_color = self.rehearse_tab.app_config.get_character_color(char)
            self._update_color_button(btn, current_color)
            row.addWidget(btn)
            
            # Visibility toggle
            visibility_label = QLabel("Visibility")
            row.addWidget(visibility_label)
            visibility_checkbox = QCheckBox()
            if char_upper in self.rehearse_tab.character_visibility_checkboxes:
                visibility_checkbox.setChecked(self.rehearse_tab.character_visibility_checkboxes[char_upper].isChecked())
            visibility_checkbox.stateChanged.connect(partial(self._on_visibility_changed, char))
            row.addWidget(visibility_checkbox)
            
            # Hieroglyphs toggle
            hieroglyphs_label = QLabel("Hieroglyphs")
            row.addWidget(hieroglyphs_label)
            hieroglyphs_checkbox = QCheckBox()
            if char_upper in self.rehearse_tab.character_hieroglyphs_checkboxes:
                hieroglyphs_checkbox.setChecked(self.rehearse_tab.character_hieroglyphs_checkboxes[char_upper].isChecked())
            hieroglyphs_checkbox.stateChanged.connect(partial(self._on_hieroglyphs_changed, char))
            row.addWidget(hieroglyphs_checkbox)
            
            row.addStretch()
            self.colors_layout.addLayout(row)
        
        self.colors_layout.addStretch()
    
    def _clear_layout(self, layout) -> None:
        """Recursively clear a layout."""
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())
    
    def _update_color_button(self, btn: QPushButton, color: Optional[str]) -> None:
        """Update a color button's appearance."""
        if color is None or color == NO_HIGHLIGHT:
            btn.setText("")
            btn.setStyleSheet("""
                QPushButton {
                    background-color: white;
                    border: 2px solid #ccc;
                    border-radius: 3px;
                }
                QPushButton:hover {
                    border-color: #999;
                    background-color: #f5f5f5;
                }
            """)
            btn.setToolTip("No Highlight")
        else:
            btn.setText("")
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {color};
                    border: 2px solid #999;
                    border-radius: 3px;
                }}
                QPushButton:hover {{
                    border-color: #333;
                    border-width: 3px;
                }}
            """)
            btn.setToolTip(f"Color: {color}")
    
    def _on_rehearse_toggled(self, character: str, checked: bool) -> None:
        """Handle rehearse radio button toggle in fullscreen."""
        if checked:
            # Update main tab
            self.rehearse_tab.set_character(character)
            self._update_script_content()
    
    def _on_visibility_changed(self, character: str, state: int) -> None:
        """Handle visibility checkbox change in fullscreen."""
        char_upper = character.upper().strip()
        if char_upper in self.rehearse_tab.character_visibility_checkboxes:
            self.rehearse_tab.character_visibility_checkboxes[char_upper].setChecked(state == Qt.CheckState.Checked.value)
        self._update_script_content()
    
    def _on_hieroglyphs_changed(self, character: str, state: int) -> None:
        """Handle hieroglyphs checkbox change in fullscreen."""
        char_upper = character.upper().strip()
        if char_upper in self.rehearse_tab.character_hieroglyphs_checkboxes:
            self.rehearse_tab.character_hieroglyphs_checkboxes[char_upper].setChecked(state == Qt.CheckState.Checked.value)
        self._update_script_content()
    
    def _on_font_size_changed(self, value: int) -> None:
        """Handle font size slider change."""
        self.font_size = value
        self.font_size_display.setText(str(value))
        
        # Apply font size to entire document
        cursor = self.txt_script.textCursor()
        cursor.beginEditBlock()
        cursor.select(QTextCursor.SelectionType.Document)
        fmt = QTextCharFormat()
        fmt.setFontPointSize(self.font_size)
        fmt.setFontFamily("Courier Prime")
        cursor.mergeCharFormat(fmt)
        cursor.endEditBlock()
    
    def _toggle_toolbar(self) -> None:
        """Toggle toolbar collapsed/expanded state."""
        self.toolbar_collapsed = not self.toolbar_collapsed
        
        if self.toolbar_collapsed:
            # Hide font size controls
            self.font_size_container.hide()
            # Change button icon to expand
            self.btn_collapse_toolbar.setText("▲")
            self.btn_collapse_toolbar.setToolTip("Expand Toolbar")
            # Minimize toolbar height
            self.splitter.setSizes([1000, 40])
        else:
            # Show font size controls
            self.font_size_container.show()
            # Change button icon to collapse
            self.btn_collapse_toolbar.setText("▼")
            self.btn_collapse_toolbar.setToolTip("Collapse Toolbar")
            # Restore toolbar height
            self.splitter.setSizes([1000, 80])
    
    def _update_script_content(self) -> None:
        """Update the script content in fullscreen window."""
        # Copy the formatted text from the main tab
        self.txt_script.setDocument(self.rehearse_tab.txt_script.document().clone(self))
        # Apply font size to entire document
        cursor = self.txt_script.textCursor()
        cursor.beginEditBlock()
        cursor.select(QTextCursor.SelectionType.Document)
        fmt = QTextCharFormat()
        fmt.setFontPointSize(self.font_size)
        fmt.setFontFamily("Courier Prime")
        cursor.mergeCharFormat(fmt)
        cursor.endEditBlock()
    
    def eventFilter(self, obj, event) -> bool:
        """Filter events to catch escape key in text edit."""
        if obj == self.txt_script and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape:
                self.close()
                return True
        return super().eventFilter(obj, event)
    
    def keyPressEvent(self, event) -> None:
        """Handle key press events."""
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        super().keyPressEvent(event)
    
    def closeEvent(self, event) -> None:
        """Handle window close."""
        if self.rehearse_tab.fullscreen_window == self:
            self.rehearse_tab.fullscreen_window = None
        super().closeEvent(event)

