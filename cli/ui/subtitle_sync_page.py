from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from PySide6.QtCore import (
QObject,
Qt,
QThread,
Signal,
Slot,
)
from PySide6.QtWidgets import (
QComboBox,
QFileDialog,
QGroupBox,
QHBoxLayout,
QLabel,
QLineEdit,
QMessageBox,
QPushButton,
QScrollArea,
QVBoxLayout,
QWidget,
)

from jobs.subtitle_sync_processor import (
JobCancelled,
SubtitleSyncJobProcessor,
)

from cli.ui.widgets.video_player import VideoPlayer
from cli.ui.widgets.subtitle_preview import (
SubtitlePreviewWidget,
)
from cli.ui.widgets.subtitle_controller import (
SubtitleControllerWidget,
)
from cli.ui.widgets.subtitle_operation import (
SubtitleOperationWidget,
)

# ==============================================================

# WORKER

# ==============================================================

class SubtitleSyncWorker(QObject):
    """
    Worker used exclusively inside a QThread.


    The worker never touches Qt widgets.
    """

    progress = Signal(str)
    finished = Signal(object)
    error = Signal(object)
    cancelled = Signal()

    def __init__(
        self,
        processor: SubtitleSyncJobProcessor,
        settings: Dict[str, Any],
    ) -> None:
        super().__init__()

        self.processor = processor
        self.settings = dict(settings)

    @Slot()
    def run(self) -> None:

        try:
            result = self.processor.process_subtitle(
                self.settings
            )

            self.finished.emit(result)

        except JobCancelled:
            self.cancelled.emit()

        except Exception as exc:
            self.error.emit(exc)


# ==============================================================

# PAGE

# ==============================================================

class SubtitleSyncPage(QWidget):


    MAX_MULTI_SUBTITLES = 4

    OPERATION_MAP = {
        "offset": "offset",
        "two_points": "two_point",
        "points": "multi_point",
        "start_end": "start_end",
        "join_parts": "join_parts",
        "merge_tracks": "merge_tracks",
        "fit": "fit",
        "clamp": "clamp",
        "validate": "validate",
    }

    MULTI_OPERATIONS = {
        "join_parts",
        "merge_tracks",
    }

    def __init__(
        self,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)

        # ------------------------------------------------------
        # THREAD STATE
        # ------------------------------------------------------

        self.processor: Optional[
            SubtitleSyncJobProcessor
        ] = None

        self.worker: Optional[
            SubtitleSyncWorker
        ] = None

        self.worker_thread: Optional[
            QThread
        ] = None

        self._operation_running = False
        self._closing = False

        # ------------------------------------------------------
        # VIDEO STATE
        # ------------------------------------------------------

        self.video_path: Optional[str] = None

        # IMPORTANT:
        #
        # VideoPlayer is a TOP-LEVEL WINDOW.
        #
        # Do NOT pass self as its parent.
        #
        self.video_player = VideoPlayer()

        # ------------------------------------------------------
        # SUBTITLE STATE
        # ------------------------------------------------------

        self.controller_files: List[str] = []
        self.preview_files: List[str] = []
        self.preview_subtitle: Optional[str] = None

        self._updating_preview_selection = False

        # ------------------------------------------------------
        # BUILD
        # ------------------------------------------------------

        self._build_ui()
        self._connect_signals()

        self._update_operation_ui()

        self._controller_files_changed(
            self.subtitle_controller.files()
        )

    # ==========================================================
    # UI
    # ==========================================================

    def _build_ui(self) -> None:

        outer_layout = QVBoxLayout(self)

        outer_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        outer_layout.setSpacing(0)

        # ------------------------------------------------------
        # SCROLL AREA
        # ------------------------------------------------------

        scroll_area = QScrollArea()

        scroll_area.setWidgetResizable(True)

        scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff
        )

        scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarAsNeeded
        )

        scroll_area.setFrameShape(
            QScrollArea.NoFrame
        )

        outer_layout.addWidget(
            scroll_area
        )

        content = QWidget()

        scroll_area.setWidget(
            content
        )

        root = QVBoxLayout(content)

        root.setContentsMargins(
            20,
            20,
            20,
            20,
        )

        root.setSpacing(14)

        # ======================================================
        # HEADER
        # ======================================================

        header = QHBoxLayout()

        title = QLabel(
            "Subtitle Sync"
        )

        title.setObjectName(
            "PageTitle"
        )

        header.addWidget(
            title
        )

        header.addStretch()

        root.addLayout(
            header
        )

        # ======================================================
        # VIDEO / CONTROLLER WORKSPACE
        # ======================================================

        workspace = QHBoxLayout()

        workspace.setSpacing(16)

        # ======================================================
        # VIDEO PANEL
        #
        # IMPORTANT:
        #
        # There is NO QVideoWidget here.
        #
        # The actual video lives in self.video_player,
        # which is a separate top-level window.
        # ======================================================

        video_group = QGroupBox(
            "Video"
        )

        video_layout = QVBoxLayout(
            video_group
        )

        video_layout.setContentsMargins(
            10,
            16,
            10,
            10,
        )

        self.video_status_label = QLabel(
            "No video selected."
        )

        self.video_status_label.setObjectName(
            "VideoStatusLabel"
        )

        self.video_status_label.setWordWrap(
            True
        )

        video_layout.addWidget(
            self.video_status_label
        )

        self.video_edit = QLineEdit()

        self.video_edit.setPlaceholderText(
            "No video selected"
        )

        self.video_edit.setReadOnly(
            True
        )

        video_layout.addWidget(
            self.video_edit
        )

        video_buttons = QHBoxLayout()

        self.video_select_button = QPushButton(
            "Select Video"
        )

        self.video_open_button = QPushButton(
            "Open Video Player"
        )

        self.video_open_button.setEnabled(
            False
        )

        video_buttons.addWidget(
            self.video_select_button,
            1,
        )

        video_buttons.addWidget(
            self.video_open_button,
            1,
        )

        video_layout.addLayout(
            video_buttons
        )

        video_info = QLabel(
            "The video player opens in a separate window."
        )

        video_info.setObjectName(
            "VideoInfo"
        )

        video_info.setWordWrap(
            True
        )

        video_layout.addWidget(
            video_info
        )

        video_layout.addStretch()

        workspace.addWidget(
            video_group,
            1,
        )

        # ======================================================
        # CONTROLLER
        # ======================================================

        controller_group = QGroupBox(
            "Subtitle Controllers"
        )

        controller_layout = QVBoxLayout(
            controller_group
        )

        controller_layout.setContentsMargins(
            10,
            16,
            10,
            10,
        )

        controller_layout.addWidget(
            QLabel("Subtitle Files")
        )

        self.subtitle_files_edit = QLineEdit()

        self.subtitle_files_edit.setPlaceholderText(
            "No subtitle files loaded"
        )

        self.subtitle_files_edit.setReadOnly(
            True
        )

        controller_layout.addWidget(
            self.subtitle_files_edit
        )

        self.subtitle_select_button = QPushButton(
            "Select Subtitle Files"
        )

        controller_layout.addWidget(
            self.subtitle_select_button
        )

        self.subtitle_controller = (
            SubtitleControllerWidget(self)
        )

        controller_layout.addWidget(
            self.subtitle_controller,
            1,
        )

        workspace.addWidget(
            controller_group,
            2,
        )

        root.addLayout(
            workspace
        )

        # ======================================================
        # PREVIEW
        # ======================================================

        preview_group = QGroupBox(
            "Subtitle Preview"
        )

        preview_layout = QVBoxLayout(
            preview_group
        )

        self.subtitle_preview = (
            SubtitlePreviewWidget(self)
        )

        preview_layout.addWidget(
            self.subtitle_preview
        )

        root.addWidget(
            preview_group
        )

        # ======================================================
        # OPERATIONS
        # ======================================================

        operation_group = QGroupBox(
            "Synchronization & Subtitle Operations"
        )

        operation_layout = QVBoxLayout(
            operation_group
        )

        # ------------------------------------------------------
        # OPERATION SELECTOR
        # ------------------------------------------------------

        operation_row = QHBoxLayout()

        operation_row.addWidget(
            QLabel("Operation:")
        )

        self.operation_combo = QComboBox()

        operations = [
            (
                "Fixed Offset",
                "offset",
            ),
            (
                "Two Point Synchronization",
                "two_points",
            ),
            (
                "Multi Point Synchronization",
                "points",
            ),
            (
                "Start + End Synchronization",
                "start_end",
            ),
            (
                "Join Subtitle Parts",
                "join_parts",
            ),
            (
                "Merge Subtitle Tracks",
                "merge_tracks",
            ),
            (
                "Fit to Video",
                "fit",
            ),
            (
                "Clamp to Video",
                "clamp",
            ),
            (
                "Validate",
                "validate",
            ),
        ]

        for label, value in operations:

            self.operation_combo.addItem(
                label,
                value,
            )

        operation_row.addWidget(
            self.operation_combo,
            1,
        )

        operation_layout.addLayout(
            operation_row
        )

        # ------------------------------------------------------
        # OPERATION WIDGET
        # ------------------------------------------------------

        self.subtitle_operation = (
            SubtitleOperationWidget(self)
        )

        operation_layout.addWidget(
            self.subtitle_operation
        )

        # ------------------------------------------------------
        # BUTTONS
        # ------------------------------------------------------

        buttons = QHBoxLayout()

        self.run_button = QPushButton(
            "Run Operation"
        )

        self.run_button.setObjectName(
            "PrimaryButton"
        )

        self.cancel_button = QPushButton(
            "Cancel"
        )

        self.cancel_button.setEnabled(
            False
        )

        buttons.addWidget(
            self.run_button,
            1,
        )

        buttons.addWidget(
            self.cancel_button
        )

        operation_layout.addLayout(
            buttons
        )

        # ------------------------------------------------------
        # STATUS
        # ------------------------------------------------------

        self.status_label = QLabel(
            "Ready."
        )

        self.status_label.setObjectName(
            "StatusLabel"
        )

        self.status_label.setWordWrap(
            True
        )

        operation_layout.addWidget(
            self.status_label
        )

        root.addWidget(
            operation_group
        )

        root.addStretch()

    # ==========================================================
    # SIGNALS
    # ==========================================================

    def _connect_signals(self) -> None:

        # ------------------------------------------------------
        # VIDEO
        # ------------------------------------------------------

        self.video_select_button.clicked.connect(
            self.select_video
        )

        self.video_open_button.clicked.connect(
            self.open_video_player
        )

        self.video_player.video_loaded.connect(
            self._on_video_loaded
        )

        self.video_player.duration_changed.connect(
            self._on_video_duration_changed
        )

        self.video_player.position_changed.connect(
            self._on_video_position_changed
        )

        self.video_player.error_occurred.connect(
            self._on_player_error
        )

        # ------------------------------------------------------
        # SUBTITLES
        # ------------------------------------------------------

        self.subtitle_select_button.clicked.connect(
            self.select_subtitles
        )

        self.subtitle_controller.files_changed.connect(
            self._controller_files_changed
        )

        # ------------------------------------------------------
        # OPERATION
        # ------------------------------------------------------

        self.operation_combo.currentIndexChanged.connect(
            self._update_operation_ui
        )

        self.run_button.clicked.connect(
            self.run_operation
        )

        self.cancel_button.clicked.connect(
            self.cancel_operation
        )

        # ------------------------------------------------------
        # OPERATION WIDGET
        # ------------------------------------------------------

        if hasattr(
            self.subtitle_operation,
            "use_video_time_requested",
        ):

            self.subtitle_operation.use_video_time_requested.connect(
                self._current_video_seconds
            )

        # ------------------------------------------------------
        # PREVIEW
        # ------------------------------------------------------

        self.subtitle_preview.track_combo.currentIndexChanged.connect(
            self._preview_track_changed
        )

        self.subtitle_preview.subtitle_loaded.connect(
            self._on_preview_subtitle_loaded
        )

    # ==========================================================
    # VIDEO
    # ==========================================================

    def select_video(self) -> None:

        if self._operation_running:
            return

        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Select Video",
            "",
            (
                "Video Files "
                "(*.mp4 *.mkv *.avi *.mov *.webm *.m4v);;"
                "All Files (*)"
            ),
        )

        if not filepath:
            return

        self.load_video(
            filepath
        )

    def load_video(
        self,
        filepath: str,
    ) -> None:

        filepath = os.path.abspath(
            os.path.expanduser(
                str(filepath)
            )
        )

        if not os.path.isfile(filepath):

            self._show_operation_error(
                ValueError(
                    "Video file does not exist:\n"
                    f"{filepath}"
                )
            )

            return

        self.status_label.setText(
            "Loading video..."
        )

        self.video_status_label.setText(
            "Loading video..."
        )

        self.video_select_button.setEnabled(
            False
        )

        try:

            loaded = self.video_player.load(
                filepath
            )

        except Exception as exc:

            self.video_select_button.setEnabled(
                not self._operation_running
            )

            self._show_operation_error(
                exc
            )

            return

        if not loaded:

            self.video_select_button.setEnabled(
                not self._operation_running
            )

    def open_video_player(self) -> None:

        if not self.video_path:
            return

        try:

            self.video_player.show()

            self.video_player.raise_()

            self.video_player.activateWindow()

        except Exception as exc:

            self._show_operation_error(
                exc
            )

    def _on_video_loaded(
        self,
        filepath: str,
    ) -> None:

        self.video_select_button.setEnabled(
            not self._operation_running
        )

        self.video_open_button.setEnabled(
            True
        )

        self.video_path = filepath

        self.video_edit.setText(
            filepath
        )

        self.video_status_label.setText(
            f"Loaded: {os.path.basename(filepath)}"
        )

        self.status_label.setText(
            "Video loaded: "
            f"{os.path.basename(filepath)}"
        )

        self._update_preview_time()

        # ------------------------------------------------------
        # Automatically show the separate video window.
        # ------------------------------------------------------

        self.open_video_player()

    def _on_video_duration_changed(
        self,
        duration: int,
    ) -> None:

        if hasattr(
            self.subtitle_operation,
            "set_video_duration",
        ):

            try:

                self.subtitle_operation.set_video_duration(
                    duration / 1000.0
                )

            except Exception:
                pass

    def _on_video_position_changed(
        self,
        position: int,
    ) -> None:

        try:

            self.subtitle_preview.set_current_time(
                int(position)
            )

        except Exception:
            pass

    def _current_video_seconds(self) -> float:

        try:

            return float(
                self.video_player.position_seconds()
            )

        except Exception:

            return 0.0

    def _get_video_duration(
        self,
    ) -> Optional[float]:

        try:

            duration = (
                self.video_player.duration()
            )

        except Exception:

            return None

        try:

            duration = int(
                duration
            )

        except (
            TypeError,
            ValueError,
        ):

            return None

        if duration <= 0:
            return None

        return duration / 1000.0

    def _update_preview_time(self) -> None:

        try:

            position = (
                self.video_player.position()
            )

        except Exception:

            return

        try:

            self.subtitle_preview.set_current_time(
                int(position)
            )

        except Exception:

            pass

    def _on_player_error(
        self,
        message: str,
    ) -> None:

        self.video_select_button.setEnabled(
            not self._operation_running
        )

        self.video_open_button.setEnabled(
            bool(self.video_path)
        )

        self.video_status_label.setText(
            f"Video error: {message}"
        )

        self.status_label.setText(
            f"Video error: {message}"
        )

    # ==========================================================
    # SUBTITLE FILES
    # ==========================================================

    def select_subtitles(self) -> None:

        if self._operation_running:
            return

        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Subtitle Files",
            "",
            (
                "Subtitle Files "
                "(*.srt *.vtt);;"
                "SRT (*.srt);;"
                "VTT (*.vtt);;"
                "All Files (*)"
            ),
        )

        if not files:
            return

        files = list(
            dict.fromkeys(
                os.path.abspath(
                    os.path.expanduser(
                        str(path)
                    )
                )
                for path in files
            )
        )

        if len(files) > self.MAX_MULTI_SUBTITLES:

            QMessageBox.warning(
                self,
                "Subtitle Sync",
                "You can select a maximum of "
                f"{self.MAX_MULTI_SUBTITLES} "
                "subtitle files.",
            )

            files = files[
                :self.MAX_MULTI_SUBTITLES
            ]

        try:

            self.subtitle_controller.add_files(
                files
            )

            self.status_label.setText(
                f"Added {len(files)} subtitle file(s)."
            )

        except Exception as exc:

            self._show_operation_error(
                exc
            )

    # ==========================================================
    # CONTROLLER
    # ==========================================================

    def _controller_files_changed(
        self,
        files: object,
    ) -> None:

        try:

            incoming = list(
                files or []
            )

        except Exception:

            incoming = []

        normalized: List[str] = []

        for filepath in incoming:

            if not filepath:
                continue

            filepath = os.path.abspath(
                os.path.expanduser(
                    str(filepath)
                )
            )

            if filepath not in normalized:

                normalized.append(
                    filepath
                )

        self.controller_files = normalized

        old_preview = (
            self.preview_subtitle
        )

        self.preview_files = list(
            self.controller_files
        )

        try:

            self.subtitle_preview.set_files(
                self.preview_files
            )

        except Exception as exc:

            self.status_label.setText(
                f"Preview error: {exc}"
            )

            return

        if (
            old_preview
            and old_preview in self.preview_files
        ):

            self._select_preview_subtitle(
                old_preview
            )

        elif self.preview_files:

            self._select_preview_subtitle(
                self.preview_files[0]
            )

        else:

            self.preview_subtitle = None

        self._refresh_operation_files()

        count = len(
            self.controller_files
        )

        if count:

            self.subtitle_files_edit.setText(
                f"{count} subtitle file(s) loaded"
            )

        else:

            self.subtitle_files_edit.clear()

        self._update_preview_time()

    # ==========================================================
    # OPERATION FILES
    # ==========================================================

    def _refresh_operation_files(self) -> None:

        if not hasattr(
            self.subtitle_operation,
            "set_files",
        ):
            return

        try:

            self.subtitle_operation.set_files(
                self.controller_files
            )

            self.subtitle_operation.set_operation(
                self.current_operation()
            )

        except Exception as exc:

            self.status_label.setText(
                f"Operation UI error: {exc}"
            )

    # ==========================================================
    # PREVIEW
    # ==========================================================

    def _select_preview_subtitle(
        self,
        filepath: str,
    ) -> None:

        if filepath not in self.preview_files:
            return

        index = self.preview_files.index(
            filepath
        )

        self.preview_subtitle = filepath

        self._updating_preview_selection = True

        try:

            self.subtitle_preview.track_combo.setCurrentIndex(
                index
            )

        finally:

            self._updating_preview_selection = False

        try:

            self.subtitle_preview.load_file(
                filepath
            )

        except Exception as exc:

            self.status_label.setText(
                f"Subtitle preview error: {exc}"
            )

            return

        self._update_preview_time()

    def _preview_track_changed(
        self,
        index: int,
    ) -> None:

        if self._updating_preview_selection:
            return

        if index < 0:

            self.preview_subtitle = None

            return

        try:

            filepath = (
                self.subtitle_preview.track_combo.itemData(
                    index
                )
            )

        except Exception:

            return

        if not filepath:
            return

        if filepath not in self.preview_files:
            return

        self.preview_subtitle = filepath

        try:

            self.subtitle_preview.load_file(
                filepath
            )

        except Exception as exc:

            self.status_label.setText(
                f"Subtitle preview error: {exc}"
            )

            return

        self._update_preview_time()

        self.status_label.setText(
            "Previewing: "
            f"{os.path.basename(filepath)}"
        )

    def _on_preview_subtitle_loaded(
        self,
        filepath: str,
    ) -> None:

        if filepath in self.preview_files:

            self.preview_subtitle = filepath

    # ==========================================================
    # OPERATION
    # ==========================================================

    def current_operation(
        self,
    ) -> str:

        value = (
            self.operation_combo.currentData()
        )

        return str(
            value or ""
        )

    def processor_operation(
        self,
        operation: Optional[str] = None,
    ) -> str:

        operation = (
            operation
            or self.current_operation()
        )

        return self.OPERATION_MAP.get(
            operation,
            operation,
        )

    def _update_operation_ui(
        self,
        *_args: Any,
    ) -> None:

        operation = (
            self.current_operation()
        )

        try:

            self.subtitle_operation.set_operation(
                operation
            )

        except Exception:

            pass

        self._refresh_operation_files()

        button_text = {
            "validate": "Validate Subtitle",
            "join_parts": "Join Subtitle Parts",
            "merge_tracks": "Merge Subtitle Tracks",
        }.get(
            operation,
            "Run Operation",
        )

        self.run_button.setText(
            button_text
        )

    # ==========================================================
    # SELECTED FILES
    # ==========================================================

    def _operation_selected_files(
        self,
    ) -> List[str]:

        if not hasattr(
            self.subtitle_operation,
            "selected_files",
        ):
            return []

        try:

            files = (
                self.subtitle_operation.selected_files()
                or []
            )

        except Exception:

            return []

        result: List[str] = []

        for filepath in files:

            if not filepath:
                continue

            filepath = os.path.abspath(
                os.path.expanduser(
                    str(filepath)
                )
            )

            if filepath not in result:

                result.append(
                    filepath
                )

        return result

    def _operation_selected_file(
        self,
    ) -> Optional[str]:

        files = (
            self._operation_selected_files()
        )

        if not files:
            return None

        return files[0]

    def _validate_multi_subtitle_selection(
        self,
    ) -> List[str]:

        files = (
            self._operation_selected_files()
        )

        if len(files) < 2:

            raise ValueError(
                "Select at least two subtitle files."
            )

        if len(files) > self.MAX_MULTI_SUBTITLES:

            raise ValueError(
                "A maximum of four subtitle files "
                "can be used."
            )

        return files

    # ==========================================================
    # BUILD SETTINGS
    # ==========================================================

    def _build_operation_settings(
        self,
        operation: str,
    ) -> Dict[str, Any]:

        processor_operation = (
            self.processor_operation(
                operation
            )
        )

        if hasattr(
            self.subtitle_operation,
            "build_settings",
        ):

            settings = (
                self.subtitle_operation.build_settings(
                    video_duration=self._get_video_duration()
                )
            )

            if settings is not None:

                settings = dict(
                    settings
                )

                settings["operation"] = (
                    processor_operation
                )

                return settings

        # ------------------------------------------------------
        # VALIDATE
        # ------------------------------------------------------

        if operation == "validate":

            subtitle = (
                self._operation_selected_file()
            )

            if not subtitle:

                raise ValueError(
                    "Select a subtitle."
                )

            return {
                "operation": "validate",
                "subtitle_file": subtitle,
            }

        # ------------------------------------------------------
        # JOIN
        # ------------------------------------------------------

        if operation == "join_parts":

            files = (
                self._validate_multi_subtitle_selection()
            )

            output = (
                self._get_operation_output()
            )

            if not output:

                raise ValueError(
                    "Select an output file."
                )

            return {
                "operation": "join_parts",
                "subtitle_files": files,
                "output": output,
            }

        # ------------------------------------------------------
        # MERGE
        # ------------------------------------------------------

        if operation == "merge_tracks":

            files = (
                self._validate_multi_subtitle_selection()
            )

            output = (
                self._get_operation_output()
            )

            if not output:

                raise ValueError(
                    "Select an output file."
                )

            return {
                "operation": "merge_tracks",
                "subtitle_files": files,
                "output": output,
            }

        # ------------------------------------------------------
        # NORMAL SINGLE FILE
        # ------------------------------------------------------

        subtitle = (
            self._operation_selected_file()
        )

        if not subtitle:

            raise ValueError(
                "Select a subtitle."
            )

        output = (
            self._default_output_path(
                subtitle
            )
        )

        duration = (
            self._get_video_duration()
        )

        # ------------------------------------------------------
        # OFFSET
        # ------------------------------------------------------

        if operation == "offset":

            if not hasattr(
                self.subtitle_operation,
                "offset",
            ):

                raise ValueError(
                    "Offset controls are unavailable."
                )

            return {
                "operation": "offset",
                "subtitle_file": subtitle,
                "output": output,
                "offset": float(
                    self.subtitle_operation.offset()
                ),
                "video_duration": duration,
            }

        # ------------------------------------------------------
        # TWO POINT
        # ------------------------------------------------------

        if operation == "two_points":

            if not hasattr(
                self.subtitle_operation,
                "two_point_values",
            ):

                raise ValueError(
                    "Two-point controls are unavailable."
                )

            values = dict(
                self.subtitle_operation.two_point_values()
            )

            return {
                "operation": "two_point",
                "subtitle_file": subtitle,
                "output": output,
                **values,
                "video_duration": duration,
            }

        # ------------------------------------------------------
        # MULTI POINT
        # ------------------------------------------------------

        if operation == "points":

            if not hasattr(
                self.subtitle_operation,
                "sync_points",
            ):

                raise ValueError(
                    "Multi-point controls are unavailable."
                )

            points = list(
                self.subtitle_operation.sync_points()
                or []
            )

            if len(points) < 2:

                raise ValueError(
                    "At least two synchronization "
                    "points are required."
                )

            return {
                "operation": "multi_point",
                "subtitle_file": subtitle,
                "output": output,
                "sync_points": points,
                "video_duration": duration,
            }

        # ------------------------------------------------------
        # START / END
        # ------------------------------------------------------

        if operation == "start_end":

            if not hasattr(
                self.subtitle_operation,
                "start_end_duration",
            ):

                raise ValueError(
                    "Start/end controls are unavailable."
                )

            start_end_duration = float(
                self.subtitle_operation.start_end_duration()
            )

            if start_end_duration <= 0:

                raise ValueError(
                    "Video duration must be greater "
                    "than zero."
                )

            return {
                "operation": "start_end",
                "subtitle_file": subtitle,
                "output": output,
                "video_duration": start_end_duration,
            }

        # ------------------------------------------------------
        # FIT
        # ------------------------------------------------------

        if operation == "fit":

            if duration is None:

                raise ValueError(
                    "Load a video before fitting subtitles."
                )

            return {
                "operation": "fit",
                "subtitle_file": subtitle,
                "output": output,
                "video_duration": duration,
            }

        # ------------------------------------------------------
        # CLAMP
        # ------------------------------------------------------

        if operation == "clamp":

            if duration is None:

                raise ValueError(
                    "Load a video before clamping subtitles."
                )

            return {
                "operation": "clamp",
                "subtitle_file": subtitle,
                "output": output,
                "video_duration": duration,
            }

        raise ValueError(
            "Unsupported operation: "
            f"{operation}"
        )

    # ==========================================================
    # OUTPUT
    # ==========================================================

    def _get_operation_output(self) -> str:

        if hasattr(
            self.subtitle_operation,
            "output_path",
        ):

            try:

                output = (
                    self.subtitle_operation.output_path()
                    or ""
                )

            except Exception:

                output = ""

            output = str(
                output
            ).strip()

            if output:

                return os.path.abspath(
                    os.path.expanduser(
                        output
                    )
                )

        return ""

    @staticmethod
    def _default_output_path(
        subtitle: str,
    ) -> str:

        base, _ = os.path.splitext(
            subtitle
        )

        return (
            base + "_synced.srt"
        )

    # ==========================================================
    # RUN
    # ==========================================================

    def run_operation(self) -> None:

        if self._closing:
            return

        if self._operation_running:
            return

        operation = (
            self.current_operation()
        )

        if not operation:
            return

        try:

            settings = (
                self._build_operation_settings(
                    operation
                )
            )

        except Exception as exc:

            self._show_operation_error(
                exc
            )

            return

        self._start_worker(
            operation,
            settings,
        )

    # ==========================================================
    # START WORKER
    # ==========================================================

    def _start_worker(
        self,
        operation: str,
        settings: Dict[str, Any],
    ) -> None:

        if self._operation_running:
            return

        processor_operation = (
            self.processor_operation(
                operation
            )
        )

        try:

            processor = (
                SubtitleSyncJobProcessor(
                    operation=processor_operation,
                    progress_callback=None,
                    error_callback=None,
                )
            )

        except Exception as exc:

            self._show_operation_error(
                exc
            )

            return

        thread = QThread()

        thread.setObjectName(
            "SubtitleSyncWorkerThread"
        )

        worker = SubtitleSyncWorker(
            processor=processor,
            settings=settings,
        )

        self.processor = processor
        self.worker = worker
        self.worker_thread = thread
        self._operation_running = True

        worker.moveToThread(
            thread
        )

        thread.started.connect(
            worker.run
        )

        worker.progress.connect(
            self._on_worker_progress
        )

        worker.finished.connect(
            self._on_worker_finished
        )

        worker.error.connect(
            self._on_worker_error
        )

        worker.cancelled.connect(
            self._on_worker_cancelled
        )

        worker.finished.connect(
            thread.quit
        )

        worker.error.connect(
            thread.quit
        )

        worker.cancelled.connect(
            thread.quit
        )

        worker.finished.connect(
            worker.deleteLater
        )

        worker.error.connect(
            worker.deleteLater
        )

        worker.cancelled.connect(
            worker.deleteLater
        )

        thread.finished.connect(
            thread.deleteLater
        )

        thread.finished.connect(
            self._on_worker_thread_finished
        )

        self._set_operation_controls_enabled(
            False
        )

        self.cancel_button.setEnabled(
            True
        )

        self.status_label.setText(
            f"Running {operation}..."
        )

        try:

            thread.start()

        except Exception as exc:

            self._operation_running = False

            self.processor = None
            self.worker = None
            self.worker_thread = None

            self._set_operation_controls_enabled(
                True
            )

            self._show_operation_error(
                exc
            )

    # ==========================================================
    # CANCEL
    # ==========================================================

    def cancel_operation(self) -> None:

        if not self._operation_running:
            return

        processor = self.processor

        if processor is None:
            return

        self.cancel_button.setEnabled(
            False
        )

        self.status_label.setText(
            "Cancellation requested..."
        )

        try:

            processor.cancel()

        except Exception:

            pass

    # ==========================================================
    # WORKER CALLBACKS
    # ==========================================================

    @Slot(str)
    def _on_worker_progress(
        self,
        message: str,
    ) -> None:

        if self._closing:
            return

        if message:

            self.status_label.setText(
                str(message)
            )

    @Slot(object)
    def _on_worker_finished(
        self,
        result: Any,
    ) -> None:

        if self._closing:
            return

        operation = (
            self.current_operation()
        )

        self.status_label.setText(
            self._result_message(
                operation,
                result,
            )
        )

        if operation == "validate":

            self._show_validation_result(
                result
            )

        else:

            QMessageBox.information(
                self,
                "Subtitle Sync",
                "Operation completed successfully.",
            )

    @Slot(object)
    def _on_worker_error(
        self,
        error: Any,
    ) -> None:

        if self._closing:
            return

        self._show_operation_error(
            error
        )

    @Slot()
    def _on_worker_cancelled(
        self,
    ) -> None:

        if self._closing:
            return

        self.status_label.setText(
            "Operation cancelled."
        )

    # ==========================================================
    # THREAD FINISHED
    # ==========================================================

    @Slot()
    def _on_worker_thread_finished(
        self,
    ) -> None:

        thread = self.worker_thread

        if thread is None:
            return

        self.worker_thread = None
        self.worker = None
        self.processor = None

        self._operation_running = False

        if not self._closing:

            self._set_operation_controls_enabled(
                True
            )

            self.cancel_button.setEnabled(
                False
            )

            self.video_open_button.setEnabled(
                bool(self.video_path)
            )

    # ==========================================================
    # UI LOCK
    # ==========================================================

    def _set_operation_controls_enabled(
        self,
        enabled: bool,
    ) -> None:

        self.run_button.setEnabled(
            enabled
        )

        self.operation_combo.setEnabled(
            enabled
        )

        self.subtitle_select_button.setEnabled(
            enabled
        )

        self.video_select_button.setEnabled(
            enabled
        )

        self.video_open_button.setEnabled(
            enabled and bool(self.video_path)
        )

    # ==========================================================
    # RESULTS
    # ==========================================================

    def _result_message(
        self,
        operation: str,
        result: Any,
    ) -> str:

        if operation == "validate":

            if isinstance(
                result,
                dict,
            ):

                errors = result.get(
                    "errors",
                    [],
                )

                if errors:

                    return (
                        "Validation found "
                        f"{len(errors)} error(s)."
                    )

                return (
                    "Subtitle validation passed."
                )

            return (
                "Validation completed."
            )

        if isinstance(
            result,
            dict,
        ):

            output = result.get(
                "output",
                "",
            )

            if output:

                return (
                    f"{operation} completed: "
                    f"{output}"
                )

        return (
            f"{operation} completed successfully."
        )

    def _show_validation_result(
        self,
        result: Any,
    ) -> None:

        errors: List[Any] = []

        if isinstance(
            result,
            dict,
        ):

            errors = list(
                result.get(
                    "errors",
                    [],
                )
                or []
            )

        if errors:

            QMessageBox.warning(
                self,
                "Subtitle Validation",
                "\n".join(
                    str(error)
                    for error in errors
                ),
            )

        else:

            QMessageBox.information(
                self,
                "Subtitle Validation",
                "Subtitle file is valid.",
            )

    def _show_operation_error(
        self,
        error: Any,
    ) -> None:

        if isinstance(
            error,
            JobCancelled,
        ):

            self.status_label.setText(
                "Operation cancelled."
            )

            return

        message = str(
            error
            or "Unknown error."
        )

        self.status_label.setText(
            f"Error: {message}"
        )

        QMessageBox.critical(
            self,
            "Subtitle Sync Error",
            message,
        )

    # ==========================================================
    # STYLE
    # ==========================================================

    def apply_style(self) -> None:

        self.setStyleSheet(
            """
            QWidget {
                color: #e5e7eb;
            }

            #PageTitle {
                color: #ffffff;
                font-size: 26px;
                font-weight: 800;
                padding-bottom: 4px;
            }

            QGroupBox {
                color: #ffffff;
                font-weight: 700;
                border: 1px solid #263244;
                border-radius: 10px;
                margin-top: 8px;
                padding: 12px;
            }

            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
            }

            QLineEdit,
            QComboBox,
            QDoubleSpinBox {
                background: #0f172a;
                color: #e5e7eb;
                border: 1px solid #334155;
                border-radius: 7px;
                padding: 7px;
            }

            QPushButton {
                background: #1f2937;
                color: #e5e7eb;
                border: 1px solid #374151;
                border-radius: 7px;
                padding: 8px 12px;
            }

            QPushButton:hover {
                background: #374151;
            }

            QPushButton:disabled {
                color: #6b7280;
            }

            #PrimaryButton {
                background: #2563eb;
                color: white;
                border: none;
                font-weight: 700;
            }

            #PrimaryButton:hover {
                background: #1d4ed8;
            }

            #StatusLabel {
                color: #93c5fd;
            }

            #VideoStatusLabel {
                color: #e5e7eb;
                font-weight: 600;
            }

            #VideoInfo {
                color: #94a3b8;
            }

            #SubtitlePreviewInfo,
            #SubtitleControllerInfo {
                color: #94a3b8;
            }

            QScrollArea {
                background: transparent;
                border: none;
            }
            """
        )

    def showEvent(
        self,
        event,
    ) -> None:

        super().showEvent(
            event
        )

        self.apply_style()

    # ==========================================================
    # CLEANUP
    # ==========================================================

    def closeEvent(
        self,
        event,
    ) -> None:

        self._closing = True

        # ------------------------------------------------------
        # CANCEL ACTIVE PROCESSOR
        # ------------------------------------------------------

        processor = self.processor

        if processor is not None:

            try:
                processor.cancel()
            except Exception:
                pass

        # ------------------------------------------------------
        # VIDEO WINDOW
        # ------------------------------------------------------

        try:

            self.video_player.cleanup()

        except Exception:

            pass

        # ------------------------------------------------------
        # WORKER THREAD
        # ------------------------------------------------------

        thread = self.worker_thread

        if thread is not None:

            try:
                thread.quit()
            except Exception:
                pass

        super().closeEvent(
            event
        )

