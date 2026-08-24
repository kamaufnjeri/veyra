from __future__ import annotations

import os
from dataclasses import dataclass

from PySide6.QtCore import (
    QObject,
    QThread,
    Qt,
    Signal,
    Slot,
    QMetaObject,
    QSize,
)

from PySide6.QtGui import QColor

from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGridLayout,
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
    QSpinBox,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from jobs.download_processor import MediaJobProcessor, JobCancelled


# ============================================================
# CONSTANTS
# ============================================================

QUEUE_ITEM_HEIGHT = 105


# ============================================================
# HELPERS
# ============================================================

def safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def media_title(media):
    return str(
        media.get("title")
        or media.get("name")
        or media.get("filename")
        or "Untitled"
    )


def media_url(media):
    return str(
        media.get("url")
        or media.get("webpage_url")
        or media.get("original_url")
        or ""
    )


def format_bytes(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "--"

    if value < 0:
        return "--"

    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024:
            return (
                f"{value:.0f} {unit}"
                if unit == "B"
                else f"{value:.1f} {unit}"
            )

        value /= 1024

    return f"{value:.1f} PB"


def format_eta(value):
    try:
        value = max(0, int(float(value)))
    except (TypeError, ValueError):
        return "--:--"

    minutes, seconds = divmod(value, 60)
    hours, minutes = divmod(minutes, 60)

    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    return f"{minutes:02d}:{seconds:02d}"


def set_combo_data(combo, value):
    index = combo.findData(value)

    if index >= 0:
        combo.setCurrentIndex(index)


DEFAULT_OUTPUT = os.path.join(
    os.path.expanduser("~"),
    "Downloads",
)


# ============================================================
# ADVANCED SETTINGS
# ============================================================

class DownloadSettingsDialog(QDialog):

    def __init__(self, settings=None, parent=None):
        super().__init__(parent)

        self.settings = {
            "concurrent_downloads": 2,
            "fragments": 4,
            "retries": 10,
            "cookies": False,
            "cookie_browser": "firefox",
            "sponsorblock": False,
            "no_warnings": False,
            "keep_fragments": False,
        }

        self.settings.update(settings or {})

        self.setWindowTitle("Advanced Settings")
        self.resize(500, 400)

        layout = QVBoxLayout(self)

        title = QLabel("Advanced Downloader Settings")

        title.setStyleSheet(
            "font-size:20px;font-weight:700;"
        )

        layout.addWidget(title)

        grid = QGridLayout()

        grid.addWidget(
            QLabel("Concurrent downloads:"),
            0,
            0,
        )

        self.concurrent = QSpinBox()
        self.concurrent.setRange(1, 16)
        self.concurrent.setValue(
            safe_int(
                self.settings["concurrent_downloads"],
                2,
            )
        )

        grid.addWidget(
            self.concurrent,
            0,
            1,
        )

        grid.addWidget(
            QLabel("Fragments per download:"),
            1,
            0,
        )

        self.fragments = QSpinBox()
        self.fragments.setRange(1, 32)
        self.fragments.setValue(
            safe_int(
                self.settings["fragments"],
                4,
            )
        )

        grid.addWidget(
            self.fragments,
            1,
            1,
        )

        grid.addWidget(
            QLabel("Retries:"),
            2,
            0,
        )

        self.retries = QSpinBox()
        self.retries.setRange(0, 100)
        self.retries.setValue(
            safe_int(
                self.settings["retries"],
                10,
            )
        )

        grid.addWidget(
            self.retries,
            2,
            1,
        )

        self.cookies = QCheckBox(
            "Use browser cookies"
        )

        self.cookies.setChecked(
            bool(self.settings["cookies"])
        )

        grid.addWidget(
            self.cookies,
            3,
            0,
            1,
            2,
        )

        grid.addWidget(
            QLabel("Browser:"),
            4,
            0,
        )

        self.browser = QComboBox()

        for name, value in (
            ("Firefox", "firefox"),
            ("Chrome", "chrome"),
            ("Chromium", "chromium"),
            ("Brave", "brave"),
        ):
            self.browser.addItem(
                name,
                value,
            )

        set_combo_data(
            self.browser,
            self.settings["cookie_browser"],
        )

        self.browser.setEnabled(
            self.cookies.isChecked()
        )

        self.cookies.toggled.connect(
            self.browser.setEnabled
        )

        grid.addWidget(
            self.browser,
            4,
            1,
        )

        self.sponsorblock = QCheckBox(
            "Remove SponsorBlock sections"
        )

        self.sponsorblock.setChecked(
            bool(self.settings["sponsorblock"])
        )

        grid.addWidget(
            self.sponsorblock,
            5,
            0,
            1,
            2,
        )

        self.warnings = QCheckBox(
            "Suppress non-critical warnings"
        )

        self.warnings.setChecked(
            bool(self.settings["no_warnings"])
        )

        grid.addWidget(
            self.warnings,
            6,
            0,
            1,
            2,
        )

        self.fragments_check = QCheckBox(
            "Keep fragments on failure"
        )

        self.fragments_check.setChecked(
            bool(self.settings["keep_fragments"])
        )

        grid.addWidget(
            self.fragments_check,
            7,
            0,
            1,
            2,
        )

        layout.addLayout(grid)
        layout.addStretch()

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok
            | QDialogButtonBox.Cancel
        )

        buttons.accepted.connect(
            self.accept
        )

        buttons.rejected.connect(
            self.reject
        )

        layout.addWidget(buttons)

    def get_settings(self):
        return {
            "concurrent_downloads":
                self.concurrent.value(),

            "fragments":
                self.fragments.value(),

            "retries":
                self.retries.value(),

            "cookies":
                self.cookies.isChecked(),

            "cookie_browser":
                self.browser.currentData(),

            "sponsorblock":
                self.sponsorblock.isChecked(),

            "no_warnings":
                self.warnings.isChecked(),

            "keep_fragments":
                self.fragments_check.isChecked(),
        }


# ============================================================
# INFORMATION WORKER
# ============================================================

class MediaInfoWorker(QObject):

    finished = Signal(object)
    error = Signal(object)
    cancelled = Signal()

    def __init__(self, processor, settings):
        super().__init__()

        self.processor = processor
        self.settings = dict(settings)

    @Slot()
    def run(self):
        try:
            result = self.processor.fetch_media_info(
                self.settings
            )

            if (
                isinstance(result, dict)
                and result.get("cancelled")
            ):
                self.cancelled.emit()
                return

            self.finished.emit(result)

        except JobCancelled:
            self.cancelled.emit()

        except Exception as exc:
            self.error.emit(exc)

    @Slot()
    def cancel(self):
        try:
            self.processor.cancel()
        except Exception:
            pass


# ============================================================
# DOWNLOAD WORKER
# ============================================================

class MediaDownloadWorker(QObject):

    progress = Signal(
        int,
        str,
        str,
        int,
        object,
    )

    finished = Signal(int, object)
    error = Signal(int, object)
    cancelled = Signal(int)

    def __init__(self, index, settings):
        super().__init__()

        self.index = index
        self.settings = dict(settings)
        self.processor = None

    @Slot()
    def run(self):
        try:
            self.processor = MediaJobProcessor(
                progress_callback=self.on_progress,
                error_callback=self.on_error,
            )

            result = self.processor.process_settings(
                self.settings
            )

            if getattr(
                self.processor,
                "cancelled",
                False,
            ):
                self.cancelled.emit(self.index)
                return

            self.finished.emit(
                self.index,
                result,
            )

        except JobCancelled:
            self.cancelled.emit(self.index)

        except Exception as exc:
            self.error.emit(
                self.index,
                exc,
            )

    @Slot()
    def cancel(self):
        if self.processor is None:
            return

        try:
            self.processor.cancel()
        except Exception:
            pass

    def on_progress(
        self,
        info,
        filename,
        percentage,
        details,
    ):
        percentage = max(
            0,
            min(
                100,
                safe_int(percentage),
            ),
        )

        if not isinstance(details, dict):
            details = {}

        self.progress.emit(
            self.index,
            str(info or ""),
            str(filename or ""),
            percentage,
            details,
        )

    def on_error(self, error):
        self.error.emit(
            self.index,
            error,
        )


# ============================================================
# MEDIA SELECTION
# ============================================================

class MediaSelectionDialog(QDialog):

    accepted_media = Signal(object)

    def __init__(
        self,
        media_items=None,
        download_mode="video_subtitles",
        parent=None,
    ):
        super().__init__(parent)

        self.media_items = []
        self.selected_media = []
        self.download_mode = download_mode

        self.setWindowTitle("Select Media")
        self.resize(900, 650)

        self.build_ui()

        if media_items:
            self.set_media_items(media_items)
        else:
            self.set_loading(True)

    def build_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel("Select Media")

        title.setStyleSheet(
            "font-size:24px;font-weight:700;"
        )

        layout.addWidget(title)

        self.info = QLabel(
            "Fetching media information..."
        )

        layout.addWidget(self.info)

        self.loading = QProgressBar()
        self.loading.setRange(0, 0)

        layout.addWidget(self.loading)

        controls = QHBoxLayout()

        self.select_all_button = QPushButton(
            "Select All"
        )

        self.clear_button = QPushButton(
            "Deselect All"
        )

        self.invert_button = QPushButton(
            "Invert"
        )

        controls.addWidget(
            self.select_all_button
        )

        controls.addWidget(
            self.clear_button
        )

        controls.addWidget(
            self.invert_button
        )

        controls.addStretch()

        self.count = QLabel(
            "0 selected / 0"
        )

        controls.addWidget(
            self.count
        )

        layout.addLayout(controls)

        self.list = QListWidget()

        self.list.setSelectionMode(
            QAbstractItemView.ExtendedSelection
        )

        self.list.setAlternatingRowColors(True)

        layout.addWidget(
            self.list,
            1,
        )

        self.details = QLabel(
            "Select a media item."
        )

        self.details.setWordWrap(True)
        self.details.setMinimumHeight(60)

        layout.addWidget(
            self.details
        )

        self.settings_group = QGroupBox(
            "Download Settings"
        )

        self.settings_grid = QGridLayout(
            self.settings_group
        )

        layout.addWidget(
            self.settings_group
        )

        self.build_settings()

        output = QHBoxLayout()

        self.output = QLineEdit(
            DEFAULT_OUTPUT
        )

        browse = QPushButton("Browse")

        browse.clicked.connect(
            self.browse_output
        )

        output.addWidget(
            QLabel("Folder:")
        )

        output.addWidget(
            self.output,
            1,
        )

        output.addWidget(
            browse
        )

        layout.addLayout(output)

        self.playlist_folder = QCheckBox(
            "Separate playlist folder"
        )

        self.playlist_folder.setChecked(False)

        self.duplicates = QCheckBox(
            "Avoid duplicates"
        )

        self.duplicates.setChecked(True)

        options = QHBoxLayout()

        options.addWidget(
            self.playlist_folder
        )

        options.addWidget(
            self.duplicates
        )

        options.addStretch()

        layout.addLayout(options)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok
            | QDialogButtonBox.Cancel
        )

        self.buttons.button(
            QDialogButtonBox.Ok
        ).setText("Add Selected")

        layout.addWidget(
            self.buttons
        )

        self.select_all_button.clicked.connect(
            self.select_all
        )

        self.clear_button.clicked.connect(
            self.deselect_all
        )

        self.invert_button.clicked.connect(
            self.invert
        )

        self.list.itemChanged.connect(
            self.update_count
        )

        self.list.itemSelectionChanged.connect(
            self.show_details
        )

        self.buttons.accepted.connect(
            self.accept_selection
        )

        self.buttons.rejected.connect(
            self.reject
        )

    # --------------------------------------------------------
    # SETTINGS
    # --------------------------------------------------------

    def build_settings(self):
        self.video_quality = QComboBox()

        for name, value in (
            ("Best", "best"),
            ("2160p", "2160"),
            ("1440p", "1440"),
            ("1080p", "1080"),
            ("720p", "720"),
            ("480p", "480"),
            ("360p", "360"),
        ):
            self.video_quality.addItem(
                name,
                value,
            )
        # Default video quality: 480p
        set_combo_data(
            self.video_quality,
            "480",
        )

        self.container = QComboBox()

        for name, value in (
            ("MP4", "mp4"),
            ("MKV", "mkv"),
            ("WebM", "webm"),
            ("Native", "native"),
        ):
            self.container.addItem(
                name,
                value,
            )
        set_combo_data(
            self.container,
            "mp4",
        )

        self.audio_quality = QComboBox()

        for name, value in (
            ("Best", "best"),
            ("320 kbps", "320"),
            ("256 kbps", "256"),
            ("192 kbps", "192"),
            ("128 kbps", "128"),
        ):
            self.audio_quality.addItem(
                name,
                value,
            )
        set_combo_data(
            self.audio_quality,
            "192",
        )

        self.audio_format = QComboBox()

        for value in (
            "mp3",
            "m4a",
            "aac",
            "flac",
            "wav",
            "opus",
        ):
            self.audio_format.addItem(
                value.upper(),
                value,
            )
        set_combo_data(
            self.audio_format,
            "mp3",
        )

        self.subtitle_language = QComboBox()

        languages = (
            ("English", "en"),
            ("Spanish", "es"),
            ("French", "fr"),
            ("German", "de"),
            ("Italian", "it"),
            ("Portuguese", "pt"),
            ("Arabic", "ar"),
            ("Hindi", "hi"),
            ("Swahili", "sw"),
            ("Japanese", "ja"),
            ("Korean", "ko"),
            ("Chinese", "zh"),
        )

        for name, value in languages:
            self.subtitle_language.addItem(
                name,
                value,
            )

        self.subtitle_type = QComboBox()

        for name, value in (
            ("Any", "any"),
            ("Original", "original"),
            ("Auto-generated", "auto"),
            ("Translated", "translated"),
        ):
            self.subtitle_type.addItem(
                name,
                value,
            )

        self.subtitle_format = QComboBox()

        for value in (
            "srt",
            "vtt",
            "ass",
            "ttml",
        ):
            self.subtitle_format.addItem(
                value.upper(),
                value,
            )

        self.save_subtitles = QCheckBox(
            "Save subtitle file"
        )

        self.save_subtitles.setChecked(True)

        self.embed_subtitles = QCheckBox(
            "Embed subtitles"
        )

        self.update_mode()

    def update_mode(self):
        while self.settings_grid.count():
            item = self.settings_grid.takeAt(0)

            if item.widget():
                item.widget().setParent(None)

        mode = self.download_mode
        row = 0

        if mode in (
            "video",
            "video_subtitles",
        ):
            self.add_setting(
                "Quality",
                self.video_quality,
                row,
            )

            self.add_setting(
                "Format",
                self.container,
                row,
                2,
            )

            row += 1

        if mode == "audio":
            self.add_setting(
                "Quality",
                self.audio_quality,
                row,
            )

            self.add_setting(
                "Format",
                self.audio_format,
                row,
                2,
            )

            row += 1

        if mode in (
            "subtitles",
            "video_subtitles",
        ):
            self.add_setting(
                "Language",
                self.subtitle_language,
                row,
            )

            self.add_setting(
                "Type",
                self.subtitle_type,
                row,
                2,
            )

            row += 1

            self.add_setting(
                "Format",
                self.subtitle_format,
                row,
            )

            self.settings_grid.addWidget(
                self.save_subtitles,
                row,
                2,
                1,
                2,
            )

            row += 1

        if mode == "video_subtitles":
            self.settings_grid.addWidget(
                self.embed_subtitles,
                row,
                0,
                1,
                4,
            )

    def add_setting(
        self,
        name,
        widget,
        row,
        column=0,
    ):
        self.settings_grid.addWidget(
            QLabel(name),
            row,
            column,
        )

        self.settings_grid.addWidget(
            widget,
            row,
            column + 1,
        )

    # --------------------------------------------------------
    # LOADING
    # --------------------------------------------------------

    def set_loading(self, value):
        self.loading.setVisible(value)
        self.list.setVisible(not value)
        self.settings_group.setVisible(not value)
        self.buttons.setEnabled(not value)

    # --------------------------------------------------------
    # MEDIA
    # --------------------------------------------------------

    def set_media_items(self, items):
        self.media_items = [
            dict(item)
            for item in items
            if isinstance(item, dict)
        ]

        self.list.clear()

        for media in self.media_items:
            title = media_title(media)

            if media.get("error"):
                text = f"ERROR | {title}"

            else:
                index = media.get(
                    "playlist_index",
                    "-",
                )

                text = (
                    f"{index} | "
                    f"{title} | "
                    f"{media_url(media)}"
                )

            item = QListWidgetItem(text)

            if media.get("error"):
                item.setForeground(
                    QColor("#ef4444")
                )

            item.setFlags(
                item.flags()
                | Qt.ItemIsUserCheckable
            )

            item.setCheckState(
                Qt.Checked
            )

            item.setData(
                Qt.UserRole,
                dict(media),
            )

            self.list.addItem(item)

        self.info.setText(
            f"Found {len(self.media_items)} media item(s)."
        )

        self.set_loading(False)
        self.update_count()

        if self.list.count():
            self.list.setCurrentRow(0)

    def show_details(self):
        selected = self.list.selectedItems()

        if not selected:
            self.details.setText(
                "Select a media item."
            )
            return

        media = selected[0].data(
            Qt.UserRole
        )

        if not isinstance(media, dict):
            return

        lines = [
            f"<b>{media_title(media)}</b>"
        ]

        for label, keys in (
            (
                "Channel",
                (
                    "uploader",
                    "channel",
                    "channel_title",
                ),
            ),
            (
                "Duration",
                (
                    "duration_string",
                    "duration",
                ),
            ),
            (
                "Resolution",
                (
                    "resolution",
                    "format_note",
                ),
            ),
        ):
            for key in keys:
                value = media.get(key)

                if value:
                    lines.append(
                        f"{label}: {value}"
                    )
                    break

        width = media.get("width")
        height = media.get("height")

        if width and height:
            lines.append(
                f"Size: {width} × {height}"
            )

        self.details.setText(
            "<br>".join(lines)
        )

    # --------------------------------------------------------
    # SELECTION
    # --------------------------------------------------------

    def select_all(self):
        self.set_all(Qt.Checked)

    def deselect_all(self):
        self.set_all(Qt.Unchecked)

    def invert(self):
        self.list.blockSignals(True)

        for i in range(self.list.count()):
            item = self.list.item(i)

            item.setCheckState(
                Qt.Unchecked
                if item.checkState() == Qt.Checked
                else Qt.Checked
            )

        self.list.blockSignals(False)
        self.update_count()

    def set_all(self, state):
        self.list.blockSignals(True)

        for i in range(self.list.count()):
            self.list.item(i).setCheckState(
                state
            )

        self.list.blockSignals(False)
        self.update_count()

    def update_count(self, *_):
        total = self.list.count()

        selected = sum(
            self.list.item(i).checkState()
            == Qt.Checked
            for i in range(total)
        )

        self.count.setText(
            f"{selected} selected / {total}"
        )

    # --------------------------------------------------------
    # OUTPUT
    # --------------------------------------------------------

    def browse_output(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Download Folder",
            self.output.text(),
        )

        if folder:
            self.output.setText(folder)

    def get_settings(self):
        mode = self.download_mode

        subtitles = mode in (
            "video_subtitles",
            "subtitles",
        )

        return {
            "download_mode": mode,

            "quality":
                self.video_quality.currentData(),

            "container":
                self.container.currentData(),

            "audio_quality":
                self.audio_quality.currentData(),

            "audio_format":
                self.audio_format.currentData(),

            "download_subtitles":
                subtitles,

            "subtitle_language":
                self.subtitle_language.currentData(),

            "subtitle_type":
                self.subtitle_type.currentData(),

            "subtitle_format":
                self.subtitle_format.currentData(),

            "save_separate_subtitle":
                subtitles
                and self.save_subtitles.isChecked(),

            "embed_subtitles":
                mode == "video_subtitles"
                and self.embed_subtitles.isChecked(),

            "output":
                self.output.text().strip(),

            "playlist_folder":
                self.playlist_folder.isChecked(),

            "avoid_duplicates":
                self.duplicates.isChecked(),
        }

    def accept_selection(self):
        selected = []

        for i in range(self.list.count()):
            item = self.list.item(i)

            if item.checkState() != Qt.Checked:
                continue

            media = item.data(
                Qt.UserRole
            )

            if isinstance(media, dict):
                selected.append(dict(media))

        if not selected:
            QMessageBox.warning(
                self,
                "Nothing Selected",
                "Select at least one media item.",
            )
            return

        settings = self.get_settings()

        for media in selected:
            media["download_settings"] = dict(
                settings
            )

        self.selected_media = selected

        self.accepted_media.emit(
            selected
        )

        self.accept()


# ============================================================
# QUEUE ITEM WIDGET
# ============================================================

class DownloadQueueItemWidget(QWidget):

    retry_requested = Signal(int)
    cancel_requested = Signal(int)

    def __init__(
        self,
        index,
        title,
        parent=None,
    ):
        super().__init__(parent)

        self.index = index
        self.media_title = str(
            title or "Untitled"
        )

        # ====================================================
        # IMPORTANT:
        # HARD FIXED HEIGHT.
        #
        # This prevents the QListWidget row from expanding
        # when status/details/progress are updated.
        # ====================================================

        self.setFixedHeight(
            QUEUE_ITEM_HEIGHT
        )

        self.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Fixed,
        )

        layout = QVBoxLayout(self)

        layout.setContentsMargins(
            10,
            7,
            10,
            7,
        )

        layout.setSpacing(4)

        # ----------------------------------------------------
        # TOP ROW
        # ----------------------------------------------------

        top = QHBoxLayout()

        top.setSpacing(8)

        top.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        self.title = QLabel(
            self.media_title
        )

        self.title.setWordWrap(False)

        self.title.setTextInteractionFlags(
            Qt.TextSelectableByMouse
        )

        self.title.setToolTip(
            self.media_title
        )

        # Prevent title from forcing the row wider.
        self.title.setSizePolicy(
            QSizePolicy.Ignored,
            QSizePolicy.Fixed,
        )

        self.status = QLabel(
            "Queued"
        )

        self.status.setMinimumWidth(90)
        self.status.setMaximumHeight(24)

        self.status.setAlignment(
            Qt.AlignRight
            | Qt.AlignVCenter
        )

        self.retry = QPushButton(
            "Retry"
        )

        self.cancel = QPushButton(
            "Cancel"
        )

        self.retry.setFixedWidth(70)
        self.cancel.setFixedWidth(75)

        self.retry.setFixedHeight(24)
        self.cancel.setFixedHeight(24)

        top.addWidget(
            self.title,
            1,
        )

        top.addWidget(
            self.status
        )

        top.addWidget(
            self.retry
        )

        top.addWidget(
            self.cancel
        )

        layout.addLayout(top)

        # ----------------------------------------------------
        # PROGRESS
        # ----------------------------------------------------

        self.progress = QProgressBar()

        self.progress.setRange(
            0,
            100,
        )

        self.progress.setValue(0)

        self.progress.setTextVisible(True)

        self.progress.setFixedHeight(18)

        self.progress.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Fixed,
        )

        layout.addWidget(
            self.progress
        )

        # ----------------------------------------------------
        # DETAILS
        # ----------------------------------------------------

        self.details = QLabel(
            "Waiting..."
        )

        self.details.setWordWrap(False)

        self.details.setMinimumHeight(18)
        self.details.setMaximumHeight(18)

        self.details.setSizePolicy(
            QSizePolicy.Ignored,
            QSizePolicy.Fixed,
        )

        self.details.setTextInteractionFlags(
            Qt.TextSelectableByMouse
        )

        layout.addWidget(
            self.details
        )

        # ----------------------------------------------------
        # SIGNALS
        # ----------------------------------------------------

        self.retry.clicked.connect(
            lambda: self.retry_requested.emit(
                self.index
            )
        )

        self.cancel.clicked.connect(
            lambda: self.cancel_requested.emit(
                self.index
            )
        )

        self.set_status(
            "Queued"
        )

    # --------------------------------------------------------
    # SIZE HINT
    # --------------------------------------------------------

    def sizeHint(self):
        """
        Always report the exact same size.

        QListWidget can ask child widgets for a new size hint
        whenever their contents change. Returning a fixed height
        prevents progress/status/details changes from expanding
        the row.
        """
        return QSize(
            0,
            QUEUE_ITEM_HEIGHT,
        )

    def minimumSizeHint(self):
        return QSize(
            0,
            QUEUE_ITEM_HEIGHT,
        )

    # --------------------------------------------------------
    # STATUS
    # --------------------------------------------------------

    def set_status(self, status):
        status = str(
            status or "Queued"
        )

        self.status.setText(
            status
        )

        self.retry.setVisible(
            status in (
                "Failed",
                "Cancelled",
            )
        )

        self.cancel.setVisible(
            status in (
                "Queued",
                "Downloading",
            )
        )

        if status == "Queued":
            self.set_details(
                "Waiting in queue..."
            )

        elif status == "Downloading":
            if not self.details.text():
                self.set_details(
                    "Starting download..."
                )

        elif status == "Completed":
            self.set_details(
                "Download completed."
            )

        elif status == "Failed":
            self.set_details(
                "Download failed."
            )

        elif status == "Cancelled":
            self.set_details(
                "Download cancelled."
            )

    # --------------------------------------------------------
    # DETAILS
    # --------------------------------------------------------

    def set_details(self, text):
        text = str(
            text or ""
        ).strip()

        if not text:
            return

        self.details.setText(
            text
        )

        self.details.setToolTip(
            text
        )

    # --------------------------------------------------------
    # PROGRESS
    # --------------------------------------------------------

    def set_progress(
        self,
        percentage,
        downloaded="--",
        speed="--",
        eta="--:--",
        details=None,
    ):
        percentage = max(
            0,
            min(
                100,
                safe_int(percentage),
            ),
        )

        # Progress bar
        self.progress.setValue(
            percentage
        )

        # Build media-service style status
        parts = [
            f"{percentage}%"
        ]

        if downloaded not in (
            None,
            "",
            "--",
        ):
            parts.append(
                f"Downloaded: {downloaded}"
            )

        if speed not in (
            None,
            "",
            "--",
        ):
            parts.append(
                f"Speed: {speed}"
            )

        if eta not in (
            None,
            "",
            "--:--",
        ):
            parts.append(
                f"Remaining: {eta}"
            )

        status_text = "  •  ".join(parts)

        if details:
            status_text = (
                f"{details}  •  "
                f"{status_text}"
            )

        self.set_details(
            status_text
        )


# ============================================================
# QUEUE DATA
# ============================================================

@dataclass
class QueueItem:
    data: dict
    widget: DownloadQueueItemWidget
    status: str = "Queued"
    thread: QThread | None = None
    worker: MediaDownloadWorker | None = None


# ============================================================
# MAIN PAGE
# ============================================================

class VideoDownloadPage(QWidget):

    download_requested = Signal(dict)
    cancel_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.downloading = False

        self.info_thread = None
        self.info_worker = None
        self.info_processor = None

        self.selection_dialog = None

        self.queue = []

        self.running = 0
        self.completed = 0

        self.advanced = {
            "concurrent_downloads": 2,
            "fragments": 4,
            "retries": 10,
            "cookies": False,
            "cookie_browser": "firefox",
            "sponsorblock": False,
            "no_warnings": False,
            "keep_fragments": False,
        }

        self.build_ui()

    # ========================================================
    # UI
    # ========================================================

    def build_ui(self):
        root = QVBoxLayout(self)

        root.setContentsMargins(
            8,
            8,
            8,
            8,
        )

        root.setSpacing(6)

        # ----------------------------------------------------
        # TOP
        # ----------------------------------------------------

        top = QWidget()

        top.setFixedHeight(60)

        top_layout = QHBoxLayout(top)

        top_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        top_layout.addWidget(
            QLabel("Type:")
        )

        self.mode = QComboBox()

        for name, value in (
            (
                "Video + Subtitles",
                "video_subtitles",
            ),
            (
                "Video only",
                "video",
            ),
            (
                "Audio only",
                "audio",
            ),
            (
                "Subtitles only",
                "subtitles",
            ),
        ):
            self.mode.addItem(
                name,
                value,
            )

        top_layout.addWidget(
            self.mode
        )

        self.url = QLineEdit()

        self.url.setPlaceholderText(
            "Paste video or playlist URL..."
        )

        top_layout.addWidget(
            self.url,
            1,
        )

        self.multiple = QCheckBox(
            "Multiple URLs"
        )

        top_layout.addWidget(
            self.multiple
        )

        self.fetch = QPushButton(
            "Fetch"
        )

        top_layout.addWidget(
            self.fetch
        )

        root.addWidget(
            top
        )

        # ----------------------------------------------------
        # MIDDLE
        # ----------------------------------------------------

        middle = QGroupBox(
            "Selected Media / Download Queue"
        )

        middle_layout = QVBoxLayout(
            middle
        )

        middle_layout.setContentsMargins(
            10,
            10,
            10,
            10,
        )

        self.current = QLabel(
            "Ready."
        )

        self.current.setStyleSheet(
            "font-size:16px;font-weight:600;"
        )

        self.current.setSizePolicy(
            QSizePolicy.Ignored,
            QSizePolicy.Fixed,
        )

        middle_layout.addWidget(
            self.current
        )

        self.overall = QProgressBar()

        self.overall.setRange(
            0,
            100,
        )

        self.overall.setValue(0)

        self.overall.setFixedHeight(18)

        middle_layout.addWidget(
            self.overall
        )

        self.overall_label = QLabel(
            "Completed: 0 / 0"
        )

        middle_layout.addWidget(
            self.overall_label
        )

        # ----------------------------------------------------
        # QUEUE CONTROLS
        # ----------------------------------------------------

        controls = QHBoxLayout()

        self.select_queue = QPushButton(
            "Select All"
        )

        self.clear_selection = QPushButton(
            "Clear Selection"
        )

        self.clear_queue = QPushButton(
            "Clear Queue"
        )

        controls.addWidget(
            self.select_queue
        )

        controls.addWidget(
            self.clear_selection
        )

        controls.addWidget(
            self.clear_queue
        )

        controls.addStretch()

        self.queue_count = QLabel(
            "0 queued / 0 total"
        )

        controls.addWidget(
            self.queue_count
        )

        middle_layout.addLayout(
            controls
        )

        # ----------------------------------------------------
        # QUEUE LIST
        # ----------------------------------------------------

        self.queue_list = QListWidget()

        self.queue_list.setSelectionMode(
            QAbstractItemView.ExtendedSelection
        )

        self.queue_list.setAlternatingRowColors(
            True
        )

        # ====================================================
        # IMPORTANT FIX
        # ====================================================

        # Tell QListWidget that every item has the same size.
        self.queue_list.setUniformItemSizes(
            True
        )

        # Do not resize the list based on its children.
        self.queue_list.setSizeAdjustPolicy(
            QAbstractItemView.SizeAdjustPolicy.AdjustIgnored
        )

        self.queue_list.setVerticalScrollBarPolicy(
            Qt.ScrollBarAsNeeded
        )

        self.queue_list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff
        )

        # Never allow the queue itself to request a larger
        # height from the parent when download widgets change.
        self.queue_list.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding,
        )

        middle_layout.addWidget(
            self.queue_list,
            1,
        )

        root.addWidget(
            middle,
            1,
        )

        # ----------------------------------------------------
        # BOTTOM
        # ----------------------------------------------------

        bottom = QWidget()

        bottom.setFixedHeight(60)

        bottom_layout = QHBoxLayout(
            bottom
        )

        bottom_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        self.log_label = QLabel(
            "Ready."
        )

        self.log_label.setSizePolicy(
            QSizePolicy.Ignored,
            QSizePolicy.Fixed,
        )

        bottom_layout.addWidget(
            self.log_label,
            1,
        )

        self.settings = QPushButton(
            "Settings"
        )

        self.download = QPushButton(
            "Download"
        )

        self.cancel = QPushButton(
            "Cancel All"
        )

        self.cancel.setEnabled(False)

        bottom_layout.addWidget(
            self.settings
        )

        bottom_layout.addWidget(
            self.download
        )

        bottom_layout.addWidget(
            self.cancel
        )

        root.addWidget(
            bottom
        )

        # ----------------------------------------------------
        # SIGNALS
        # ----------------------------------------------------

        self.fetch.clicked.connect(
            self.fetch_information
        )

        self.download.clicked.connect(
            self.start_downloads
        )

        self.cancel.clicked.connect(
            self.cancel_all
        )

        self.settings.clicked.connect(
            self.open_settings
        )

        self.select_queue.clicked.connect(
            self.queue_list.selectAll
        )

        self.clear_selection.clicked.connect(
            self.queue_list.clearSelection
        )

        self.clear_queue.clicked.connect(
            self.clear_queue_items
        )

    # ========================================================
    # SETTINGS
    # ========================================================

    def open_settings(self):
        if self.downloading:
            return

        dialog = DownloadSettingsDialog(
            self.advanced,
            self,
        )

        if dialog.exec() != QDialog.Accepted:
            return

        self.advanced.update(
            dialog.get_settings()
        )

        self.log(
            "Advanced settings updated."
        )

    # ========================================================
    # FETCH
    # ========================================================

    @Slot()
    def fetch_information(self):
        if self.downloading:
            return

        if (
            self.info_thread
            and self.info_thread.isRunning()
        ):
            return

        url = self.url.text().strip()

        if not url:
            QMessageBox.warning(
                self,
                "URL Required",
                "Paste a video or playlist URL.",
            )
            return

        self.close_selection()

        dialog = MediaSelectionDialog(
            download_mode=self.mode.currentData(),
            parent=self,
        )

        dialog.accepted_media.connect(
            self.add_selected
        )

        self.selection_dialog = dialog

        dialog.show()

        try:
            self.info_processor = (
                MediaJobProcessor()
            )

        except Exception as exc:
            self.info_error(exc)
            return

        settings = {
            "url": url,

            "download_mode":
                self.mode.currentData(),

            "multiple_urls":
                self.multiple.isChecked(),

            **self.advanced,
        }

        thread = QThread()

        worker = MediaInfoWorker(
            self.info_processor,
            settings,
        )

        self.info_thread = thread
        self.info_worker = worker

        worker.moveToThread(
            thread
        )

        thread.started.connect(
            worker.run
        )

        worker.finished.connect(
            self.info_finished
        )

        worker.error.connect(
            self.info_error
        )

        worker.cancelled.connect(
            self.info_cancelled
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

        thread.finished.connect(
            worker.deleteLater
        )

        thread.finished.connect(
            self.info_thread_finished
        )

        thread.start()

        self.current.setText(
            "Fetching media information..."
        )

        self.log(
            "Fetching media information..."
        )

    @Slot(object)
    def info_finished(self, result):
        if not isinstance(result, dict):
            self.info_error(
                ValueError(
                    "Invalid media information."
                )
            )
            return

        items = result.get(
            "results"
        ) or []

        if isinstance(
            items,
            dict,
        ):
            items = [items]

        if not items:
            items = [result]

        normalized = []

        for item in items:
            if not isinstance(
                item,
                dict,
            ):
                continue

            item = dict(item)

            if not item.get("url"):
                item["url"] = (
                    item.get("webpage_url")
                    or item.get("original_url")
                    or ""
                )

            if item.get("url"):
                normalized.append(
                    item
                )

        if not normalized:
            self.info_error(
                ValueError(
                    "No downloadable media found."
                )
            )
            return

        self.current.setText(
            f"Found {len(normalized)} media item(s)."
        )

        self.log(
            f"Found {len(normalized)} media item(s)."
        )

        if self.selection_dialog:
            self.selection_dialog.set_media_items(
                normalized
            )

    @Slot()
    def info_cancelled(self):
        self.current.setText(
            "Information fetch cancelled."
        )

    @Slot(object)
    def info_error(self, error):
        message = (
            str(error).strip()
            or "Unknown error."
        )

        self.log(
            f"FETCH ERROR: {message}"
        )

        self.current.setText(
            "Failed to fetch media information."
        )

        if self.selection_dialog:
            self.selection_dialog.info.setText(
                f"Error: {message}"
            )

            self.selection_dialog.set_loading(
                False
            )

        QMessageBox.critical(
            self,
            "Fetch Error",
            message,
        )

    @Slot()
    def info_thread_finished(self):
        thread = self.info_thread

        self.info_thread = None
        self.info_worker = None
        self.info_processor = None

        if thread:
            thread.deleteLater()

    # ========================================================
    # QUEUE
    # ========================================================

    @Slot(object)
    def add_selected(self, selected):
        if self.downloading:
            return

        if not isinstance(
            selected,
            list,
        ):
            return

        for media in selected:
            if isinstance(
                media,
                dict,
            ):
                self.add_queue_item(
                    media
                )

        self.update_queue_count()

    def add_queue_item(self, data):
        index = len(
            self.queue
        )

        widget = DownloadQueueItemWidget(
            index,
            media_title(data),
        )

        widget.retry_requested.connect(
            self.retry_item
        )

        widget.cancel_requested.connect(
            self.cancel_item
        )

        item = QListWidgetItem()

        # ====================================================
        # HARD FIXED ROW HEIGHT
        # ====================================================

        item.setSizeHint(
            QSize(
                0,
                QUEUE_ITEM_HEIGHT,
            )
        )

        self.queue_list.addItem(
            item
        )

        self.queue_list.setItemWidget(
            item,
            widget,
        )

        # Re-apply after assigning the widget.
        item.setSizeHint(
            QSize(
                0,
                QUEUE_ITEM_HEIGHT,
            )
        )

        self.queue.append(
            QueueItem(
                dict(data),
                widget,
            )
        )

        self.update_overall()

    def clear_queue_items(self):
        if self.downloading:
            return

        self.queue.clear()

        self.queue_list.clear()

        self.running = 0
        self.completed = 0

        self.overall.setValue(
            0
        )

        self.update_queue_count()

        self.update_overall()

    def update_queue_count(self):
        total = len(
            self.queue
        )

        queued = sum(
            item.status == "Queued"
            for item in self.queue
        )

        self.queue_count.setText(
            f"{queued} queued / {total} total"
        )

        self.overall_label.setText(
            f"Completed: "
            f"{self.completed} / {total}"
        )

    # ========================================================
    # START DOWNLOADS
    # ========================================================

    @Slot()
    def start_downloads(self):
        if self.downloading:
            return

        if not self.queue:
            QMessageBox.warning(
                self,
                "No Media",
                "Fetch and select media first.",
            )
            return

        for item in self.queue:
            if item.status in (
                "Completed",
                "Failed",
                "Cancelled",
            ):
                item.status = "Queued"

                item.widget.progress.setValue(
                    0
                )

                item.widget.set_status(
                    "Queued"
                )

        self.running = 0
        self.completed = 0

        self.set_downloading(
            True
        )

        self.log(
            "Starting download queue..."
        )

        self.start_more()

    def start_more(self):
        limit = max(
            1,
            safe_int(
                self.advanced.get(
                    "concurrent_downloads",
                    2,
                ),
                2,
            ),
        )

        while self.running < limit:
            item = next(
                (
                    x
                    for x in self.queue
                    if x.status == "Queued"
                ),
                None,
            )

            if item is None:
                break

            self.start_item(
                item
            )

        self.check_finished()

    # ========================================================
    # ONE DOWNLOAD
    # ========================================================

    def start_item(self, item):
        index = item.widget.index

        item.status = "Downloading"

        item.widget.set_status(
            "Downloading"
        )

        self.running += 1

        settings = dict(
            item.data.get(
                "download_settings",
                {},
            )
        )

        settings.update(
            self.advanced
        )

        settings["download_mode"] = (
            settings.get(
                "download_mode",
                self.mode.currentData(),
            )
        )

        settings["videos"] = [
            dict(item.data)
        ]

        settings["url"] = media_url(
            item.data
        )

        thread = QThread()

        worker = MediaDownloadWorker(
            index,
            settings,
        )

        item.thread = thread
        item.worker = worker

        worker.moveToThread(
            thread
        )

        thread.started.connect(
            worker.run
        )

        worker.progress.connect(
            self.download_progress
        )

        worker.finished.connect(
            self.download_finished
        )

        worker.error.connect(
            self.download_error
        )

        worker.cancelled.connect(
            self.download_cancelled
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

        thread.finished.connect(
            worker.deleteLater
        )

        thread.finished.connect(
            self.download_thread_finished
        )

        thread.start()

        self.current.setText(
            f"Downloading: "
            f"{media_title(item.data)}"
        )

    # ========================================================
    # PROGRESS
    # ========================================================

    @Slot(
        int,
        str,
        str,
        int,
        object,
    )
    def download_progress(
        self,
        index,
        info,
        filename,
        percentage,
        details,
    ):
        item = self.get_item(
            index
        )

        if not item:
            return

        if item.status != "Downloading":
            return

        if not isinstance(
            details,
            dict,
        ):
            details = {}

        percentage = max(
            0,
            min(
                100,
                safe_int(
                    percentage
                ),
            ),
        )

        downloaded = (
            details.get("downloaded")
            or details.get("downloaded_bytes")
            or "--"
        )

        if isinstance(
            downloaded,
            (int, float),
        ):
            downloaded = format_bytes(
                downloaded
            )

        speed = (
            details.get("speed")
            or "--"
        )

        if isinstance(
            speed,
            (int, float),
        ):
            speed = (
                f"{format_bytes(speed)}/s"
            )

        eta = (
            details.get("eta")
            or "--:--"
        )

        if isinstance(
            eta,
            (int, float),
        ):
            eta = format_eta(
                eta
            )

        stage = (
            details.get("stage")
            or details.get("status")
            or info
            or ""
        )

        stage = str(
            stage
        ).strip()

        # IMPORTANT:
        # The original media title is never replaced.
        item.widget.set_progress(
            percentage,
            downloaded,
            speed,
            eta,
            details=stage if stage else None,
        )
        self.update_overall()

        if info:
            self.log(
                f"[{media_title(item.data)}] "
                f"{info}"
            )

    # ========================================================
    # FINISHED
    # ========================================================

    @Slot(
        int,
        object,
    )
    def download_finished(
        self,
        index,
        result,
    ):
        item = self.get_item(
            index
        )

        if not item:
            return

        if item.status != "Downloading":
            return

        item.status = "Completed"

        item.widget.progress.setValue(
            100
        )

        item.widget.set_status(
            "Completed"
        )

        self.running = max(
            0,
            self.running - 1,
        )

        self.completed += 1

        self.current.setText(
            f"Completed: "
            f"{media_title(item.data)}"
        )

        self.update_overall()

        self.start_more()

    # ========================================================
    # CANCELLED
    # ========================================================

    @Slot(int)
    def download_cancelled(self, index):
        item = self.get_item(index)

        if not item:
            return

        if item.status != "Downloading":
            return

        item.status = "Cancelled"

        item.widget.set_status("Cancelled")

        self.running = max(
            0,
            self.running - 1,
        )

        self.update_overall()

        self.start_more()
        self.check_finished()
    # ========================================================
    # ERROR
    # ========================================================

    @Slot(int, object)
    def download_error(
        self,
        index,
        error,
    ):
        item = self.get_item(index)

        if not item:
            return

        if item.status != "Downloading":
            return

        message = (
            str(error).strip()
            or "Unknown error."
        )

        item.status = "Failed"

        item.widget.set_status("Failed")

        item.widget.set_details(
            f"Error: {message}"
        )

        self.running = max(
            0,
            self.running - 1,
        )

        self.log(
            f"FAILED: "
            f"{media_title(item.data)}: "
            f"{message}"
        )

        self.update_overall()

        self.start_more()
        self.check_finished()

    # ========================================================
    # THREAD CLEANUP
    # ========================================================

    @Slot()
    def download_thread_finished(self):
        thread = self.sender()

        if not isinstance(
            thread,
            QThread,
        ):
            return

        for item in self.queue:
            if item.thread is thread:
                item.thread = None
                item.worker = None
                break

        thread.deleteLater()

    # ========================================================
    # RETRY
    # ========================================================

    @Slot(int)
    def retry_item(
        self,
        index,
    ):
        item = self.get_item(
            index
        )

        if not item:
            return

        if item.status not in (
            "Failed",
            "Cancelled",
        ):
            return

        item.status = "Queued"

        item.widget.progress.setValue(
            0
        )

        item.widget.set_details(
            "Waiting for retry..."
        )

        item.widget.set_status(
            "Queued"
        )

        if not self.downloading:
            self.set_downloading(
                True
            )

        self.update_overall()

        self.start_more()

    # ========================================================
    # CANCEL ONE
    # ========================================================

    @Slot(int)
    def cancel_item(
        self,
        index,
    ):
        item = self.get_item(
            index
        )

        if not item:
            return

        if item.status == "Queued":
            item.status = "Cancelled"

            item.widget.set_status(
                "Cancelled"
            )

            self.update_overall()

            self.check_finished()

            return

        if item.status != "Downloading":
            return

        if item.worker:
            QMetaObject.invokeMethod(
                item.worker,
                "cancel",
                Qt.QueuedConnection,
            )

    # ========================================================
    # CANCEL ALL
    # ========================================================

    @Slot()
    def cancel_all(self):
        if not self.downloading:
            return

        answer = QMessageBox.question(
            self,
            "Cancel Downloads",
            "Cancel all active downloads?",
            QMessageBox.Yes
            | QMessageBox.No,
            QMessageBox.No,
        )

        if answer != QMessageBox.Yes:
            return

        for item in self.queue:
            if item.status == "Queued":
                item.status = "Cancelled"

                item.widget.set_status(
                    "Cancelled"
                )

        for item in self.queue:
            if (
                item.status == "Downloading"
                and item.worker
            ):
                QMetaObject.invokeMethod(
                    item.worker,
                    "cancel",
                    Qt.QueuedConnection,
                )

        self.update_overall()

        self.check_finished()

    # ========================================================
    # OVERALL
    # ========================================================

    def update_overall(self):
        total = len(
            self.queue
        )

        if not total:
            self.overall.setValue(
                0
            )

            self.overall_label.setText(
                "Completed: 0 / 0    Overall: 0%"
            )

            self.queue_count.setText(
                "0 queued / 0 total"
            )

            return

        total_percentage = 0

        for item in self.queue:

            if item.status == "Completed":
                total_percentage += 100

            elif item.status == "Downloading":
                total_percentage += (
                    item.widget.progress.value()
                )

            elif item.status in (
                "Queued",
                "Cancelled",
                "Failed",
            ):
                total_percentage += 0

        percentage = int(
            total_percentage / total
        )

        percentage = max(
            0,
            min(
                100,
                percentage,
            ),
        )

        self.overall.setValue(
            percentage
        )

        self.overall_label.setText(
            f"Completed: "
            f"{self.completed} / {total}"
            f"    Overall: {percentage}%"
        )

        queued = sum(
            item.status == "Queued"
            for item in self.queue
        )

        self.queue_count.setText(
            f"{queued} queued / {total} total"
        )

    # ========================================================
    # FINISHED QUEUE
    # ========================================================

    def check_finished(self):
        if not self.downloading:
            return

        if self.running:
            return

        if any(
            item.status == "Queued"
            for item in self.queue
        ):
            return

        self.set_downloading(
            False
        )

        failed = sum(
            item.status == "Failed"
            for item in self.queue
        )

        cancelled = sum(
            item.status == "Cancelled"
            for item in self.queue
        )

        if failed:
            message = (
                f"Finished with "
                f"{failed} failed item(s)."
            )

        elif cancelled:
            message = (
                f"Finished with "
                f"{cancelled} cancelled item(s)."
            )

        else:
            message = (
                "All downloads completed."
            )

        self.current.setText(
            message
        )

        self.log(
            message
        )

    # ========================================================
    # STATE
    # ========================================================

    def set_downloading(
        self,
        value,
    ):
        self.downloading = bool(
            value
        )

        enabled = not self.downloading

        self.url.setEnabled(
            enabled
        )

        self.fetch.setEnabled(
            enabled
        )

        self.mode.setEnabled(
            enabled
        )

        self.multiple.setEnabled(
            enabled
        )

        self.settings.setEnabled(
            enabled
        )

        self.download.setEnabled(
            enabled
        )

        self.select_queue.setEnabled(
            enabled
        )

        self.clear_selection.setEnabled(
            enabled
        )

        self.clear_queue.setEnabled(
            enabled
        )

        self.cancel.setEnabled(
            self.downloading
        )

    # ========================================================
    # HELPERS
    # ========================================================

    def get_item(
        self,
        index,
    ):
        if 0 <= index < len(
            self.queue
        ):
            return self.queue[index]

        return None

    def log(
        self,
        message,
    ):
        self.log_label.setText(
            str(message)
        )

    def close_selection(self):
        if not self.selection_dialog:
            return

        try:
            self.selection_dialog.close()
            self.selection_dialog.deleteLater()

        except RuntimeError:
            pass

        self.selection_dialog = None

    # ========================================================
    # CLOSE
    # ========================================================

    def closeEvent(
        self,
        event,
    ):
        # ----------------------------------------------------
        # Cancel information worker safely.
        # ----------------------------------------------------

        if (
            self.info_thread
            and self.info_thread.isRunning()
        ):
            if self.info_worker:
                QMetaObject.invokeMethod(
                    self.info_worker,
                    "cancel",
                    Qt.QueuedConnection,
                )

            if not self.info_thread.wait(
                3000
            ):
                event.ignore()
                return

        # ----------------------------------------------------
        # Cancel downloads safely.
        # ----------------------------------------------------

        if self.downloading:
            answer = QMessageBox.question(
                self,
                "Downloads Running",
                "Cancel downloads and close?",
                QMessageBox.Yes
                | QMessageBox.No,
                QMessageBox.No,
            )

            if answer != QMessageBox.Yes:
                event.ignore()
                return

            for item in self.queue:
                if (
                    item.status == "Downloading"
                    and item.worker
                ):
                    QMetaObject.invokeMethod(
                        item.worker,
                        "cancel",
                        Qt.QueuedConnection,
                    )

            for item in self.queue:
                if item.thread:
                    if not item.thread.wait(
                        5000
                    ):
                        event.ignore()
                        return

        self.close_selection()

        event.accept()