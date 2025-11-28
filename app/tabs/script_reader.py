# app/tabs/script_reader.py
"""
Script reader that reads entire scripts with different voices per character.
"""
from __future__ import annotations
from pathlib import Path
from typing import Dict, List, Optional
import re

from PyQt6.QtCore import QObject, pyqtSignal, QUrl, QTimer
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer

from core.tts import PiperTTS, PiperTTSError
from core.nlp_processor import ScriptParse, DialogueBlock
from app.tabs.voice_selection_dialog import VoiceConfig


class ScriptReader(QObject):
    """Reads scripts with different voices for each character."""
    
    # Signals
    progress = pyqtSignal(str)  # Current character/block being read
    word_highlight = pyqtSignal(int, int)  # start_pos, end_pos for word highlighting
    finished = pyqtSignal()  # Reading finished
    error = pyqtSignal(str)  # Error occurred
    
    def __init__(
        self, 
        script_parse: ScriptParse, 
        voice_configs: Dict[str, VoiceConfig], 
        parent=None,
        text_widget=None,
        start_block: int = 0,
        default_model_path: Optional[str] = None,
        prerender_manager=None,
        project=None,
        read_character_names: bool = True
    ):
        super().__init__(parent)
        self.script_parse = script_parse
        self.voice_configs = voice_configs
        self.text_widget = text_widget
        self.default_model_path = default_model_path
        self.audio_output = QAudioOutput()
        self.player = QMediaPlayer()
        self.player.setAudioOutput(self.audio_output)
        self.current_audio_files: List[Path] = []
        self.is_playing = False
        self.is_paused = False
        self.current_block_index = start_block
        self.blocks_to_read: List[tuple[DialogueBlock, VoiceConfig]] = []
        self.current_word_timer: Optional[QTimer] = None
        self.current_block_text = ""
        self.current_block_display_text = ""  # Text as displayed in widget (without "CHARACTER. " prefix)
        self.current_word_index = 0
        self.current_block_start_pos = 0
        self.current_audio_duration_ms = 0  # Duration of current audio in milliseconds
        self.current_voice_config: Optional[VoiceConfig] = None  # Current voice config for length_scale
        self.prerender_manager = prerender_manager
        self.project = project
        self.read_character_names = read_character_names
        
        # Connect player signals
        self.player.mediaStatusChanged.connect(self._on_media_status_changed)
        self.player.errorOccurred.connect(self._on_player_error)
        self.player.playbackStateChanged.connect(self._on_playback_state_changed)
        self.player.durationChanged.connect(self._on_duration_changed)
    
    def prepare_reading(self) -> bool:
        """Prepare all audio files for reading."""
        try:
            # Clear previous audio files
            self._cleanup_audio()
            
            # Prepare blocks with voice configs
            self.blocks_to_read = []
            for block in self.script_parse.blocks:
                character = block.speaker
                if character in self.voice_configs:
                    voice_config = self.voice_configs[character]
                    self.blocks_to_read.append((block, voice_config))
                else:
                    # Use first available voice config as fallback
                    if self.voice_configs:
                        fallback_voice = list(self.voice_configs.values())[0]
                        self.blocks_to_read.append((block, fallback_voice))
            
            return True
        except Exception as e:
            self.error.emit(f"Failed to prepare reading: {e}")
            return False
    
    def start_reading(self) -> None:
        """Start reading the script."""
        if not self.blocks_to_read:
            if not self.prepare_reading():
                return
        
        self.is_playing = True
        self.is_paused = False
        if self.current_block_index >= len(self.blocks_to_read):
            self.current_block_index = 0
        self._read_next_block()
    
    def pause_reading(self) -> None:
        """Pause reading."""
        self.is_paused = True
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        if self.current_word_timer:
            self.current_word_timer.stop()
    
    def resume_reading(self) -> None:
        """Resume reading."""
        self.is_paused = False
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PausedState:
            self.player.play()
        if self.current_word_timer:
            self.current_word_timer.start()
    
    def stop_reading(self) -> None:
        """Stop reading."""
        self.is_playing = False
        self.is_paused = False
        if self.player.playbackState() != QMediaPlayer.PlaybackState.StoppedState:
            self.player.stop()
        if self.current_word_timer:
            self.current_word_timer.stop()
            self.current_word_timer = None
        self._cleanup_audio()
    
    def jump_to_block(self, block_index: int) -> None:
        """Jump to a specific block index."""
        if not self.blocks_to_read:
            # Need to prepare blocks first
            if not self.prepare_reading():
                return
        
        if 0 <= block_index < len(self.blocks_to_read):
            # Stop current playback without emitting finished signal
            self.is_playing = False
            self.is_paused = False
            if self.player.playbackState() != QMediaPlayer.PlaybackState.StoppedState:
                self.player.stop()
            if self.current_word_timer:
                self.current_word_timer.stop()
                self.current_word_timer = None
            
            # Set new block index and start reading
            self.current_block_index = block_index
            self.is_playing = True
            self.is_paused = False
            self._read_next_block()
    
    def _read_next_block(self) -> None:
        """Read the next dialogue block."""
        if not self.is_playing or self.current_block_index >= len(self.blocks_to_read):
            self.is_playing = False
            self.finished.emit()
            return
        
        block, voice_config = self.blocks_to_read[self.current_block_index]
        
        # Emit progress
        self.progress.emit(f"{block.speaker}: {block.text[:50]}...")
        
        # Calculate block position in text widget
        if self.text_widget:
            self._calculate_block_position(block)
        
        # Synthesize audio
        try:
            # Resolve model path: use voice config's model, or default model, or try auto-discovery
            model_path = voice_config.model_path
            if not model_path or not model_path.strip() or not Path(model_path).exists():
                model_path = self.default_model_path
            
            # If still no valid model, try auto-discovery (without library_presets_dir since we don't have access to it here)
            if not model_path or not model_path.strip() or not Path(model_path).exists():
                from app.tabs.voice_selection_dialog import VoicePresets
                discovered_model = VoicePresets._find_onnx_model(None)
                if discovered_model and Path(discovered_model).exists():
                    model_path = discovered_model
                else:
                    raise PiperTTSError(
                        f"Preset '{voice_config.name or 'Unknown'}' has no voice model configured for {block.speaker}.\n\n"
                        "Please set a model path for this preset or configure a default model in settings.\n"
                        "No .onnx model files were found in standard locations."
                    )
            
            # Find config file (same directory as model, with .onnx.json extension)
            config_path = None
            model_path_obj = Path(model_path)
            if model_path_obj.exists():
                config_path_obj = model_path_obj.with_suffix('.onnx.json')
                if config_path_obj.exists():
                    config_path = str(config_path_obj)
            
            tts = PiperTTS(
                model_path=model_path,
                config_path=config_path,
                speaker=voice_config.speaker,
                noise_scale=voice_config.noise_scale,
                length_scale=voice_config.length_scale,
                noise_w=voice_config.noise_w,
                sentence_silence_seconds=voice_config.sentence_silence_seconds
            )
            
            # Verify TTS is available
            if not tts.is_available():
                raise PiperTTSError(
                    f"TTS not available for {block.speaker}. "
                    f"Model: {model_path}, "
                    f"Speaker: {voice_config.speaker}. "
                    f"Make sure Piper is installed and the model path is correct."
                )
            
            # Prepare text (character name + dialogue based on read_character_names setting)
            if block.speaker == "NARRATOR":
                # For narrator, check if we should read the character name of the next dialogue block
                text = block.text
                display_text = block.text
                
                # If read_character_names is enabled, check if there's a character block after this narrator block
                if self.read_character_names and self.current_block_index + 1 < len(self.blocks_to_read):
                    next_block, _ = self.blocks_to_read[self.current_block_index + 1]
                    if next_block.speaker != "NARRATOR":
                        # Add character name to narrator text
                        text = f"{block.text} {next_block.speaker}."
                        display_text = block.text  # Display text doesn't change
            else:
                # For character blocks, include character name if enabled
                if self.read_character_names:
                    text = f"{block.speaker}. {block.text}"
                else:
                    text = block.text
                display_text = block.text  # Widget text doesn't include "CHARACTER. " prefix
            self.current_block_text = text
            self.current_block_display_text = display_text
            
            # Try to use prerendered audio first
            audio_path = None
            if self.prerender_manager and self.project:
                try:
                    prerendered_path = self.prerender_manager.get_prerendered_audio_path(
                        self.project, self.current_block_index
                    )
                    if prerendered_path:
                        # Resolve to absolute path and verify
                        prerendered_path = prerendered_path.resolve()
                        if prerendered_path.exists() and prerendered_path.is_file():
                            audio_path = prerendered_path
                except Exception as e:
                    # If there's an error loading prerendered audio, fall back to synthesis
                    import traceback
                    print(f"Warning: Could not load prerendered audio for block {self.current_block_index}: {e}")
                    traceback.print_exc()
                    audio_path = None
            
            # Fall back to on-the-fly synthesis if no prerendered audio
            if not audio_path:
                audio_path = tts.synthesize(text)
                self.current_audio_files.append(audio_path)  # Only track temp files
            
            self.current_voice_config = voice_config  # Store for length_scale
            
            # Play audio first, then start highlighting once duration is known
            self.player.setSource(QUrl.fromLocalFile(str(audio_path)))
            # Duration will be available after media is loaded, which triggers _on_duration_changed
            # We'll start highlighting in _on_duration_changed or after a short delay
            self.player.play()
            
            # Start word highlighting (will be adjusted when duration is known)
            if self.text_widget:
                self._start_word_highlighting()
            
        except PiperTTSError as e:
            self.error.emit(f"TTS error for {block.speaker}: {e}")
            # Continue with next block
            self.current_block_index += 1
            self._read_next_block()
        except Exception as e:
            self.error.emit(f"Error reading block: {e}")
            self.is_playing = False
            self.finished.emit()
    
    def _calculate_block_position(self, block: DialogueBlock) -> None:
        """Calculate the text position of a dialogue block."""
        if not self.text_widget:
            return
        
        # Get full text from widget
        full_text = self.text_widget.toPlainText()
        lines = full_text.split('\n')
        
        # Calculate position based on line numbers
        # block.start_line is the line index in the parsed lines
        start_pos = 0
        
        # Sum up lengths of all lines before the block starts
        # Make sure we don't go out of bounds
        for i in range(min(block.start_line, len(lines))):
            start_pos += len(lines[i]) + 1  # +1 for newline
        
        self.current_block_start_pos = start_pos
    
    def _start_word_highlighting(self) -> None:
        """Start word-by-word highlighting."""
        if not self.text_widget or not self.current_block_text:
            return
        
        # Extract words from text (TTS text, includes character name)
        words = re.findall(r'\S+', self.current_block_text)
        if not words:
            return
        
        # Calculate word duration based on actual audio duration if available
        # Otherwise use a reasonable estimate
        if self.current_audio_duration_ms > 0:
            # Use actual audio duration divided by number of words
            # This accounts for length_scale and actual TTS timing
            word_duration_ms = max(50, int(self.current_audio_duration_ms / len(words)))
        else:
            # Fallback: estimate based on length_scale if available
            length_scale = self.current_voice_config.length_scale if self.current_voice_config else 1.0
            # Base estimate: ~2.5 words per second at normal speed
            # Adjust for length_scale (higher = slower = longer per word)
            base_words_per_second = 2.5 / length_scale
            word_duration_ms = int(1000 / base_words_per_second)
        
        self.current_word_index = 0
        
        # Create timer for word highlighting
        if self.current_word_timer:
            self.current_word_timer.stop()
            self.current_word_timer.deleteLater()
        
        self.current_word_timer = QTimer(self)
        self.current_word_timer.timeout.connect(self._highlight_next_word)
        self.current_word_timer.start(word_duration_ms)
        
        # Highlight first word immediately
        self._highlight_next_word()
    
    def _on_duration_changed(self, duration: int) -> None:
        """Handle audio duration change - update word highlighting timing."""
        if duration > 0:
            old_duration = self.current_audio_duration_ms
            self.current_audio_duration_ms = duration
            
            # Only restart highlighting if we didn't have a duration before
            # This prevents restarting if duration changes slightly
            if old_duration == 0 and self.current_word_timer and self.current_word_timer.isActive():
                # Restart with accurate timing now that we have the duration
                self._start_word_highlighting()
    
    def _highlight_next_word(self) -> None:
        """Highlight the next word."""
        if not self.text_widget or not self.current_block_text or self.is_paused:
            return
        
        # Extract words with their positions in the TTS block text (includes "CHARACTER. " prefix)
        tts_words_with_pos = []
        for match in re.finditer(r'\S+', self.current_block_text):
            tts_words_with_pos.append((match.group(), match.start(), match.end()))
        
        # Extract words with their positions in the display text (without prefix)
        display_words_with_pos = []
        for match in re.finditer(r'\S+', self.current_block_display_text):
            display_words_with_pos.append((match.group(), match.start(), match.end()))
        
        if self.current_word_index >= len(tts_words_with_pos):
            # Done with this block
            if self.current_word_timer:
                self.current_word_timer.stop()
            return
        
        # Skip the character name word(s) in TTS text (e.g., "CHARACTER.")
        # Find how many words to skip (usually 1 word like "CHARACTER." or 2 words like "CHARACTER NAME.")
        tts_word_count = len(tts_words_with_pos)
        display_word_count = len(display_words_with_pos)
        words_to_skip = tts_word_count - display_word_count
        
        # Get the word index in the display text (skip character name words)
        display_word_index = self.current_word_index - words_to_skip
        
        if display_word_index < 0 or display_word_index >= len(display_words_with_pos):
            # Still in character name part, skip highlighting
            self.current_word_index += 1
            return
        
        # Get word and its position in display text (the actual widget text)
        word, word_start_in_display, word_end_in_display = display_words_with_pos[display_word_index]
        
        # Calculate position in full text widget
        start_pos = self.current_block_start_pos + word_start_in_display
        end_pos = self.current_block_start_pos + word_end_in_display
        
        self.word_highlight.emit(start_pos, end_pos)
        self.current_word_index += 1
    
    def _on_media_status_changed(self, status) -> None:
        """Handle media status change."""
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            # Stop word highlighting
            if self.current_word_timer:
                self.current_word_timer.stop()
                self.current_word_timer = None
            
            # Move to next block
            self.current_block_index += 1
            if self.is_playing and not self.is_paused:
                self._read_next_block()
            else:
                self.finished.emit()
        elif status == QMediaPlayer.MediaStatus.InvalidMedia:
            self.error.emit("Invalid audio file")
            self.is_playing = False
            self.finished.emit()
    
    def _on_playback_state_changed(self, state) -> None:
        """Handle playback state change."""
        if state == QMediaPlayer.PlaybackState.PlayingState and not self.is_paused:
            if self.current_word_timer:
                self.current_word_timer.start()
        elif state == QMediaPlayer.PlaybackState.PausedState:
            if self.current_word_timer:
                self.current_word_timer.stop()
    
    def _on_player_error(self, error) -> None:
        """Handle player error."""
        self.error.emit(f"Audio playback error: {self.player.errorString()}")
        self.is_playing = False
        self.finished.emit()
    
    def _cleanup_audio(self) -> None:
        """Clean up temporary audio files."""
        for audio_path in self.current_audio_files:
            if audio_path.exists():
                try:
                    audio_path.unlink()
                except Exception:
                    pass
        self.current_audio_files.clear()
        
        if self.current_word_timer:
            self.current_word_timer.stop()
            self.current_word_timer.deleteLater()
            self.current_word_timer = None
