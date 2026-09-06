from __future__ import annotations

import dataclasses
import math
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QObject,
    QThread,
    Qt,
    Signal,
    Slot,
)
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from services import MediaPipelineService
from jobs.media_pipeline_processor import (
    JobCancelled,
    MediaPipelineServiceProcessor,
)


# ==============================================================
# WORKER
# ==============================================================


class MediaPipelineWorker(QObject):
    """
    Background worker for MediaPipelineServiceProcessor.

    All media processing runs outside the Qt GUI thread.
    """

    progress = Signal(
        str,
        str,
        float,
        object,
        object,
        object,
    )

    completed = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        operation: str,
        kwargs: dict[str, Any],
    ) -> None:
        super().__init__()

        self.operation = operation
        self.kwargs = kwargs

        self.processor: (
            MediaPipelineServiceProcessor | None
        ) = None

    @Slot()
    def run(self) -> None:
        try:
            self.processor = (
                MediaPipelineServiceProcessor(
                    pipeline=MediaPipelineService(),
                    progress_callback=self._on_progress,
                    error_callback=self._on_error,
                )
            )

            result = self.processor.process(
                self.operation,
                **self.kwargs,
            )

            self.completed.emit(result)

        except JobCancelled:
            self.cancelled.emit()

        except Exception as exc:
            self.failed.emit(str(exc))

    def cancel(self) -> None:
        if self.processor is not None:
            self.processor.cancel()

    def _on_progress(
        self,
        info: str,
        filename: str,
        percentage: float | int,
        downloaded: Any = "--",
        speed: Any = "--",
        eta: Any = "--:--",
    ) -> None:
        self.progress.emit(
            info,
            filename,
            float(percentage),
            downloaded,
            speed,
            eta,
        )

    def _on_error(
        self,
        error: Exception,
    ) -> None:
        self.failed.emit(str(error))


# ==============================================================
# ACTIVITY CARD
# ==============================================================


class ActivityCard(QFrame):
    """
    Premium activity entry.

    This replaces raw console-style output with a readable
    structured activity card.
    """

    def __init__(
        self,
        title: str,
        message: str = "",
        status: str = "info",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.setObjectName(
            f"ActivityCard_{status}"
        )

        layout = QVBoxLayout(self)

        layout.setContentsMargins(
            18,
            15,
            18,
            15,
        )

        layout.setSpacing(8)

        # ------------------------------------------------------
        # Header
        # ------------------------------------------------------

        header = QHBoxLayout()
        header.setSpacing(10)

        self.status_icon = QLabel(
            self._status_icon(status)
        )

        self.status_icon.setObjectName(
            "ActivityIcon"
        )

        self.status_icon.setFixedWidth(
            26
        )

        self.title_label = QLabel(
            title
        )

        self.title_label.setObjectName(
            "ActivityTitle"
        )

        self.title_label.setWordWrap(
            True
        )

        self.time_label = QLabel(
            datetime.now().strftime(
                "%H:%M:%S"
            )
        )

        self.time_label.setObjectName(
            "ActivityTime"
        )

        header.addWidget(
            self.status_icon
        )

        header.addWidget(
            self.title_label,
            1,
        )

        header.addWidget(
            self.time_label
        )

        layout.addLayout(
            header
        )

        # ------------------------------------------------------
        # Message
        # ------------------------------------------------------

        if message:
            self.message_label = QLabel(
                message
            )

            self.message_label.setObjectName(
                "ActivityMessage"
            )

            self.message_label.setWordWrap(
                True
            )

            layout.addWidget(
                self.message_label
            )

        self.details_container = QWidget()

        self.details_layout = QVBoxLayout(
            self.details_container
        )

        self.details_layout.setContentsMargins(
            0,
            5,
            0,
            0,
        )

        self.details_layout.setSpacing(
            4
        )

        self.details_container.hide()

        layout.addWidget(
            self.details_container
        )

    @staticmethod
    def _status_icon(
        status: str,
    ) -> str:
        return {
            "success": "✓",
            "warning": "!",
            "error": "×",
            "cancelled": "Ⅱ",
            "info": "•",
        }.get(
            status,
            "•",
        )

    def add_detail(
        self,
        label: str,
        value: str,
    ) -> None:
        row = QHBoxLayout()

        row.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        label_widget = QLabel(
            label.upper()
        )

        label_widget.setObjectName(
            "ActivityDetailLabel"
        )

        label_widget.setFixedWidth(
            105
        )

        value_widget = QLabel(
            value
        )

        value_widget.setObjectName(
            "ActivityDetailValue"
        )

        value_widget.setWordWrap(
            True
        )

        row.addWidget(
            label_widget
        )

        row.addWidget(
            value_widget,
            1,
        )

        self.details_layout.addLayout(
            row
        )

        self.details_container.show()


# ==============================================================
# MEDIA PROCESSING PAGE
# ==============================================================


class MediaPipelinePage(QWidget):
    """
    Premium Media Processing interface.

    UI/orchestration layer only.

    All media work is delegated to:

        MediaPipelineServiceProcessor
                ↓
        MediaPipelineService
    """

    OPERATIONS = [
        (
            "Inspect",
            "Analyze a media file and view its properties.",
        ),
        (
            "Duration",
            "Get the exact duration of a media file.",
        ),
        (
            "Convert",
            "Convert or transcode a media file.",
        ),
        (
            "Concatenate",
            "Combine multiple videos into one file.",
        ),
        (
            "Join",
            "Join media parts and their corresponding subtitles.",
        ),
        (
            "Mux",
            "Combine video, audio and subtitle streams.",
        ),
        (
            "Extract Audio",
            "Extract an audio stream from a video.",
        ),
        (
            "Extract Subtitle",
            "Extract a subtitle stream from a video.",
        ),
        (
            "Trim",
            "Cut a section from a media file.",
        ),
        (
            "Burn Subtitles",
            "Permanently render subtitles into a video.",
        ),
    ]

    def __init__(
        self,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.thread: QThread | None = None
        self.worker: MediaPipelineWorker | None = None

        self._build_ui()
        self._connect_signals()

    # ==========================================================
    # BUILD UI
    # ==========================================================

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        root.setContentsMargins(
            30,
            26,
            30,
            26,
        )

        root.setSpacing(
            18
        )

        # ------------------------------------------------------
        # Header
        # ------------------------------------------------------

        header = QHBoxLayout()

        title_container = QVBoxLayout()
        title_container.setSpacing(4)

        title = QLabel(
            "Media Processing"
        )

        title.setObjectName(
            "PageTitle"
        )

        subtitle = QLabel(
            "Convert, combine, extract, trim and prepare your media."
        )

        subtitle.setObjectName(
            "PageSubtitle"
        )

        title_container.addWidget(
            title
        )

        title_container.addWidget(
            subtitle
        )

        header.addLayout(
            title_container,
            1,
        )

        self.ready_badge = QLabel(
            "● READY"
        )

        self.ready_badge.setObjectName(
            "ReadyBadge"
        )

        header.addWidget(
            self.ready_badge,
            0,
            Qt.AlignTop,
        )

        root.addLayout(
            header
        )

        # ------------------------------------------------------
        # Operation selector
        # ------------------------------------------------------

        operation_card = QFrame()

        operation_card.setObjectName(
            "OperationCard"
        )

        operation_layout = QVBoxLayout(
            operation_card
        )

        operation_layout.setContentsMargins(
            20,
            18,
            20,
            18,
        )

        operation_layout.setSpacing(
            12
        )

        operation_header = QHBoxLayout()

        operation_title = QLabel(
            "What would you like to do?"
        )

        operation_title.setObjectName(
            "SectionTitle"
        )

        operation_header.addWidget(
            operation_title
        )

        operation_header.addStretch()

        self.operation_number = QLabel(
            "1 / 10"
        )

        self.operation_number.setObjectName(
            "OperationNumber"
        )

        operation_header.addWidget(
            self.operation_number
        )

        operation_layout.addLayout(
            operation_header
        )

        self.operation_combo = QComboBox()

        self.operation_combo.setMinimumHeight(
            48
        )

        for name, description in self.OPERATIONS:
            self.operation_combo.addItem(
                name,
                description,
            )

        operation_layout.addWidget(
            self.operation_combo
        )

        self.operation_description = QLabel()

        self.operation_description.setObjectName(
            "OperationDescription"
        )

        self.operation_description.setWordWrap(
            True
        )

        operation_layout.addWidget(
            self.operation_description
        )

        root.addWidget(
            operation_card
        )

        # ------------------------------------------------------
        # Dynamic operation pages
        # ------------------------------------------------------

        self.operation_stack = (
            QStackedWidget()
        )

        self.inspect_page = (
            self._create_inspect_page()
        )

        self.duration_page = (
            self._create_duration_page()
        )

        self.convert_page = (
            self._create_convert_page()
        )

        self.concatenate_page = (
            self._create_concatenate_page()
        )

        self.join_page = (
            self._create_join_page()
        )

        self.mux_page = (
            self._create_mux_page()
        )

        self.extract_audio_page = (
            self._create_extract_audio_page()
        )

        self.extract_subtitle_page = (
            self._create_extract_subtitle_page()
        )

        self.trim_page = (
            self._create_trim_page()
        )

        self.burn_page = (
            self._create_burn_page()
        )

        pages = [
            self.inspect_page,
            self.duration_page,
            self.convert_page,
            self.concatenate_page,
            self.join_page,
            self.mux_page,
            self.extract_audio_page,
            self.extract_subtitle_page,
            self.trim_page,
            self.burn_page,
        ]

        for page in pages:
            self.operation_stack.addWidget(
                page
            )

        root.addWidget(
            self.operation_stack,
            1,
        )

        # ------------------------------------------------------
        # Progress card
        # ------------------------------------------------------

        progress_card = QFrame()

        progress_card.setObjectName(
            "ProgressCard"
        )

        progress_layout = QVBoxLayout(
            progress_card
        )

        progress_layout.setContentsMargins(
            20,
            17,
            20,
            17,
        )

        progress_layout.setSpacing(
            9
        )

        progress_header = QHBoxLayout()

        self.status_label = QLabel(
            "Ready to process"
        )

        self.status_label.setObjectName(
            "ProgressTitle"
        )

        self.percentage_label = QLabel(
            "0%"
        )

        self.percentage_label.setObjectName(
            "ProgressPercentage"
        )

        progress_header.addWidget(
            self.status_label
        )

        progress_header.addStretch()

        progress_header.addWidget(
            self.percentage_label
        )

        progress_layout.addLayout(
            progress_header
        )

        self.file_label = QLabel(
            "No media selected"
        )

        self.file_label.setObjectName(
            "ProgressFile"
        )

        self.file_label.setWordWrap(
            True
        )

        progress_layout.addWidget(
            self.file_label
        )

        self.progress_bar = QProgressBar()

        self.progress_bar.setRange(
            0,
            100,
        )

        self.progress_bar.setValue(
            0
        )

        self.progress_bar.setTextVisible(
            False
        )

        self.progress_bar.setFixedHeight(
            8
        )

        progress_layout.addWidget(
            self.progress_bar
        )

        progress_info = QHBoxLayout()

        self.downloaded_label = QLabel(
            ""
        )

        self.speed_label = QLabel(
            ""
        )

        self.eta_label = QLabel(
            ""
        )

        progress_info.addWidget(
            self.downloaded_label
        )

        progress_info.addStretch()

        progress_info.addWidget(
            self.speed_label
        )

        progress_info.addSpacing(
            15
        )

        progress_info.addWidget(
            self.eta_label
        )

        progress_layout.addLayout(
            progress_info
        )

        root.addWidget(
            progress_card
        )

        # ------------------------------------------------------
        # Activity
        # ------------------------------------------------------

        activity_header = QHBoxLayout()

        activity_title = QLabel(
            "Activity"
        )

        activity_title.setObjectName(
            "SectionTitle"
        )

        activity_header.addWidget(
            activity_title
        )

        activity_header.addStretch()

        self.activity_count = QLabel(
            "0 activities"
        )

        self.activity_count.setObjectName(
            "ActivityCount"
        )

        activity_header.addWidget(
            self.activity_count
        )

        root.addLayout(
            activity_header
        )

        self.activity_scroll = QScrollArea()

        self.activity_scroll.setWidgetResizable(
            True
        )

        self.activity_scroll.setFrameShape(
            QFrame.NoFrame
        )

        self.activity_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff
        )

        self.activity_container = QWidget()

        self.activity_layout = QVBoxLayout(
            self.activity_container
        )

        self.activity_layout.setContentsMargins(
            0,
            0,
            4,
            0,
        )

        self.activity_layout.setSpacing(
            10
        )

        self.activity_layout.addStretch()

        self.activity_scroll.setWidget(
            self.activity_container
        )

        root.addWidget(
            self.activity_scroll,
            1,
        )

        # ------------------------------------------------------
        # Bottom actions
        # ------------------------------------------------------

        actions = QHBoxLayout()

        self.run_button = QPushButton(
            "Run Processing"
        )

        self.run_button.setObjectName(
            "PrimaryButton"
        )

        self.run_button.setMinimumHeight(
            46
        )

        self.cancel_button = QPushButton(
            "Cancel"
        )

        self.cancel_button.setObjectName(
            "CancelButton"
        )

        self.cancel_button.setMinimumHeight(
            46
        )

        self.cancel_button.setEnabled(
            False
        )

        self.clear_button = QPushButton(
            "Clear Activity"
        )

        self.clear_button.setObjectName(
            "SecondaryButton"
        )

        self.clear_button.setMinimumHeight(
            46
        )

        actions.addWidget(
            self.run_button,
            2,
        )

        actions.addWidget(
            self.cancel_button,
            1,
        )

        actions.addStretch(
            1
        )

        actions.addWidget(
            self.clear_button
        )

        root.addLayout(
            actions
        )

        # Initial description
        self._update_operation_description()

        self._apply_style()

    # ==========================================================
    # OPERATION PAGES
    # ==========================================================

    def _create_inspect_page(self) -> QWidget:
        page = self._card_page()

        layout = QFormLayout(page)

        self.inspect_input = self._file_row(
            layout,
            "Media file",
            save=False,
        )

        return page

    def _create_duration_page(self) -> QWidget:
        page = self._card_page()

        layout = QFormLayout(page)

        self.duration_input = self._file_row(
            layout,
            "Media file",
            save=False,
        )

        return page

    def _create_convert_page(self) -> QWidget:
        page = self._card_page()

        layout = QFormLayout(page)

        self.convert_input = self._file_row(
            layout,
            "Input",
            save=False,
        )

        self.convert_output = self._file_row(
            layout,
            "Output",
            save=True,
        )

        return page

    def _create_concatenate_page(self) -> QWidget:
        page = self._card_page()

        layout = QVBoxLayout(page)

        self.concatenate_files = QListWidget()

        self.concatenate_files.setMinimumHeight(
            110
        )

        layout.addWidget(
            self._section_label(
                "Input videos"
            )
        )

        layout.addWidget(
            self.concatenate_files
        )

        buttons = QHBoxLayout()

        add_button = QPushButton(
            "＋  Add Videos"
        )

        remove_button = QPushButton(
            "Remove Selected"
        )

        clear_button = QPushButton(
            "Clear"
        )

        buttons.addWidget(
            add_button
        )

        buttons.addWidget(
            remove_button
        )

        buttons.addWidget(
            clear_button
        )

        buttons.addStretch()

        layout.addLayout(
            buttons
        )

        output_label = self._section_label(
            "Output file"
        )

        layout.addWidget(
            output_label
        )

        output_row = QHBoxLayout()

        self.concatenate_output = QLineEdit()

        output_button = QPushButton(
            "Browse..."
        )

        output_row.addWidget(
            self.concatenate_output
        )

        output_row.addWidget(
            output_button
        )

        layout.addLayout(
            output_row
        )

        add_button.clicked.connect(
            self._add_concatenate_files
        )

        remove_button.clicked.connect(
            self._remove_concatenate_files
        )

        clear_button.clicked.connect(
            self.concatenate_files.clear
        )

        output_button.clicked.connect(
            lambda: self._browse_save(
                self.concatenate_output
            )
        )

        return page

    def _create_join_page(self) -> QWidget:
        page = self._card_page()

        layout = QVBoxLayout(page)

        title = QLabel(
            "Join Media Parts"
        )

        title.setObjectName(
            "FormTitle"
        )

        layout.addWidget(
            title
        )

        description = QLabel(
            "Join configuration requires MediaPart objects "
            "from your application workflow. This interface "
            "does not fabricate those objects."
        )

        description.setObjectName(
            "FormDescription"
        )

        description.setWordWrap(
            True
        )

        layout.addWidget(
            description
        )

        output_layout = QFormLayout()

        self.join_output = self._file_row(
            output_layout,
            "Output video",
            save=True,
        )

        layout.addLayout(
            output_layout
        )

        return page

    def _create_mux_page(self) -> QWidget:
        page = self._card_page()

        layout = QFormLayout(page)

        self.mux_video = self._file_row(
            layout,
            "Video",
            save=False,
        )

        self.mux_audio = self._file_row(
            layout,
            "Audio",
            save=False,
            optional=True,
        )

        self.mux_output = self._file_row(
            layout,
            "Output",
            save=True,
        )

        return page

    def _create_extract_audio_page(self) -> QWidget:
        page = self._card_page()

        layout = QFormLayout(page)

        self.extract_audio_video = self._file_row(
            layout,
            "Video",
            save=False,
        )

        self.extract_audio_output = self._file_row(
            layout,
            "Output",
            save=True,
        )

        self.extract_audio_stream = QSpinBox()

        self.extract_audio_stream.setMinimum(
            0
        )

        self.extract_audio_stream.setValue(
            0
        )

        layout.addRow(
            "Audio stream",
            self.extract_audio_stream,
        )

        return page

    def _create_extract_subtitle_page(self) -> QWidget:
        page = self._card_page()

        layout = QFormLayout(page)

        self.extract_subtitle_video = self._file_row(
            layout,
            "Video",
            save=False,
        )

        self.extract_subtitle_output = self._file_row(
            layout,
            "Output",
            save=True,
        )

        self.extract_subtitle_stream = QSpinBox()

        self.extract_subtitle_stream.setMinimum(
            0
        )

        self.extract_subtitle_stream.setValue(
            0
        )

        layout.addRow(
            "Subtitle stream",
            self.extract_subtitle_stream,
        )

        return page

    def _create_trim_page(self) -> QWidget:
        page = self._card_page()

        layout = QFormLayout(page)

        self.trim_input = self._file_row(
            layout,
            "Input",
            save=False,
        )

        self.trim_output = self._file_row(
            layout,
            "Output",
            save=True,
        )

        info = QLabel(
            "The available trim options are determined by "
            "your CutOptions implementation."
        )

        info.setObjectName(
            "FormDescription"
        )

        info.setWordWrap(
            True
        )

        layout.addRow(
            info
        )

        return page

    def _create_burn_page(self) -> QWidget:
        page = self._card_page()

        layout = QFormLayout(page)

        self.burn_video = self._file_row(
            layout,
            "Video",
            save=False,
        )

        self.burn_subtitle = self._file_row(
            layout,
            "Subtitle",
            save=False,
        )

        self.burn_output = self._file_row(
            layout,
            "Output",
            save=True,
        )

        return page

    # ==========================================================
    # CARD HELPERS
    # ==========================================================

    @staticmethod
    def _card_page() -> QWidget:
        page = QFrame()

        page.setObjectName(
            "InputCard"
        )

        return page

    @staticmethod
    def _section_label(
        text: str,
    ) -> QLabel:
        label = QLabel(text)

        label.setObjectName(
            "FieldTitle"
        )

        return label

    # ==========================================================
    # FILE HELPERS
    # ==========================================================

    def _file_row(
        self,
        layout: QFormLayout,
        label: str,
        *,
        save: bool,
        optional: bool = False,
    ) -> QLineEdit:
        field = QLineEdit()

        field.setMinimumHeight(
            42
        )

        button = QPushButton(
            "Browse..."
        )

        button.setMinimumHeight(
            42
        )

        row = QHBoxLayout()

        row.setSpacing(
            8
        )

        row.addWidget(
            field
        )

        row.addWidget(
            button
        )

        if save:
            button.clicked.connect(
                lambda: self._browse_save(
                    field
                )
            )
        else:
            button.clicked.connect(
                lambda: self._browse_open(
                    field
                )
            )

        if optional:
            label = f"{label}  ·  optional"

        layout.addRow(
            label,
            row,
        )

        return field

    def _browse_open(
        self,
        field: QLineEdit,
    ) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Media",
        )

        if path:
            field.setText(
                path
            )

    def _browse_save(
        self,
        field: QLineEdit,
    ) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Choose Output",
        )

        if path:
            field.setText(
                path
            )

    def _add_concatenate_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Videos",
        )

        for path in paths:
            if not self._list_contains(
                self.concatenate_files,
                path,
            ):
                self.concatenate_files.addItem(
                    path
                )

    @staticmethod
    def _list_contains(
        widget: QListWidget,
        value: str,
    ) -> bool:
        for index in range(
            widget.count()
        ):
            if widget.item(index).text() == value:
                return True

        return False

    def _remove_concatenate_files(self) -> None:
        for item in self.concatenate_files.selectedItems():
            self.concatenate_files.takeItem(
                self.concatenate_files.row(item)
            )

    # ==========================================================
    # SIGNALS
    # ==========================================================

    def _connect_signals(self) -> None:
        self.operation_combo.currentIndexChanged.connect(
            self._operation_changed
        )

        self.run_button.clicked.connect(
            self.run
        )

        self.cancel_button.clicked.connect(
            self.cancel
        )

        self.clear_button.clicked.connect(
            self.clear_activity
        )

    def _operation_changed(
        self,
        index: int,
    ) -> None:
        self.operation_stack.setCurrentIndex(
            index
        )

        self.operation_number.setText(
            f"{index + 1} / {len(self.OPERATIONS)}"
        )

        self._update_operation_description()

    def _update_operation_description(self) -> None:
        index = self.operation_combo.currentIndex()

        if index < 0:
            return

        description = (
            self.operation_combo.itemData(
                index
            )
        )

        self.operation_description.setText(
            str(description)
        )

    # ==========================================================
    # BUILD JOB
    # ==========================================================

    def _build_job(
        self,
    ) -> tuple[str, dict[str, Any]]:
        index = (
            self.operation_combo.currentIndex()
        )

        if index == 0:
            return (
                "inspect",
                {
                    "path": self._required(
                        self.inspect_input
                    )
                },
            )

        if index == 1:
            return (
                "duration",
                {
                    "path": self._required(
                        self.duration_input
                    )
                },
            )

        if index == 2:
            return (
                "convert",
                {
                    "input_path": self._required(
                        self.convert_input
                    ),
                    "output_path": self._required(
                        self.convert_output
                    ),
                },
            )

        if index == 3:
            inputs = [
                self.concatenate_files.item(
                    i
                ).text()
                for i in range(
                    self.concatenate_files.count()
                )
            ]

            if not inputs:
                raise ValueError(
                    "Add at least one input video."
                )

            return (
                "concatenate",
                {
                    "inputs": inputs,
                    "output": self._required(
                        self.concatenate_output
                    ),
                },
            )

        if index == 4:
            return (
                "join",
                {
                    "parts": [],
                    "output_video": self._required(
                        self.join_output
                    ),
                },
            )

        if index == 5:
            video = self._required(
                self.mux_video
            )

            output = self._required(
                self.mux_output
            )

            kwargs: dict[str, Any] = {}

            audio = (
                self.mux_audio.text()
                .strip()
            )

            if audio:
                kwargs["audio"] = audio

            return (
                "mux",
                {
                    "video": video,
                    "output": output,
                    **kwargs,
                },
            )

        if index == 6:
            return (
                "extract_audio",
                {
                    "video": self._required(
                        self.extract_audio_video
                    ),
                    "output": self._required(
                        self.extract_audio_output
                    ),
                    "stream_index": (
                        self.extract_audio_stream.value()
                    ),
                },
            )

        if index == 7:
            return (
                "extract_subtitle",
                {
                    "video": self._required(
                        self.extract_subtitle_video
                    ),
                    "output": self._required(
                        self.extract_subtitle_output
                    ),
                    "stream_index": (
                        self.extract_subtitle_stream.value()
                    ),
                },
            )

        if index == 8:
            return (
                "trim",
                {
                    "input_path": self._required(
                        self.trim_input
                    ),
                    "output_path": self._required(
                        self.trim_output
                    ),
                },
            )

        if index == 9:
            return (
                "burn_subtitles",
                {
                    "video": self._required(
                        self.burn_video
                    ),
                    "subtitle": self._required(
                        self.burn_subtitle
                    ),
                    "output": self._required(
                        self.burn_output
                    ),
                },
            )

        raise ValueError(
            "Unsupported operation."
        )

    @staticmethod
    def _required(
        field: QLineEdit,
    ) -> str:
        value = field.text().strip()

        if not value:
            raise ValueError(
                "Please fill in all required fields."
            )

        return value

    # ==========================================================
    # RUN
    # ==========================================================

    @Slot()
    def run(self) -> None:
        if self.thread is not None:
            return

        try:
            operation, kwargs = (
                self._build_job()
            )

        except Exception as exc:
            QMessageBox.warning(
                self,
                "Input Required",
                str(exc),
            )
            return

        self._set_running(
            True
        )

        self.progress_bar.setValue(
            0
        )

        self.percentage_label.setText(
            "0%"
        )

        self.status_label.setText(
            self._operation_display_name(
                operation
            )
        )

        self.file_label.setText(
            "Preparing..."
        )

        self.downloaded_label.clear()
        self.speed_label.clear()
        self.eta_label.clear()

        self.ready_badge.setText(
            "● PROCESSING"
        )

        self.ready_badge.setObjectName(
            "ProcessingBadge"
        )

        self._refresh_style(
            self.ready_badge
        )

        self._add_activity(
            "Processing started",
            f"Starting {self._operation_display_name(operation).lower()}.",
            "info",
        )

        self.thread = QThread(
            self
        )

        self.worker = MediaPipelineWorker(
            operation,
            kwargs,
        )

        self.worker.moveToThread(
            self.thread
        )

        self.thread.started.connect(
            self.worker.run
        )

        self.worker.progress.connect(
            self._on_progress
        )

        self.worker.completed.connect(
            self._on_completed
        )

        self.worker.failed.connect(
            self._on_failed
        )

        self.worker.cancelled.connect(
            self._on_cancelled
        )

        self.worker.completed.connect(
            self._finish_worker
        )

        self.worker.failed.connect(
            self._finish_worker
        )

        self.worker.cancelled.connect(
            self._finish_worker
        )

        self.thread.finished.connect(
            self._cleanup_worker
        )

        self.thread.start()

    # ==========================================================
    # CANCEL
    # ==========================================================

    @Slot()
    def cancel(self) -> None:
        if self.worker is None:
            return

        self.status_label.setText(
            "Cancelling..."
        )

        self.ready_badge.setText(
            "● CANCELLING"
        )

        self._add_activity(
            "Cancellation requested",
            "Veyra is stopping the current media operation.",
            "warning",
        )

        self.worker.cancel()

    # ==========================================================
    # PROGRESS
    # ==========================================================

    @Slot(
        str,
        str,
        float,
        object,
        object,
        object,
    )
    def _on_progress(
        self,
        info: str,
        filename: str,
        percentage: float,
        downloaded: Any,
        speed: Any,
        eta: Any,
    ) -> None:
        value = max(
            0,
            min(
                100,
                int(percentage),
            ),
        )

        self.status_label.setText(
            info or "Processing..."
        )

        self.file_label.setText(
            filename or "Processing media..."
        )

        self.progress_bar.setValue(
            value
        )

        self.percentage_label.setText(
            f"{value}%"
        )

        if downloaded not in (
            None,
            "",
            "--",
        ):
            self.downloaded_label.setText(
                f"Processed  {downloaded}"
            )

        if speed not in (
            None,
            "",
            "--",
        ):
            self.speed_label.setText(
                f"Speed  {speed}"
            )

        if eta not in (
            None,
            "",
            "--:--",
        ):
            self.eta_label.setText(
                f"ETA  {eta}"
            )

    # ==========================================================
    # COMPLETED
    # ==========================================================

    @Slot(object)
    def _on_completed(
        self,
        result: Any,
    ) -> None:
        self.progress_bar.setValue(
            100
        )

        self.percentage_label.setText(
            "100%"
        )

        self.status_label.setText(
            "Processing completed"
        )

        self.file_label.setText(
            "The operation finished successfully."
        )

        self.ready_badge.setText(
            "● COMPLETE"
        )

        self.ready_badge.setObjectName(
            "CompleteBadge"
        )

        self._refresh_style(
            self.ready_badge
        )

        self._add_result_activity(
            result
        )

    # ==========================================================
    # FAILED
    # ==========================================================

    @Slot(str)
    def _on_failed(
        self,
        error: str,
    ) -> None:
        self.status_label.setText(
            "Processing failed"
        )

        self.ready_badge.setText(
            "● FAILED"
        )

        self.ready_badge.setObjectName(
            "FailedBadge"
        )

        self._refresh_style(
            self.ready_badge
        )

        self._add_activity(
            "Processing failed",
            error,
            "error",
        )

        QMessageBox.critical(
            self,
            "Media Processing Error",
            error,
        )

    # ==========================================================
    # CANCELLED
    # ==========================================================

    @Slot()
    def _on_cancelled(self) -> None:
        self.status_label.setText(
            "Processing cancelled"
        )

        self.ready_badge.setText(
            "● CANCELLED"
        )

        self.ready_badge.setObjectName(
            "CancelledBadge"
        )

        self._refresh_style(
            self.ready_badge
        )

        self._add_activity(
            "Processing cancelled",
            "The media operation was cancelled.",
            "cancelled",
        )

    # ==========================================================
    # WORKER FINISH
    # ==========================================================

    def _finish_worker(
        self,
        *_args: Any,
    ) -> None:
        if self.thread is not None:
            self.thread.quit()

    def _cleanup_worker(self) -> None:
        if self.worker is not None:
            self.worker.deleteLater()

        if self.thread is not None:
            self.thread.deleteLater()

        self.worker = None
        self.thread = None

        self._set_running(
            False
        )

    # ==========================================================
    # STATE
    # ==========================================================

    def _set_running(
        self,
        running: bool,
    ) -> None:
        self.run_button.setEnabled(
            not running
        )

        self.cancel_button.setEnabled(
            running
        )

        self.operation_combo.setEnabled(
            not running
        )

    # ==========================================================
    # ACTIVITY
    # ==========================================================

    def _add_activity(
        self,
        title: str,
        message: str = "",
        status: str = "info",
    ) -> ActivityCard:
        card = ActivityCard(
            title,
            message,
            status,
        )

        # Insert before stretch.
        self.activity_layout.insertWidget(
            self.activity_layout.count() - 1,
            card,
        )

        self._update_activity_count()

        QApplication.processEvents()

        scrollbar = (
            self.activity_scroll.verticalScrollBar()
        )

        scrollbar.setValue(
            scrollbar.maximum()
        )

        return card

    def _add_result_activity(
        self,
        result: Any,
    ) -> None:
        """
        Render a processor result without exposing Python
        repr(), JSON or implementation details.
        """

        operation = self.operation_combo.currentText()

        if isinstance(
            result,
            dict,
        ):
            if result.get(
                "skipped"
            ):
                card = self._add_activity(
                    f"{operation} skipped",
                    "The requested output already exists.",
                    "warning",
                )

                self._render_mapping(
                    card,
                    result,
                )

                return

        card = self._add_activity(
            f"{operation} completed",
            "The media operation completed successfully.",
            "success",
        )

        self._render_result(
            card,
            result,
        )

    def _render_result(
        self,
        card: ActivityCard,
        result: Any,
    ) -> None:
        if result is None:
            return

        if isinstance(
            result,
            (str, Path),
        ):
            card.add_detail(
                "Result",
                str(result),
            )
            return

        if isinstance(
            result,
            bool,
        ):
            card.add_detail(
                "Status",
                "Yes" if result else "No",
            )
            return

        if isinstance(
            result,
            (int, float),
        ):
            card.add_detail(
                "Result",
                self._format_value(
                    result
                ),
            )
            return

        if isinstance(
            result,
            dict,
        ):
            self._render_mapping(
                card,
                result,
            )
            return

        if dataclasses.is_dataclass(
            result
        ):
            self._render_mapping(
                card,
                dataclasses.asdict(
                    result
                ),
            )
            return

        attributes = getattr(
            result,
            "__dict__",
            None,
        )

        if isinstance(
            attributes,
            dict,
        ):
            self._render_mapping(
                card,
                attributes,
            )
            return

        card.add_detail(
            "Result",
            self._format_value(
                result
            ),
        )

    def _render_mapping(
        self,
        card: ActivityCard,
        values: dict[str, Any],
    ) -> None:
        for key, value in values.items():
            if key.startswith(
                "_"
            ):
                continue

            if value is None:
                continue

            label = self._humanize_key(
                key
            )

            formatted = self._format_value(
                value,
                key=key,
            )

            if formatted:
                card.add_detail(
                    label,
                    formatted,
                )

    # ==========================================================
    # VALUE FORMATTERS
    # ==========================================================

    @classmethod
    def _format_value(
        cls,
        value: Any,
        *,
        key: str = "",
    ) -> str:
        if value is None:
            return ""

        if isinstance(
            value,
            bool,
        ):
            return (
                "Yes"
                if value
                else "No"
            )

        if isinstance(
            value,
            Path,
        ):
            return value.name or str(value)

        if isinstance(
            value,
            str,
        ):
            return cls._format_string(
                value,
                key,
            )

        if isinstance(
            value,
            float,
        ):
            if (
                "duration" in key.lower()
                or key.lower()
                in {
                    "length",
                    "time",
                    "seconds",
                }
            ):
                return cls._format_duration(
                    value
                )

            if (
                "size" in key.lower()
                or "bytes" in key.lower()
            ):
                return cls._format_size(
                    value
                )

            if math.isfinite(value):
                return f"{value:g}"

            return str(value)

        if isinstance(
            value,
            int,
        ):
            if (
                "duration" in key.lower()
                or key.lower()
                in {
                    "length",
                    "time",
                    "seconds",
                }
            ):
                return cls._format_duration(
                    float(value)
                )

            if (
                "size" in key.lower()
                or "bytes" in key.lower()
            ):
                return cls._format_size(
                    float(value)
                )

            return f"{value:,}"

        if isinstance(
            value,
            (list, tuple, set),
        ):
            if not value:
                return "None"

            if all(
                isinstance(
                    item,
                    (str, Path),
                )
                for item in value
            ):
                return " · ".join(
                    str(item)
                    for item in value
                )

            return f"{len(value)} items"

        if isinstance(
            value,
            dict,
        ):
            return f"{len(value)} fields"

        return str(value)

    @classmethod
    def _format_string(
        cls,
        value: str,
        key: str = "",
    ) -> str:
        text = value.strip()

        if not text:
            return ""

        lower_key = key.lower()

        # ------------------------------------------------------
        # Duration strings
        # ------------------------------------------------------

        if (
            "duration" in lower_key
            and cls._looks_like_seconds(
                text
            )
        ):
            try:
                return cls._format_duration(
                    float(text)
                )
            except ValueError:
                pass

        # ------------------------------------------------------
        # Paths
        # ------------------------------------------------------

        if (
            "/" in text
            or text.startswith(
                "~"
            )
        ):
            try:
                path = Path(text)

                if path.exists():
                    return path.name
            except Exception:
                pass

        return text

    @staticmethod
    def _looks_like_seconds(
        value: str,
    ) -> bool:
        try:
            float(value)
            return True
        except ValueError:
            return False

    @staticmethod
    def _format_duration(
        seconds: float,
    ) -> str:
        if not math.isfinite(
            seconds
        ):
            return str(seconds)

        negative = seconds < 0

        seconds = abs(
            seconds
        )

        total_ms = int(
            round(
                seconds * 1000
            )
        )

        hours, remainder = divmod(
            total_ms,
            3_600_000,
        )

        minutes, remainder = divmod(
            remainder,
            60_000,
        )

        secs, milliseconds = divmod(
            remainder,
            1000,
        )

        prefix = "-" if negative else ""

        return (
            f"{prefix}"
            f"{hours:02d}:"
            f"{minutes:02d}:"
            f"{secs:02d}."
            f"{milliseconds:03d}"
        )

    @staticmethod
    def _format_size(
        value: float,
    ) -> str:
        if value < 0:
            return str(value)

        units = [
            "B",
            "KB",
            "MB",
            "GB",
            "TB",
        ]

        size = float(value)

        for unit in units:
            if size < 1024 or unit == units[-1]:
                if unit == "B":
                    return f"{int(size)} {unit}"

                return f"{size:.1f} {unit}"

            size /= 1024

        return f"{size:.1f} TB"

    @staticmethod
    def _humanize_key(
        key: str,
    ) -> str:
        replacements = {
            "output_path": "Output",
            "input_path": "Input",
            "stream_index": "Stream",
            "video_codec": "Video Codec",
            "audio_codec": "Audio Codec",
            "codec_name": "Codec",
            "codec_type": "Type",
            "sample_rate": "Sample Rate",
            "bit_rate": "Bitrate",
            "frame_rate": "Frame Rate",
            "width": "Width",
            "height": "Height",
            "format_name": "Format",
            "format_long_name": "Format",
        }

        if key in replacements:
            return replacements[key]

        text = key.replace(
            "_",
            " ",
        )

        return text.title()

    # ==========================================================
    # DISPLAY HELPERS
    # ==========================================================

    @staticmethod
    def _operation_display_name(
        operation: str,
    ) -> str:
        return {
            "inspect": "Inspecting media",
            "duration": "Reading duration",
            "convert": "Converting media",
            "concatenate": "Concatenating videos",
            "join": "Joining media",
            "mux": "Muxing media",
            "extract_audio": "Extracting audio",
            "extract_subtitle": "Extracting subtitles",
            "trim": "Trimming media",
            "burn_subtitles": "Burning subtitles",
        }.get(
            operation,
            operation.replace(
                "_",
                " ",
            ).title(),
        )

    def _update_activity_count(
        self,
    ) -> None:
        count = (
            self.activity_layout.count()
            - 1
        )

        word = (
            "activity"
            if count == 1
            else "activities"
        )

        self.activity_count.setText(
            f"{count} {word}"
        )

    def clear_activity(self) -> None:
        while (
            self.activity_layout.count()
            > 1
        ):
            item = (
                self.activity_layout.takeAt(
                    0
                )
            )

            widget = item.widget()

            if widget is not None:
                widget.deleteLater()

        self._update_activity_count()

        self.status_label.setText(
            "Ready to process"
        )

        self.file_label.setText(
            "No media selected"
        )

        self.progress_bar.setValue(
            0
        )

        self.percentage_label.setText(
            "0%"
        )

        self.downloaded_label.clear()
        self.speed_label.clear()
        self.eta_label.clear()

        self.ready_badge.setText(
            "● READY"
        )

        self.ready_badge.setObjectName(
            "ReadyBadge"
        )

        self._refresh_style(
            self.ready_badge
        )

    @staticmethod
    def _refresh_style(
        widget: QWidget,
    ) -> None:
        widget.style().unpolish(
            widget
        )

        widget.style().polish(
            widget
        )

        widget.update()

    # ==========================================================
    # STYLE
    # ==========================================================

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            /* ==================================================
               PAGE
               ================================================== */

            QWidget {
                font-family: "Inter", "Noto Sans", sans-serif;
            }

            #PageTitle {
                color: #f8fafc;
                font-size: 28px;
                font-weight: 800;
            }

            #PageSubtitle {
                color: #94a3b8;
                font-size: 13px;
            }

            /* ==================================================
               BADGES
               ================================================== */

            #ReadyBadge,
            #ProcessingBadge,
            #CompleteBadge,
            #FailedBadge,
            #CancelledBadge {
                border-radius: 999px;
                padding: 7px 13px;
                font-size: 11px;
                font-weight: 700;
            }

            #ReadyBadge {
                color: #94a3b8;
                background: #1e293b;
            }

            #ProcessingBadge {
                color: #60a5fa;
                background: #172554;
            }

            #CompleteBadge {
                color: #34d399;
                background: #052e25;
            }

            #FailedBadge {
                color: #fb7185;
                background: #450a0a;
            }

            #CancelledBadge {
                color: #fbbf24;
                background: #422006;
            }

            /* ==================================================
               OPERATION
               ================================================== */

            #OperationCard {
                background: #151f32;
                border: 1px solid #253249;
                border-radius: 14px;
            }

            #SectionTitle {
                color: #f8fafc;
                font-size: 14px;
                font-weight: 700;
            }

            #OperationNumber {
                color: #64748b;
                font-size: 12px;
                font-weight: 600;
            }

            #OperationDescription {
                color: #64748b;
                font-size: 12px;
            }

            QComboBox {
                background: #0f172a;
                color: #e2e8f0;
                border: 1px solid #334155;
                border-radius: 9px;
                padding: 0 13px;
                font-size: 13px;
                min-height: 44px;
            }

            QComboBox:hover {
                border-color: #475569;
            }

            QComboBox:focus {
                border-color: #3b82f6;
            }

            QComboBox QAbstractItemView {
                background: #111827;
                color: #e2e8f0;
                border: 1px solid #334155;
                selection-background-color: #2563eb;
                selection-color: white;
                padding: 5px;
            }

            /* ==================================================
               INPUT CARD
               ================================================== */

            #InputCard {
                background: #151f32;
                border: 1px solid #253249;
                border-radius: 14px;
            }

            #InputCard QLabel {
                color: #94a3b8;
                font-size: 12px;
            }

            #FieldTitle {
                color: #cbd5e1;
                font-size: 12px;
                font-weight: 700;
            }

            #FormTitle {
                color: #f8fafc;
                font-size: 15px;
                font-weight: 700;
            }

            #FormDescription {
                color: #64748b;
                font-size: 12px;
            }

            QLineEdit {
                background: #0f172a;
                color: #e2e8f0;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 0 12px;
                font-size: 12px;
            }

            QLineEdit:hover {
                border-color: #475569;
            }

            QLineEdit:focus {
                border-color: #3b82f6;
            }

            QListWidget {
                background: #0f172a;
                color: #cbd5e1;
                border: 1px solid #334155;
                border-radius: 9px;
                padding: 5px;
                font-size: 12px;
            }

            QListWidget::item {
                padding: 8px;
                border-radius: 6px;
            }

            QListWidget::item:selected {
                background: #1d4ed8;
                color: white;
            }

            QSpinBox {
                background: #0f172a;
                color: #e2e8f0;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 7px 10px;
            }

            /* ==================================================
               PROGRESS
               ================================================== */

            #ProgressCard {
                background: #151f32;
                border: 1px solid #253249;
                border-radius: 14px;
            }

            #ProgressTitle {
                color: #e2e8f0;
                font-size: 13px;
                font-weight: 700;
            }

            #ProgressPercentage {
                color: #60a5fa;
                font-size: 13px;
                font-weight: 800;
            }

            #ProgressFile {
                color: #64748b;
                font-size: 11px;
            }

            QProgressBar {
                background: #0f172a;
                border: none;
                border-radius: 4px;
            }

            QProgressBar::chunk {
                background: #2563eb;
                border-radius: 4px;
            }

            #ProgressCard QLabel {
                color: #64748b;
                font-size: 10px;
            }

            /* ==================================================
               ACTIVITY
               ================================================== */

            #ActivityCount {
                color: #64748b;
                font-size: 11px;
            }

            #ActivityCard_info,
            #ActivityCard_success,
            #ActivityCard_warning,
            #ActivityCard_error,
            #ActivityCard_cancelled {
                border-radius: 12px;
            }

            #ActivityCard_info {
                background: #121d2e;
                border: 1px solid #24334a;
            }

            #ActivityCard_success {
                background: #0d201c;
                border: 1px solid #164e3b;
            }

            #ActivityCard_warning {
                background: #211a0c;
                border: 1px solid #574015;
            }

            #ActivityCard_error {
                background: #210f13;
                border: 1px solid #5f1d2a;
            }

            #ActivityCard_cancelled {
                background: #21170b;
                border: 1px solid #5a4012;
            }

            #ActivityIcon {
                color: #60a5fa;
                font-size: 18px;
                font-weight: 800;
            }

            #ActivityCard_success #ActivityIcon {
                color: #34d399;
            }

            #ActivityCard_warning #ActivityIcon {
                color: #fbbf24;
            }

            #ActivityCard_error #ActivityIcon {
                color: #fb7185;
            }

            #ActivityCard_cancelled #ActivityIcon {
                color: #fbbf24;
            }

            #ActivityTitle {
                color: #e2e8f0;
                font-size: 12px;
                font-weight: 700;
            }

            #ActivityTime {
                color: #475569;
                font-size: 10px;
            }

            #ActivityMessage {
                color: #94a3b8;
                font-size: 11px;
            }

            #ActivityDetailLabel {
                color: #475569;
                font-size: 9px;
                font-weight: 800;
                letter-spacing: 0.5px;
            }

            #ActivityDetailValue {
                color: #cbd5e1;
                font-size: 11px;
            }

            /* ==================================================
               BUTTONS
               ================================================== */

            QPushButton {
                background: #1e293b;
                color: #cbd5e1;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 0 15px;
                font-size: 12px;
                font-weight: 600;
                min-height: 40px;
            }

            QPushButton:hover {
                background: #263449;
                border-color: #475569;
            }

            QPushButton:pressed {
                background: #334155;
            }

            QPushButton:disabled {
                color: #475569;
                background: #111827;
                border-color: #1e293b;
            }

            #PrimaryButton {
                background: #2563eb;
                color: white;
                border: none;
                font-size: 13px;
                font-weight: 700;
            }

            #PrimaryButton:hover {
                background: #3b82f6;
            }

            #PrimaryButton:pressed {
                background: #1d4ed8;
            }

            #CancelButton {
                background: #21131a;
                color: #fb7185;
                border-color: #4c1d2b;
            }

            #CancelButton:hover {
                background: #351720;
            }

            #SecondaryButton {
                background: transparent;
                color: #94a3b8;
            }

            /* ==================================================
               SCROLL AREA
               ================================================== */

            QScrollArea {
                background: transparent;
                border: none;
            }

            QScrollBar:vertical {
                background: transparent;
                width: 7px;
                margin: 2px;
            }

            QScrollBar::handle:vertical {
                background: #334155;
                border-radius: 3px;
                min-height: 30px;
            }

            QScrollBar::handle:vertical:hover {
                background: #475569;
            }

            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0px;
            }
            """
        )