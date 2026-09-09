from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QProgressBar,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from media.models import (
    BurnerSettings,
    ConverterSettings,
    CutterSettings,
    JoinerSettings,
)

from jobs.media_engine_processor import (
    JobCancelled,
    MediaEngineJob,
    MediaEngineJobResult,
    MediaEngineProcessor,
)


# ============================================================
# MEDIA ENGINE PAGE
# ============================================================


class MediaEnginePage(QWidget):
    """
    Media Engine page.

    Supported operations:

        - Inspect
        - Convert
        - Cut
        - Join
        - Burn subtitles

    Output handling:

        Convert:
            output directory + custom filename + output format

        Cut:
            output directory + custom base filename + output format

        Join:
            output directory + custom filename + output format

        Burn subtitles:
            output directory + custom filename + output format
    """

    operation_changed = Signal(str)

    # ========================================================
    # INIT
    # ========================================================

    def __init__(
        self,
        *,
        ffmpeg: str = "ffmpeg",
        ffprobe: str = "ffprobe",
        parent: QWidget | None = None,
    ) -> None:

        super().__init__(parent)

        self.ffmpeg = ffmpeg
        self.ffprobe = ffprobe

        # ----------------------------------------------------
        # STATE
        # ----------------------------------------------------

        self.media_files: list[Path] = []
        self.subtitle_files: list[Path] = []

        self.selected_media: Path | None = None
        self.selected_subtitle: Path | None = None

        self.working_media: list[Path] = []

        self.operation = "convert"

        self.inspection_cache: dict[Path, Any] = {}

        self.output_directory: Path | None = None
        self._output_directory_user_modified = False

        # ----------------------------------------------------
        # OUTPUT NAME STATE
        # ----------------------------------------------------

        self._output_name_user_modified = False

        # ----------------------------------------------------
        # PROCESSOR
        # ----------------------------------------------------

        self.processor = MediaEngineProcessor(
            ffmpeg=self.ffmpeg,
            ffprobe=self.ffprobe,
            progress_callback=self._on_progress,
            error_callback=self._on_error,
            job_callback=self._on_job,
        )

        # ----------------------------------------------------
        # UI
        # ----------------------------------------------------

        self._build_ui()
        self._connect_signals()

        self._update_operation_ui()

    # ========================================================
    # BUILD UI
    # ========================================================

    def _build_ui(self) -> None:

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        # ----------------------------------------------------
        # SCROLL AREA
        # ----------------------------------------------------

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        content = QWidget()

        root = QVBoxLayout(content)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # ----------------------------------------------------
        # TITLE
        # ----------------------------------------------------

        title = QLabel("Media Engine")
        title.setObjectName("pageTitle")

        subtitle = QLabel(
            "Inspect, convert, cut, join and burn subtitles."
        )
        subtitle.setObjectName("pageSubtitle")

        root.addWidget(title)
        root.addWidget(subtitle)

        # ----------------------------------------------------
        # TOP AREA
        # ----------------------------------------------------

        top_splitter = QSplitter(Qt.Horizontal)

        self.media_panel = self._build_media_panel()
        self.inspection_panel = self._build_inspection_panel()

        top_splitter.addWidget(self.media_panel)
        top_splitter.addWidget(self.inspection_panel)

        top_splitter.setStretchFactor(0, 1)
        top_splitter.setStretchFactor(1, 1)

        top_splitter.setMinimumHeight(220)
        top_splitter.setMaximumHeight(330)

        root.addWidget(top_splitter)

        # ----------------------------------------------------
        # OPERATION
        # ----------------------------------------------------

        root.addWidget(
            self._build_action_panel()
        )

        # ----------------------------------------------------
        # WORK WITH
        # ----------------------------------------------------

        root.addWidget(
            self._build_work_panel()
        )

        # ----------------------------------------------------
        # SETTINGS
        # ----------------------------------------------------

        settings_splitter = QSplitter(Qt.Horizontal)

        settings_splitter.addWidget(
            self._build_shared_settings()
        )

        settings_splitter.addWidget(
            self._build_specific_settings()
        )

        settings_splitter.setStretchFactor(0, 1)
        settings_splitter.setStretchFactor(1, 1)

        root.addWidget(settings_splitter)

        # ----------------------------------------------------
        # OUTPUT
        # ----------------------------------------------------

        self.output_panel = self._build_output_panel()

        root.addWidget(
            self.output_panel
        )

        # ----------------------------------------------------
        # START
        # ----------------------------------------------------

        root.addWidget(
            self._build_start_panel()
        )

        # ----------------------------------------------------
        # PROGRESS
        # ----------------------------------------------------

        root.addWidget(
            self._build_progress_panel()
        )

        root.addStretch()

        scroll.setWidget(content)

        outer_layout.addWidget(scroll)

        self._scroll_area = scroll
        self._content_widget = content
        self._top_splitter = top_splitter

    # ========================================================
    # MEDIA PANEL
    # ========================================================

    def _build_media_panel(self) -> QWidget:

        panel = QGroupBox("Media")

        layout = QVBoxLayout(panel)
        layout.setSpacing(6)

        buttons = QHBoxLayout()

        self.add_media_button = QPushButton(
            "Add Media"
        )

        self.add_srt_button = QPushButton(
            "Add SRT"
        )

        self.remove_media_button = QPushButton(
            "Remove"
        )

        self.clear_media_button = QPushButton(
            "Clear"
        )

        buttons.addWidget(
            self.add_media_button
        )

        buttons.addWidget(
            self.add_srt_button
        )

        buttons.addStretch()

        buttons.addWidget(
            self.remove_media_button
        )

        buttons.addWidget(
            self.clear_media_button
        )

        layout.addLayout(buttons)

        layout.addWidget(
            QLabel("Loaded Media")
        )

        self.media_list = QListWidget()

        self.media_list.setSelectionMode(
            QListWidget.SingleSelection
        )

        layout.addWidget(
            self.media_list,
            stretch=1,
        )

        layout.addWidget(
            QLabel("Subtitle Files")
        )

        self.srt_list = QListWidget()

        self.srt_list.setMaximumHeight(70)

        layout.addWidget(
            self.srt_list
        )

        return panel

    # ========================================================
    # INSPECTION PANEL
    # ========================================================

    def _build_inspection_panel(self) -> QWidget:

        panel = QGroupBox("Inspection")

        layout = QVBoxLayout(panel)
        layout.setSpacing(5)

        self.inspection_header = QLabel(
            "Select media to inspect."
        )

        self.inspection_header.setObjectName(
            "inspectionHeader"
        )

        layout.addWidget(
            self.inspection_header
        )

        self.inspection_text = QTextEdit()

        self.inspection_text.setReadOnly(
            True
        )

        self.inspection_text.setPlaceholderText(
            "Detailed media information will appear here."
        )

        layout.addWidget(
            self.inspection_text,
            stretch=1,
        )

        self.inspect_button = QPushButton(
            "Inspect Selected"
        )

        layout.addWidget(
            self.inspect_button
        )

        return panel

    # ========================================================
    # ACTION PANEL
    # ========================================================

    def _build_action_panel(self) -> QWidget:

        panel = QGroupBox(
            "What would you like to do?"
        )

        layout = QHBoxLayout(panel)

        self.operation_combo = QComboBox()

        self.operation_combo.addItem(
            "Convert",
            "convert",
        )

        self.operation_combo.addItem(
            "Cut",
            "cut",
        )

        self.operation_combo.addItem(
            "Join",
            "join",
        )

        self.operation_combo.addItem(
            "Burn Subtitles",
            "burn_subtitles",
        )

        layout.addWidget(
            QLabel("Operation:")
        )

        layout.addWidget(
            self.operation_combo,
            stretch=1,
        )

        return panel

    # ========================================================
    # WORK WITH
    # ========================================================

    def _build_work_panel(self) -> QWidget:

        panel = QGroupBox("Work With")

        layout = QVBoxLayout(panel)

        self.work_description = QLabel(
            "Choose the media you want to work with."
        )

        self.work_description.setWordWrap(True)

        layout.addWidget(
            self.work_description
        )

        media_row = QHBoxLayout()

        self.work_selected_button = QPushButton(
            "Use Selected"
        )

        self.work_all_button = QPushButton(
            "Use All Loaded"
        )

        self.choose_work_button = QPushButton(
            "Choose Loaded..."
        )

        self.browse_work_button = QPushButton(
            "Browse..."
        )

        media_row.addWidget(
            self.work_selected_button
        )

        media_row.addWidget(
            self.work_all_button
        )

        media_row.addWidget(
            self.choose_work_button
        )

        media_row.addWidget(
            self.browse_work_button
        )

        media_row.addStretch()

        layout.addLayout(
            media_row
        )

        self.working_label = QLabel(
            "No media selected."
        )

        self.working_label.setWordWrap(True)

        layout.addWidget(
            self.working_label
        )

        self.subtitle_controls = QWidget()

        subtitle_layout = QHBoxLayout(
            self.subtitle_controls
        )

        subtitle_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        subtitle_layout.addWidget(
            QLabel("Subtitle:")
        )

        self.use_selected_subtitle_button = QPushButton(
            "Use Selected SRT"
        )

        self.browse_subtitle_button = QPushButton(
            "Browse SRT..."
        )

        subtitle_layout.addWidget(
            self.use_selected_subtitle_button
        )

        subtitle_layout.addWidget(
            self.browse_subtitle_button
        )

        subtitle_layout.addStretch()

        layout.addWidget(
            self.subtitle_controls
        )

        self.subtitle_controls.setVisible(
            False
        )

        self.subtitle_working_label = QLabel(
            "No subtitle selected."
        )

        self.subtitle_working_label.setWordWrap(
            True
        )

        layout.addWidget(
            self.subtitle_working_label
        )

        return panel

    # ========================================================
    # SHARED SETTINGS
    # ========================================================

    def _build_shared_settings(self) -> QWidget:

        panel = QGroupBox(
            "Shared Settings"
        )

        layout = QFormLayout(panel)

        self.video_mode = QComboBox()

        self.video_mode.addItems([
            "Fast Copy",
            "Re-encode",
        ])

        self.audio_mode = QComboBox()

        self.audio_mode.addItems([
            "Fast Copy",
            "Re-encode",
        ])

        self.video_codec = QComboBox()

        self.video_codec.addItems([
            "libx264",
            "libx265",
            "libvpx-vp9",
            "copy",
        ])

        self.audio_codec = QComboBox()

        self.audio_codec.addItems([
            "aac",
            "libopus",
            "mp3",
            "copy",
        ])

        self.preset = QComboBox()

        self.preset.addItems([
            "ultrafast",
            "superfast",
            "veryfast",
            "faster",
            "fast",
            "medium",
            "slow",
        ])

        self.crf = QComboBox()

        self.crf.addItems([
            "18",
            "20",
            "22",
            "23",
            "24",
            "26",
            "28",
        ])

        self.audio_bitrate = QComboBox()

        self.audio_bitrate.addItems([
            "128k",
            "160k",
            "192k",
            "256k",
            "320k",
        ])

        self.pixel_format = QComboBox()

        self.pixel_format.addItems([
            "yuv420p",
            "yuv422p",
            "yuv444p",
        ])

        self.faststart = QCheckBox(
            "Faststart"
        )

        self.faststart.setChecked(
            True
        )

        self.overwrite = QCheckBox(
            "Overwrite existing files"
        )

        layout.addRow(
            "Video Mode",
            self.video_mode,
        )

        layout.addRow(
            "Audio Mode",
            self.audio_mode,
        )

        layout.addRow(
            "Video Codec",
            self.video_codec,
        )

        layout.addRow(
            "Audio Codec",
            self.audio_codec,
        )

        layout.addRow(
            "Preset",
            self.preset,
        )

        layout.addRow(
            "CRF",
            self.crf,
        )

        layout.addRow(
            "Audio Bitrate",
            self.audio_bitrate,
        )

        layout.addRow(
            "Pixel Format",
            self.pixel_format,
        )

        layout.addRow(
            self.faststart
        )

        layout.addRow(
            self.overwrite
        )

        return panel

    # ========================================================
    # SPECIFIC SETTINGS
    # ========================================================

    def _build_specific_settings(self) -> QWidget:

        self.specific_stack = QStackedWidget()

        self.specific_stack.addWidget(
            self._build_convert_settings()
        )

        self.specific_stack.addWidget(
            self._build_cut_settings()
        )

        self.specific_stack.addWidget(
            self._build_join_settings()
        )

        self.specific_stack.addWidget(
            self._build_burn_settings()
        )

        panel = QGroupBox(
            "Work Specific Settings"
        )

        layout = QVBoxLayout(panel)

        layout.addWidget(
            self.specific_stack
        )

        return panel


    # ========================================================
    # CONVERT SETTINGS
    # ========================================================

    def _build_convert_settings(self) -> QWidget:

        widget = QWidget()

        layout = QFormLayout(widget)

        self.convert_output_format = QComboBox()

        self.convert_output_format.addItems([
            "mp4",
            "mkv",
            "mov",
            "avi",
            "webm",
            "ts",
        ])

        self.keep_subtitles = QCheckBox(
            "Keep subtitles"
        )

        self.keep_subtitles.setChecked(
            True
        )

        self.keep_metadata = QCheckBox(
            "Keep metadata"
        )

        self.keep_metadata.setChecked(
            True
        )

        layout.addRow(
            "Output Format:",
            self.convert_output_format,
        )

        layout.addRow(
            self.keep_subtitles
        )

        layout.addRow(
            self.keep_metadata
        )

        return widget


    # ========================================================
    # CUT SETTINGS
    # ========================================================

    def _build_cut_settings(self) -> QWidget:

        widget = QWidget()

        layout = QVBoxLayout(widget)

        mode_form = QFormLayout()

        self.cut_mode = QComboBox()

        self.cut_mode.addItems([
            "Duration",
            "Parts",
            "Timestamps",
            "Start / End",
        ])

        mode_form.addRow(
            "Cut Method:",
            self.cut_mode,
        )

        layout.addLayout(
            mode_form
        )

        self.cut_stack = QStackedWidget()

        self.cut_stack.addWidget(
            self._build_cut_duration_widget()
        )

        self.cut_stack.addWidget(
            self._build_cut_parts_widget()
        )

        self.cut_stack.addWidget(
            self._build_cut_timestamps_widget()
        )

        self.cut_stack.addWidget(
            self._build_cut_start_end_widget()
        )

        layout.addWidget(
            self.cut_stack
        )

        self.cut_subtitles = QCheckBox(
            "Cut subtitles along with the media"
        )

        self.cut_subtitles.setChecked(
            True
        )

        layout.addWidget(
            self.cut_subtitles
        )

        layout.addStretch()

        return widget

    # ========================================================
    # CUT - DURATION
    # ========================================================

    def _build_cut_duration_widget(self) -> QWidget:

        widget = QWidget()

        layout = QFormLayout(widget)

        self.cut_duration = QDoubleSpinBox()

        self.cut_duration.setRange(
            0.001,
            86400.0,
        )

        self.cut_duration.setDecimals(
            3
        )

        self.cut_duration.setSingleStep(
            1.0
        )

        self.cut_duration.setValue(
            60.0
        )

        self.cut_duration.setSuffix(
            " seconds"
        )

        layout.addRow(
            "Duration:",
            self.cut_duration,
        )

        help_label = QLabel(
            "Enter how long each output segment should be."
        )

        help_label.setWordWrap(True)

        layout.addRow(
            help_label
        )

        return widget

    # ========================================================
    # CUT - PARTS
    # ========================================================

    def _build_cut_parts_widget(self) -> QWidget:

        widget = QWidget()

        layout = QFormLayout(widget)

        self.cut_parts = QSpinBox()

        self.cut_parts.setRange(
            2,
            1000,
        )

        self.cut_parts.setValue(
            2
        )

        layout.addRow(
            "Number of Parts:",
            self.cut_parts,
        )

        help_label = QLabel(
            "The media will be divided into this many parts."
        )

        help_label.setWordWrap(True)

        layout.addRow(
            help_label
        )

        return widget

    # ========================================================
    # CUT - TIMESTAMPS
    # ========================================================

    def _build_cut_timestamps_widget(self) -> QWidget:

        widget = QWidget()

        layout = QVBoxLayout(widget)

        layout.addWidget(
            QLabel(
                "Add timestamps where a new segment should begin."
            )
        )

        row = QHBoxLayout()

        self.timestamp_input = QLineEdit()

        self.timestamp_input.setPlaceholderText(
            "Example: 00:05:00 or 300"
        )

        self.add_timestamp_button = QPushButton(
            "Add Timestamp"
        )

        row.addWidget(
            self.timestamp_input,
            stretch=1,
        )

        row.addWidget(
            self.add_timestamp_button
        )

        layout.addLayout(
            row
        )

        self.timestamp_list = QListWidget()

        self.timestamp_list.setMinimumHeight(
            100
        )

        self.timestamp_list.setMaximumHeight(
            180
        )

        layout.addWidget(
            self.timestamp_list
        )

        remove_row = QHBoxLayout()

        self.remove_timestamp_button = QPushButton(
            "Remove Selected Timestamp"
        )

        self.clear_timestamps_button = QPushButton(
            "Clear Timestamps"
        )

        remove_row.addWidget(
            self.remove_timestamp_button
        )

        remove_row.addWidget(
            self.clear_timestamps_button
        )

        remove_row.addStretch()

        layout.addLayout(
            remove_row
        )

        return widget

    # ========================================================
    # CUT - START / END
    # ========================================================

    def _build_cut_start_end_widget(self) -> QWidget:

        widget = QWidget()

        layout = QFormLayout(widget)

        self.cut_start = QDoubleSpinBox()

        self.cut_start.setRange(
            0.0,
            86400.0,
        )

        self.cut_start.setDecimals(
            3
        )

        self.cut_start.setValue(
            0.0
        )

        self.cut_start.setSuffix(
            " seconds"
        )

        self.cut_end = QDoubleSpinBox()

        self.cut_end.setRange(
            0.0,
            86400.0,
        )

        self.cut_end.setDecimals(
            3
        )

        self.cut_end.setValue(
            60.0
        )

        self.cut_end.setSuffix(
            " seconds"
        )

        layout.addRow(
            "Start:",
            self.cut_start,
        )

        layout.addRow(
            "End:",
            self.cut_end,
        )

        return widget

    # ========================================================
    # JOIN SETTINGS
    # ========================================================

    def _build_join_settings(self) -> QWidget:

        widget = QWidget()

        layout = QVBoxLayout(widget)

        self.join_subtitles = QCheckBox(
            "Join subtitles"
        )

        self.join_subtitles.setChecked(
            True
        )

        layout.addWidget(
            self.join_subtitles
        )

        label = QLabel(
            "Join requires two or more media files. "
            "The files are joined in the order shown in Work With."
        )

        label.setWordWrap(True)

        layout.addWidget(
            label
        )

        layout.addStretch()

        return widget

    # ========================================================
    # BURN SETTINGS
    # ========================================================

    def _build_burn_settings(self) -> QWidget:

        widget = QWidget()

        layout = QFormLayout(widget)

        self.burn_subtitle_combo = QComboBox()

        self.burn_font = QComboBox()

        self.burn_font.addItems([
            "Default",
            "Arial",
            "Helvetica",
            "DejaVu Sans",
        ])

        self.burn_font_size = QComboBox()

        self.burn_font_size.addItems([
            "Default",
            "18",
            "20",
            "24",
            "28",
            "32",
            "36",
        ])

        self.burn_color = QComboBox()

        self.burn_color.addItems([
            "White",
            "Yellow",
            "Green",
            "Cyan",
        ])

        layout.addRow(
            "Subtitle:",
            self.burn_subtitle_combo,
        )

        layout.addRow(
            "Font:",
            self.burn_font,
        )

        layout.addRow(
            "Font Size:",
            self.burn_font_size,
        )

        layout.addRow(
            "Color:",
            self.burn_color,
        )

        return widget

    # ========================================================
    # OUTPUT PANEL
    # ========================================================

    def _build_output_panel(self) -> QWidget:

        panel = QGroupBox(
            "Output"
        )

        layout = QFormLayout(panel)

        # ----------------------------------------------------
        # OUTPUT DIRECTORY
        # ----------------------------------------------------

        self.output_directory_label = QLabel(
            "No output directory selected."
        )

        self.output_directory_label.setWordWrap(
            True
        )

        self.output_button = QPushButton(
            "Choose Output Directory..."
        )

        directory_row = QHBoxLayout()

        directory_row.addWidget(
            self.output_directory_label,
            stretch=1,
        )

        directory_row.addWidget(
            self.output_button
        )

        layout.addRow(
            "Directory:",
            directory_row,
        )

        # ----------------------------------------------------
        # OUTPUT FILENAME
        # ----------------------------------------------------

        self.output_name = QLineEdit()

        self.output_name.setPlaceholderText(
            "Output filename / base name"
        )

        layout.addRow(
            "Filename:",
            self.output_name,
        )

        # ----------------------------------------------------
        # OUTPUT PREVIEW
        # ----------------------------------------------------

        self.output_preview_label = QLabel(
            "Output: not configured."
        )

        self.output_preview_label.setWordWrap(
            True
        )

        layout.addRow(
            self.output_preview_label
        )

        return panel



    # ========================================================
    # START PANEL
    # ========================================================

    def _build_start_panel(self) -> QWidget:

        panel = QGroupBox(
            "Ready to Process"
        )

        layout = QHBoxLayout(panel)

        self.run_button = QPushButton(
            "▶  START"
        )

        self.run_button.setObjectName(
            "primaryButton"
        )

        self.run_button.setMinimumHeight(
            55
        )

        self.run_button.setMinimumWidth(
            220
        )

        self.run_button.setStyleSheet(
            """
            QPushButton#primaryButton {
                font-size: 17px;
                font-weight: bold;
                padding: 12px 28px;
                border-radius: 8px;
                background-color: #1976d2;
                color: white;
            }

            QPushButton#primaryButton:hover {
                background-color: #1565c0;
            }

            QPushButton#primaryButton:pressed {
                background-color: #0d47a1;
            }

            QPushButton#primaryButton:disabled {
                background-color: #777777;
                color: #dddddd;
            }
            """
        )

        self.start_description = QLabel(
            "Choose an operation and media, then press Start."
        )

        self.start_description.setWordWrap(
            True
        )

        layout.addWidget(
            self.start_description,
            stretch=1,
        )

        layout.addWidget(
            self.run_button
        )

        return panel

    # ========================================================
    # PROGRESS
    # ========================================================

    def _build_progress_panel(self) -> QWidget:

        panel = QGroupBox(
            "Progress"
        )

        layout = QVBoxLayout(panel)

        self.progress_label = QLabel(
            "Ready"
        )

        self.progress_label.setWordWrap(
            True
        )

        self.progress_bar = QProgressBar()

        self.progress_bar.setRange(
            0,
            100,
        )

        self.cancel_button = QPushButton(
            "Cancel"
        )

        self.cancel_button.setEnabled(
            False
        )

        row = QHBoxLayout()

        row.addWidget(
            self.progress_label,
            stretch=1,
        )

        row.addWidget(
            self.cancel_button
        )

        layout.addLayout(
            row
        )

        layout.addWidget(
            self.progress_bar
        )

        return panel

    # ========================================================
    # SIGNALS
    # ========================================================

    def _connect_signals(self) -> None:

        self.add_media_button.clicked.connect(
            self._add_media
        )

        self.add_srt_button.clicked.connect(
            self._add_srt
        )

        self.remove_media_button.clicked.connect(
            self._remove_selected_media
        )

        self.clear_media_button.clicked.connect(
            self._clear_media
        )

        self.media_list.currentRowChanged.connect(
            self._media_selection_changed
        )

        self.srt_list.currentRowChanged.connect(
            self._subtitle_selection_changed
        )

        self.inspect_button.clicked.connect(
            self._inspect_selected
        )

        self.operation_combo.currentIndexChanged.connect(
            self._operation_changed
        )

        self.work_selected_button.clicked.connect(
            self._use_selected_media
        )

        self.work_all_button.clicked.connect(
            self._use_all_media
        )

        self.choose_work_button.clicked.connect(
            self._choose_work_media
        )

        self.browse_work_button.clicked.connect(
            self._browse_work_media
        )

        self.use_selected_subtitle_button.clicked.connect(
            self._use_selected_subtitle
        )

        self.browse_subtitle_button.clicked.connect(
            self._browse_subtitle
        )

        self.output_button.clicked.connect(
            self._choose_output
        )

        self.output_name.textChanged.connect(
            self._output_name_changed
        )

        self.convert_output_format.currentIndexChanged.connect(
            self._update_output_preview
        )


        self.run_button.clicked.connect(
            self._run
        )

        self.cancel_button.clicked.connect(
            self._cancel
        )

        self.cut_mode.currentIndexChanged.connect(
            self._cut_mode_changed
        )

        self.add_timestamp_button.clicked.connect(
            self._add_timestamp
        )

        self.remove_timestamp_button.clicked.connect(
            self._remove_timestamp
        )

        self.clear_timestamps_button.clicked.connect(
            self._clear_timestamps
        )

        self.cut_start.valueChanged.connect(
            self._validate_cut_range
        )

        self.cut_end.valueChanged.connect(
            self._validate_cut_range
        )

    # ========================================================
    # MEDIA
    # ========================================================

    def _validate_media_file(
        self,
        path: Path,
    ) -> bool:

        return (
            path.exists()
            and path.is_file()
        )

    def _add_media(self) -> None:

        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Media",
            "",
            (
                "Media Files "
                "(*.mp4 *.mkv *.mov *.avi *.webm "
                "*.m4v *.mp3 *.wav *.flac *.aac);;"
                "All Files (*)"
            ),
        )

        if not files:
            return

        added_any = False

        for filename in files:

            path = Path(filename)

            if not self._validate_media_file(path):
                continue

            if path in self.media_files:
                continue

            self.media_files.append(path)

            self.media_list.addItem(
                path.name
            )

            added_any = True

        if not added_any:
            return

        if self.selected_media is None:
            self._select_first_media()

        self._update_operation_ui()

    # ========================================================
    # ADD SRT
    # ========================================================

    def _add_srt(self) -> None:

        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Subtitle Files",
            "",
            "Subtitle Files (*.srt);;All Files (*)",
        )

        if not files:
            return

        for filename in files:

            path = Path(filename)

            if not path.exists():
                continue

            if not path.is_file():
                continue

            if path in self.subtitle_files:
                continue

            self.subtitle_files.append(path)

            self.srt_list.addItem(
                path.name
            )

        if (
            self.selected_subtitle is None
            and self.subtitle_files
        ):
            self.srt_list.setCurrentRow(0)

        self._refresh_subtitle_combo()

        self._update_operation_ui()

    # ========================================================
    # SELECT FIRST MEDIA
    # ========================================================

    def _select_first_media(self) -> None:

        if not self.media_files:

            self.selected_media = None

            return

        self.media_list.setCurrentRow(0)

    # ========================================================
    # MEDIA SELECTION
    # ========================================================

    def _media_selection_changed(
        self,
        row: int,
    ) -> None:

        if row < 0:

            self.selected_media = None

            self.inspection_header.setText(
                "Select media to inspect."
            )

            self.inspection_text.clear()

            self._update_operation_ui()

            return

        if row >= len(self.media_files):
            return

        self.selected_media = (
            self.media_files[row]
        )

        self._auto_inspect_selected()

        if self.operation in {
            "convert",
            "cut",
            "burn_subtitles",
        }:

            self.working_media = [
                self.selected_media
            ]
            self._set_default_output_directory()
            self._set_default_output_name(
                force=True
            )

        self._update_working_label()
        self._update_operation_ui()

    # ========================================================
    # SUBTITLE SELECTION
    # ========================================================

    def _subtitle_selection_changed(
        self,
        row: int,
    ) -> None:

        if 0 <= row < len(
            self.subtitle_files
        ):

            self.selected_subtitle = (
                self.subtitle_files[row]
            )

        else:

            self.selected_subtitle = None

        self._refresh_subtitle_combo()

        self._update_subtitle_label()

    # ========================================================
    # INSPECTION
    # ========================================================

    def _inspect_selected(self) -> None:

        if self.selected_media is None:

            QMessageBox.warning(
                self,
                "No Media",
                "Select a media file first.",
            )

            return

        self._inspect_media(
            self.selected_media
        )

    def _auto_inspect_selected(self) -> None:

        if self.selected_media is None:
            return

        if self.selected_media in self.inspection_cache:

            self._show_cached_inspection()

            return

        self._inspect_media(
            self.selected_media
        )

    def _inspect_media(
        self,
        path: Path,
    ) -> None:

        if not self._validate_media_file(path):

            self.inspection_header.setText(
                path.name
            )

            self.inspection_text.setPlainText(
                "The selected file does not exist."
            )

            return

        self.inspection_header.setText(
            f"Inspecting: {path.name}"
        )

        self.inspection_text.setPlainText(
            "Inspecting media..."
        )

        self.progress_label.setText(
            f"Inspecting {path.name}..."
        )

        try:

            job = MediaEngineJob(
                operation="inspect",
                inputs=(path,),
                options={
                    "include_subtitle_text": False,
                    "include_raw": True,
                },
            )

            result = self.processor.process(
                job
            )

            self.inspection_cache[path] = (
                result.result
            )

            if self.selected_media == path:
                self._show_cached_inspection()

        except JobCancelled:

            self.inspection_text.setPlainText(
                "Inspection cancelled."
            )

        except Exception as exc:

            self.inspection_text.setPlainText(
                "Inspection failed:\n\n"
                + str(exc)
            )

        finally:

            if not self.cancel_button.isEnabled():
                self.progress_label.setText(
                    "Ready"
                )

    # ========================================================
    # HUMAN READABLE INSPECTION
    # ========================================================

    def _show_cached_inspection(self) -> None:

        if self.selected_media is None:
            return

        result = self.inspection_cache.get(
            self.selected_media
        )

        self.inspection_header.setText(
            self.selected_media.name
        )

        if result is None:

            self.inspection_text.setPlainText(
                "No inspection results yet."
            )

            return

        self.inspection_text.setPlainText(
            self._format_inspection_readable(
                result
            )
        )

    def _format_inspection_readable(
        self,
        result: Any,
    ) -> str:

        data = result

        if isinstance(result, str):

            try:
                data = json.loads(result)

            except Exception:

                return result

        lines: list[str] = []

        self._render_inspection_value(
            data,
            lines,
            level=0,
            key_name=None,
        )

        if not lines:
            return "No inspection information available."

        return "\n".join(lines)

    def _render_inspection_value(
        self,
        value: Any,
        lines: list[str],
        *,
        level: int,
        key_name: str | None,
    ) -> None:

        indent = "    " * level

        if isinstance(value, dict):

            for key, child in value.items():

                readable_key = (
                    self._humanize_key(
                        str(key)
                    )
                )

                if isinstance(
                    child,
                    (dict, list, tuple),
                ):

                    if lines and lines[-1] != "":
                        lines.append("")

                    lines.append(
                        f"{indent}{readable_key}"
                    )

                    self._render_inspection_value(
                        child,
                        lines,
                        level=level + 1,
                        key_name=str(key),
                    )

                else:

                    formatted = (
                        self._format_inspection_value(
                            child,
                            key=str(key),
                        )
                    )

                    lines.append(
                        f"{indent}{readable_key}: "
                        f"{formatted}"
                    )

            return

        if isinstance(
            value,
            (list, tuple),
        ):

            for index, child in enumerate(
                value
            ):

                if key_name == "streams":

                    stream_type = (
                        self._stream_type_name(
                            child
                        )
                    )

                    lines.append(
                        f"{indent}{stream_type} "
                        f"{index}"
                    )

                    self._render_inspection_value(
                        child,
                        lines,
                        level=level + 1,
                        key_name="stream",
                    )

                else:

                    lines.append(
                        f"{indent}Item {index + 1}"
                    )

                    self._render_inspection_value(
                        child,
                        lines,
                        level=level + 1,
                        key_name=None,
                    )

            return

        if key_name is not None:

            lines.append(
                f"{indent}{self._humanize_key(key_name)}: "
                f"{self._format_inspection_value(value)}"
            )

        else:

            lines.append(
                f"{indent}{self._format_inspection_value(value)}"
            )

    # ========================================================
    # INSPECTION HELPERS
    # ========================================================

    @staticmethod
    def _humanize_key(
        key: str,
    ) -> str:

        key = key.replace(
            "_",
            " ",
        )

        key = key.replace(
            "-",
            " ",
        )

        key = " ".join(
            key.split()
        )

        return key.title()

    @staticmethod
    def _format_inspection_value(
        value: Any,
        *,
        key: str = "",
    ) -> str:

        if value is None:
            return "Not available"

        if isinstance(
            value,
            bool,
        ):
            return "Yes" if value else "No"

        if isinstance(
            value,
            float,
        ):

            if "duration" in key.lower():

                return (
                    MediaEnginePage._format_duration(
                        value
                    )
                    + f" ({value:.3f} seconds)"
                )

            return (
                f"{value:.4f}"
                .rstrip("0")
                .rstrip(".")
            )

        if isinstance(
            value,
            int,
        ):
            return f"{value:,}"

        if isinstance(value, str):

            if key.lower() in {
                "duration",
                "start_time",
            }:

                try:

                    seconds = float(value)

                    return (
                        MediaEnginePage._format_duration(
                            seconds
                        )
                        + f" ({seconds:.3f} seconds)"
                    )

                except (
                    ValueError,
                    TypeError,
                ):
                    pass

            return value

        return str(value)

    @staticmethod
    def _stream_type_name(
        stream: Any,
    ) -> str:

        if isinstance(stream, dict):

            codec_type = stream.get(
                "codec_type"
            )

            if codec_type:
                return str(
                    codec_type
                ).title() + " Stream"

        return "Stream"

    @staticmethod
    def _format_duration(
        seconds: float,
    ) -> str:

        if seconds < 0:
            return "Unknown"

        total = int(seconds)

        hours = total // 3600

        minutes = (
            total % 3600
        ) // 60

        secs = total % 60

        if hours > 0:

            return (
                f"{hours:02d}:"
                f"{minutes:02d}:"
                f"{secs:02d}"
            )

        return (
            f"{minutes:02d}:"
            f"{secs:02d}"
        )

    # ========================================================
    # OPERATION
    # ========================================================

    def _operation_changed(
        self,
        index: int,
    ) -> None:

        operation = (
            self.operation_combo.itemData(
                index
            )
        )

        if not operation:
            return

        self.operation = operation

        self._set_operation_default_media()

        self._update_operation_ui()

        self.operation_changed.emit(
            operation
        )

    def _set_operation_default_media(self) -> None:

        if self.operation in {
            "convert",
            "cut",
            "burn_subtitles",
        }:

            if self.selected_media is not None:

                self.working_media = [
                    self.selected_media
                ]

            elif self.media_files:

                self.selected_media = (
                    self.media_files[0]
                )

                self.media_list.setCurrentRow(
                    0
                )

                self.working_media = [
                    self.media_files[0]
                ]

            else:

                self.working_media = []

            self._set_default_output_directory()
            self._set_default_output_name(
                force=True
            )


            return

        if self.operation == "join":

            if len(self.working_media) >= 2:
                return

            if len(self.media_files) >= 2:

                self.working_media = list(
                    self.media_files
                )

            else:

                self.working_media = list(
                    self.media_files
                )

            self._set_default_output_directory()
            self._set_default_output_name(
                force=True
            )


    # ========================================================
    # OPERATION UI
    # ========================================================

    def _update_operation_ui(self) -> None:

        mapping = {
            "convert": 0,
            "cut": 1,
            "join": 2,
            "burn_subtitles": 3,
        }

        self.specific_stack.setCurrentIndex(
            mapping.get(
                self.operation,
                0,
            )
        )

        self._cut_mode_changed(
            self.cut_mode.currentIndex()
        )

        if self.operation == "convert":

            self.work_description.setText(
                "Convert one media file. "
                "You can use the currently selected loaded media "
                "or browse for another file."
            )

        elif self.operation == "cut":

            self.work_description.setText(
                "Cut one media file. "
                "Choose the loaded media you want, or browse for "
                "another media file."
            )

        elif self.operation == "join":

            self.work_description.setText(
                "Join two or more media files. "
                "Choose loaded files in the desired order, "
                "or browse for additional media."
            )

        elif self.operation == "burn_subtitles":

            self.work_description.setText(
                "Burn subtitles into one video. "
                "Choose the video and then select an existing SRT "
                "or browse for another SRT file."
            )

        has_media = bool(
            self.media_files
        )

        self.work_selected_button.setEnabled(
            self.selected_media is not None
        )

        self.work_all_button.setEnabled(
            has_media
        )

        self.choose_work_button.setEnabled(
            has_media
        )

        self.browse_work_button.setEnabled(
            True
        )

        is_burn = (
            self.operation
            == "burn_subtitles"
        )

        self.subtitle_controls.setVisible(
            is_burn
        )

        self.subtitle_working_label.setVisible(
            is_burn
        )

        # ----------------------------------------------------
        # OUTPUT
        #
        # Cut now also requires an output directory.
        # ----------------------------------------------------

        needs_output = self.operation in {
            "convert",
            "cut",
            "join",
            "burn_subtitles",
        }

        self.output_panel.setVisible(
            needs_output
        )

       
        # ----------------------------------------------------
        # START DESCRIPTION
        # ----------------------------------------------------

        self.start_description.setText(
            self._start_description()
        )

        self._update_working_label()
        self._update_subtitle_label()
        self._update_output_preview()

    # ========================================================
    # OUTPUT FORMAT OPTIONS
    # ========================================================

    def _update_output_format_options(self) -> None:
        """
        Output format is controlled by the Convert-specific settings.

        For Cut, Join and Burn Subtitles, the output format follows
        the first working media file's extension.
        """
        return


    def _start_description(self) -> str:

        if self.operation == "convert":

            return (
                "Ready to convert one media file."
            )

        if self.operation == "cut":

            return (
                "Ready to cut one media file. "
                "Choose an output directory, base filename "
                "and format for the generated parts."
            )

        if self.operation == "join":

            return (
                "Ready to join two or more media files."
            )

        if self.operation == "burn_subtitles":

            return (
                "Ready to burn one subtitle file into one video."
            )

        return "Ready."

    # ========================================================
    # WORKING MEDIA
    # ========================================================

    def _use_selected_media(self) -> None:

        if self.selected_media is None:

            QMessageBox.warning(
                self,
                "No Media Selected",
                "Select a media file first.",
            )

            return

        self.working_media = [
            self.selected_media
        ]
        self._set_default_output_directory()
        self._set_default_output_name(
            force=True
        )

        self._update_working_label()
        self._update_output_preview()

    # ========================================================
    # USE ALL
    # ========================================================

    def _use_all_media(self) -> None:

        if not self.media_files:

            QMessageBox.warning(
                self,
                "No Media",
                "Add media files first.",
            )

            return

        if self.operation in {
            "convert",
            "cut",
            "burn_subtitles",
        }:

            QMessageBox.information(
                self,
                "One Media Required",
                (
                    "This operation uses one media file at a time.\n\n"
                    "Use 'Use Selected' or 'Choose Loaded...' "
                    "to select the media."
                ),
            )

            return

        self.working_media = list(
            self.media_files
        )
        self._set_default_output_directory()
        self._set_default_output_name(
            force=True
        )

        self._update_working_label()
        self._update_output_preview()

    # ========================================================
    # CHOOSE LOADED MEDIA
    # ========================================================

    def _choose_work_media(self) -> None:

        if not self.media_files:
            return

        dialog = QGroupBox(
            "Choose Loaded Media"
        )

        dialog.setWindowModality(
            Qt.ApplicationModal
        )

        layout = QVBoxLayout(dialog)

        label = QLabel()

        if self.operation == "join":

            label.setText(
                "Select two or more files. "
                "Their order here determines the join order."
            )

        else:

            label.setText(
                "Select one media file."
            )

        label.setWordWrap(True)

        layout.addWidget(
            label
        )

        list_widget = QListWidget()

        if self.operation == "join":

            list_widget.setSelectionMode(
                QListWidget.MultiSelection
            )

        else:

            list_widget.setSelectionMode(
                QListWidget.SingleSelection
            )

        for path in self.media_files:

            item = QListWidgetItem(
                path.name
            )

            item.setData(
                Qt.UserRole,
                path,
            )

            list_widget.addItem(
                item
            )

            if path in self.working_media:

                item.setSelected(
                    True
                )

        layout.addWidget(
            list_widget,
            stretch=1,
        )

        buttons = QHBoxLayout()

        apply_button = QPushButton(
            "Use Selected"
        )

        cancel_button = QPushButton(
            "Cancel"
        )

        buttons.addWidget(
            apply_button
        )

        buttons.addWidget(
            cancel_button
        )

        layout.addLayout(
            buttons
        )

        def apply() -> None:

            selected = (
                list_widget.selectedItems()
            )

            paths: list[Path] = []

            for item in selected:

                path = item.data(
                    Qt.UserRole
                )

                if isinstance(
                    path,
                    Path,
                ):
                    paths.append(path)

            if self.operation == "join":

                if len(paths) < 2:

                    QMessageBox.warning(
                        dialog,
                        "Not Enough Media",
                        "Join requires at least two media files.",
                    )

                    return

            else:

                if len(paths) != 1:

                    QMessageBox.warning(
                        dialog,
                        "One Media Required",
                        "This operation requires exactly one media file.",
                    )

                    return

            self.working_media = paths

            self._set_default_output_name(
                force=True
            )

            dialog.close()

            self._update_working_label()
            self._update_output_preview()

        apply_button.clicked.connect(
            apply
        )

        cancel_button.clicked.connect(
            dialog.close
        )

        dialog.resize(
            500,
            500,
        )

        dialog.show()

        self._work_dialog = dialog

    # ========================================================
    # BROWSE MEDIA
    # ========================================================

    def _browse_work_media(self) -> None:

        if self.operation == "join":

            files, _ = QFileDialog.getOpenFileNames(
                self,
                "Add Media for Join",
                "",
                (
                    "Media Files "
                    "(*.mp4 *.mkv *.mov *.avi *.webm "
                    "*.m4v *.mp3 *.wav *.flac *.aac);;"
                    "All Files (*)"
                ),
            )

            if not files:
                return

            for filename in files:

                path = Path(filename)

                if not self._validate_media_file(path):
                    continue

                if path not in self.media_files:

                    self.media_files.append(
                        path
                    )

                    self.media_list.addItem(
                        path.name
                    )

                if path not in self.working_media:

                    self.working_media.append(
                        path
                    )

            self._set_default_output_name(
                force=True
            )

            self._update_working_label()
            self._update_output_preview()

            return

        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Choose Media",
            "",
            (
                "Media Files "
                "(*.mp4 *.mkv *.mov *.avi *.webm "
                "*.m4v *.mp3 *.wav *.flac *.aac);;"
                "All Files (*)"
            ),
        )

        if not filename:
            return

        path = Path(filename)

        if not self._validate_media_file(path):

            QMessageBox.warning(
                self,
                "Invalid Media",
                "The selected file does not exist or is not a file.",
            )

            return

        if path not in self.media_files:

            self.media_files.append(
                path
            )

            self.media_list.addItem(
                path.name
            )

        self.working_media = [
            path
        ]

        self.selected_media = path

        row = self.media_files.index(
            path
        )

        self.media_list.setCurrentRow(
            row
        )
        
        self._set_default_output_directory()
        self._set_default_output_name(
            force=True
        )


        self._update_working_label()
        self._update_output_preview()

    # ========================================================
    # WORKING LABEL
    # ========================================================

    def _update_working_label(self) -> None:

        if not self.working_media:

            self.working_label.setText(
                "No media selected."
            )

            return

        if self.operation == "join":

            lines = [
                f"{index}. {path.name}"
                for index, path in enumerate(
                    self.working_media,
                    start=1,
                )
            ]

            self.working_label.setText(
                "Files to join:\n"
                + "\n".join(lines)
            )

            return

        path = self.working_media[0]

        self.working_label.setText(
            f"Media: {path.name}\n"
            f"Location: {path.parent}"
        )

    # ========================================================
    # SUBTITLES
    # ========================================================

    def _refresh_subtitle_combo(self) -> None:

        self.burn_subtitle_combo.clear()

        for path in self.subtitle_files:

            self.burn_subtitle_combo.addItem(
                path.name,
                path,
            )

        if self.selected_subtitle is not None:

            index = (
                self.burn_subtitle_combo.findData(
                    self.selected_subtitle
                )
            )

            if index >= 0:

                self.burn_subtitle_combo.setCurrentIndex(
                    index
                )

    def _use_selected_subtitle(self) -> None:

        if self.selected_subtitle is None:

            QMessageBox.warning(
                self,
                "No Subtitle",
                "Select an SRT file first.",
            )

            return

        self._refresh_subtitle_combo()

        index = (
            self.burn_subtitle_combo.findData(
                self.selected_subtitle
            )
        )

        if index >= 0:

            self.burn_subtitle_combo.setCurrentIndex(
                index
            )

        self._update_subtitle_label()

    def _browse_subtitle(self) -> None:

        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Choose Subtitle File",
            "",
            "Subtitle Files (*.srt);;All Files (*)",
        )

        if not filename:
            return

        path = Path(filename)

        if not path.exists():
            return

        if path not in self.subtitle_files:

            self.subtitle_files.append(
                path
            )

            self.srt_list.addItem(
                path.name
            )

        self.selected_subtitle = path

        row = self.subtitle_files.index(
            path
        )

        self.srt_list.setCurrentRow(
            row
        )

        self._refresh_subtitle_combo()

        self._update_subtitle_label()

    def _update_subtitle_label(self) -> None:

        if not self.subtitle_controls.isVisible():
            return

        if self.selected_subtitle is None:

            self.subtitle_working_label.setText(
                "No subtitle selected."
            )

            return

        self.subtitle_working_label.setText(
            f"Subtitle: {self.selected_subtitle.name}\n"
            f"Location: {self.selected_subtitle.parent}"
        )

    # ========================================================
    # OUTPUT
    # ========================================================

    def _choose_output(self) -> None:

        if self.output_directory is not None:
            initial_directory = self.output_directory

        elif self.working_media:
            initial_directory = self.working_media[0].parent

        else:
            initial_directory = Path.home()

        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Output Directory",
            str(initial_directory),
        )

        if not directory:
            return

        self.output_directory = Path(directory)

        # Remember that the user explicitly selected this directory.
        self._output_directory_user_modified = True

        self._update_output_preview()


    # ========================================================
    # OUTPUT NAME
    # ========================================================

    def _output_name_changed(
        self,
        text: str,
    ) -> None:

        self._output_name_user_modified = bool(
            text.strip()
        )

        self._update_output_preview()

    def _set_default_output_directory(
        self,
        *,
        force: bool = False,
    ) -> None:
        """
        Use the first working media file's directory as the default
        output directory.

        Once the user explicitly chooses an output directory, don't
        replace it automatically unless force=True.
        """

        if not self.working_media:
            return

        if (
            self._output_directory_user_modified
            and not force
        ):
            return

        self.output_directory = (
            self.working_media[0].parent
        )



    def _set_default_output_name(
        self,
        *,
        force: bool = False,
    ) -> None:

        if not self.working_media:
            return

        if (
            self._output_name_user_modified
            and not force
        ):
            return

        source = self.working_media[0]

        # --------------------------------------------------------
        # CUT
        #
        # Cut creates multiple files, so don't create a single
        # output filename.
        # --------------------------------------------------------

        if self.operation == "cut":

            self.output_name.blockSignals(
                True
            )

            self.output_name.clear()

            self.output_name.blockSignals(
                False
            )

            self._output_name_user_modified = False

            return

        # --------------------------------------------------------
        # DEFAULT NAMES
        # --------------------------------------------------------

        if self.operation == "convert":

            name = f"{source.stem}_converted"

        elif self.operation == "join":

            name = f"{source.stem}_joined"

        elif self.operation == "burn_subtitles":

            name = f"{source.stem}_burned"

        else:

            name = source.stem

        self.output_name.blockSignals(
            True
        )

        self.output_name.setText(
            name
        )

        self.output_name.blockSignals(
            False
        )

        self._output_name_user_modified = False


    # ========================================================
    # OUTPUT FORMAT
    # ========================================================

    def _selected_output_format(self) -> str:

        if self.operation == "convert":

            return (
                self.convert_output_format.currentText()
                .strip()
                .lower()
                .lstrip(".")
            )

        if self.working_media:

            suffix = self.working_media[0].suffix

            if suffix:
                return suffix.lstrip(".").lower()

        return ""



    # ========================================================
    # CLEAN OUTPUT NAME
    # ========================================================

    @staticmethod
    def _clean_output_name(
        name: str,
    ) -> str:

        name = name.strip()

        if not name:
            return ""

        # If user enters:
        #
        #     My Movie.mkv
        #
        # and selects mp4, produce:
        #
        #     My Movie.mp4
        #
        # instead of:
        #
        #     My Movie.mkv.mp4
        #
        return Path(name).stem

    # ========================================================
    # OUTPUT PREVIEW
    # ========================================================

    def _update_output_preview(self) -> None:

        if not hasattr(
            self,
            "output_directory_label",
        ):
            return

        if self.output_directory is None:

            self.output_directory_label.setText(
                "No output directory selected."
            )

            self.output_preview_label.setText(
                "Output: not configured."
            )

            return

        self.output_directory_label.setText(
            str(self.output_directory)
        )

        if not self.working_media:

            self.output_preview_label.setText(
                "Output: select media first."
            )

            return

        try:

            output_format = (
                self._selected_output_format()
            )

            name = self._clean_output_name(
                self.output_name.text()
            )

            if not name:

                name = self.working_media[0].stem

            if self.operation == "cut":

                self.output_preview_label.setText(
                    "Output directory:\n"
                    f"{self.output_directory}\n\n"
                    "Generated files will use:\n"
                    f"{name}-of-N.{output_format}"
                )

                return

            output = self._build_output_path()

            self.output_preview_label.setText(
                f"Output:\n{output}"
            )

        except Exception as exc:

            self.output_preview_label.setText(
                f"Output: {exc}"
            )

    # ========================================================
    # OUTPUT PATH
    # ========================================================

    def _build_output_path(self) -> Path:

        if self.output_directory is None:

            raise ValueError(
                "Choose an output directory."
            )

        if not self.working_media:

            raise ValueError(
                "Select media to work with."
            )

        source = self.working_media[0]

        output_format = self._selected_output_format()

        if not output_format:

            raise ValueError(
                "Could not determine the output format."
            )

        name = self._clean_output_name(
            self.output_name.text()
        )

        if not name:

            name = source.stem

        if self.operation in {
            "convert",
            "join",
            "burn_subtitles",
        }:

            return (
                self.output_directory
                / f"{name}.{output_format}"
            )

        raise ValueError(
            "This operation does not use a single output path."
        )

    # ========================================================
    # COMMON SETTINGS
    # ========================================================

    def _video_mode(self) -> str:

        return (
            "fast_copy"
            if self.video_mode.currentText()
            == "Fast Copy"
            else "reencode"
        )

    def _audio_mode(self) -> str:

        return (
            "fast_copy"
            if self.audio_mode.currentText()
            == "Fast Copy"
            else "reencode"
        )

    def _build_common_settings_kwargs(
        self,
    ) -> dict[str, Any]:

        return {
            "video_mode": self._video_mode(),
            "audio_mode": self._audio_mode(),
            "video_codec": self.video_codec.currentText(),
            "audio_codec": self.audio_codec.currentText(),
            "preset": self.preset.currentText(),
            "crf": int(
                self.crf.currentText()
            ),
            "audio_bitrate": self.audio_bitrate.currentText(),
            "pixel_format": self.pixel_format.currentText(),
            "faststart": self.faststart.isChecked(),
            "overwrite": self.overwrite.isChecked(),
        }

    # ========================================================
    # BUILD JOB
    # ========================================================

    def _build_job(
        self,
    ) -> MediaEngineJob:

        if not self.working_media:

            raise ValueError(
                "Select media to work with."
            )

        # ====================================================
        # OUTPUT DIRECTORY
        # ====================================================

        if self.output_directory is None:

            raise ValueError(
                "Choose an output directory."
            )

        # ====================================================
        # CONVERT
        # ====================================================

        if self.operation == "convert":

            if len(self.working_media) != 1:

                raise ValueError(
                    "Convert requires exactly one media file."
                )

            output = self._build_output_path()

            settings = ConverterSettings(
                **self._build_common_settings_kwargs(),
                output_format=(
                    self._selected_output_format()
                ),
                keep_subtitles=(
                    self.keep_subtitles.isChecked()
                ),
                keep_metadata=(
                    self.keep_metadata.isChecked()
                ),
            )

            return MediaEngineJob(
                operation="convert",
                inputs=(
                    self.working_media[0],
                ),
                output=output,
                settings=settings,
            )

        # ====================================================
        # CUT
        # ====================================================

        if self.operation == "cut":

            if len(self.working_media) != 1:

                raise ValueError(
                    "Cut requires exactly one media file."
                )

            mode = (
                self.cut_mode.currentText()
            )

            if mode == "Duration":

                duration = (
                    self.cut_duration.value()
                )

                if duration <= 0:

                    raise ValueError(
                        "Duration must be greater than zero."
                    )

                settings = CutterSettings(
                    **self._build_common_settings_kwargs(),
                    output_format=(
                        self._selected_output_format()
                    ),
                    mode="duration",
                    duration=duration,
                    parts=None,
                    timestamps=(),
                    start=0.0,
                    end=None,
                    cut_subtitles=(
                        self.cut_subtitles.isChecked()
                    ),
                )

            elif mode == "Parts":

                parts = (
                    self.cut_parts.value()
                )

                if parts < 2:

                    raise ValueError(
                        "Parts must be at least 2."
                    )

                settings = CutterSettings(
                    **self._build_common_settings_kwargs(),
                    output_format=(
                        self._selected_output_format()
                    ),
                    mode="parts",
                    parts=parts,
                    duration=None,
                    timestamps=(),
                    start=0.0,
                    end=None,
                    cut_subtitles=(
                        self.cut_subtitles.isChecked()
                    ),
                )

            elif mode == "Timestamps":

                timestamps = (
                    self._get_timestamps()
                )

                if not timestamps:

                    raise ValueError(
                        "Add at least one timestamp."
                    )

                settings = CutterSettings(
                    **self._build_common_settings_kwargs(),
                    output_format=(
                        self._selected_output_format()
                    ),
                    mode="timestamps",
                    parts=None,
                    duration=None,
                    timestamps=tuple(
                        timestamps
                    ),
                    start=0.0,
                    end=None,
                    cut_subtitles=(
                        self.cut_subtitles.isChecked()
                    ),
                )

            else:

                start = (
                    self.cut_start.value()
                )

                end = (
                    self.cut_end.value()
                )

                if end <= start:

                    raise ValueError(
                        "End time must be greater than start time."
                    )

                settings = CutterSettings(
                    **self._build_common_settings_kwargs(),
                    output_format=(
                        self._selected_output_format()
                    ),
                    mode="start_end",
                    parts=None,
                    duration=None,
                    timestamps=(),
                    start=start,
                    end=end,
                    cut_subtitles=(
                        self.cut_subtitles.isChecked()
                    ),
                )

            # ------------------------------------------------
            # CUT OUTPUT
            #
            # For cut, output represents the output directory.
            #
            # The processor/service should use:
            #
            #     settings.output_format
            #
            # and generate the individual part filenames.
            #
            # The base name is passed through the job options.
            # ------------------------------------------------

            return MediaEngineJob(
                operation="cut",
                inputs=(
                    self.working_media[0],
                ),
                output=self.output_directory,
                settings=settings,
                options={
                    "output_directory": self.output_directory,
                    "output_base_name": self._clean_output_name(
                        self.output_name.text()
                    )
                    or self.working_media[0].stem,
                },
            )

        # ====================================================
        # JOIN
        # ====================================================

        if self.operation == "join":

            if len(self.working_media) < 2:

                raise ValueError(
                    "Join requires at least two media files."
                )

            output = self._build_output_path()

            settings = JoinerSettings(
                **self._build_common_settings_kwargs(),
                output_format=(
                    self._selected_output_format()
                ),
                join_subtitles=(
                    self.join_subtitles.isChecked()
                ),
            )

            return MediaEngineJob(
                operation="join",
                inputs=tuple(
                    self.working_media
                ),
                output=output,
                settings=settings,
            )

        # ====================================================
        # BURN SUBTITLES
        # ====================================================

        if self.operation == "burn_subtitles":

            if len(self.working_media) != 1:

                raise ValueError(
                    "Burn subtitles requires exactly one media file."
                )

            subtitle = (
                self.burn_subtitle_combo.currentData()
            )

            if not isinstance(
                subtitle,
                Path,
            ):

                raise ValueError(
                    "Select an SRT file."
                )

            if not subtitle.exists():

                raise ValueError(
                    "The selected subtitle file does not exist."
                )

            output = self._build_output_path()

            font_size_text = (
                self.burn_font_size.currentText()
            )

            subtitle_font_size = None

            if font_size_text != "Default":

                subtitle_font_size = int(
                    font_size_text
                )

            font_text = (
                self.burn_font.currentText()
            )

            subtitle_font = None

            if font_text != "Default":

                subtitle_font = font_text

            subtitle_color = (
                self.burn_color.currentText()
            )

            settings = BurnerSettings(
                video_codec=self.video_codec.currentText(),
                audio_mode=self._audio_mode(),
                audio_codec=self.audio_codec.currentText(),
                preset=self.preset.currentText(),
                crf=int(
                    self.crf.currentText()
                ),
                audio_bitrate=self.audio_bitrate.currentText(),
                pixel_format=self.pixel_format.currentText(),
                subtitle_font=subtitle_font,
                subtitle_font_size=subtitle_font_size,
                subtitle_color=subtitle_color,
                overwrite=self.overwrite.isChecked(),
                faststart=self.faststart.isChecked(),
               
            )

            return MediaEngineJob(
                operation="burn_subtitles",
                inputs=(
                    self.working_media[0],
                    subtitle,
                ),
                output=output,
                settings=settings,
            )

        raise ValueError(
            f"Unsupported operation: {self.operation}"
        )

    # ========================================================
    # CUT MODE
    # ========================================================

    def _cut_mode_changed(
        self,
        index: int,
    ) -> None:

        self.cut_stack.setCurrentIndex(
            max(
                0,
                min(
                    index,
                    self.cut_stack.count() - 1,
                ),
            )
        )

    # ========================================================
    # CUT TIMESTAMPS
    # ========================================================

    @staticmethod
    def _parse_timestamp(
        value: str,
    ) -> float:

        value = value.strip()

        if not value:
            raise ValueError(
                "Timestamp cannot be empty."
            )

        try:

            seconds = float(value)

            if seconds < 0:
                raise ValueError

            return seconds

        except ValueError:
            pass

        pieces = value.split(":")

        try:

            if len(pieces) == 3:

                hours = float(
                    pieces[0]
                )

                minutes = float(
                    pieces[1]
                )

                seconds = float(
                    pieces[2]
                )

                if (
                    hours < 0
                    or minutes < 0
                    or seconds < 0
                ):
                    raise ValueError

                return (
                    hours * 3600
                    + minutes * 60
                    + seconds
                )

            if len(pieces) == 2:

                minutes = float(
                    pieces[0]
                )

                seconds = float(
                    pieces[1]
                )

                if (
                    minutes < 0
                    or seconds < 0
                ):
                    raise ValueError

                return (
                    minutes * 60
                    + seconds
                )

        except ValueError:
            pass

        raise ValueError(
            f"Invalid timestamp: {value}\n\n"
            "Use seconds or HH:MM:SS."
        )

    def _add_timestamp(self) -> None:

        text = (
            self.timestamp_input.text()
            .strip()
        )

        if not text:
            return

        try:

            seconds = (
                self._parse_timestamp(
                    text
                )
            )

        except ValueError as exc:

            QMessageBox.warning(
                self,
                "Invalid Timestamp",
                str(exc),
            )

            return

        existing: list[float] = []

        for index in range(
            self.timestamp_list.count()
        ):

            item = self.timestamp_list.item(
                index
            )

            try:

                existing.append(
                    float(
                        item.data(
                            Qt.UserRole
                        )
                    )
                )

            except (
                TypeError,
                ValueError,
            ):
                pass

        if any(
            abs(seconds - value) < 0.0001
            for value in existing
        ):

            QMessageBox.information(
                self,
                "Duplicate Timestamp",
                "That timestamp is already in the list.",
            )

            return

        item = QListWidgetItem(
            self._format_timestamp(seconds)
        )

        item.setData(
            Qt.UserRole,
            seconds,
        )

        self.timestamp_list.addItem(
            item
        )

        self._sort_timestamp_list()

        self.timestamp_input.clear()

    def _remove_timestamp(self) -> None:

        row = (
            self.timestamp_list.currentRow()
        )

        if row < 0:
            return

        self.timestamp_list.takeItem(
            row
        )

    def _clear_timestamps(self) -> None:

        self.timestamp_list.clear()

    def _sort_timestamp_list(self) -> None:

        values: list[float] = []

        for index in range(
            self.timestamp_list.count()
        ):

            item = self.timestamp_list.item(
                index
            )

            try:

                values.append(
                    float(
                        item.data(
                            Qt.UserRole
                        )
                    )
                )

            except (
                TypeError,
                ValueError,
            ):
                pass

        values.sort()

        self.timestamp_list.clear()

        for seconds in values:

            item = QListWidgetItem(
                self._format_timestamp(
                    seconds
                )
            )

            item.setData(
                Qt.UserRole,
                seconds,
            )

            self.timestamp_list.addItem(
                item
            )

    def _get_timestamps(self) -> list[float]:

        values: list[float] = []

        for index in range(
            self.timestamp_list.count()
        ):

            item = self.timestamp_list.item(
                index
            )

            value = item.data(
                Qt.UserRole
            )

            try:

                values.append(
                    float(value)
                )

            except (
                TypeError,
                ValueError,
            ):

                try:

                    values.append(
                        self._parse_timestamp(
                            item.text()
                        )
                    )

                except ValueError:
                    continue

        values.sort()

        return values

    @staticmethod
    def _format_timestamp(
        seconds: float,
    ) -> str:

        total_ms = int(
            round(
                seconds * 1000
            )
        )

        hours = (
            total_ms // 3_600_000
        )

        remainder = (
            total_ms % 3_600_000
        )

        minutes = (
            remainder // 60_000
        )

        remainder %= 60_000

        secs = (
            remainder // 1_000
        )

        milliseconds = (
            remainder % 1_000
        )

        return (
            f"{hours:02d}:"
            f"{minutes:02d}:"
            f"{secs:02d}."
            f"{milliseconds:03d}"
        )

    # ========================================================
    # CUT RANGE VALIDATION
    # ========================================================

    def _validate_cut_range(
        self,
        value: float,
    ) -> None:

        if (
            self.cut_end.value()
            <= self.cut_start.value()
        ):

            self.cut_end.setStyleSheet(
                "border: 1px solid #d32f2f;"
            )

        else:

            self.cut_end.setStyleSheet(
                ""
            )

    # ========================================================
    # RUN
    # ========================================================

    def _run(self) -> None:

        self.processor.reset_cancellation()

        try:

            job = self._build_job()

        except Exception as exc:

            QMessageBox.warning(
                self,
                "Cannot Start",
                str(exc),
            )

            return

        # ----------------------------------------------------
        # CONFIRM OVERWRITE
        #
        # For cut, output is a directory and individual output
        # names are generated by the cutter, so don't perform
        # the single-file existence check here.
        # ----------------------------------------------------

        if (
            self.operation != "cut"
            and job.output is not None
            and isinstance(
                job.output,
                Path,
            )
            and job.output.exists()
            and not getattr(
                job.settings,
                "overwrite",
                False,
            )
        ):

            answer = QMessageBox.question(
                self,
                "Output Already Exists",
                (
                    f"The output already exists:\n\n"
                    f"{job.output}\n\n"
                    "Do you want to replace it?"
                ),
                QMessageBox.Yes
                | QMessageBox.No,
                QMessageBox.No,
            )

            if answer != QMessageBox.Yes:
                return

        # ----------------------------------------------------
        # CUT DIRECTORY CHECK
        # ----------------------------------------------------

        if self.operation == "cut":

            if self.output_directory is None:

                QMessageBox.warning(
                    self,
                    "No Output Directory",
                    "Choose an output directory first.",
                )

                return

            self.output_directory.mkdir(
                parents=True,
                exist_ok=True,
            )

        # ----------------------------------------------------
        # UI STATE
        # ----------------------------------------------------

        self.run_button.setEnabled(
            False
        )

        self.cancel_button.setEnabled(
            True
        )

        self.operation_combo.setEnabled(
            False
        )

        self.progress_bar.setRange(
            0,
            100,
        )

        self.progress_bar.setValue(
            0
        )

        self.progress_label.setText(
            f"Running {self.operation}..."
        )

        # ----------------------------------------------------
        # EXECUTE
        # ----------------------------------------------------

        try:

            result = self.processor.process(
                job
            )

            self.progress_bar.setValue(
                100
            )

            self.progress_label.setText(
                "Completed"
            )

            self._handle_completed_result(
                result
            )

        except JobCancelled:

            self.progress_label.setText(
                "Cancelled"
            )

        except Exception as exc:

            self.progress_label.setText(
                "Failed"
            )

            QMessageBox.critical(
                self,
                "Media Engine Error",
                str(exc),
            )

        finally:

            self.run_button.setEnabled(
                True
            )

            self.cancel_button.setEnabled(
                False
            )

            self.operation_combo.setEnabled(
                True
            )

    # ========================================================
    # RESULT
    # ========================================================

    def _handle_completed_result(
        self,
        result: MediaEngineJobResult,
    ) -> None:

        if self.operation == "cut":

            result_data = result.result

            if result_data is not None:

                self.progress_label.setText(
                    self._format_cut_result(
                        result_data
                    )
                )

            else:

                self.progress_label.setText(
                    "Cut completed."
                )

            return

        if result.output is not None:

            self.output_label_set_result(
                result.output
            )

        self.progress_label.setText(
            (
                f"{result.operation.replace('_', ' ').title()}"
                " completed."
            )
        )

    # ========================================================
    # RESULT OUTPUT DISPLAY
    # ========================================================

    def output_label_set_result(
        self,
        output: Path,
    ) -> None:

        self.output_preview_label.setText(
            f"Output created:\n{output}"
        )

    def _format_cut_result(
        self,
        result: Any,
    ) -> str:

        outputs = getattr(
            result,
            "outputs",
            None,
        )

        parts = getattr(
            result,
            "parts",
            None,
        )

        if outputs:

            return (
                f"Cut completed — "
                f"{len(outputs)} output file(s) created."
            )

        if parts:

            return (
                f"Cut completed — "
                f"{len(parts)} part(s) created."
            )

        return "Cut completed."

    # ========================================================
    # CANCEL
    # ========================================================

    def _cancel(self) -> None:

        self.processor.cancel()

        self.cancel_button.setEnabled(
            False
        )

        self.progress_label.setText(
            "Cancelling..."
        )

    # ========================================================
    # PROGRESS
    # ========================================================

    def _on_progress(
        self,
        *args: Any,
    ) -> None:

        if len(args) >= 2:

            try:

                value = float(
                    args[1]
                )

                if value <= 1.0:

                    percent = int(
                        value * 100
                    )

                else:

                    percent = int(
                        value
                    )

                self.progress_bar.setValue(
                    max(
                        0,
                        min(
                            100,
                            percent,
                        ),
                    )
                )

            except (
                TypeError,
                ValueError,
            ):
                pass

        if len(args) >= 3:

            self.progress_label.setText(
                str(args[2])
            )

    # ========================================================
    # ERROR
    # ========================================================

    def _on_error(
        self,
        error: Any,
    ) -> None:

        self.progress_label.setText(
            f"Error: {error}"
        )

    # ========================================================
    # JOB EVENTS
    # ========================================================

    def _on_job(
        self,
        event: str,
        *args: Any,
    ) -> None:

        if event == "started":

            self.progress_label.setText(
                "Starting..."
            )

        elif event == "completed":

            self.progress_label.setText(
                "Completed"
            )

        elif event == "cancelled":

            self.progress_label.setText(
                "Cancelled"
            )

        elif event == "failed":

            self.progress_label.setText(
                "Failed"
            )

    # ========================================================
    # REMOVE MEDIA
    # ========================================================

    def _remove_selected_media(self) -> None:

        row = (
            self.media_list.currentRow()
        )

        if row < 0:
            return

        path = self.media_files.pop(
            row
        )

        self.inspection_cache.pop(
            path,
            None,
        )

        if path in self.working_media:

            self.working_media.remove(
                path
            )

        self.media_list.takeItem(
            row
        )

        if self.selected_media == path:

            self.selected_media = None

            if self.media_files:

                new_row = min(
                    row,
                    len(
                        self.media_files
                    ) - 1,
                )

                self.media_list.setCurrentRow(
                    new_row
                )

            else:

                self.inspection_header.setText(
                    "Select media to inspect."
                )

                self.inspection_text.clear()

        self._set_default_output_directory()
        self._set_default_output_name(
            force=True
        )


        self._update_working_label()
        self._update_operation_ui()

    # ========================================================
    # CLEAR
    # ========================================================

    def _clear_media(self) -> None:

        self.processor.cancel()
        self.processor.reset_cancellation()

        self.media_files.clear()
        self.subtitle_files.clear()
        self.working_media.clear()
        self.inspection_cache.clear()

        self.media_list.clear()
        self.srt_list.clear()

        self.selected_media = None
        self.selected_subtitle = None

        self.inspection_header.setText(
            "Select media to inspect."
        )

        self.inspection_text.clear()

        self.working_label.setText(
            "No media selected."
        )

        self.subtitle_working_label.setText(
            "No subtitle selected."
        )

        self.timestamp_list.clear()
        self.timestamp_input.clear()

        self._reset_output()

        self.progress_bar.setValue(
            0
        )

        self.progress_label.setText(
            "Ready"
        )

        self._refresh_subtitle_combo()
        self._update_operation_ui()

    # ========================================================
    # OUTPUT RESET
    # ========================================================

    def _reset_output(self) -> None:

        self.output_directory = None

        self._output_directory_user_modified = False

        self.output_directory_label.setText(
            "No output directory selected."
        )

        self.output_name.blockSignals(
            True
        )

        self.output_name.clear()

        self.output_name.blockSignals(
            False
        )

        self.output_preview_label.setText(
            "Output: not configured."
        )

        self._output_name_user_modified = False

    # ========================================================
    # SETTINGS RESET
    # ========================================================

    def reset_settings(self) -> None:
        """
        Restore UI settings to their defaults.
        """

        self.video_mode.setCurrentText(
            "Fast Copy"
        )

        self.audio_mode.setCurrentText(
            "Fast Copy"
        )

        self.video_codec.setCurrentText(
            "libx264"
        )

        self.audio_codec.setCurrentText(
            "aac"
        )

        self.preset.setCurrentText(
            "veryfast"
        )

        self.crf.setCurrentText(
            "20"
        )

        self.audio_bitrate.setCurrentText(
            "192k"
        )

        self.pixel_format.setCurrentText(
            "yuv420p"
        )

        self.faststart.setChecked(
            True
        )

        self.overwrite.setChecked(
            False
        )

        # --------------------------------------------------------
        # CONVERT
        # --------------------------------------------------------

        self.convert_output_format.setCurrentText(
            "mp4"
        )

        self.keep_subtitles.setChecked(
            True
        )

        self.keep_metadata.setChecked(
            True
        )

        # --------------------------------------------------------
        # CUT
        # --------------------------------------------------------

        self.cut_mode.setCurrentText(
            "Duration"
        )

        self.cut_duration.setValue(
            60.0
        )

        self.cut_parts.setValue(
            2
        )

        self.cut_start.setValue(
            0.0
        )

        self.cut_end.setValue(
            60.0
        )

        self.cut_subtitles.setChecked(
            True
        )

        self.timestamp_list.clear()
        self.timestamp_input.clear()

        # --------------------------------------------------------
        # JOIN
        # --------------------------------------------------------

        self.join_subtitles.setChecked(
            True
        )

        # --------------------------------------------------------
        # BURN
        # --------------------------------------------------------

        self.burn_font.setCurrentText(
            "Default"
        )

        self.burn_font_size.setCurrentText(
            "Default"
        )

        self.burn_color.setCurrentText(
            "White"
        )

        self._reset_output()


    # ========================================================
    # PAGE RESET
    # ========================================================

    def reset_page(self) -> None:
        """
        Completely reset the Media Engine page.
        """

        self.processor.cancel()
        self.processor.reset_cancellation()

        self.media_files.clear()
        self.subtitle_files.clear()
        self.working_media.clear()
        self.inspection_cache.clear()

        self.selected_media = None
        self.selected_subtitle = None

        self.media_list.clear()
        self.srt_list.clear()

        self.inspection_header.setText(
            "Select media to inspect."
        )

        self.inspection_text.clear()

        self.working_label.setText(
            "No media selected."
        )

        self.subtitle_working_label.setText(
            "No subtitle selected."
        )

        self.timestamp_list.clear()
        self.timestamp_input.clear()

        self._reset_output()

        self.operation_combo.setCurrentIndex(
            0
        )

        self.operation = "convert"

        self.reset_settings()

        self.progress_bar.setValue(
            0
        )

        self.progress_label.setText(
            "Ready"
        )

        self.run_button.setEnabled(
            True
        )

        self.cancel_button.setEnabled(
            False
        )

        self.operation_combo.setEnabled(
            True
        )

        self._update_operation_ui()
