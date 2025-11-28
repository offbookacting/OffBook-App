# app/tabs/memorize_tab.py
"""
Memorize tab - tools for memorizing lines and scenes.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional, List

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextCharFormat, QColor, QTextCursor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton,
    QLabel, QSlider, QGroupBox, QFileDialog, QMessageBox
)
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtCore import QUrl

from app.config import AppConfig
from core.tts import PiperTTS, PiperTTSError

from core.nlp_processor import ScriptParse, blocks_for_character, DialogueBlock


class MemorizeTab(QWidget):
    """Memorize tab with tools for line memorization."""
    
    def __init__(self, config: AppConfig, library_presets_dir: Optional[Path] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.current_parse: Optional[ScriptParse] = None
        self.current_character: Optional[str] = None
        self.current_blocks: List[DialogueBlock] = []
        self.current_block_index: int = 0
        self.mode: str = "full"  # "full", "fade", "blank"
        self.config = config
        self.library_presets_dir = library_presets_dir
        self._tts_engine: Optional[PiperTTS] = None
        self._tts_error: Optional[str] = None
        self.audio_output = QAudioOutput()
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio_output)
        self._current_audio_path: Optional[Path] = None
        self.player.mediaStatusChanged.connect(self._on_media_status_changed)
        self.player.errorOccurred.connect(self._on_player_error)
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Build the UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Controls
        controls = QGroupBox("Memorization Mode")
        controls_layout = QVBoxLayout()
        
        mode_layout = QHBoxLayout()
        self.btn_full = QPushButton("Full Text")
        self.btn_full.setCheckable(True)
        self.btn_full.setChecked(True)
        self.btn_full.clicked.connect(lambda: self._set_mode("full"))
        mode_layout.addWidget(self.btn_full)
        
        self.btn_fade = QPushButton("Fade Out")
        self.btn_fade.setCheckable(True)
        self.btn_fade.clicked.connect(lambda: self._set_mode("fade"))
        mode_layout.addWidget(self.btn_fade)
        
        self.btn_blank = QPushButton("Blank Lines")
        self.btn_blank.setCheckable(True)
        self.btn_blank.clicked.connect(lambda: self._set_mode("blank"))
        mode_layout.addWidget(self.btn_blank)
        
        controls_layout.addLayout(mode_layout)

        # TTS controls
        tts_layout = QHBoxLayout()
        self.btn_speak = QPushButton("Speak Block")
        self.btn_speak.clicked.connect(self._speak_current_block)
        tts_layout.addWidget(self.btn_speak)

        self.btn_choose_voice = QPushButton("Select Piper Voice…")
        self.btn_choose_voice.clicked.connect(self._choose_voice_model)
        tts_layout.addWidget(self.btn_choose_voice)

        tts_layout.addStretch()
        controls_layout.addLayout(tts_layout)
        
        # Navigation
        nav_layout = QHBoxLayout()
        self.btn_prev = QPushButton("← Previous")
        self.btn_prev.clicked.connect(self._on_previous)
        nav_layout.addWidget(self.btn_prev)
        
        self.lbl_block_info = QLabel("Block 0 of 0")
        nav_layout.addWidget(self.lbl_block_info)
        
        self.btn_next = QPushButton("Next →")
        self.btn_next.clicked.connect(self._on_next)
        nav_layout.addWidget(self.btn_next)
        
        controls_layout.addLayout(nav_layout)
        
        # Fade settings
        fade_layout = QHBoxLayout()
        fade_layout.addWidget(QLabel("Fade Level:"))
        self.slider_fade = QSlider(Qt.Orientation.Horizontal)
        self.slider_fade.setMinimum(0)
        self.slider_fade.setMaximum(100)
        self.slider_fade.setValue(50)
        self.slider_fade.valueChanged.connect(self._on_fade_changed)
        fade_layout.addWidget(self.slider_fade)
        self.lbl_fade_value = QLabel("50%")
        fade_layout.addWidget(self.lbl_fade_value)
        controls_layout.addLayout(fade_layout)
        
        controls.setLayout(controls_layout)
        layout.addWidget(controls)
        
        # Text display - formatted like read tab
        self.txt_display = QTextEdit()
        self.txt_display.setReadOnly(True)
        self.txt_display.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.txt_display.setFontFamily("Courier Prime")
        self.txt_display.setFontPointSize(14)
        self.txt_display.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)  # Disable horizontal scroll
        # Set white background and black text
        self.txt_display.setStyleSheet("QTextEdit { background-color: white; color: black; }")
        layout.addWidget(self.txt_display, stretch=1)

        self._update_tts_buttons()
    
    def set_script(self, script_parse: Optional[ScriptParse], character: Optional[str] = None) -> None:
        """Set the script and character for memorization."""
        self.current_parse = script_parse
        self.current_character = character
        
        if script_parse and character:
            self.current_blocks = blocks_for_character(script_parse, character)
            self.current_block_index = 0
            self._update_display()
        else:
            self.current_blocks = []
            self.current_block_index = 0
            self.txt_display.clear()
            self.lbl_block_info.setText("No character selected")
        self._update_tts_buttons()
    
    def _set_mode(self, mode: str) -> None:
        """Set memorization mode."""
        self.mode = mode
        self.btn_full.setChecked(mode == "full")
        self.btn_fade.setChecked(mode == "fade")
        self.btn_blank.setChecked(mode == "blank")
        self._update_display()
    
    def _on_previous(self) -> None:
        """Go to previous block."""
        if self.current_block_index > 0:
            self.current_block_index -= 1
            self._update_display()
    
    def _on_next(self) -> None:
        """Go to next block."""
        if self.current_block_index < len(self.current_blocks) - 1:
            self.current_block_index += 1
            self._update_display()
    
    def _on_fade_changed(self, value: int) -> None:
        """Handle fade level change."""
        self.lbl_fade_value.setText(f"{value}%")
        if self.mode == "fade":
            self._update_display()
    
    def _update_display(self) -> None:
        """Update the display based on current mode and block."""
        if not self.current_blocks or self.current_block_index >= len(self.current_blocks):
            self.txt_display.clear()
            self.lbl_block_info.setText("No blocks available")
            return
        
        block = self.current_blocks[self.current_block_index]
        self.lbl_block_info.setText(f"Block {self.current_block_index + 1} of {len(self.current_blocks)}")
        
        if self.mode == "full":
            self._show_full_text(block)
        elif self.mode == "fade":
            self._show_fade_text(block)
        elif self.mode == "blank":
            self._show_blank_text(block)
    
    def _show_full_text(self, block: DialogueBlock) -> None:
        """Show full text."""
        text = f"{block.speaker}\n\n{block.text}"
        self.txt_display.clear()
        self.txt_display.setPlainText(text)
    
    def _show_fade_text(self, block: DialogueBlock) -> None:
        """Show text with fade effect."""
        fade_level = self.slider_fade.value() / 100.0
        words = block.text.split()
        num_visible = int(len(words) * (1 - fade_level))
        
        visible_text = " ".join(words[:num_visible])
        faded_text = " ".join(words[num_visible:])
        
        self.txt_display.clear()
        cursor = self.txt_display.textCursor()
        
        # Add speaker
        cursor.insertText(f"{block.speaker}\n\n")
        
        # Add visible text
        cursor.insertText(visible_text + " ")
        
        # Add faded text
        fmt = QTextCharFormat()
        alpha = int(255 * fade_level)
        fmt.setForeground(QColor(0, 0, 0, 255 - alpha))
        cursor.mergeCharFormat(fmt)
        cursor.insertText(faded_text)
    
    def _show_blank_text(self, block: DialogueBlock) -> None:
        """Show text with blanked lines."""
        lines = block.text.splitlines()
        blanked_lines = []
        for i, line in enumerate(lines):
            if i % 2 == 0:  # Show even lines
                blanked_lines.append(line)
            else:  # Blank odd lines
                blanked_lines.append("_" * len(line))
        
        text = f"{block.speaker}\n\n" + "\n".join(blanked_lines)
        self.txt_display.clear()
        self.txt_display.setPlainText(text)

    # ---------- TTS ----------

    def _get_tts_engine(self) -> Optional[PiperTTS]:
        """Get TTS engine, creating it lazily if needed."""
        if self._tts_engine is None and self._tts_error is None:
            try:
                self._tts_engine = PiperTTS(
                    model_path=self.config.tts_model_path(),
                    speaker=self.config.tts_speaker(),
                )
            except PiperTTSError as e:
                self._tts_error = str(e)
                return None
        return self._tts_engine

    def _update_tts_buttons(self) -> None:
        tts_engine = self._get_tts_engine()
        available = tts_engine is not None and tts_engine.is_available() if tts_engine else False
        self.btn_speak.setEnabled(available and bool(self.current_blocks))

    def _choose_voice_model(self) -> None:
        # Check if TTS is available first
        tts_engine = self._get_tts_engine()
        if tts_engine is None:
            if self._tts_error:
                QMessageBox.warning(self, "TTS Not Available", self._tts_error)
            else:
                QMessageBox.warning(self, "TTS Not Available", "TTS engine could not be initialized.")
            return
        
        # Start in library presets directory if available, otherwise use empty string
        start_dir = str(self.library_presets_dir) if self.library_presets_dir and self.library_presets_dir.exists() else ""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Piper Voice Model",
            start_dir,
            "Piper Models (*.onnx *.onnx.gz);;All Files (*.*)",
        )
        if not path:
            return
        try:
            # Find config file
            config_path = None
            model_path_obj = Path(path)
            if model_path_obj.exists():
                config_path_obj = model_path_obj.with_suffix('.onnx.json')
                if config_path_obj.exists():
                    config_path = str(config_path_obj)
            
            tts_engine.set_model(path, config_path)
            try:
                self.config.set_tts_model_path(path)
            except ValueError as e:
                QMessageBox.warning(self, "Invalid Model Path", str(e))
                return
            self._update_tts_buttons()
        except PiperTTSError as e:
            QMessageBox.warning(self, "Piper Error", str(e))

    def _speak_current_block(self) -> None:
        if not self.current_blocks or self.current_block_index >= len(self.current_blocks):
            return
        
        tts_engine = self._get_tts_engine()
        if tts_engine is None:
            if self._tts_error:
                QMessageBox.warning(self, "TTS Not Available", self._tts_error)
            else:
                QMessageBox.warning(self, "TTS Not Available", "TTS engine could not be initialized.")
            self._update_tts_buttons()
            return
        
        block = self.current_blocks[self.current_block_index]
        text = f"{block.speaker}. {block.text}"
        self._cleanup_audio()
        try:
            audio_path = tts_engine.synthesize(text)
        except PiperTTSError as e:
            QMessageBox.warning(self, "Piper Error", str(e))
            self._update_tts_buttons()
            return

        self._current_audio_path = audio_path
        self.player.setSource(QUrl.fromLocalFile(str(audio_path)))
        self.player.play()

    def _on_media_status_changed(self, status) -> None:
        if status in (QMediaPlayer.MediaStatus.EndOfMedia, QMediaPlayer.MediaStatus.InvalidMedia):
            self._cleanup_audio()

    def _on_player_error(self, error) -> None:
        self._cleanup_audio()
        QMessageBox.warning(self, "Audio Playback Error", self.player.errorString())

    def _cleanup_audio(self) -> None:
        if self.player.playbackState() != QMediaPlayer.PlaybackState.StoppedState:
            self.player.stop()
        if self._current_audio_path and self._current_audio_path.exists():
            try:
                self._current_audio_path.unlink()
            except Exception:
                pass
            self._current_audio_path = None

