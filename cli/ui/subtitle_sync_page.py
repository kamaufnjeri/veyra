from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QComboBox,
    QDoubleSpinBox,
    QProgressBar,
    QSplitter,
    QVBoxLayout,
    QWidget,
)


# Use the processor created above.
from services.subtitle_sync_service import (
    SyncPoint,
)

from services.subtitle_sync_processor import (
    SubtitleSyncJobProcessor,
)


class SubtitleSyncPage(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.video_path: Optional[Path] = None
        self.subtitle_paths: list[Path] = []

        self._build_ui()
        self._connect_signals()
        self._update_sync_controls()

    # ==========================================================
    # UI
    # ==========================================================

    def _build_ui(self):

        layout = QVBoxLayout(self)

        layout.setContentsMargins(
            30,
            25,
            30,
            25,
        )

        layout.setSpacing(15)

        # ------------------------------------------------------
        # TITLE
        # ------------------------------------------------------

        title = QLabel(
            "Subtitle Sync"
        )

        title.setStyleSheet(
            """
            font-size: 28px;
            font-weight: 700;
            color: white;
            """
        )

        layout.addWidget(title)

        description = QLabel(
            "Synchronize subtitle timing with your video."
        )

        description.setStyleSheet(
            """
            color: #9ca3af;
            font-size: 14px;
            """
        )

        layout.addWidget(description)

        # ------------------------------------------------------
        # MAIN SPLITTER
        # ------------------------------------------------------

        splitter = QSplitter(
            Qt.Horizontal
        )

        # ======================================================
        # LEFT: VIDEO
        # ======================================================

        video_container = QFrame()

        video_container.setStyleSheet(
            """
            QFrame {
                background-color: #111827;
                border: 1px solid #374151;
                border-radius: 8px;
            }
            """
        )

        video_layout = QVBoxLayout(
            video_container
        )

        video_layout.setContentsMargins(
            10,
            10,
            10,
            10,
        )

        video_title = QLabel(
            "Video Preview"
        )

        video_title.setStyleSheet(
            """
            color: white;
            font-size: 16px;
            font-weight: 600;
            """
        )

        video_layout.addWidget(
            video_title
        )

        # ------------------------------------------------------
        # VIDEO PLAYER
        # ------------------------------------------------------

        self.video_widget = QVideoWidget()

        self.video_widget.setMinimumSize(
            600,
            340,
        )

        video_layout.addWidget(
            self.video_widget,
            stretch=1,
        )

        # ------------------------------------------------------
        # VIDEO CONTROLS
        # ------------------------------------------------------

        controls = QHBoxLayout()

        self.play_button = QPushButton(
            "▶ Play"
        )

        self.play_button.setEnabled(
            False
        )

        controls.addWidget(
            self.play_button
        )

        self.video_position_label = QLabel(
            "00:00 / 00:00"
        )

        self.video_position_label.setStyleSheet(
            "color: #9ca3af;"
        )

        controls.addWidget(
            self.video_position_label
        )

        controls.addStretch()

        video_layout.addLayout(
            controls
        )

        # ======================================================
        # RIGHT: SUBTITLES
        # ======================================================

        subtitle_container = QFrame()

        subtitle_container.setStyleSheet(
            """
            QFrame {
                background-color: #111827;
                border: 1px solid #374151;
                border-radius: 8px;
            }
            """
        )

        subtitle_layout = QVBoxLayout(
            subtitle_container
        )

        subtitle_layout.setContentsMargins(
            15,
            15,
            15,
            15,
        )

        subtitle_title = QLabel(
            "Subtitle Files"
        )

        subtitle_title.setStyleSheet(
            """
            color: white;
            font-size: 16px;
            font-weight: 600;
            """
        )

        subtitle_layout.addWidget(
            subtitle_title
        )

        self.subtitle_list = QListWidget()

        self.subtitle_list.setMinimumWidth(
            300
        )

        self.subtitle_list.setStyleSheet(
            """
            QListWidget {
                background-color: #0f172a;
                color: #e5e7eb;
                border: 1px solid #374151;
                border-radius: 6px;
                padding: 5px;
            }

            QListWidget::item {
                padding: 9px;
            }

            QListWidget::item:selected {
                background-color: #2563eb;
                color: white;
            }
            """
        )

        subtitle_layout.addWidget(
            self.subtitle_list,
            stretch=1,
        )

        subtitle_buttons = QHBoxLayout()

        self.select_video_button = QPushButton(
            "Select Video"
        )

        subtitle_buttons.addWidget(
            self.select_video_button
        )

        self.select_subtitle_button = QPushButton(
            "Add Subtitle"
        )

        subtitle_buttons.addWidget(
            self.select_subtitle_button
        )

        subtitle_layout.addLayout(
            subtitle_buttons
        )

        splitter.addWidget(
            video_container
        )

        splitter.addWidget(
            subtitle_container
        )

        splitter.setStretchFactor(
            0,
            2,
        )

        splitter.setStretchFactor(
            1,
            1,
        )

        layout.addWidget(
            splitter,
            stretch=1,
        )

        # ======================================================
        # SYNC OPTIONS
        # ======================================================

        options_frame = QFrame()

        options_frame.setStyleSheet(
            """
            QFrame {
                background-color: #111827;
                border: 1px solid #374151;
                border-radius: 8px;
            }
            """
        )

        options_layout = QVBoxLayout(
            options_frame
        )

        options_title = QLabel(
            "Synchronization"
        )

        options_title.setStyleSheet(
            """
            color: white;
            font-size: 16px;
            font-weight: 600;
            """
        )

        options_layout.addWidget(
            options_title
        )

        form = QFormLayout()

        # ------------------------------------------------------
        # SYNC MODE
        # ------------------------------------------------------

        self.sync_mode = QComboBox()

        self.sync_mode.addItem(
            "Fixed Offset",
            "offset",
        )

        self.sync_mode.addItem(
            "Two Point Sync",
            "two_points",
        )

        self.sync_mode.addItem(
            "Multi Point Sync",
            "points",
        )

        self.sync_mode.addItem(
            "Start + End Sync",
            "start_end",
        )

        form.addRow(
            "Sync Mode:",
            self.sync_mode,
        )

        # ------------------------------------------------------
        # OFFSET
        # ------------------------------------------------------

        self.offset_spin = QDoubleSpinBox()

        self.offset_spin.setRange(
            -86400.0,
            86400.0,
        )

        self.offset_spin.setDecimals(
            3
        )

        self.offset_spin.setSingleStep(
            0.1
        )

        self.offset_spin.setSuffix(
            " sec"
        )

        form.addRow(
            "Offset:",
            self.offset_spin,
        )

        # ------------------------------------------------------
        # POINT 1
        # ------------------------------------------------------

        self.subtitle_point_1 = QDoubleSpinBox()
        self.subtitle_point_1.setRange(
            0,
            86400,
        )
        self.subtitle_point_1.setDecimals(
            3
        )
        self.subtitle_point_1.setSuffix(
            " sec"
        )

        self.video_point_1 = QDoubleSpinBox()
        self.video_point_1.setRange(
            0,
            86400,
        )
        self.video_point_1.setDecimals(
            3
        )
        self.video_point_1.setSuffix(
            " sec"
        )

        form.addRow(
            "Subtitle Point 1:",
            self.subtitle_point_1,
        )

        form.addRow(
            "Video Point 1:",
            self.video_point_1,
        )

        # ------------------------------------------------------
        # POINT 2
        # ------------------------------------------------------

        self.subtitle_point_2 = QDoubleSpinBox()
        self.subtitle_point_2.setRange(
            0,
            86400,
        )
        self.subtitle_point_2.setDecimals(
            3
        )
        self.subtitle_point_2.setSuffix(
            " sec"
        )

        self.video_point_2 = QDoubleSpinBox()
        self.video_point_2.setRange(
            0,
            86400,
        )
        self.video_point_2.setDecimals(
            3
        )
        self.video_point_2.setSuffix(
            " sec"
        )

        form.addRow(
            "Subtitle Point 2:",
            self.subtitle_point_2,
        )

        form.addRow(
            "Video Point 2:",
            self.video_point_2,
        )

        # ------------------------------------------------------
        # VIDEO DURATION
        # ------------------------------------------------------

        self.video_duration_spin = QDoubleSpinBox()

        self.video_duration_spin.setRange(
            0,
            86400,
        )

        self.video_duration_spin.setDecimals(
            3
        )

        self.video_duration_spin.setSuffix(
            " sec"
        )

        form.addRow(
            "Video Duration:",
            self.video_duration_spin,
        )

        options_layout.addLayout(
            form
        )

        layout.addWidget(
            options_frame
        )

        # ======================================================
        # ACTIONS
        # ======================================================

        actions = QHBoxLayout()

        self.sync_button = QPushButton(
            "Synchronize Subtitle"
        )

        self.sync_button.setMinimumHeight(
            42
        )

        self.sync_button.setStyleSheet(
            """
            QPushButton {
                background-color: #2563eb;
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: 600;
                padding: 8px 20px;
            }

            QPushButton:hover {
                background-color: #1d4ed8;
            }

            QPushButton:disabled {
                background-color: #374151;
                color: #9ca3af;
            }
            """
        )

        actions.addWidget(
            self.sync_button
        )

        self.cancel_button = QPushButton(
            "Cancel"
        )

        self.cancel_button.setEnabled(
            False
        )

        actions.addWidget(
            self.cancel_button
        )

        actions.addStretch()

        layout.addLayout(
            actions
        )

        # ======================================================
        # STATUS
        # ======================================================

        self.status_label = QLabel(
            "Ready."
        )

        self.status_label.setStyleSheet(
            """
            color: #9ca3af;
            """
        )

        layout.addWidget(
            self.status_label
        )

        self.progress_bar = QProgressBar()

        self.progress_bar.setRange(
            0,
            100,
        )

        self.progress_bar.setValue(
            0
        )

        layout.addWidget(
            self.progress_bar
        )

        # ======================================================
        # MEDIA PLAYER
        # ======================================================

        self.player = QMediaPlayer(
            self
        )

        self.audio_output = QAudioOutput(
            self
        )

        self.player.setAudioOutput(
            self.audio_output
        )

        self.player.setVideoOutput(
            self.video_widget
        )

    # ==========================================================
    # SIGNALS
    # ==========================================================

    def _connect_signals(self):

        self.select_video_button.clicked.connect(
            self.select_video
        )

        self.select_subtitle_button.clicked.connect(
            self.select_subtitle
        )

        self.play_button.clicked.connect(
            self.toggle_play
        )

        self.sync_mode.currentIndexChanged.connect(
            self._update_sync_controls
        )

        self.sync_button.clicked.connect(
            self.synchronize
        )

        self.cancel_button.clicked.connect(
            self.cancel
        )

        self.player.positionChanged.connect(
            self._position_changed
        )

        self.player.durationChanged.connect(
            self._duration_changed
        )

    # ==========================================================
    # VIDEO
    # ==========================================================

    def select_video(self):

        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Select Video",
            "",
            (
                "Video Files "
                "(*.mp4 *.mkv *.avi *.mov *.webm);;"
                "All Files (*)"
            ),
        )

        if not filepath:
            return

        self.video_path = Path(
            filepath
        )

        self.player.setSource(
            QUrl.fromLocalFile(
                filepath
            )
        )

        self.play_button.setEnabled(
            True
        )

        self.status_label.setText(
            f"Video: {self.video_path.name}"
        )

    def toggle_play(self):

        if self.player.playbackState() == (
            QMediaPlayer.PlaybackState.PlayingState
        ):
            self.player.pause()
            self.play_button.setText(
                "▶ Play"
            )

        else:
            self.player.play()
            self.play_button.setText(
                "⏸ Pause"
            )

    def _position_changed(
        self,
        position: int,
    ):

        duration = self.player.duration()

        self.video_position_label.setText(
            (
                f"{self._format_time(position)}"
                f" / "
                f"{self._format_time(duration)}"
            )
        )

    def _duration_changed(
        self,
        duration: int,
    ):

        if duration > 0:
            self.video_duration_spin.setValue(
                duration / 1000.0
            )

    @staticmethod
    def _format_time(
        milliseconds: int,
    ) -> str:

        total_seconds = max(
            0,
            milliseconds // 1000,
        )

        hours, remainder = divmod(
            total_seconds,
            3600,
        )

        minutes, seconds = divmod(
            remainder,
            60,
        )

        if hours:
            return (
                f"{hours:02d}:"
                f"{minutes:02d}:"
                f"{seconds:02d}"
            )

        return (
            f"{minutes:02d}:"
            f"{seconds:02d}"
        )

    # ==========================================================
    # SUBTITLES
    # ==========================================================

    def select_subtitle(self):

        filepaths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Subtitle Files",
            "",
            (
                "Subtitle Files "
                "(*.srt *.vtt);;"
                "All Files (*)"
            ),
        )

        if not filepaths:
            return

        for filepath in filepaths:

            path = Path(filepath)

            if path not in self.subtitle_paths:
                self.subtitle_paths.append(
                    path
                )

                self.subtitle_list.addItem(
                    path.name
                )

        self.status_label.setText(
            f"{len(self.subtitle_paths)} subtitle file(s) loaded."
        )

    # ==========================================================
    # SYNC OPTIONS
    # ==========================================================

    def _update_sync_controls(self):

        mode = self.sync_mode.currentData()

        offset = mode == "offset"

        two_points = mode == "two_points"

        points = mode == "points"

        start_end = mode == "start_end"

        self.offset_spin.setEnabled(
            offset
        )

        self.subtitle_point_1.setEnabled(
            two_points or points
        )

        self.video_point_1.setEnabled(
            two_points or points
        )

        self.subtitle_point_2.setEnabled(
            two_points or points
        )

        self.video_point_2.setEnabled(
            two_points or points
        )

        self.video_duration_spin.setEnabled(
            start_end
            or two_points
            or points
        )

    # ==========================================================
    # SYNCHRONIZE
    # ==========================================================

    def synchronize(self):

        if self.video_path is None:
            QMessageBox.warning(
                self,
                "Video Required",
                "Please select a video first.",
            )
            return

        if not self.subtitle_paths:
            QMessageBox.warning(
                self,
                "Subtitle Required",
                "Please select at least one subtitle file.",
            )
            return

        selected = self.subtitle_list.currentRow()

        if selected < 0:
            selected = 0

        subtitle_path = self.subtitle_paths[
            selected
        ]

        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Synchronized Subtitle",
            str(
                subtitle_path.with_name(
                    subtitle_path.stem
                    + "_synced.srt"
                )
            ),
            "SRT Files (*.srt)",
        )

        if not output_path:
            return

        mode = self.sync_mode.currentData()

        processor = SubtitleSyncJobProcessor(
            operation=mode,
            progress_callback=self._on_progress,
            error_callback=self._on_error,
        )

        self._processor = processor

        self.sync_button.setEnabled(
            False
        )

        self.cancel_button.setEnabled(
            True
        )

        try:

            if mode == "offset":

                processor.process(
                    subtitle_path,
                    output_path,
                    offset=self.offset_spin.value(),
                    video_duration=(
                        self.video_duration_spin.value()
                        or None
                    ),
                )

            elif mode == "two_points":

                processor.process(
                    subtitle_path,
                    output_path,
                    subtitle_point_1=(
                        self.subtitle_point_1.value()
                    ),
                    video_point_1=(
                        self.video_point_1.value()
                    ),
                    subtitle_point_2=(
                        self.subtitle_point_2.value()
                    ),
                    video_point_2=(
                        self.video_point_2.value()
                    ),
                    video_duration=(
                        self.video_duration_spin.value()
                        or None
                    ),
                )

            elif mode == "points":

                # These are the existing SyncPoint objects.
                points = [
                    SyncPoint(
                        self.subtitle_point_1.value(),
                        self.video_point_1.value(),
                    ),
                    SyncPoint(
                        self.subtitle_point_2.value(),
                        self.video_point_2.value(),
                    ),
                ]

                processor.process(
                    subtitle_path,
                    output_path,
                    points=points,
                    video_duration=(
                        self.video_duration_spin.value()
                        or None
                    ),
                )

            elif mode == "start_end":

                processor.process(
                    subtitle_path,
                    output_path,
                    video_duration=(
                        self.video_duration_spin.value()
                    ),
                )

            self.status_label.setText(
                "Subtitle synchronization complete."
            )

            self.progress_bar.setValue(
                100
            )

            QMessageBox.information(
                self,
                "Synchronization Complete",
                (
                    "Synchronized subtitle saved to:\n\n"
                    f"{output_path}"
                ),
            )

        except Exception as exc:

            self._on_error(
                exc
            )

        finally:

            self.sync_button.setEnabled(
                True
            )

            self.cancel_button.setEnabled(
                False
            )

    # ==========================================================
    # CANCEL
    # ==========================================================

    def cancel(self):

        processor = getattr(
            self,
            "_processor",
            None,
        )

        if processor is not None:
            processor.cancel()

        self.status_label.setText(
            "Cancelling..."
        )

    # ==========================================================
    # CALLBACKS
    # ==========================================================

    def _on_progress(
        self,
        message,
        filepath=None,
        progress=0,
    ):

        self.status_label.setText(
            str(message)
        )

        try:
            self.progress_bar.setValue(
                int(progress)
            )
        except (
            TypeError,
            ValueError,
        ):
            pass

    def _on_error(
        self,
        error,
    ):

        self.status_label.setText(
            f"Error: {error}"
        )

        self.progress_bar.setValue(
            0
        )