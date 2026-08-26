from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from PySide6.QtCore import (
    QObject,
    QThread,
    Qt,
    Signal,
    Slot,
    QMetaObject,
    QSize,
    QItemSelectionModel,
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
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from jobs.media_processor import (
    MediaJobProcessor,
    JobCancelled,
)


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


def safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def media_title(media):
    if not isinstance(media, dict):
        return "Untitled"

    return str(
        media.get("title")
        or media.get("name")
        or media.get("filename")
        or "Untitled"
    )


def media_url(media):
    if not isinstance(media, dict):
        return ""

    return str(
        media.get("webpage_url")
        or media.get("original_url")
        or media.get("url")
        or ""
    )


def format_bytes(value):
    if value in (None, "", "--"):
        return "--"

    try:
        value = float(value)
    except (TypeError, ValueError):
        return "--"

    if value < 0:
        return "--"

    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024:
            if unit == "B":
                return f"{value:.0f} {unit}"

            return f"{value:.1f} {unit}"

        value /= 1024

    return f"{value:.1f} PB"


def format_speed(value):
    if value in (None, "", "--"):
        return "--"

    try:
        value = float(value)
    except (TypeError, ValueError):
        return str(value)

    if value < 0:
        return "--"

    return f"{format_bytes(value)}/s"


def format_eta(value):
    if value in (None, "", "--", "--:--"):
        return "--:--"

    try:
        value = max(0, int(float(value)))
    except (TypeError, ValueError):
        return str(value)

    minutes, seconds = divmod(value, 60)
    hours, minutes = divmod(minutes, 60)

    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    return f"{minutes:02d}:{seconds:02d}"


def normalize_stage(value):
    """Return a stable, lowercase stage key from processor progress text."""
    text = str(value or "").strip().lower()

    if any(token in text for token in (
        "download",
        "downloading",
        "fetching",
    )):
        return "download"

    if any(token in text for token in (
        "merge",
        "merging",
        "remux",
        "remuxing",
        "mux",
        "muxing",
    )):
        return "merge"

    if any(token in text for token in (
        "subtitle",
        "subtitles",
        "embed",
        "embedding",
    )):
        return "subtitle"

    if any(token in text for token in (
        "encode",
        "encoding",
        "convert",
        "converting",
        "transcod",
    )):
        return "encode"

    if any(token in text for token in (
        "final",
        "finish",
        "saving",
        "save",
        "writing",
    )):
        return "finalize"

    return "other"


class QueueListWidget(QListWidget):
    """QListWidget with reliable click/Ctrl/Shift/drag selection."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._selection_anchor = None
        self._dragging_selection = False

    def _index_from_global(self, global_pos):
        return self.indexAt(
            self.viewport().mapFromGlobal(global_pos)
        )

    def _select_range(self, first_row, last_row, clear=True):
        if self.count() == 0:
            return

        first_row = max(0, min(self.count() - 1, first_row))
        last_row = max(0, min(self.count() - 1, last_row))

        top = min(first_row, last_row)
        bottom = max(first_row, last_row)

        model = self.model()
        selection_model = self.selectionModel()

        if clear:
            selection_model.clearSelection()

        for row in range(top, bottom + 1):
            selection_model.select(
                model.index(row, 0),
                QItemSelectionModel.Select,
            )

        selection_model.setCurrentIndex(
            model.index(last_row, 0),
            QItemSelectionModel.NoUpdate,
        )
        self.setCurrentRow(last_row)

    def select_from_global(self, global_pos, modifiers=Qt.NoModifier):
        index = self._index_from_global(global_pos)
        if not index.isValid():
            return False

        row = index.row()
        shift = bool(modifiers & Qt.ShiftModifier)
        ctrl = bool(modifiers & Qt.ControlModifier)

        if shift and self._selection_anchor is not None:
            self._select_range(
                self._selection_anchor,
                row,
                clear=True,
            )
        elif ctrl:
            self.selectionModel().select(
                index,
                QItemSelectionModel.Toggle,
            )
            self.setCurrentIndex(index)
        else:
            self.selectionModel().clearSelection()
            self.selectionModel().select(
                index,
                QItemSelectionModel.Select,
            )
            self.setCurrentIndex(index)
            self._selection_anchor = row

        if not shift:
            self._selection_anchor = row

        self._dragging_selection = True
        return True

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self.select_from_global(
                event.globalPosition().toPoint(),
                event.modifiers(),
            ):
                event.accept()
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (
            self._dragging_selection
            and event.buttons() & Qt.LeftButton
            and self._selection_anchor is not None
        ):
            index = self._index_from_global(
                event.globalPosition().toPoint()
            )
            if index.isValid():
                self._select_range(
                    self._selection_anchor,
                    index.row(),
                    clear=True,
                )
                event.accept()
                return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._dragging_selection = False
        super().mouseReleaseEvent(event)

    def clearSelection(self):
        super().clearSelection()
        self._selection_anchor = None
        self._dragging_selection = False


def set_combo_data(combo, value):
    index = combo.findData(value)

    if index >= 0:
        combo.setCurrentIndex(index)


DEFAULT_OUTPUT = os.path.join(
    os.path.expanduser("~"),
    "Downloads",
    "Videos",
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
        float,
        object,
    )

    finished = Signal(int, object)
    error = Signal(int, object)
    cancelled = Signal(int)

    def __init__(self, index, settings):
        super().__init__()

        self.index = index
        self.settings = dict(settings)
        self.processor: Optional[MediaJobProcessor] = None

    # --------------------------------------------------------
    # RUN
    # --------------------------------------------------------

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
                self.cancelled.emit(
                    self.index
                )
                return

            self.finished.emit(
                self.index,
                result,
            )

        except JobCancelled:
            self.cancelled.emit(
                self.index
            )

        except Exception as exc:
            self.error.emit(
                self.index,
                exc,
            )

    # --------------------------------------------------------
    # CANCEL
    # --------------------------------------------------------

    @Slot()
    def cancel(self):
        processor = self.processor

        if processor is None:
            return

        try:
            processor.cancel()
        except Exception:
            pass

    # --------------------------------------------------------
    # PROGRESS
    #
    # IMPORTANT:
    #
    # This matches the callback used by test.py:
    #
    # progress_callback(
    #     info,
    #     filename,
    #     percentage,
    #     downloaded,
    #     speed,
    #     eta,
    #     **kwargs,
    # )
    #
    # We additionally support the old:
    #
    # progress_callback(
    #     info,
    #     filename,
    #     percentage,
    #     details,
    # )
    #
    # so this worker is tolerant of either MediaJobProcessor
    # callback implementation.
    # --------------------------------------------------------

    def on_progress(
        self,
        info,
        filename,
        percentage,
        downloaded=None,
        speed=None,
        eta=None,
        **kwargs,
    ):
        details: Dict[str, Any] = {}

        # ----------------------------------------------------
        # NEW CALLBACK FORMAT
        # ----------------------------------------------------

        if isinstance(
            downloaded,
            dict,
        ):
            # Old callback format:
            #
            # info, filename, percentage, details
            #
            details.update(downloaded)

            downloaded = (
                details.get("downloaded")
                or details.get("downloaded_bytes")
                or details.get("bytes_downloaded")
            )

            speed = (
                details.get("speed")
                or details.get("speed_bytes")
            )

            eta = details.get("eta")

        # ----------------------------------------------------
        # EXTRA DETAILS
        # ----------------------------------------------------

        if kwargs:
            details.update(kwargs)

        # ----------------------------------------------------
        # STANDARDIZE VALUES
        # ----------------------------------------------------

        try:
            percentage = float(
                percentage
            )
        except (
            TypeError,
            ValueError,
        ):
            percentage = 0.0

        percentage = max(
            0.0,
            min(
                100.0,
                percentage,
            ),
        )

        if downloaded is not None:
            details["downloaded"] = downloaded

        if speed is not None:
            details["speed"] = speed

        if eta is not None:
            details["eta"] = eta

        # ----------------------------------------------------
        # STAGE
        # ----------------------------------------------------

        stage = (
            details.get("stage")
            or details.get("status")
            or details.get("message")
            or info
            or ""
        )

        details["stage"] = str(
            stage or ""
        ).strip()

        # ----------------------------------------------------
        # EMIT TO GUI
        # ----------------------------------------------------

        self.progress.emit(
            self.index,
            str(info or ""),
            str(filename or ""),
            percentage,
            details,
        )

    # --------------------------------------------------------
    # ERROR
    # --------------------------------------------------------

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
        self._last_selected_rows = set()
        self.download_mode = download_mode

        self.setWindowTitle("Select Media")
        self.resize(900, 650)

        self.build_ui()

        if media_items:
            self.set_media_items(
                media_items
            )
        else:
            self.set_loading(True)

    # ========================================================
    # UI
    # ========================================================

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
        self.list.setDragEnabled(False)
        self.list.setDragDropMode(
            QAbstractItemView.NoDragDrop
        )
        self.list.setDefaultDropAction(
            Qt.IgnoreAction
        )
        self.list.setSelectionRectVisible(True)

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

        self.list.itemSelectionChanged.connect(
            self.sync_row_selection_to_checks
        )

        self.buttons.accepted.connect(
            self.accept_selection
        )

        self.buttons.rejected.connect(
            self.reject
        )

    # ========================================================
    # SETTINGS
    # ========================================================

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

        self.subtitle_output = QComboBox()

        self.subtitle_output.addItem(
            "Save subtitle separately",
            "separate",
        )

        self.subtitle_output.addItem(
            "Embed subtitles",
            "embed",
        )

        self.subtitle_output.addItem(
            "Don't save subtitles",
            "none",
        )

        set_combo_data(
            self.subtitle_output,
            "separate",
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
                QLabel("Output"),
                row,
                2,
            )

            self.settings_grid.addWidget(
                self.subtitle_output,
                row,
                3,
            )

            row += 1

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

    # ========================================================
    # LOADING
    # ========================================================

    def set_loading(self, value):
        self.loading.setVisible(value)
        self.list.setVisible(not value)
        self.settings_group.setVisible(not value)
        self.buttons.setEnabled(not value)

    # ========================================================
    # MEDIA
    # ========================================================

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

        self.list.clearSelection()
        self._last_selected_rows.clear()

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

    # ========================================================
    # SELECTION
    # ========================================================

    def select_all(self):
        self.set_all(Qt.Checked)
        self.list.selectAll()

    def deselect_all(self):
        self.set_all(Qt.Unchecked)
        self.list.clearSelection()

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

    def sync_row_selection_to_checks(self):
        """Synchronize row selection gestures with the existing check state."""
        current_rows = {
            self.list.row(item)
            for item in self.list.selectedItems()
        }

        # If there was an actual previous user selection, rows removed from
        # it were deselected with Ctrl-click or by replacing the selection.
        # Keep the checkbox state in sync with that action.
        removed_rows = self._last_selected_rows - current_rows
        added_rows = current_rows - self._last_selected_rows

        self.list.blockSignals(True)
        try:
            for row in removed_rows:
                item = self.list.item(row)
                if item is not None:
                    item.setCheckState(Qt.Unchecked)

            for row in added_rows:
                item = self.list.item(row)
                if item is not None:
                    item.setCheckState(Qt.Checked)
        finally:
            self.list.blockSignals(False)

        self._last_selected_rows = current_rows
        self.update_count()

    # ========================================================
    # OUTPUT
    # ========================================================

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

        subtitle_output = (
            self.subtitle_output.currentData()
            if subtitles
            else "none"
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

            "save_separate_subtitle": bool(
                subtitles
                and subtitle_output == "separate"
            ),

            "embed_subtitles": bool(
                subtitles
                and subtitle_output == "embed"
            ),

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
                selected.append(
                    dict(media)
                )

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

        self.setFixedHeight(
            QUEUE_ITEM_HEIGHT
        )

        self.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Fixed,
        )

        self.setMouseTracking(True)

        self.setStyleSheet(
            """
            DownloadQueueItemWidget {
                background: transparent;
                border: 1px solid transparent;
                border-radius: 6px;
            }

            DownloadQueueItemWidget[selected="true"] {
                background: rgba(59, 130, 246, 0.12);
                border: 1px solid rgba(59, 130, 246, 0.35);
            }
            """
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

        layout.addLayout(
            top
        )

        # ----------------------------------------------------
        # PROGRESS
        # ----------------------------------------------------

        self.progress = QProgressBar()

        self.progress.setRange(
            0,
            100,
        )

        self.progress.setValue(
            0
        )

        self.progress.setTextVisible(
            True
        )

        self.progress.setFixedHeight(
            18
        )

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

        self.details.setWordWrap(
            False
        )

        self.details.setMinimumHeight(
            18
        )

        self.details.setMaximumHeight(
            18
        )

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
        # MOUSE BEHAVIOUR
        # ----------------------------------------------------

        self.title.setAttribute(
            Qt.WA_TransparentForMouseEvents,
            True,
        )

        self.progress.setAttribute(
            Qt.WA_TransparentForMouseEvents,
            True,
        )

        self.details.setAttribute(
            Qt.WA_TransparentForMouseEvents,
            True,
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

    # ========================================================
    # QUEUE LIST
    # ========================================================

    def _queue_list(self):
        parent = self.parentWidget()

        while parent is not None:
            if isinstance(
                parent,
                QListWidget,
            ):
                return parent

            parent = parent.parentWidget()

        return None

    # ========================================================
    # MOUSE
    # ========================================================

    def mousePressEvent(
        self,
        event,
    ):
        if event.button() == Qt.LeftButton:

            queue_list = self._queue_list()

            if queue_list is not None:

                if queue_list.select_from_global(
                    event.globalPosition().toPoint(),
                    event.modifiers(),
                ):
                    event.accept()
                    return

        super().mousePressEvent(
            event
        )

    def mouseMoveEvent(
        self,
        event,
    ):
        queue_list = self._queue_list()

        if (
            queue_list is not None
            and (
                event.buttons()
                & Qt.LeftButton
            )
            and queue_list._selection_anchor
            is not None
        ):

            index = queue_list._index_from_global(
                event.globalPosition().toPoint()
            )

            if index.isValid():

                queue_list._select_range(
                    queue_list._selection_anchor,
                    index.row(),
                    clear=True,
                )

                event.accept()
                return

        super().mouseMoveEvent(
            event
        )

    # ========================================================
    # SIZE
    # ========================================================

    def sizeHint(self):
        return QSize(
            0,
            QUEUE_ITEM_HEIGHT,
        )

    def minimumSizeHint(self):
        return QSize(
            0,
            QUEUE_ITEM_HEIGHT,
        )

    # ========================================================
    # SELECTION
    # ========================================================

    def set_selected(
        self,
        selected,
    ):
        self.setProperty(
            "selected",
            bool(selected),
        )

        self.style().unpolish(
            self
        )

        self.style().polish(
            self
        )

        self.update()

    # ========================================================
    # STATUS
    # ========================================================

    def set_status(
        self,
        status,
    ):
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

            self.set_details(
                "Starting download..."
            )

        elif status == "Cancelling...":

            self.set_details(
                "Cancelling download..."
            )

            self.cancel.setVisible(
                False
            )

            self.retry.setVisible(
                False
            )

        elif status == "Completed":

            self.set_details(
                "Download completed."
            )

            self.cancel.setVisible(
                False
            )

            self.retry.setVisible(
                False
            )

        elif status == "Failed":

            self.cancel.setVisible(
                False
            )

            self.retry.setVisible(
                True
            )

        elif status == "Cancelled":

            self.cancel.setVisible(
                False
            )

            self.retry.setVisible(
                True
            )

            self.set_details(
                "Download cancelled."
            )

    # ========================================================
    # DETAILS
    # ========================================================

    def set_details(
        self,
        text,
    ):
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

    # ========================================================
    # PROGRESS
    # ========================================================

    def set_progress(
        self,
        percentage,
        downloaded="--",
        speed="--",
        eta="--:--",
        details=None,
        filename=None,
    ):
        percentage = max(
            0.0,
            min(
                100.0,
                safe_float(
                    percentage,
                    0.0,
                ),
            ),
        )

        self.progress.setValue(
            round(percentage)
        )

        parts = []

        if details:
            parts.append(
                str(details)
            )

        parts.append(
            f"{percentage:.2f}%"
        )

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
                f"ETA: {eta}"
            )

        if filename:
            parts.append(
                str(filename)
            )

        self.set_details(
            "  •  ".join(parts)
        )

# ============================================================
# QUEUE DATA
# ============================================================

@dataclass
class QueueItem:
    data: dict
    widget: DownloadQueueItemWidget
    status: str = "Queued"
    progress: float = 0.0
    stage: str = ""
    thread: QThread | None = None
    worker: MediaDownloadWorker | None = None


# ============================================================
# MAIN PAGE
# ============================================================

class VideoDownloadPage(QWidget):

    download_requested = Signal(dict)
    cancel_requested = Signal()

    def __init__(
        self,
        parent=None,
    ):
        super().__init__(
            parent
        )

        self.downloading = False
        self.cancel_requested = False

        self.info_thread: Optional[QThread] = None
        self.info_worker: Optional[MediaInfoWorker] = None
        self.info_processor: Optional[MediaJobProcessor] = None

        self.selection_dialog = None

        self.queue: List[QueueItem] = []

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

        root = QVBoxLayout(
            self
        )

        root.setContentsMargins(
            8,
            8,
            8,
            8,
        )

        root.setSpacing(
            6
        )

        # ====================================================
        # TOP
        # ====================================================

        top = QWidget()

        top.setFixedHeight(
            60
        )

        top_layout = QHBoxLayout(
            top
        )

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

        # ====================================================
        # URL
        # ====================================================

        self.url = QLineEdit()

        self.url.setPlaceholderText(
            "Paste video or playlist URL here..."
        )

        self.url.setMinimumHeight(
            36
        )

        self.url.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Fixed,
        )

        self.url.setStyleSheet(
            """
            QLineEdit {
                border: 2px solid #3b82f6;
                border-radius: 7px;
                padding: 6px 10px;
                background: palette(base);
                color: palette(text);
                font-size: 14px;
            }

            QLineEdit:hover {
                border: 2px solid #60a5fa;
            }

            QLineEdit:focus {
                border: 2px solid #2563eb;
                background: palette(base);
            }

            QLineEdit:disabled {
                border: 2px solid #9ca3af;
            }
            """
        )

        # Press Enter = Fetch.
        self.url.returnPressed.connect(
            self._fetch_from_enter
        )

        top_layout.addWidget(
            self.url,
            1,
        )

        # ====================================================
        # MULTIPLE
        # ====================================================

        self.multiple = QCheckBox(
            "Multiple URLs"
        )

        top_layout.addWidget(
            self.multiple
        )

        # ====================================================
        # FETCH
        # ====================================================

        self.fetch = QPushButton(
            "Fetch"
        )

        top_layout.addWidget(
            self.fetch
        )

        root.addWidget(
            top
        )

        # ====================================================
        # MIDDLE
        # ====================================================

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

        self.overall.setValue(
            0
        )

        self.overall.setFixedHeight(
            18
        )

        middle_layout.addWidget(
            self.overall
        )

        self.overall_label = QLabel(
            "Completed: 0 / 0    Overall: 0%"
        )

        middle_layout.addWidget(
            self.overall_label
        )

        # ====================================================
        # QUEUE CONTROLS
        # ====================================================

        controls = QHBoxLayout()

        self.select_queue = QPushButton(
            "Select All"
        )

        self.clear_selection = QPushButton(
            "Remove Selected"
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

        # ====================================================
        # QUEUE LIST
        # ====================================================

        self.queue_list = QueueListWidget()

        self.queue_list.setSelectionMode(
            QAbstractItemView.ExtendedSelection
        )

        self.queue_list.setAlternatingRowColors(
            True
        )

        self.queue_list.setUniformItemSizes(
            True
        )

        self.queue_list.setSizeAdjustPolicy(
            QAbstractItemView.SizeAdjustPolicy.AdjustIgnored
        )

        self.queue_list.setVerticalScrollBarPolicy(
            Qt.ScrollBarAsNeeded
        )

        self.queue_list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff
        )

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

        # ====================================================
        # BOTTOM
        # ====================================================

        bottom = QWidget()

        bottom.setFixedHeight(
            60
        )

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

        self.cancel.setEnabled(
            False
        )

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

        # ====================================================
        # SIGNALS
        # ====================================================

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

        # Keep Select All as a normal Select All operation.
        self.select_queue.clicked.connect(
            self.queue_list.selectAll
        )

        self.clear_selection.clicked.connect(
            self.clear_queue_selection
        )

        self.clear_queue.clicked.connect(
            self.clear_queue_items
        )

        self.queue_list.itemSelectionChanged.connect(
            self.update_queue_widget_selection
        )

    # ========================================================
    # ENTER -> FETCH
    # ========================================================

    @Slot()
    def _fetch_from_enter(self):

        if self.downloading:
            return

        self.fetch_information()

    # ========================================================
    # SELECTION VISUALS
    # ========================================================

    def update_queue_widget_selection(self):

        selected_rows = {
            self.queue_list.row(item)
            for item in self.queue_list.selectedItems()
        }

        for row, queue_item in enumerate(
            self.queue
        ):

            queue_item.widget.set_selected(
                row in selected_rows
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

            self.url.setFocus()

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

            self.info_error(
                exc
            )

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

    # ========================================================
    # INFO FINISHED
    # ========================================================

    @Slot(object)
    def info_finished(
        self,
        result,
    ):

        if not isinstance(
            result,
            dict,
        ):

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

            items = [
                items
            ]

        if not items:
            items = [
                result
            ]

        normalized = []

        for item in items:

            if not isinstance(
                item,
                dict,
            ):
                continue

            item = dict(
                item
            )

            if not item.get(
                "url"
            ):

                item["url"] = (
                    item.get(
                        "webpage_url"
                    )
                    or item.get(
                        "original_url"
                    )
                    or ""
                )

            if item.get(
                "url"
            ):

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

    # ========================================================
    # INFO CANCELLED
    # ========================================================

    @Slot()
    def info_cancelled(self):

        self.current.setText(
            "Information fetch cancelled."
        )

    # ========================================================
    # INFO ERROR
    # ========================================================

    @Slot(object)
    def info_error(
        self,
        error,
    ):

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

    # ========================================================
    # INFO THREAD CLEANUP
    # ========================================================

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
    def add_selected(
        self,
        selected,
    ):

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

        self.update_queue_widget_selection()

    # ========================================================
    # ADD QUEUE ITEM
    # ========================================================

    def add_queue_item(
        self,
        data,
    ):

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

    # ========================================================
    # REMOVE SELECTED
    # ========================================================

    def clear_queue_selection(self):

        if self.downloading:
            return

        selected_items = (
            self.queue_list.selectedItems()
        )

        if not selected_items:
            return

        # Work backwards so removing one row
        # does not invalidate the rows above it.
        rows = sorted(
            (
                self.queue_list.row(item)
                for item in selected_items
            ),
            reverse=True,
        )

        for row in rows:

            if not (
                0 <= row < len(self.queue)
            ):
                continue

            # Remove data item.
            self.queue.pop(
                row
            )

            # Remove QListWidgetItem.
            list_item = (
                self.queue_list.takeItem(
                    row
                )
            )

            if list_item is not None:
                del list_item

        # Re-number widgets because their indexes
        # are used by download worker signals.
        for index, queue_item in enumerate(
            self.queue
        ):

            queue_item.widget.index = index

        self.queue_list.clearSelection()

        self.update_queue_widget_selection()

        self.update_queue_count()

        self.update_overall()

        if not self.queue:

            self.current.setText(
                "Ready."
            )

            self.log(
                "Queue cleared."
            )

    # ========================================================
    # CLEAR ENTIRE QUEUE
    # ========================================================

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

        self.current.setText(
            "Ready."
        )

        self.log(
            "Queue cleared."
        )

    # ========================================================
    # QUEUE COUNT
    # ========================================================

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

        self.cancel_requested = False

        # Reset failed/cancelled items for another run.
        for item in self.queue:

            if item.status in (
                "Completed",
                "Failed",
                "Cancelled",
            ):

                item.status = "Queued"
                item.progress = 0.0
                item.stage = ""

                item.widget.progress.setValue(
                    0
                )

                item.widget.set_status(
                    "Queued"
                )

        self.running = 0

        self.completed = sum(
            item.status == "Completed"
            for item in self.queue
        )

        self.set_downloading(
            True
        )

        self.log(
            "Starting download queue..."
        )

        self.start_more()

    # ========================================================
    # START MORE
    # ========================================================

    def start_more(self):

        if self.cancel_requested:

            self.check_finished()

            return

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

    def start_item(
        self,
        item,
    ):

        index = item.widget.index

        item.status = "Downloading"
        item.progress = 0.0
        item.stage = ""

        item.widget.progress.setValue(
            0
        )

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

        self.update_overall()

    # ========================================================
    # PROGRESS
    # ========================================================

    @Slot(
        int,
        str,
        str,
        float,
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
        item = self.get_item(index)

        if not item:
            return

        if item.status not in (
            "Downloading",
            "Cancelling...",
        ):
            return

        if not isinstance(details, dict):
            details = {}

        # --------------------------------------------------------
        # REAL DOWNLOAD PERCENTAGE
        # --------------------------------------------------------

        percentage = safe_float(
            percentage,
            0.0,
        )

        percentage = max(
            0.0,
            min(
                100.0,
                percentage,
            ),
        )

        item.progress = percentage

        # --------------------------------------------------------
        # STAGE
        # --------------------------------------------------------

        stage = (
            details.get("stage")
            or details.get("status")
            or details.get("message")
            or info
            or ""
        )

        stage = str(stage).strip()
        item.stage = stage

        # --------------------------------------------------------
        # DOWNLOADED
        # --------------------------------------------------------

        downloaded = (
            details.get("downloaded")
            or details.get("downloaded_bytes")
            or details.get("bytes_downloaded")
            or "--"
        )

        if isinstance(downloaded, (int, float)):
            downloaded = format_bytes(downloaded)

        # --------------------------------------------------------
        # SPEED
        # --------------------------------------------------------

        speed = (
            details.get("speed")
            or details.get("speed_bytes")
            or details.get("download_speed")
            or "--"
        )

        if isinstance(speed, (int, float)):
            speed = format_speed(speed)

        # --------------------------------------------------------
        # ETA
        # --------------------------------------------------------

        eta = (
            details.get("eta")
            or details.get("ETA")
            or "--:--"
        )

        if isinstance(eta, (int, float)):
            eta = format_eta(eta)

        # --------------------------------------------------------
        # FILENAME
        # --------------------------------------------------------

        filename = str(
            filename or ""
        ).strip()

        # --------------------------------------------------------
        # UPDATE WIDGET
        # --------------------------------------------------------

        item.widget.set_progress(
            percentage=percentage,
            downloaded=downloaded,
            speed=speed,
            eta=eta,
            details=stage if stage else None,
            filename=filename if filename else None,
        )

        # --------------------------------------------------------
        # CURRENT
        # --------------------------------------------------------

        title = media_title(
            item.data
        )

        if stage:
            self.current.setText(
                f"{stage}: {title}"
            )
        else:
            self.current.setText(
                f"Downloading: {title}"
            )

        # --------------------------------------------------------
        # LOG
        # --------------------------------------------------------

        log_parts = [
            f"{percentage:.2f}%",
        ]

        if downloaded not in (
            None,
            "",
            "--",
        ):
            log_parts.append(
                str(downloaded)
            )

        if speed not in (
            None,
            "",
            "--",
        ):
            log_parts.append(
                str(speed)
            )

        if eta not in (
            None,
            "",
            "--:--",
        ):
            log_parts.append(
                f"ETA {eta}"
            )

        self.log(
            f"[{title}] "
            + " | ".join(log_parts)
        )

        self.update_overall()

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

        item.progress = 100.0

        item.stage = "Completed"

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

        self.completed = sum(
            x.status == "Completed"
            for x in self.queue
        )

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
    def download_cancelled(
        self,
        index,
    ):

        item = self.get_item(
            index
        )

        if not item:
            return

        if item.status not in (
            "Downloading",
            "Cancelling...",
        ):
            return

        item.status = "Cancelled"

        item.widget.set_status(
            "Cancelled"
        )

        self.running = max(
            0,
            self.running - 1,
        )

        self.update_overall()

        if not self.cancel_requested:
            self.start_more()

        self.check_finished()

    # ========================================================
    # ERROR
    # ========================================================

    @Slot(
        int,
        object,
    )
    def download_error(
        self,
        index,
        error,
    ):

        item = self.get_item(
            index
        )

        if not item:
            return

        if item.status != "Downloading":
            return

        message = (
            str(error).strip()
            or "Unknown error."
        )

        item.status = "Failed"

        item.widget.set_status(
            "Failed"
        )

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

        if not self.cancel_requested:
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

        item.progress = 0.0
        item.stage = ""

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

            self.cancel_requested = False

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

        # ----------------------------------------------------
        # QUEUED
        # ----------------------------------------------------

        if item.status == "Queued":

            item.status = "Cancelled"

            item.widget.set_status(
                "Cancelled"
            )

            self.update_overall()

            self.check_finished()

            return

        # ----------------------------------------------------
        # NOT ACTIVE
        # ----------------------------------------------------

        if item.status != "Downloading":
            return

        # ----------------------------------------------------
        # ACTIVE
        # ----------------------------------------------------

        if item.worker:

            item.status = "Cancelling..."

            item.widget.set_status(
                "Cancelling..."
            )

            self.current.setText(
                f"Cancelling: "
                f"{media_title(item.data)}"
            )

            self.log(
                f"Cancelling: "
                f"{media_title(item.data)}"
            )

            try:

                item.worker.cancel()

            except Exception:
                pass

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

        self.cancel_requested = True

        # ----------------------------------------------------
        # Cancel queued
        # ----------------------------------------------------

        for item in self.queue:

            if item.status == "Queued":

                item.status = "Cancelled"

                item.widget.set_status(
                    "Cancelled"
                )

        # ----------------------------------------------------
        # Cancel active
        # ----------------------------------------------------

        for item in self.queue:

            if (
                item.status == "Downloading"
                and item.worker
            ):

                item.status = "Cancelling..."

                item.widget.set_status(
                    "Cancelling..."
                )

                try:

                    item.worker.cancel()

                except Exception:
                    pass

        self.current.setText(
            "Cancelling downloads..."
        )

        self.log(
            "Cancelling all downloads..."
        )

        self.update_overall()

        # Do not start another queued item.
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

        total_percentage = 0.0

        for item in self.queue:

            if item.status == "Completed":

                total_percentage += 100.0

            elif item.status in (
                "Downloading",
                "Cancelling...",
            ):

                total_percentage += max(
                    0.0,
                    min(
                        100.0,
                        float(
                            item.progress
                        ),
                    ),
                )

            # Failed / Cancelled / Queued
            # contribute their current progress.
            #
            # Normally these are 0, but retaining the
            # current value makes the overall bar accurate
            # if cancellation happens mid-download.
            elif item.status in (
                "Failed",
                "Cancelled",
            ):

                total_percentage += max(
                    0.0,
                    min(
                        100.0,
                        float(
                            item.progress
                        ),
                    ),
                )

        percentage = (
            total_percentage / total
        )

        percentage = max(
            0.0,
            min(
                100.0,
                percentage,
            ),
        )

        self.overall.setValue(
            round(percentage)
        )

        completed = sum(
            item.status == "Completed"
            for item in self.queue
        )

        self.completed = completed

        self.overall_label.setText(
            f"Completed: "
            f"{completed} / {total}"
            f"    Overall: "
            f"{percentage:.2f}%"
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

        if self.cancel_requested:

            message = (
                "Downloads cancelled."
            )

        elif failed:

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

        self.cancel_requested = False

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
                    item.status
                    in (
                        "Downloading",
                        "Cancelling...",
                    )
                    and item.worker
                ):

                    try:

                        item.worker.cancel()

                    except Exception:
                        pass

            for item in self.queue:

                if item.thread:

                    if not item.thread.wait(
                        5000
                    ):

                        event.ignore()

                        return

        self.close_selection()

        event.accept()

