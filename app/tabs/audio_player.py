# app/tabs/audio_player.py
"""
Audio player widget for playing audio files in popout windows.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QUrl, QTimer, QSize
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QSlider, QStyle
)


class AudioPlayer(QWidget):
    """Audio player widget with playback controls."""
    
    # Supported audio file extensions
    SUPPORTED_FORMATS = {
        '.mp3', '.wav', '.ogg', '.m4a', '.aac', '.flac', '.wma',
        '.opus', '.mp4', '.m4v', '.3gp', '.3g2', '.mkv', '.webm'
    }
    
    def __init__(self, file_path: Path, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.file_path = Path(file_path)
        self.audio_output = QAudioOutput()
        self.player = QMediaPlayer()
        self.player.setAudioOutput(self.audio_output)
        
        self.position_timer = QTimer()
        self.position_timer.timeout.connect(self._update_position)
        self.position_timer.setInterval(100)  # Update every 100ms
        
        self._setup_ui()
        self._connect_signals()
        self._load_file()
    
    def _setup_ui(self) -> None:
        """Build the UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)
        
        # File name label
        self.file_label = QLabel(self.file_path.name)
        self.file_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.file_label.setStyleSheet("font-weight: bold; font-size: 14pt;")
        layout.addWidget(self.file_label)
        
        # Time labels and progress slider
        time_layout = QHBoxLayout()
        
        self.position_label = QLabel("0:00")
        self.position_label.setMinimumWidth(60)
        time_layout.addWidget(self.position_label)
        
        self.progress_slider = QSlider(Qt.Orientation.Horizontal)
        self.progress_slider.setMinimum(0)
        self.progress_slider.setMaximum(0)
        self.progress_slider.setMaximumWidth(450)  # Limit width to keep window compact
        self.progress_slider.sliderPressed.connect(self._on_slider_pressed)
        self.progress_slider.sliderReleased.connect(self._on_slider_released)
        self.progress_slider.valueChanged.connect(self._on_slider_value_changed)
        time_layout.addWidget(self.progress_slider, stretch=1)
        
        self.duration_label = QLabel("0:00")
        self.duration_label.setMinimumWidth(60)
        self.duration_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        time_layout.addWidget(self.duration_label)
        
        layout.addLayout(time_layout)
        
        # Control buttons
        controls_layout = QHBoxLayout()
        controls_layout.addStretch()
        
        self.btn_play_pause = QPushButton()
        self.btn_play_pause.setIcon(self.style().standardIcon(
            self.style().StandardPixmap.SP_MediaPlay
        ))
        self.btn_play_pause.setIconSize(QSize(32, 32))
        self.btn_play_pause.clicked.connect(self._on_play_pause)
        self.btn_play_pause.setToolTip("Play/Pause")
        controls_layout.addWidget(self.btn_play_pause)
        
        self.btn_stop = QPushButton()
        self.btn_stop.setIcon(self.style().standardIcon(
            self.style().StandardPixmap.SP_MediaStop
        ))
        self.btn_stop.setIconSize(QSize(32, 32))
        self.btn_stop.clicked.connect(self._on_stop)
        self.btn_stop.setToolTip("Stop")
        controls_layout.addWidget(self.btn_stop)
        
        controls_layout.addStretch()
        
        layout.addLayout(controls_layout)
        
        # Volume control
        volume_layout = QHBoxLayout()
        volume_label = QLabel("Volume:")
        volume_layout.addWidget(volume_label)
        
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setMinimum(0)
        self.volume_slider.setMaximum(100)
        self.volume_slider.setValue(100)
        self.volume_slider.setMaximumWidth(200)
        self.volume_slider.valueChanged.connect(self._on_volume_changed)
        volume_layout.addWidget(self.volume_slider)
        
        self.volume_label = QLabel("100%")
        self.volume_label.setMinimumWidth(50)
        volume_layout.addWidget(self.volume_label)
        
        volume_layout.addStretch()
        layout.addLayout(volume_layout)
        
        # Don't add stretch - let the widget size to its content
        # layout.addStretch()
    
    def sizeHint(self) -> QSize:
        """Return the preferred size for the audio player."""
        # Calculate approximate size based on content
        # File label: ~30px height
        # Progress slider row: ~30px height
        # Control buttons row: ~50px height
        # Volume control row: ~30px height
        # Margins: 20px top + 20px bottom = 40px
        # Spacing: 10px * 3 = 30px
        height = 30 + 30 + 50 + 30 + 40 + 30  # ~210px
        
        # Width: enough for controls, labels, and progress slider
        # Progress slider max width is 450px, plus labels (60px each) and margins (40px)
        width = 450 + 60 + 60 + 40  # ~610px
        
        return QSize(width, height)
    
    def _connect_signals(self) -> None:
        """Connect player signals."""
        self.player.playbackStateChanged.connect(self._on_playback_state_changed)
        self.player.durationChanged.connect(self._on_duration_changed)
        self.player.errorOccurred.connect(self._on_error)
        self.player.mediaStatusChanged.connect(self._on_media_status_changed)
    
    def _load_file(self) -> None:
        """Load the audio file."""
        if not self.file_path.exists():
            self._show_error("File not found")
            return
        
        url = QUrl.fromLocalFile(str(self.file_path.resolve()))
        self.player.setSource(url)
    
    def _on_play_pause(self) -> None:
        """Handle play/pause button click."""
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()
            if not self.position_timer.isActive():
                self.position_timer.start()
    
    def _on_stop(self) -> None:
        """Handle stop button click."""
        self.player.stop()
        self.position_timer.stop()
        self.progress_slider.setValue(0)
        self.position_label.setText("0:00")
    
    def _on_volume_changed(self, value: int) -> None:
        """Handle volume slider change."""
        self.audio_output.setVolume(value / 100.0)
        self.volume_label.setText(f"{value}%")
    
    def _on_playback_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        """Handle playback state change."""
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.btn_play_pause.setIcon(self.style().standardIcon(
                self.style().StandardPixmap.SP_MediaPause
            ))
            if not self.position_timer.isActive():
                self.position_timer.start()
        elif state == QMediaPlayer.PlaybackState.PausedState:
            self.btn_play_pause.setIcon(self.style().standardIcon(
                self.style().StandardPixmap.SP_MediaPlay
            ))
        else:  # StoppedState
            self.btn_play_pause.setIcon(self.style().standardIcon(
                self.style().StandardPixmap.SP_MediaPlay
            ))
            self.position_timer.stop()
    
    def _on_duration_changed(self, duration: int) -> None:
        """Handle duration change."""
        if duration > 0:
            self.progress_slider.setMaximum(duration)
            self.duration_label.setText(self._format_time(duration))
    
    def _on_media_status_changed(self, status) -> None:
        """Handle media status change."""
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._on_stop()
    
    def _on_error(self, error) -> None:
        """Handle player error."""
        error_string = self.player.errorString()
        self._show_error(f"Error playing audio: {error_string}")
    
    def _update_position(self) -> None:
        """Update position slider and label."""
        position = self.player.position()
        if not self.progress_slider.isSliderDown():
            self.progress_slider.setValue(position)
        self.position_label.setText(self._format_time(position))
    
    def _on_slider_pressed(self) -> None:
        """Handle slider press - pause updates."""
        pass
    
    def _on_slider_released(self) -> None:
        """Handle slider release - seek to position."""
        position = self.progress_slider.value()
        self.player.setPosition(position)
    
    def _on_slider_value_changed(self, value: int) -> None:
        """Handle slider value change (only when dragging)."""
        if self.progress_slider.isSliderDown():
            # Update label while dragging
            self.position_label.setText(self._format_time(value))
    
    def _format_time(self, milliseconds: int) -> str:
        """Format milliseconds as MM:SS."""
        total_seconds = milliseconds // 1000
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes}:{seconds:02d}"
    
    def _show_error(self, message: str) -> None:
        """Show error message."""
        error_label = QLabel(message)
        error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        error_label.setStyleSheet("color: red; font-weight: bold;")
        self.layout().addWidget(error_label)
    
    def closeEvent(self, event) -> None:
        """Clean up on close."""
        self.player.stop()
        self.position_timer.stop()
        super().closeEvent(event)
    
    @staticmethod
    def is_audio_file(file_path: Path) -> bool:
        """Check if a file is a supported audio file."""
        return file_path.suffix.lower() in AudioPlayer.SUPPORTED_FORMATS

