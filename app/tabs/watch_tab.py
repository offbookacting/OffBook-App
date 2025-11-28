from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtMultimediaWidgets import QVideoWidget
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QSlider,
    QSizePolicy,
)


class WatchTab(QWidget):
    """Simple video player tab with playback controls."""

    SUPPORTED_FORMATS = {
        ".mp4",
        ".m4v",
        ".mov",
        ".avi",
        ".mkv",
        ".mpg",
        ".mpeg",
        ".wmv",
        ".webm",
        ".flv",
    }

    def __init__(self, file_path: Path, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.file_path = Path(file_path)
        self._slider_is_pressed = False

        self.audio_output = QAudioOutput()
        self.player = QMediaPlayer()
        self.player.setAudioOutput(self.audio_output)

        self.video_widget = QVideoWidget()
        self.player.setVideoOutput(self.video_widget)

        self._setup_ui()
        self._connect_signals()
        self._load_file()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.title_label = QLabel(self.file_path.name)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setStyleSheet("font-weight: bold; font-size: 14pt;")
        layout.addWidget(self.title_label)

        self.video_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.video_widget, stretch=1)

        slider_row = QHBoxLayout()
        self.position_label = QLabel("0:00")
        self.position_label.setMinimumWidth(60)
        slider_row.addWidget(self.position_label)

        self.scrub_slider = QSlider(Qt.Orientation.Horizontal)
        self.scrub_slider.setMinimum(0)
        self.scrub_slider.setMaximum(0)
        self.scrub_slider.sliderPressed.connect(self._on_slider_pressed)
        self.scrub_slider.sliderReleased.connect(self._on_slider_released)
        self.scrub_slider.sliderMoved.connect(self._on_slider_moved)
        slider_row.addWidget(self.scrub_slider, stretch=1)

        self.duration_label = QLabel("0:00")
        self.duration_label.setMinimumWidth(60)
        self.duration_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        slider_row.addWidget(self.duration_label)

        layout.addLayout(slider_row)

        controls = QHBoxLayout()
        controls.addStretch()

        self.play_pause_button = QPushButton()
        self.play_pause_button.setIcon(self.style().standardIcon(self.style().StandardPixmap.SP_MediaPlay))
        self.play_pause_button.clicked.connect(self._toggle_play_pause)
        self.play_pause_button.setToolTip("Play/Pause")
        controls.addWidget(self.play_pause_button)

        controls.addStretch()
        layout.addLayout(controls)

    def _connect_signals(self) -> None:
        self.player.playbackStateChanged.connect(self._on_playback_state_changed)
        self.player.positionChanged.connect(self._on_position_changed)
        self.player.durationChanged.connect(self._on_duration_changed)
        self.player.errorOccurred.connect(self._on_error)

    def _load_file(self) -> None:
        if not self.file_path.exists():
            self.title_label.setText("File not found")
            return

        url = QUrl.fromLocalFile(str(self.file_path.resolve()))
        self.player.setSource(url)
        self.player.play()

    def _toggle_play_pause(self) -> None:
        state = self.player.playbackState()
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _on_playback_state_changed(self, state: QMediaPlayer.PlaybackState) -> None:
        icon = self.style().StandardPixmap.SP_MediaPlay
        if state == QMediaPlayer.PlaybackState.PlayingState:
            icon = self.style().StandardPixmap.SP_MediaPause
        self.play_pause_button.setIcon(self.style().standardIcon(icon))

    def _on_position_changed(self, position: int) -> None:
        if not self._slider_is_pressed:
            self.scrub_slider.setValue(position)
        self.position_label.setText(self._format_time(position))

    def _on_duration_changed(self, duration: int) -> None:
        self.scrub_slider.setMaximum(duration if duration > 0 else 0)
        self.duration_label.setText(self._format_time(duration))

    def _on_slider_pressed(self) -> None:
        self._slider_is_pressed = True

    def _on_slider_released(self) -> None:
        self._slider_is_pressed = False
        self.player.setPosition(self.scrub_slider.value())

    def _on_slider_moved(self, value: int) -> None:
        if self._slider_is_pressed:
            self.position_label.setText(self._format_time(value))

    def _on_error(self, error: QMediaPlayer.Error, message: str) -> None:
        if error != QMediaPlayer.Error.NoError:
            self.title_label.setText(f"Playback error: {message}")

    @staticmethod
    def _format_time(milliseconds: int) -> str:
        if milliseconds <= 0:
            return "0:00"
        total_seconds = milliseconds // 1000
        minutes, seconds = divmod(total_seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.player.stop()
        super().closeEvent(event)

    @staticmethod
    def is_video_file(file_path: Path) -> bool:
        return file_path.suffix.lower() in WatchTab.SUPPORTED_FORMATS

