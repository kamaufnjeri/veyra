from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import Qt, QUrl, Signal, QTimer
from PySide6.QtMultimedia import (
    QAudioOutput,
    QMediaPlayer,
)
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)


class VideoPlayer(QWidget):
    """
    Standalone video player window.

    This widget is intended to be used as a top-level window.

    Example:

        self.video_player = VideoPlayer()
        self.video_player.show()
        self.video_player.load("/path/video.mp4")

    The window owns its own QMediaPlayer, QAudioOutput and
    QVideoWidget.

    IMPORTANT:
        Do not embed this widget inside another QWidget.
    """

    video_loaded = Signal(str)
    position_changed = Signal(int)
    duration_changed = Signal(int)

    playback_started = Signal()
    playback_paused = Signal()
    playback_stopped = Signal()

    error_occurred = Signal(str)
    loading_changed = Signal(bool)

    def __init__(
        self,
        parent: Optional[QWidget] = None,
    ) -> None:

        # ------------------------------------------------------
        # IMPORTANT:
        #
        # parent MUST normally be None.
        #
        # A parented QWidget is not an independent top-level
        # window.
        # ------------------------------------------------------

        super().__init__(parent)

        self.setWindowTitle("Video Player")

        self.setMinimumSize(
            900,
            600,
        )

        self.resize(
            1100,
            700,
        )

        self.setAttribute(
            Qt.WA_DeleteOnClose,
            False,
        )

        # ------------------------------------------------------
        # STATE
        # ------------------------------------------------------

        self.media_player: Optional[
            QMediaPlayer
        ] = None

        self.audio_output: Optional[
            QAudioOutput
        ] = None

        self.video_widget: Optional[
            QVideoWidget
        ] = None

        self.video_path: Optional[str] = None

        self._duration_ms = 0
        self._loading = False
        self._load_generation = 0

        self._signals_connected = False

        # ------------------------------------------------------
        # BUILD
        # ------------------------------------------------------

        self._build_ui()
        self._connect_signals()

    # ==========================================================
    # UI
    # ==========================================================

    def _build_ui(self) -> None:

        root = QVBoxLayout(self)

        root.setContentsMargins(
            10,
            10,
            10,
            10,
        )

        root.setSpacing(8)

        # ------------------------------------------------------
        # VIDEO
        # ------------------------------------------------------

        self.video_container = QWidget()

        self.video_container.setObjectName(
            "VideoContainer"
        )

        video_layout = QVBoxLayout(
            self.video_container
        )

        video_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        self.video_placeholder = QLabel(
            "No video loaded"
        )

        self.video_placeholder.setAlignment(
            Qt.AlignCenter
        )

        self.video_placeholder.setObjectName(
            "VideoPlaceholder"
        )

        video_layout.addWidget(
            self.video_placeholder
        )

        root.addWidget(
            self.video_container,
            1,
        )

        # ------------------------------------------------------
        # CONTROLS
        # ------------------------------------------------------

        controls = QHBoxLayout()

        controls.setSpacing(6)

        self.backward_button = QPushButton(
            "−10s"
        )

        self.play_button = QPushButton(
            "Play"
        )

        self.forward_button = QPushButton(
            "+10s"
        )

        self.stop_button = QPushButton(
            "Stop"
        )

        controls.addWidget(
            self.backward_button
        )

        controls.addWidget(
            self.play_button
        )

        controls.addWidget(
            self.forward_button
        )

        controls.addWidget(
            self.stop_button
        )

        controls.addStretch()

        controls.addWidget(
            QLabel("Speed")
        )

        self.speed_combo = QComboBox()

        self.speed_combo.addItems(
            [
                "0.25x",
                "0.5x",
                "0.75x",
                "1.0x",
                "1.25x",
                "1.5x",
                "2.0x",
            ]
        )

        self.speed_combo.setCurrentText(
            "1.0x"
        )

        controls.addWidget(
            self.speed_combo
        )

        root.addLayout(
            controls
        )

        # ------------------------------------------------------
        # POSITION
        # ------------------------------------------------------

        self.position_slider = QSlider(
            Qt.Horizontal
        )

        self.position_slider.setRange(
            0,
            0,
        )

        root.addWidget(
            self.position_slider
        )

        # ------------------------------------------------------
        # TIME
        # ------------------------------------------------------

        time_row = QHBoxLayout()

        self.current_time_label = QLabel(
            "00:00:00.000"
        )

        self.duration_label = QLabel(
            "00:00:00.000"
        )

        time_row.addWidget(
            self.current_time_label
        )

        time_row.addStretch()

        time_row.addWidget(
            self.duration_label
        )

        root.addLayout(
            time_row
        )

        # ------------------------------------------------------
        # JUMP
        # ------------------------------------------------------

        jump_row = QHBoxLayout()

        jump_row.addWidget(
            QLabel("Jump to")
        )

        self.jump_time_edit = QLineEdit()

        self.jump_time_edit.setPlaceholderText(
            "HH:MM:SS.mmm"
        )

        self.jump_button = QPushButton(
            "Go"
        )

        jump_row.addWidget(
            self.jump_time_edit,
            1,
        )

        jump_row.addWidget(
            self.jump_button
        )

        root.addLayout(
            jump_row
        )

        self._apply_style()

    # ==========================================================
    # SIGNALS
    # ==========================================================

    def _connect_signals(self) -> None:

        if self._signals_connected:
            return

        self._signals_connected = True

        self.play_button.clicked.connect(
            self.toggle_play
        )

        self.stop_button.clicked.connect(
            self.stop
        )

        self.backward_button.clicked.connect(
            lambda: self.seek_relative(
                -10_000
            )
        )

        self.forward_button.clicked.connect(
            lambda: self.seek_relative(
                10_000
            )
        )

        self.position_slider.sliderMoved.connect(
            self.seek
        )

        self.speed_combo.currentTextChanged.connect(
            self.set_speed
        )

        self.jump_button.clicked.connect(
            self.jump_to_time
        )

    # ==========================================================
    # MEDIA
    # ==========================================================

    def _initialize_player(self) -> bool:

        if self.media_player is not None:
            return True

        try:

            self.video_widget = QVideoWidget()

            self.video_widget.setAspectRatioMode(
                Qt.KeepAspectRatio
            )

            self.video_container.layout().addWidget(
                self.video_widget
            )

            self.video_placeholder.hide()

            self.audio_output = QAudioOutput()

            self.media_player = QMediaPlayer()

            self.media_player.setAudioOutput(
                self.audio_output
            )

            self.media_player.setVideoOutput(
                self.video_widget
            )

            self.media_player.positionChanged.connect(
                self._on_position_changed
            )

            self.media_player.durationChanged.connect(
                self._on_duration_changed
            )

            self.media_player.playbackStateChanged.connect(
                self._on_playback_state_changed
            )

            self.media_player.mediaStatusChanged.connect(
                self._on_media_status_changed
            )

            self.media_player.errorOccurred.connect(
                self._on_error
            )

            return True

        except Exception as exc:

            self.error_occurred.emit(
                f"Unable to initialize video player: {exc}"
            )

            return False

    # ==========================================================
    # LOAD
    # ==========================================================

    def load(
        self,
        filepath: str,
    ) -> bool:

        filepath = os.path.abspath(
            os.path.expanduser(
                str(filepath)
            )
        )

        filepath = os.path.normpath(
            filepath
        )

        if not os.path.isfile(filepath):

            self.error_occurred.emit(
                "The selected video does not exist."
            )

            return False

        if not self._initialize_player():
            return False

        player = self.media_player

        if player is None:
            return False

        # ------------------------------------------------------
        # INVALIDATE PREVIOUS LOADS
        # ------------------------------------------------------

        self._load_generation += 1

        generation = self._load_generation

        self.video_path = filepath

        self._loading = True
        self._duration_ms = 0

        self.loading_changed.emit(
            True
        )

        # ------------------------------------------------------
        # RESET UI
        # ------------------------------------------------------

        self.position_slider.setRange(
            0,
            0,
        )

        self.position_slider.setValue(
            0
        )

        self.current_time_label.setText(
            "00:00:00.000"
        )

        self.duration_label.setText(
            "Loading..."
        )

        self.play_button.setEnabled(
            False
        )

        self.stop_button.setEnabled(
            False
        )

        self.setWindowTitle(
            "Video Player — "
            + os.path.basename(filepath)
        )

        # ------------------------------------------------------
        # STOP PREVIOUS MEDIA
        # ------------------------------------------------------

        try:
            player.stop()
        except Exception:
            pass

        # ------------------------------------------------------
        # DEFER MEDIA SOURCE
        # ------------------------------------------------------

        QTimer.singleShot(
            100,
            lambda: self._set_source(
                filepath,
                generation,
            ),
        )

        return True

    def _set_source(
        self,
        filepath: str,
        generation: int,
    ) -> None:

        if generation != self._load_generation:
            return

        player = self.media_player

        if player is None:
            return

        if self.video_path != filepath:
            return

        if not os.path.isfile(filepath):

            self._finish_loading(
                False,
                "The video file no longer exists.",
            )

            return

        try:

            player.setSource(
                QUrl.fromLocalFile(
                    filepath
                )
            )

        except Exception as exc:

            self._finish_loading(
                False,
                str(exc),
            )

    # ==========================================================
    # MEDIA STATUS
    # ==========================================================

    def _on_media_status_changed(
        self,
        status,
    ) -> None:

        if status == QMediaPlayer.LoadingMedia:

            self._set_loading(
                True
            )

        elif status == QMediaPlayer.LoadedMedia:

            self._finish_loading(
                True
            )

        elif status == QMediaPlayer.BufferedMedia:

            self._finish_loading(
                True
            )

        elif status == QMediaPlayer.InvalidMedia:

            self._finish_loading(
                False,
                "The video could not be decoded by "
                "the Qt multimedia backend.",
            )

    def _set_loading(
        self,
        loading: bool,
    ) -> None:

        self._loading = loading

        self.loading_changed.emit(
            loading
        )

        self.play_button.setEnabled(
            not loading
        )

        self.stop_button.setEnabled(
            not loading
        )

    def _finish_loading(
        self,
        success: bool,
        error: str = "",
    ) -> None:

        self._set_loading(
            False
        )

        if not success:

            self.play_button.setEnabled(
                False
            )

            self.stop_button.setEnabled(
                False
            )

            self.duration_label.setText(
                "00:00:00.000"
            )

            self.error_occurred.emit(
                error
                or "Unable to load video."
            )

            return

        self.play_button.setEnabled(
            True
        )

        self.stop_button.setEnabled(
            True
        )

        if self.video_path:

            self.video_loaded.emit(
                self.video_path
            )

    # ==========================================================
    # PLAYBACK
    # ==========================================================

    def toggle_play(self) -> None:

        player = self.media_player

        if player is None:
            return

        if self._loading:
            return

        if not self.video_path:
            return

        if (
            player.playbackState()
            == QMediaPlayer.PlayingState
        ):

            player.pause()

        else:

            player.play()

    def play(self) -> None:

        player = self.media_player

        if player is None:
            return

        if self._loading:
            return

        player.play()

    def pause(self) -> None:

        player = self.media_player

        if player is None:
            return

        player.pause()

    def stop(self) -> None:

        player = self.media_player

        if player is None:
            return

        if self._loading:
            return

        player.stop()

    # ==========================================================
    # SEEK
    # ==========================================================

    def seek_relative(
        self,
        milliseconds: int,
    ) -> None:

        player = self.media_player

        if player is None or self._loading:
            return

        position = (
            player.position()
            + int(milliseconds)
        )

        position = max(
            0,
            min(
                position,
                self._duration_ms,
            ),
        )

        player.setPosition(
            position
        )

    def seek(
        self,
        position: int,
    ) -> None:

        player = self.media_player

        if player is None or self._loading:
            return

        position = max(
            0,
            min(
                int(position),
                self._duration_ms,
            ),
        )

        player.setPosition(
            position
        )

    def set_position(
        self,
        milliseconds: int,
    ) -> None:

        player = self.media_player

        if player is None or self._loading:
            return

        milliseconds = max(
            0,
            min(
                int(milliseconds),
                self._duration_ms,
            ),
        )

        player.setPosition(
            milliseconds
        )

    # ==========================================================
    # POSITION / DURATION
    # ==========================================================

    def position(self) -> int:

        player = self.media_player

        if player is None:
            return 0

        try:
            return int(
                player.position()
            )
        except Exception:
            return 0

    def position_seconds(self) -> float:

        return self.position() / 1000.0

    def duration(self) -> int:

        return self._duration_ms

    def duration_seconds(self) -> float:

        return self._duration_ms / 1000.0

    # ==========================================================
    # SPEED
    # ==========================================================

    def set_speed(
        self,
        value: str,
    ) -> None:

        player = self.media_player

        if player is None:
            return

        try:

            speed = float(
                value.rstrip("x")
            )

            player.setPlaybackRate(
                speed
            )

        except Exception:
            pass

    # ==========================================================
    # JUMP
    # ==========================================================

    def jump_to_time(self) -> None:

        try:

            milliseconds = (
                self._parse_time_to_ms(
                    self.jump_time_edit.text()
                )
            )

            self.set_position(
                milliseconds
            )

        except ValueError as exc:

            self.error_occurred.emit(
                str(exc)
            )

    # ==========================================================
    # EVENTS
    # ==========================================================

    def _on_position_changed(
        self,
        position: int,
    ) -> None:

        self.position_slider.blockSignals(
            True
        )

        try:

            self.position_slider.setValue(
                int(position)
            )

        finally:

            self.position_slider.blockSignals(
                False
            )

        self.current_time_label.setText(
            self._format_ms(position)
        )

        self.position_changed.emit(
            int(position)
        )

    def _on_duration_changed(
        self,
        duration: int,
    ) -> None:

        self._duration_ms = max(
            0,
            int(duration),
        )

        self.position_slider.setRange(
            0,
            self._duration_ms,
        )

        self.duration_label.setText(
            self._format_ms(
                self._duration_ms
            )
        )

        self.duration_changed.emit(
            self._duration_ms
        )

    def _on_playback_state_changed(
        self,
        state,
    ) -> None:

        if state == QMediaPlayer.PlayingState:

            self.play_button.setText(
                "Pause"
            )

            self.playback_started.emit()

        elif state == QMediaPlayer.PausedState:

            self.play_button.setText(
                "Play"
            )

            self.playback_paused.emit()

        else:

            self.play_button.setText(
                "Play"
            )

            self.playback_stopped.emit()

    def _on_error(
        self,
        error,
        error_string: str,
    ) -> None:

        self._finish_loading(
            False,
            error_string
            or "Unknown multimedia error.",
        )

    # ==========================================================
    # TIME
    # ==========================================================

    @staticmethod
    def _format_ms(
        milliseconds: int,
    ) -> str:

        milliseconds = max(
            0,
            int(milliseconds),
        )

        hours, remainder = divmod(
            milliseconds,
            3_600_000,
        )

        minutes, remainder = divmod(
            remainder,
            60_000,
        )

        seconds, ms = divmod(
            remainder,
            1000,
        )

        return (
            f"{hours:02d}:"
            f"{minutes:02d}:"
            f"{seconds:02d}."
            f"{ms:03d}"
        )

    @staticmethod
    def _parse_time_to_ms(
        value: str,
    ) -> int:

        value = value.strip()

        if not value:
            raise ValueError(
                "Enter a time."
            )

        value = value.replace(
            ",",
            ".",
        )

        if ":" not in value:

            try:

                seconds = float(value)

            except ValueError:

                raise ValueError(
                    "Invalid time. Use HH:MM:SS.mmm "
                    "or seconds."
                )

            if seconds < 0:
                raise ValueError(
                    "Invalid time."
                )

            return int(
                round(
                    seconds * 1000
                )
            )

        parts = value.split(":")

        try:

            if len(parts) == 3:

                hours = int(parts[0])
                minutes = int(parts[1])
                seconds = float(parts[2])

            elif len(parts) == 2:

                hours = 0
                minutes = int(parts[0])
                seconds = float(parts[1])

            else:

                raise ValueError

            if (
                hours < 0
                or minutes < 0
                or seconds < 0
                or minutes >= 60
                or seconds >= 60
            ):

                raise ValueError

            total = (
                hours * 3600
                + minutes * 60
                + seconds
            )

            return int(
                round(
                    total * 1000
                )
            )

        except (
            ValueError,
            TypeError,
        ):

            raise ValueError(
                "Invalid time. Use HH:MM:SS.mmm "
                "or seconds."
            )

    # ==========================================================
    # PUBLIC
    # ==========================================================

    def current_video(
        self,
    ) -> Optional[str]:

        return self.video_path

    def is_loading(self) -> bool:

        return self._loading

    def is_playing(self) -> bool:

        player = self.media_player

        if player is None:
            return False

        try:

            return (
                player.playbackState()
                == QMediaPlayer.PlayingState
            )

        except Exception:

            return False

    # ==========================================================
    # STYLE
    # ==========================================================

    def _apply_style(self) -> None:

        self.setStyleSheet(
            """
            QWidget {
                color: #e5e7eb;
                background: #020617;
            }

            #VideoContainer {
                background: #000000;
                border: 1px solid #263244;
                border-radius: 8px;
            }

            #VideoPlaceholder {
                color: #64748b;
                font-size: 16px;
            }

            QComboBox,
            QLineEdit {
                background: #0f172a;
                color: #e5e7eb;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 6px;
            }

            QPushButton {
                background: #1f2937;
                color: #e5e7eb;
                border: 1px solid #374151;
                border-radius: 6px;
                padding: 7px 12px;
            }

            QPushButton:hover {
                background: #374151;
            }

            QPushButton:disabled {
                color: #64748b;
                background: #111827;
            }

            QSlider::groove:horizontal {
                height: 5px;
                background: #334155;
                border-radius: 2px;
            }

            QSlider::handle:horizontal {
                width: 12px;
                margin: -4px 0;
                background: #3b82f6;
                border-radius: 6px;
            }
            """
        )

    # ==========================================================
    # WINDOW CLOSE
    # ==========================================================

    def closeEvent(
        self,
        event,
    ) -> None:

        # Do not destroy the player.
        #
        # The page can reopen this same window later.

        player = self.media_player

        if player is not None:

            try:
                player.pause()
            except Exception:
                pass

        self.hide()

        event.ignore()

    # ==========================================================
    # FINAL CLEANUP
    # ==========================================================

    def cleanup(self) -> None:

        self._load_generation += 1

        player = self.media_player
        video = self.video_widget
        audio = self.audio_output

        self.media_player = None
        self.video_widget = None
        self.audio_output = None

        self.video_path = None
        self._duration_ms = 0
        self._loading = False

        if player is not None:

            try:
                player.stop()
            except Exception:
                pass

            try:
                player.setVideoOutput(None)
            except Exception:
                pass

            try:
                player.setAudioOutput(None)
            except Exception:
                pass

            try:
                player.setSource(QUrl())
            except Exception:
                pass

            player.deleteLater()

        if video is not None:
            video.deleteLater()

        if audio is not None:
            audio.deleteLater()

