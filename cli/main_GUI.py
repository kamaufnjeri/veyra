from __future__ import annotations

import os
import sys
import time
import traceback
from typing import Any, List, Optional

from PySide6.QtCore import (
    QObject,
    QThread,
    Qt,
    Signal,
    Slot,
    QEventLoop,
)
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from jobs.processor import JobProcessor


# ==============================================================
# LANGUAGES
# ==============================================================

LANGUAGES = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "ru": "Russian",
    "uk": "Ukrainian",
    "pl": "Polish",
    "nl": "Dutch",
    "sv": "Swedish",
    "da": "Danish",
    "no": "Norwegian",
    "fi": "Finnish",
    "cs": "Czech",
    "sk": "Slovak",
    "ro": "Romanian",
    "hu": "Hungarian",
    "tr": "Turkish",
    "ar": "Arabic",
    "he": "Hebrew",
    "fa": "Persian",
    "hi": "Hindi",
    "bn": "Bengali",
    "id": "Indonesian",
    "ms": "Malay",
    "vi": "Vietnamese",
    "th": "Thai",
    "ja": "Japanese",
    "ko": "Korean",
    "zh": "Chinese",
    "sw": "Swahili",
}


# ==============================================================
# WORKER
# ==============================================================

class ProcessingWorker(QObject):
    """Runs JobProcessor in a background QThread."""

    progress = Signal(str, str, int)
    error = Signal(str)
    finished = Signal(list)
    cancelled = Signal()

    overwrite_requested = Signal(str, str)

    translation_requested = Signal(
        str,
        str,
        str,
        str,
    )

    overwrite_answer = Signal(bool)
    translation_answer = Signal(bool)

    def __init__(
        self,
        files: List[str],
        source_language: str,
        target_language: Optional[str],
        subtitle_format: str,
        overwrite_mode: str,
        translation_mode: str,
    ):
        super().__init__()

        self.files = files
        self.source_language = source_language
        self.target_language = target_language
        self.subtitle_format = subtitle_format

        self.overwrite_mode = overwrite_mode
        self.translation_mode = translation_mode

        self.processor: Optional[JobProcessor] = None

        self._cancel_requested = False

    # ==========================================================
    # CANCEL
    # ==========================================================

    @Slot()
    def request_cancel(self) -> None:
        self._cancel_requested = True

        if self.processor is not None:
            try:
                self.processor.cancel()
            except Exception:
                pass

    # ==========================================================
    # ASK OVERWRITE
    # ==========================================================

    def ask_overwrite(
        self,
        filepath: str,
        subtitle_type: str = "subtitle",
    ) -> bool:

        if self._cancel_requested:
            return False

        loop = QEventLoop()

        result = {
            "value": False,
        }

        def receive_answer(
            value: bool,
        ) -> None:
            result["value"] = bool(value)
            loop.quit()

        self.overwrite_answer.connect(
            receive_answer,
            Qt.QueuedConnection,
        )

        self.overwrite_requested.emit(
            filepath,
            subtitle_type,
        )

        loop.exec()

        try:
            self.overwrite_answer.disconnect(
                receive_answer
            )
        except (RuntimeError, TypeError):
            pass

        return result["value"]

    # ==========================================================
    # ASK TRANSLATION
    # ==========================================================

    def ask_translation(
        self,
        source_language: str,
        target_language: str,
        source_subtitle: str,
        translated_subtitle: str,
    ) -> bool:

        if self._cancel_requested:
            return False

        loop = QEventLoop()

        result = {
            "value": False,
        }

        def receive_answer(
            value: bool,
        ) -> None:
            result["value"] = bool(value)
            loop.quit()

        self.translation_answer.connect(
            receive_answer,
            Qt.QueuedConnection,
        )

        self.translation_requested.emit(
            source_language,
            target_language,
            source_subtitle,
            translated_subtitle,
        )

        loop.exec()

        try:
            self.translation_answer.disconnect(
                receive_answer
            )
        except (RuntimeError, TypeError):
            pass

        return result["value"]

    # ==========================================================
    # RUN
    # ==========================================================

    @Slot()
    def run(self) -> None:
        try:
            self.processor = JobProcessor(
                source_language=self.source_language,
                target_language=self.target_language,
                subtitle_format=self.subtitle_format,
                progress_callback=self._progress_callback,
                error_callback=self._error_callback,
                overwrite_callback=self.ask_overwrite,
                translate_callback=self.ask_translation,
                overwrite_mode=self.overwrite_mode,
                translation_mode=self.translation_mode,
            )

            if self._cancel_requested:
                self.cancelled.emit()
                return

            results = self.processor.process_files(
                self.files
            )

            if self._cancel_requested:
                self.cancelled.emit()
                return

            if self.processor.cancelled:
                self.cancelled.emit()
                return

            self.finished.emit(results)

        except Exception as exc:
            if (
                self._cancel_requested
                or (
                    self.processor is not None
                    and self.processor.cancelled
                )
            ):
                self.cancelled.emit()
                return

            self.error.emit(
                f"{exc}\n\n"
                f"{traceback.format_exc()}"
            )

    # ==========================================================
    # PROGRESS
    # ==========================================================

    def _progress_callback(
        self,
        info: Any,
        filename: Any,
        percentage: Any,
        *_,
    ) -> None:

        try:
            percentage = int(percentage)
        except (TypeError, ValueError):
            percentage = 0

        percentage = max(
            0,
            min(100, percentage),
        )

        self.progress.emit(
            str(info),
            str(filename),
            percentage,
        )

    # ==========================================================
    # ERROR
    # ==========================================================

    def _error_callback(
        self,
        error: Any,
    ) -> None:

        if not self._cancel_requested:
            self.error.emit(str(error))


# ==============================================================
# MAIN WINDOW
# ==============================================================

class VeyraWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        self.worker: Optional[ProcessingWorker] = None
        self.thread: Optional[QThread] = None

        self.processing = False

        self._close_after_cancel = False

        # ======================================================
        # ETA / TIMING STATE
        # ======================================================

        self.processing_start_time: Optional[float] = None

        self.total_files = 0
        self.current_file_number = 0
        self.current_file_percentage = 0

        self.last_overall_percentage = 0

        self.setWindowTitle(
            "Veyra Subtitle Generator"
        )

        self.resize(
            1050,
            750,
        )

        self._build_ui()

    # ==========================================================
    # UI
    # ==========================================================

    def _build_ui(self) -> None:

        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)

        # ======================================================
        # LANGUAGE
        # ======================================================

        language_group = QGroupBox(
            "Language Settings"
        )

        language_layout = QHBoxLayout(
            language_group
        )

        language_layout.addWidget(
            QLabel("Source language:")
        )

        self.source_combo = QComboBox()

        self._populate_language_combo(
            self.source_combo,
            include_none=False,
        )

        self.source_combo.setCurrentIndex(
            self.source_combo.findData("es")
        )

        language_layout.addWidget(
            self.source_combo,
            1,
        )

        language_layout.addSpacing(20)

        language_layout.addWidget(
            QLabel("Target language:")
        )

        self.target_combo = QComboBox()

        self._populate_language_combo(
            self.target_combo,
            include_none=True,
        )

        self.target_combo.setCurrentIndex(
            self.target_combo.findData("en")
        )

        language_layout.addWidget(
            self.target_combo,
            1,
        )

        main_layout.addWidget(
            language_group
        )

        # ======================================================
        # TRANSLATION MODE
        # ======================================================

        translation_layout = QHBoxLayout()

        translation_layout.addWidget(
            QLabel("Translation:")
        )

        self.translation_mode_combo = QComboBox()

        self.translation_mode_combo.addItem(
            "Always translate",
            "translate",
        )

        self.translation_mode_combo.addItem(
            "Ask when needed",
            "ask",
        )

        self.translation_mode_combo.addItem(
            "Never translate",
            "skip",
        )

        translation_layout.addWidget(
            self.translation_mode_combo,
            1,
        )

        translation_layout.addStretch()

        main_layout.addLayout(
            translation_layout
        )

        # ======================================================
        # FORMAT
        # ======================================================

        format_layout = QHBoxLayout()

        format_layout.addWidget(
            QLabel("Subtitle format:")
        )

        self.format_combo = QComboBox()

        self.format_combo.addItems(
            [
                "SRT",
                "VTT",
                "JSON",
                "RAW",
            ]
        )

        self.format_combo.setCurrentText("SRT")

        format_layout.addWidget(
            self.format_combo
        )

        format_layout.addStretch()

        main_layout.addLayout(
            format_layout
        )

        # ======================================================
        # EXISTING SUBTITLES
        # ======================================================

        overwrite_layout = QHBoxLayout()

        overwrite_layout.addWidget(
            QLabel("If subtitle already exists:")
        )

        self.overwrite_mode_combo = QComboBox()

        self.overwrite_mode_combo.addItem(
            "Keep existing",
            "keep",
        )

        self.overwrite_mode_combo.addItem(
            "Ask me",
            "ask",
        )

        self.overwrite_mode_combo.addItem(
            "Overwrite existing",
            "overwrite",
        )

        self.overwrite_mode_combo.setCurrentIndex(0)

        overwrite_layout.addWidget(
            self.overwrite_mode_combo,
            1,
        )

        overwrite_layout.addStretch()

        main_layout.addLayout(
            overwrite_layout
        )

        # ======================================================
        # FILES
        # ======================================================

        files_group = QGroupBox(
            "Media Files"
        )

        files_layout = QVBoxLayout(
            files_group
        )

        buttons_layout = QHBoxLayout()

        self.add_files_button = QPushButton(
            "Add Files"
        )

        self.add_folder_button = QPushButton(
            "Add Folder"
        )

        self.remove_file_button = QPushButton(
            "Remove Selected"
        )

        self.clear_files_button = QPushButton(
            "Clear"
        )

        buttons_layout.addWidget(
            self.add_files_button
        )

        buttons_layout.addWidget(
            self.add_folder_button
        )

        buttons_layout.addWidget(
            self.remove_file_button
        )

        buttons_layout.addWidget(
            self.clear_files_button
        )

        buttons_layout.addStretch()

        files_layout.addLayout(
            buttons_layout
        )

        self.file_list = QListWidget()

        self.file_list.setSelectionMode(
            QListWidget.ExtendedSelection
        )

        files_layout.addWidget(
            self.file_list,
            1,
        )

        main_layout.addWidget(
            files_group,
            1,
        )

        # ======================================================
        # CURRENT FILE
        # ======================================================

        self.current_file_label = QLabel(
            "Ready."
        )

        self.current_file_label.setTextInteractionFlags(
            Qt.TextSelectableByMouse
        )

        main_layout.addWidget(
            self.current_file_label
        )

        # ======================================================
        # PROGRESS
        # ======================================================

        self.progress_bar = QProgressBar()

        self.progress_bar.setRange(
            0,
            100,
        )

        self.progress_bar.setValue(0)

        main_layout.addWidget(
            self.progress_bar
        )

        # ======================================================
        # STATUS
        # ======================================================

        self.status_label = QLabel(
            "Ready to process."
        )

        main_layout.addWidget(
            self.status_label
        )

        # ======================================================
        # TIME / ETA
        # ======================================================

        timing_layout = QHBoxLayout()

        self.elapsed_label = QLabel(
            "Elapsed: 00:00"
        )

        self.eta_label = QLabel(
            "ETA: --:--"
        )

        self.progress_detail_label = QLabel(
            "0%"
        )

        timing_layout.addWidget(
            self.elapsed_label
        )

        timing_layout.addSpacing(20)

        timing_layout.addWidget(
            self.eta_label
        )

        timing_layout.addSpacing(20)

        timing_layout.addWidget(
            self.progress_detail_label
        )

        timing_layout.addStretch()

        main_layout.addLayout(
            timing_layout
        )

        # ======================================================
        # LOG
        # ======================================================

        self.log = QPlainTextEdit()

        self.log.setReadOnly(True)

        main_layout.addWidget(
            self.log,
            1,
        )

        # ======================================================
        # CONTROLS
        # ======================================================

        controls_layout = QHBoxLayout()

        controls_layout.addStretch()

        self.start_button = QPushButton(
            "Generate Subtitles"
        )

        self.start_button.setMinimumHeight(42)

        self.cancel_button = QPushButton(
            "Cancel"
        )

        self.cancel_button.setMinimumHeight(42)

        self.cancel_button.setEnabled(False)

        controls_layout.addWidget(
            self.start_button
        )

        controls_layout.addWidget(
            self.cancel_button
        )

        main_layout.addLayout(
            controls_layout
        )

        # ======================================================
        # CONNECTIONS
        # ======================================================

        self.add_files_button.clicked.connect(
            self.add_files
        )

        self.add_folder_button.clicked.connect(
            self.add_folder
        )

        self.remove_file_button.clicked.connect(
            self.remove_selected_files
        )

        self.clear_files_button.clicked.connect(
            self.clear_files
        )

        self.start_button.clicked.connect(
            self.start_processing
        )

        self.cancel_button.clicked.connect(
            self.cancel_processing
        )

    # ==========================================================
    # LANGUAGE COMBO
    # ==========================================================

    @staticmethod
    def _populate_language_combo(
        combo: QComboBox,
        include_none: bool,
    ) -> None:

        combo.clear()

        if include_none:
            combo.addItem(
                "No translation",
                None,
            )

        for code, name in LANGUAGES.items():
            combo.addItem(
                f"{name} ({code})",
                code,
            )

    # ==========================================================
    # FILES
    # ==========================================================

    @Slot()
    def add_files(self) -> None:

        if self.processing:
            return

        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Media Files",
            "",
            (
                "Media Files "
                "(*.mp4 *.mkv *.avi *.mov *.webm "
                "*.m4v *.mpg *.mpeg *.ts *.mts *.m2ts "
                "*.flv *.wmv *.3gp *.ogv);;"
                "All Files (*)"
            ),
        )

        if files:
            self._add_files(files)

    @Slot()
    def add_folder(self) -> None:

        if self.processing:
            return

        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Media Folder",
        )

        if not folder:
            return

        extensions = {
            ".mp4",
            ".mkv",
            ".avi",
            ".mov",
            ".webm",
            ".m4v",
            ".mpg",
            ".mpeg",
            ".ts",
            ".mts",
            ".m2ts",
            ".flv",
            ".wmv",
            ".3gp",
            ".ogv",
        }

        files = []

        for root, _, filenames in os.walk(folder):
            for filename in filenames:

                extension = os.path.splitext(
                    filename
                )[1].lower()

                if extension in extensions:
                    files.append(
                        os.path.join(
                            root,
                            filename,
                        )
                    )

        files.sort()

        self._add_files(files)

    def _add_files(
        self,
        files: List[str],
    ) -> None:

        existing = {
            self.file_list.item(i).data(Qt.UserRole)
            for i in range(self.file_list.count())
        }

        for filepath in files:

            filepath = os.path.abspath(filepath)

            if not os.path.isfile(filepath):
                continue

            if filepath in existing:
                continue

            item = QListWidgetItem(filepath)

            item.setData(
                Qt.UserRole,
                filepath,
            )

            self.file_list.addItem(item)

            existing.add(filepath)

        self._update_file_count()

    @Slot()
    def remove_selected_files(self) -> None:

        if self.processing:
            return

        for item in self.file_list.selectedItems():
            self.file_list.takeItem(
                self.file_list.row(item)
            )

        self._update_file_count()

    @Slot()
    def clear_files(self) -> None:

        if self.processing:
            return

        self.file_list.clear()

        self._update_file_count()

    def _update_file_count(self) -> None:

        count = self.file_list.count()

        self.status_label.setText(
            f"{count} media file(s) selected."
        )

    def get_files(self) -> List[str]:

        files = []

        for index in range(self.file_list.count()):

            filepath = self.file_list.item(
                index
            ).data(
                Qt.UserRole
            )

            if filepath:
                files.append(filepath)

        return files

    # ==========================================================
    # START
    # ==========================================================

    @Slot()
    def start_processing(self) -> None:

        if self.processing:
            return

        files = self.get_files()

        if not files:
            QMessageBox.warning(
                self,
                "No Media Files",
                "Please add at least one media file.",
            )
            return

        source_language = (
            self.source_combo.currentData()
        )

        target_language = (
            self.target_combo.currentData()
        )

        subtitle_format = (
            self.format_combo.currentText().lower()
        )

        overwrite_mode = (
            self.overwrite_mode_combo.currentData()
        )

        translation_mode = (
            self.translation_mode_combo.currentData()
        )

        if not source_language:
            QMessageBox.warning(
                self,
                "Source Language",
                "Please select a source language.",
            )
            return

        if (
            target_language
            and target_language == source_language
        ):
            QMessageBox.warning(
                self,
                "Invalid Languages",
                (
                    "Source and target languages "
                    "cannot be the same."
                ),
            )
            return

        if not target_language:
            translation_mode = "skip"

        source_name = LANGUAGES.get(
            source_language,
            source_language,
        )

        if target_language:

            target_name = LANGUAGES.get(
                target_language,
                target_language,
            )

            translation_text = (
                f"{target_name} ({target_language})"
            )

        else:
            translation_text = "Disabled"

        overwrite_names = {
            "ask": "Ask me",
            "overwrite": "Overwrite existing",
            "keep": "Keep existing",
        }

        translation_names = {
            "ask": "Ask when needed",
            "translate": "Always translate",
            "skip": "Never translate",
        }

        answer = QMessageBox.question(
            self,
            "Start Processing",
            (
                f"Files: {len(files)}\n"
                f"Source: {source_name} ({source_language})\n"
                f"Target: {translation_text}\n"
                f"Format: {subtitle_format.upper()}\n"
                f"Existing subtitles: "
                f"{overwrite_names[overwrite_mode]}\n"
                f"Translation: "
                f"{translation_names[translation_mode]}\n\n"
                "Start subtitle generation?"
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )

        if answer != QMessageBox.Yes:
            return

        # ======================================================
        # RESET ETA STATE
        # ======================================================

        self.total_files = len(files)
        self.current_file_number = 1
        self.current_file_percentage = 0
        self.last_overall_percentage = 0

        self.processing_start_time = time.monotonic()

        self.elapsed_label.setText(
            "Elapsed: 00:00"
        )

        self.eta_label.setText(
            "ETA: calculating..."
        )

        self.progress_detail_label.setText(
            "0%"
        )

        self._set_processing(True)

        self.progress_bar.setValue(0)

        self.current_file_label.setText(
            "Starting..."
        )

        self.status_label.setText(
            "Starting..."
        )

        self.log.clear()

        self.log_message(
            "Starting Veyra..."
        )

        self.log_message(
            f"Files: {len(files)}"
        )

        self.log_message(
            f"Source language: {source_language}"
        )

        self.log_message(
            f"Target language: "
            f"{target_language or 'disabled'}"
        )

        self.log_message(
            f"Format: {subtitle_format}"
        )

        self.log_message(
            f"Existing subtitles: "
            f"{overwrite_names[overwrite_mode]}"
        )

        self.log_message(
            f"Translation: "
            f"{translation_names[translation_mode]}"
        )

        # ======================================================
        # THREAD
        # ======================================================

        self.thread = QThread(self)

        self.worker = ProcessingWorker(
            files=files,
            source_language=source_language,
            target_language=target_language,
            subtitle_format=subtitle_format,
            overwrite_mode=overwrite_mode,
            translation_mode=translation_mode,
        )

        self.worker.moveToThread(
            self.thread
        )

        # ======================================================
        # START
        # ======================================================

        self.thread.started.connect(
            self.worker.run
        )

        # ======================================================
        # WORKER -> GUI
        # ======================================================

        self.worker.progress.connect(
            self.update_progress
        )

        self.worker.error.connect(
            self.processing_error
        )

        self.worker.finished.connect(
            self.processing_finished
        )

        self.worker.cancelled.connect(
            self.processing_cancelled
        )

        # ======================================================
        # QUESTIONS
        # ======================================================

        self.worker.overwrite_requested.connect(
            self.show_overwrite_dialog,
            Qt.QueuedConnection,
        )

        self.worker.translation_requested.connect(
            self.show_translation_dialog,
            Qt.QueuedConnection,
        )

        # ======================================================
        # THREAD CLEANUP
        # ======================================================

        self.worker.finished.connect(
            self.thread.quit
        )

        self.worker.cancelled.connect(
            self.thread.quit
        )

        self.worker.error.connect(
            self.thread.quit
        )

        self.thread.finished.connect(
            self.worker.deleteLater
        )

        self.thread.finished.connect(
            self.thread.deleteLater
        )

        self.thread.finished.connect(
            self.thread_finished
        )

        self.thread.start()

    # ==========================================================
    # THREAD FINISHED
    # ==========================================================

    @Slot()
    def thread_finished(self) -> None:

        self.thread = None
        self.worker = None

        if self._close_after_cancel:

            self._close_after_cancel = False

            app = QApplication.instance()

            if app is not None:
                app.quit()

    # ==========================================================
    # PROCESSING STATE
    # ==========================================================

    def _set_processing(
        self,
        processing: bool,
    ) -> None:

        self.processing = processing

        enabled = not processing

        self.add_files_button.setEnabled(enabled)
        self.add_folder_button.setEnabled(enabled)
        self.remove_file_button.setEnabled(enabled)
        self.clear_files_button.setEnabled(enabled)

        self.source_combo.setEnabled(enabled)
        self.target_combo.setEnabled(enabled)

        self.translation_mode_combo.setEnabled(
            enabled
        )

        self.format_combo.setEnabled(enabled)

        self.overwrite_mode_combo.setEnabled(
            enabled
        )

        self.start_button.setEnabled(enabled)

        self.cancel_button.setEnabled(
            processing
        )

    # ==========================================================
    # TIME FORMAT
    # ==========================================================

    @staticmethod
    def format_duration(
        seconds: float,
    ) -> str:

        if seconds < 0:
            seconds = 0

        total_seconds = int(seconds)

        hours = total_seconds // 3600

        minutes = (
            total_seconds % 3600
        ) // 60

        secs = total_seconds % 60

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

    # ==========================================================
    # CALCULATE OVERALL PROGRESS
    # ==========================================================

    def calculate_overall_progress(
        self,
        percentage: int,
    ) -> int:

        if self.total_files <= 0:
            return percentage

        current_file = max(
            1,
            min(
                self.total_files,
                self.current_file_number,
            ),
        )

        percentage = max(
            0,
            min(100, percentage),
        )

        completed_files = current_file - 1

        overall = (
            (
                completed_files * 100
            )
            + percentage
        ) / self.total_files

        overall = int(overall)

        # Never allow the displayed progress to move backwards.
        overall = max(
            self.last_overall_percentage,
            overall,
        )

        overall = min(
            100,
            overall,
        )

        self.last_overall_percentage = overall

        return overall

    # ==========================================================
    # ETA UPDATE
    # ==========================================================

    def update_timing(
        self,
        overall_percentage: int,
    ) -> None:

        if self.processing_start_time is None:
            return

        elapsed = (
            time.monotonic()
            - self.processing_start_time
        )

        self.elapsed_label.setText(
            "Elapsed: "
            + self.format_duration(elapsed)
        )

        self.progress_detail_label.setText(
            f"{overall_percentage}%"
        )

        # ------------------------------------------------------
        # ETA
        # ------------------------------------------------------

        if overall_percentage <= 0 or elapsed <= 0:

            self.eta_label.setText(
                "ETA: calculating..."
            )

            return

        if overall_percentage >= 100:

            self.eta_label.setText(
                "ETA: 00:00"
            )

            return

        estimated_total_time = (
            elapsed
            * 100.0
            / float(overall_percentage)
        )

        remaining = (
            estimated_total_time
            - elapsed
        )

        remaining = max(
            0,
            remaining,
        )

        self.eta_label.setText(
            "ETA: "
            + self.format_duration(remaining)
        )

    # ==========================================================
    # PROGRESS
    # ==========================================================

    @Slot(str, str, int)
    def update_progress(
        self,
        info: str,
        filename: str,
        percentage: int,
    ) -> None:

        percentage = max(
            0,
            min(100, int(percentage)),
        )

        # ------------------------------------------------------
        # Determine current file number
        #
        # JobProcessor sends:
        #
        # Processing file 1 of 5
        # Processing file 2 of 5
        # ...
        # ------------------------------------------------------

        import re

        match = re.search(
            r"Processing\s+file\s+(\d+)\s+of\s+(\d+)",
            info,
            re.IGNORECASE,
        )

        if match:

            try:
                self.current_file_number = int(
                    match.group(1)
                )

                self.total_files = int(
                    match.group(2)
                )

            except (ValueError, TypeError):
                pass

        self.current_file_percentage = percentage

        # ------------------------------------------------------
        # Overall progress
        # ------------------------------------------------------

        overall_percentage = (
            self.calculate_overall_progress(
                percentage
            )
        )

        self.progress_bar.setValue(
            overall_percentage
        )

        # ------------------------------------------------------
        # Current file
        # ------------------------------------------------------

        if filename:

            self.current_file_label.setText(
                f"File "
                f"{self.current_file_number} "
                f"of "
                f"{self.total_files}: "
                f"{filename}"
            )

        # ------------------------------------------------------
        # Status
        # ------------------------------------------------------

        self.status_label.setText(
            info
        )

        # ------------------------------------------------------
        # ETA / ELAPSED
        # ------------------------------------------------------

        self.update_timing(
            overall_percentage
        )

        # ------------------------------------------------------
        # LOG
        # ------------------------------------------------------

        text = (
            f"[{overall_percentage:3d}%]"
            f" "
            f"[File "
            f"{self.current_file_number}/"
            f"{self.total_files}] "
            f"{info}"
        )

        if filename:
            text += f" — {filename}"

        self.log_message(text)

    # ==========================================================
    # ERROR
    # ==========================================================

    @Slot(str)
    def processing_error(
        self,
        message: str,
    ) -> None:

        if not self.processing:
            return

        self.log_message(
            f"ERROR: {message}"
        )

        self.status_label.setText(
            "Processing failed."
        )

        self._set_processing(False)

        QMessageBox.critical(
            self,
            "Processing Error",
            message,
        )

    # ==========================================================
    # FINISHED
    # ==========================================================

    @Slot(list)
    def processing_finished(
        self,
        results: list,
    ) -> None:

        # ------------------------------------------------------
        # FINAL TIMING
        # ------------------------------------------------------

        if self.processing_start_time is not None:

            elapsed = (
                time.monotonic()
                - self.processing_start_time
            )

            self.elapsed_label.setText(
                "Elapsed: "
                + self.format_duration(elapsed)
            )

        self.progress_bar.setValue(100)

        self.progress_detail_label.setText(
            "100%"
        )

        self.eta_label.setText(
            "ETA: 00:00"
        )

        self.status_label.setText(
            "Processing complete."
        )

        self._set_processing(False)

        self.log_message("")
        self.log_message("=" * 60)
        self.log_message(
            "PROCESSING COMPLETE"
        )

        self.log_message(
            f"Successfully processed: "
            f"{len(results)} file(s)"
        )

        # ------------------------------------------------------
        # FINAL ELAPSED TIME IN LOG
        # ------------------------------------------------------

        if self.processing_start_time is not None:

            elapsed = (
                time.monotonic()
                - self.processing_start_time
            )

            self.log_message(
                f"Total elapsed time: "
                f"{self.format_duration(elapsed)}"
            )

        for result in results:

            media = result.get(
                "media",
                "",
            )

            source = result.get(
                "source_subtitle",
                "",
            )

            translated = result.get(
                "translated_subtitle"
            )

            self.log_message(
                f"\nMedia: {media}"
            )

            if source:

                self.log_message(
                    f"Source subtitle: {source}"
                )

            if translated:

                self.log_message(
                    f"Translated subtitle: "
                    f"{translated}"
                )

        QMessageBox.information(
            self,
            "Complete",
            (
                "Subtitle processing completed.\n\n"
                f"Successfully processed: "
                f"{len(results)} file(s)."
            ),
        )

    # ==========================================================
    # CANCELLED
    # ==========================================================

    @Slot()
    def processing_cancelled(self) -> None:

        if self.processing_start_time is not None:

            elapsed = (
                time.monotonic()
                - self.processing_start_time
            )

            self.elapsed_label.setText(
                "Elapsed: "
                + self.format_duration(elapsed)
            )

        self.eta_label.setText(
            "ETA: cancelled"
        )

        self.status_label.setText(
            "Cancelled."
        )

        self.log_message(
            "Processing cancelled."
        )

        self._set_processing(False)

    # ==========================================================
    # CANCEL
    # ==========================================================

    @Slot()
    def cancel_processing(self) -> None:

        if not self.processing:
            return

        answer = QMessageBox.question(
            self,
            "Cancel Processing",
            (
                "Are you sure you want to "
                "cancel subtitle processing?"
            ),
            QMessageBox.Yes
            | QMessageBox.No,
            QMessageBox.No,
        )

        if answer != QMessageBox.Yes:
            return

        self.status_label.setText(
            "Cancelling..."
        )

        self.eta_label.setText(
            "ETA: cancelling..."
        )

        self.cancel_button.setEnabled(False)

        if self.worker is not None:
            self.worker.request_cancel()

    # ==========================================================
    # OVERWRITE DIALOG
    # ==========================================================

    @Slot(str, str)
    def show_overwrite_dialog(
        self,
        filepath: str,
        subtitle_type: str,
    ) -> None:

        if not self.processing:
            return

        answer = QMessageBox.question(
            self,
            "Subtitle Already Exists",
            (
                f"An existing {subtitle_type} "
                "subtitle was found:\n\n"
                f"{filepath}\n\n"
                "Do you want to overwrite it?"
            ),
            QMessageBox.Yes
            | QMessageBox.No,
            QMessageBox.No,
        )

        if self.worker is not None:

            self.worker.overwrite_answer.emit(
                answer == QMessageBox.Yes
            )

    # ==========================================================
    # TRANSLATION DIALOG
    # ==========================================================

    @Slot(str, str, str, str)
    def show_translation_dialog(
        self,
        source_language: str,
        target_language: str,
        source_subtitle: str,
        translated_subtitle: str,
    ) -> None:

        if not self.processing:
            return

        source_name = LANGUAGES.get(
            source_language,
            source_language,
        )

        target_name = LANGUAGES.get(
            target_language,
            target_language,
        )

        answer = QMessageBox.question(
            self,
            "Translate Subtitle",
            (
                f"Source:\n"
                f"  {source_name} ({source_language})\n\n"
                f"Target:\n"
                f"  {target_name} ({target_language})\n\n"
                f"Source subtitle:\n"
                f"  {source_subtitle}\n\n"
                f"Output subtitle:\n"
                f"  {translated_subtitle}\n\n"
                "Translate using NLLB?"
            ),
            QMessageBox.Yes
            | QMessageBox.No,
            QMessageBox.Yes,
        )

        if self.worker is not None:

            self.worker.translation_answer.emit(
                answer == QMessageBox.Yes
            )

    # ==========================================================
    # LOG
    # ==========================================================

    def log_message(
        self,
        message: str,
    ) -> None:

        self.log.appendPlainText(
            str(message)
        )

    # ==========================================================
    # CLOSE
    # ==========================================================

    def closeEvent(
        self,
        event: QCloseEvent,
    ) -> None:

        if not self.processing:
            event.accept()
            return

        answer = QMessageBox.question(
            self,
            "Veyra Is Processing",
            (
                "Subtitle processing is still running.\n\n"
                "Cancel the current job and exit?"
            ),
            QMessageBox.Yes
            | QMessageBox.No,
            QMessageBox.No,
        )

        if answer != QMessageBox.Yes:

            event.ignore()
            return

        self._close_after_cancel = True

        self.status_label.setText(
            "Cancelling before exit..."
        )

        self.eta_label.setText(
            "ETA: cancelling..."
        )

        self.cancel_button.setEnabled(False)

        if self.worker is not None:
            self.worker.request_cancel()

        event.ignore()


# ==============================================================
# MAIN
# ==============================================================

def main() -> int:

    app = QApplication(sys.argv)

    app.setApplicationName("Veyra")
    app.setOrganizationName("Veyra")

    window = VeyraWindow()

    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())