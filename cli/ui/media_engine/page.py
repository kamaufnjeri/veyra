from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QFileDialog,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from jobs.media_engine_processor import (
    JobCancelled,
    MediaEngineJob,
    MediaEngineJobResult,
    MediaEngineProcessor,
)

from .widgets.inspection_panel import InspectionPanel
from .widgets.media_library import MediaLibrary
from .widgets.media_group import MediaGroupColumn, AUDIO_EXTENSIONS, VIDEO_EXTENSIONS
from .widgets.media_selection_dialog import MediaSelectionDialog
from .widgets.operation_selector import OperationSelector
from .widgets.output_settings import OutputSettings
from .widgets.progress_panel import ProgressPanel
from .widgets.shared_settings import SharedSettings

from .workspaces.burn_subtitles import BurnSubtitlesWorkspace
from .workspaces.compress import CompressWorkspace
from .workspaces.convert import ConvertWorkspace
from .workspaces.cut import CutWorkspace
from .workspaces.extract import ExtractWorkspace
from .workspaces.join import JoinWorkspace
from .workspaces.mux import MuxWorkspace


# ============================================================
# CONSTANTS
# ============================================================


PROCESSING_OPERATIONS = (
    "convert",
    "cut",
    "join",
    "burn_subtitles",
    "mux",
    "compress",
    "extract",
)


# ============================================================
# INSPECTION WORKER
# ============================================================


class MediaInspectionWorker(QObject):
    """
    Background worker dedicated to inspecting one media file.

    Inspection is intentionally separate from normal processing.

    Selecting media:
        - updates inspection
        - does not change working_media
        - does not become a processing operation
    """

    finished = Signal(object)
    failed = Signal(object)
    cancelled = Signal()

    def __init__(
        self,
        source: Path,
        *,
        ffmpeg: str,
        ffprobe: str,
    ) -> None:
        super().__init__()

        self.source = Path(source)

        self.processor = MediaEngineProcessor(
            ffmpeg=ffmpeg,
            ffprobe=ffprobe,
        )

    @Slot()
    def run(self) -> None:
        job = MediaEngineJob(
            operation="inspect",
            inputs=(self.source,),
            options={
                "include_subtitle_text": False,
                "include_raw": True,
            },
        )

        try:
            results = self.processor.process_jobs(
                [job]
            )

            if not results:
                self.failed.emit(
                    RuntimeError(
                        f"Inspection returned no result for "
                        f"{self.source.name}."
                    )
                )
                return

            result = results[0]

            if not isinstance(
                result,
                MediaEngineJobResult,
            ):
                self.failed.emit(
                    RuntimeError(
                        "Inspection returned an invalid "
                        "job result."
                    )
                )
                return

            if result.error is not None:
                self.failed.emit(
                    result.error
                )
                return

            if result.result is None:
                self.failed.emit(
                    RuntimeError(
                        f"Inspection returned no data for "
                        f"{self.source.name}."
                    )
                )
                return

            self.finished.emit(
                result
            )

        except JobCancelled:
            self.cancelled.emit()

        except Exception as exc:
            self.failed.emit(
                exc
            )

    def cancel(self) -> None:
        self.processor.cancel()


# ============================================================
# PROCESSING WORKER
# ============================================================


class MediaEngineWorker(QObject):
    """
    QObject running the media-processing batch inside a QThread.
    """

    progress = Signal(int, str)
    error = Signal(object)
    job_event = Signal(str, object)
    finished = Signal(object)
    cancelled = Signal()
    failed = Signal(object)

    def __init__(
        self,
        jobs: list[MediaEngineJob],
        *,
        ffmpeg: str,
        ffprobe: str,
    ) -> None:
        super().__init__()

        self.jobs = list(jobs)

        self.processor = MediaEngineProcessor(
            ffmpeg=ffmpeg,
            ffprobe=ffprobe,
            progress_callback=self._on_progress,
            error_callback=self._on_error,
            job_callback=self._on_job,
        )

    # ========================================================
    # CALLBACKS
    # ========================================================

    def _on_progress(
        self,
        *args: Any,
    ) -> None:
        if len(args) < 2:
            return

        try:
            progress = float(
                args[1]
            )

        except (
            TypeError,
            ValueError,
        ):
            return

        if progress <= 1:
            percent = int(
                progress * 100
            )
        else:
            percent = int(
                progress
            )

        percent = max(
            0,
            min(
                100,
                percent,
            ),
        )

        message = (
            str(args[2])
            if len(args) >= 3
            else ""
        )

        self.progress.emit(
            percent,
            message,
        )

    def _on_error(
        self,
        error: Any,
    ) -> None:
        self.error.emit(
            error
        )

    def _on_job(
        self,
        event: str,
        *args: Any,
    ) -> None:
        if len(args) == 1:
            data = args[0]

        else:
            data = args

        self.job_event.emit(
            str(event),
            data,
        )

    # ========================================================
    # RUN
    # ========================================================

    @Slot()
    def run(self) -> None:
        try:
            results = self.processor.process_jobs(
                self.jobs
            )

            self.finished.emit(
                results
            )

        except JobCancelled:
            self.cancelled.emit()

        except Exception as exc:
            self.failed.emit(
                exc
            )

    def cancel(self) -> None:
        self.processor.cancel()


# ============================================================
# PAGE
# ============================================================


class MediaEnginePage(QWidget):
    operationChanged = Signal(str)

    def __init__(
        self,
        *,
        ffmpeg: str = "ffmpeg",
        ffprobe: str = "ffprobe",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            parent
        )

        self.ffmpeg = ffmpeg
        self.ffprobe = ffprobe

        # -----------------------------------------------------
        # MEDIA STATE
        # -----------------------------------------------------

        self.selected_media: Path | None = None

        self.working_media: list[Path] = []

        self.subtitle_files: list[Path] = []

        self.inspection_cache: dict[
            Path,
            Any,
        ] = {}

        # -----------------------------------------------------
        # OPERATION STATE
        # -----------------------------------------------------

        self.operation = "convert"

        # -----------------------------------------------------
        # PROCESSING STATE
        # -----------------------------------------------------

        self._processing = False

        self._worker_thread: QThread | None = None
        self._worker: MediaEngineWorker | None = None

        self._batch_total = 0
        self._batch_completed = 0
        self._batch_current = 0
        self._batch_current_name = ""

        # -----------------------------------------------------
        # INSPECTION STATE
        # -----------------------------------------------------

        self._inspection_thread: QThread | None = None
        self._inspection_worker: MediaInspectionWorker | None = None
        self._inspection_path: Path | None = None

        self._build_ui()
        self._connect_signals()

        self._remove_inspection_operations()

        self._operation_changed(
            "convert"
        )

    # =========================================================
    # UI
    # =========================================================

    def _build_ui(self) -> None:
        outer = QVBoxLayout(
            self
        )

        outer.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        scroll = QScrollArea()

        scroll.setWidgetResizable(
            True
        )

        scroll.setFrameShape(
            QFrame.Shape.NoFrame
        )

        outer.addWidget(
            scroll
        )

        content = QWidget()

        scroll.setWidget(
            content
        )

        main = QVBoxLayout(
            content
        )

        main.setContentsMargins(
            12,
            12,
            12,
            12,
        )

        main.setSpacing(
            12
        )

        # -----------------------------------------------------
        # HEADER
        # -----------------------------------------------------

        title = QLabel(
            "Media Engine"
        )

        title.setStyleSheet(
            "font-size: 22px; font-weight: 600;"
        )

        subtitle = QLabel(
            "Inspect, convert, cut, join, mux, compress, "
            "extract and burn subtitles."
        )

        subtitle.setWordWrap(
            True
        )

        main.addWidget(
            title
        )

        main.addWidget(
            subtitle
        )

        # -----------------------------------------------------
        # TOP: MEDIA + INSPECTION
        # -----------------------------------------------------

        top_splitter = QSplitter(
            Qt.Orientation.Horizontal
        )

        self.media_library = MediaLibrary()

        self.inspection_panel = InspectionPanel()

        top_splitter.addWidget(
            self.media_library
        )

        top_splitter.addWidget(
            self.inspection_panel
        )

        top_splitter.setStretchFactor(
            0,
            1,
        )

        top_splitter.setStretchFactor(
            1,
            1,
        )

        main.addWidget(
            top_splitter
        )

        # -----------------------------------------------------
        # OPERATION
        # -----------------------------------------------------

        self.operation_selector = OperationSelector()

        main.addWidget(
            self.operation_selector
        )

        # -----------------------------------------------------
        # WORKING MEDIA
        # -----------------------------------------------------

        self.working_media_column = MediaGroupColumn(
            "Working Media",
            "media",
            allow_multiple=True,
        )

        # Keep this section compact, like the columns used by
        # MediaGroupWidget.
        self.working_media_column.list_widget.setMinimumHeight(80)
        self.working_media_column.list_widget.setMaximumHeight(140)

        self.working_media_column.selectRequested.connect(
            self._select_working_media
        )

        self.working_media_column.filesChanged.connect(
            self._working_media_changed
        )

        self.working_media_column.filesAdded.connect(
            self._working_media_browsed
        )

        main.addWidget(
            self.working_media_column
        )

        # -----------------------------------------------------
        # SETTINGS
        # -----------------------------------------------------

        settings_splitter = QSplitter(
            Qt.Orientation.Horizontal
        )

        self.shared_settings = SharedSettings()

        self.workspace_stack = QStackedWidget()

        self.workspaces: dict[
            str,
            QWidget,
        ] = {}

        self._create_workspaces()

        settings_splitter.addWidget(
            self.shared_settings
        )

        settings_splitter.addWidget(
            self.workspace_stack
        )

        settings_splitter.setStretchFactor(
            0,
            1,
        )

        settings_splitter.setStretchFactor(
            1,
            2,
        )

        settings_splitter.setMinimumHeight(
            350
        )

        main.addWidget(
            settings_splitter
        )

        # -----------------------------------------------------
        # OUTPUT
        # -----------------------------------------------------

        self.output_settings = OutputSettings()

        main.addWidget(
            self.output_settings
        )

        # -----------------------------------------------------
        # ACTIONS
        # -----------------------------------------------------

        actions = QHBoxLayout()

        self.start_button = QPushButton(
            "Start Processing"
        )

        self.cancel_button = QPushButton(
            "Cancel"
        )

        self.reset_button = QPushButton(
            "Reset"
        )

        self.cancel_button.setEnabled(
            False
        )

        actions.addWidget(
            self.start_button
        )

        actions.addWidget(
            self.cancel_button
        )

        actions.addWidget(
            self.reset_button
        )

        main.addLayout(
            actions
        )

        # -----------------------------------------------------
        # PROGRESS
        # -----------------------------------------------------

        self.progress_panel = ProgressPanel()

        main.addWidget(
            self.progress_panel
        )

        main.addStretch(
            1
        )

    # =========================================================
    # WORKSPACES
    # =========================================================

    def _create_workspaces(self) -> None:
        self.workspaces = {
            "convert": ConvertWorkspace(),
            "cut": CutWorkspace(),
            "join": JoinWorkspace(),
            "burn_subtitles": BurnSubtitlesWorkspace(),
            "mux": MuxWorkspace(),
            "compress": CompressWorkspace(),
            "extract": ExtractWorkspace(),
        }

        for workspace in self.workspaces.values():
            self.workspace_stack.addWidget(
                workspace
            )

        # -----------------------------------------------------
        # Extract settings affect its output suffix/preview.
        # -----------------------------------------------------

        extract_workspace = self.workspaces.get(
            "extract"
        )

        settings_changed = getattr(
            extract_workspace,
            "settingsChanged",
            None,
        )

        if settings_changed is not None:
            settings_changed.connect(
                self._extract_settings_changed
            )

    # =========================================================
    # OPERATION SELECTOR
    # =========================================================

    def _remove_inspection_operations(self) -> None:
        combo = self.operation_selector.findChild(
            QComboBox
        )

        if combo is None:
            return

        for index in range(
            combo.count() - 1,
            -1,
            -1,
        ):
            data = combo.itemData(
                index
            )

            text = combo.itemText(
                index
            ).strip().lower()

            if data in {
                "inspect",
                "inspect_json",
            } or text in {
                "inspect",
                "inspect json",
                "inspection",
                "inspection json",
            }:
                combo.removeItem(
                    index
                )

    # =========================================================
    # SIGNALS
    # =========================================================

    def _connect_signals(self) -> None:
        self.media_library.mediaSelectionChanged.connect(
            self._media_selection_changed
        )

        self.media_library.mediaFilesChanged.connect(
            self._media_files_changed
        )

        self.operation_selector.operationChanged.connect(
            self._operation_changed
        )

        self.output_settings.changed.connect(
            self._output_settings_changed
        )

        self.start_button.clicked.connect(
            self._run
        )

        self.cancel_button.clicked.connect(
            self._cancel
        )

        self.reset_button.clicked.connect(
            self.reset_page
        )

    # =========================================================
    # MEDIA
    # =========================================================

    def _media_files_changed(self) -> None:
        """
        Media-library changes affect inspection and workspace
        synchronization.

        They do not automatically become working media.
        """

        self._reconcile_working_media()
        self._sync_workspaces()

        files = self.media_library.files()

        if not files:
            self.selected_media = None

            self.working_media.clear()

            self.inspection_panel.clear()

            self._cancel_inspection()

            self._update_working_label()
            self._update_output_preview()
            self._update_stream_choices()

            return

        if (
            self.selected_media is None
            or self.selected_media not in files
        ):
            self.selected_media = Path(
                files[0]
            )

        self._show_cached_inspection()

        self._inspect_media(
            self.selected_media
        )

        self._update_stream_choices()

        self._update_output_defaults()
        self._update_output_preview()

    def _media_selection_changed(
        self,
        selected: object,
    ) -> None:
        """
        Media selection affects inspection only.

        It never changes working_media.
        """

        try:
            paths = [
                Path(path)
                for path in selected
            ]

        except (
            TypeError,
            ValueError,
        ):
            paths = []

        if not paths:
            self.selected_media = None

            self.inspection_panel.clear()

            return

        self.selected_media = paths[0]

        self._show_cached_inspection()

        self._inspect_media(
            self.selected_media
        )

        # If Extract is using the selected media for inspection,
        # refresh its stream information.
        if (
            self.selected_media
            in self.inspection_cache
        ):
            self._update_stream_choices()

    # =========================================================
    # INSPECTION
    # =========================================================

    def _inspect_media(
        self,
        source: Path | None,
    ) -> None:
        """
        Inspect one media file in the background.

        Cached inspection data is displayed immediately.
        """

        if source is None:
            return

        source = Path(
            source
        )

        if not source.is_file():
            self.inspection_panel.show_path(
                source
            )
            return

        if source in self.inspection_cache:
            self.inspection_panel.show_cached(
                source,
                self.inspection_cache[
                    source
                ],
            )

            self._update_stream_choices()

            return

        if (
            self._inspection_thread is not None
            and self._inspection_thread.isRunning()
            and self._inspection_path == source
        ):
            return

        self._cancel_inspection()

        self._inspection_path = source

        self.inspection_panel.show_path(
            source
        )

        thread = QThread(
            self
        )

        worker = MediaInspectionWorker(
            source,
            ffmpeg=self.ffmpeg,
            ffprobe=self.ffprobe,
        )

        worker.moveToThread(
            thread
        )

        thread.started.connect(
            worker.run
        )

        worker.finished.connect(
            self._inspection_finished
        )

        worker.failed.connect(
            self._inspection_failed
        )

        worker.cancelled.connect(
            self._inspection_cancelled
        )

        worker.finished.connect(
            thread.quit
        )

        worker.failed.connect(
            thread.quit
        )

        worker.cancelled.connect(
            thread.quit
        )

        worker.finished.connect(
            worker.deleteLater
        )

        worker.failed.connect(
            worker.deleteLater
        )

        worker.cancelled.connect(
            worker.deleteLater
        )

        # Capture this exact thread so an old inspection thread
        # cannot clear references belonging to a newer inspection.
        thread.finished.connect(
            lambda thread=thread:
            self._inspection_thread_finished(
                thread
            )
        )

        self._inspection_thread = thread
        self._inspection_worker = worker

        thread.start()

    def _inspection_finished(
        self,
        result: Any,
    ) -> None:
        if not isinstance(
            result,
            MediaEngineJobResult,
        ):
            return

        if result.error is not None:
            self._inspection_failed(
                result.error
            )
            return

        if result.operation != "inspect":
            return

        if not result.inputs:
            return

        source = Path(
            result.inputs[0]
        )

        value = result.result

        if value is None:
            self._inspection_failed(
                RuntimeError(
                    f"Inspection returned no data for "
                    f"{source.name}."
                )
            )
            return

        self.inspection_cache[
            source
        ] = value

        if self.selected_media == source:
            self.inspection_panel.show_cached(
                source,
                value,
            )

        # -----------------------------------------------------
        # Extract gets the complete inspection result.
        # -----------------------------------------------------

        if source in self.inspection_cache:
            self._update_stream_choices()

    def _inspection_failed(
        self,
        error: Any,
    ) -> None:
        source = self._inspection_path

        if source is None:
            return

        if self.selected_media != source:
            return

        self.inspection_panel.show_error(
            source,
            error,
        )

    def _inspection_cancelled(self) -> None:
        pass

    def _cancel_inspection(self) -> None:
        """
        Request cancellation of the active inspection.

        We intentionally do not clear the thread references here.
        The actual thread-finished callback owns cleanup.
        """

        worker = self._inspection_worker

        if worker is not None:
            worker.cancel()

    def _inspection_thread_finished(
        self,
        thread: QThread,
    ) -> None:
        """
        Clear inspection references only if this is still the
        currently tracked thread.
        """

        if self._inspection_thread is not thread:
            return

        self._inspection_worker = None
        self._inspection_thread = None
        self._inspection_path = None

    def _show_cached_inspection(self) -> None:
        if self.selected_media is None:
            self.inspection_panel.clear()
            return

        source = self.selected_media

        if source not in self.inspection_cache:
            self.inspection_panel.show_path(
                source
            )
            return

        self.inspection_panel.show_cached(
            source,
            self.inspection_cache[
                source
            ],
        )

    # =========================================================
    # WORKING MEDIA
    # =========================================================

    def _select_working_media(self) -> None:
        """
        Select working media from the shared Media Library.

        This deliberately behaves like a multi-select MediaGroupColumn:
        selected files are added to the working list, while Remove Selected
        remains responsible for removing them.
        """
        available = [
            Path(path)
            for path in self.media_library.files()
            if Path(path).suffix.lower()
            in (VIDEO_EXTENSIONS | AUDIO_EXTENSIONS)
        ]

        if not available:
            return

        dialog = MediaSelectionDialog(
            title="Select Working Media",
            files=available,
            allowed_extensions=VIDEO_EXTENSIONS | AUDIO_EXTENSIONS,
            allow_multiple=True,
            existing_files=self.working_media,
            parent=self,
        )

        if dialog.exec() != dialog.DialogCode.Accepted:
            return

        selected = dialog.selected_files()

        if not selected:
            return

        self.working_media_column.add_files(
            selected,
            emit_added=False,
        )

        self._sync_working_media_state()

    def _working_media_browsed(self, files: object) -> None:
        """
        Browse is owned by MediaGroupColumn.

        Newly browsed files are added to the shared Media Library as well
        as the Working Media column.
        """
        if not isinstance(files, list):
            return

        paths = [
            Path(path)
            for path in files
            if Path(path).is_file()
            and Path(path).suffix.lower()
            in (VIDEO_EXTENSIONS | AUDIO_EXTENSIONS)
        ]

        if not paths:
            return

        self.media_library.add_files(
            paths,
            select=False,
        )

        self._sync_working_media_state()

        self.selected_media = paths[0]
        self._show_cached_inspection()
        self._inspect_media(self.selected_media)
        self._update_stream_choices()
        self._update_output_defaults()
        self._update_output_preview()

    def _working_media_changed(self) -> None:
        """
        Synchronize page state after Working Media is changed directly.
        """
        self._sync_working_media_state()

    def _sync_working_media_state(self) -> None:
        self.working_media = self.working_media_column.files()

        self._sync_workspaces()
        self._update_output_defaults()
        self._update_output_preview()
        self._update_stream_choices()

    def _reconcile_working_media(self) -> None:
        available_keys = {
            self._path_key(path)
            for path in self.media_library.files()
        }

        current = self.working_media_column.files()
        reconciled = [
            path
            for path in current
            if self._path_key(path) in available_keys
        ]

        if reconciled != current:
            self.working_media_column.set_files(reconciled)
        else:
            self.working_media = current

    @staticmethod
    def _path_key(path: Path) -> Path:
        try:
            return Path(path).resolve()
        except OSError:
            return Path(path).absolute()

    # =========================================================
    # WORKING MEDIA DISPLAY
    # =========================================================

    def _update_working_label(self) -> None:
        # Compatibility helper for existing call sites.
        self.working_media_column.set_files(
            self.working_media
        )

    def _sync_workspaces(self) -> None:
        media = list(
            self.working_media
        )

        subtitles = list(
            self.subtitle_files
        )

        available_media = list(
            self.media_library.files()
        )

        for workspace in self.workspaces.values():
            setter = getattr(
                workspace,
                "set_media",
                None,
            )

            if callable(setter):
                setter(
                    media
                )

            available_media_setter = getattr(
                workspace,
                "set_available_media",
                None,
            )

            if callable(available_media_setter):
                available_media_setter(
                    available_media
                )

            subtitle_setter = getattr(
                workspace,
                "set_subtitles",
                None,
            )

            if callable(subtitle_setter):
                subtitle_setter(
                    subtitles
                )

            available_subtitle_setter = getattr(
                workspace,
                "set_available_subtitles",
                None,
            )

            if callable(available_subtitle_setter):
                available_subtitle_setter(
                    subtitles
                )

    # =========================================================
    # OPERATION
    # =========================================================

    def _operation_changed(
        self,
        operation: str,
    ) -> None:
        if operation not in PROCESSING_OPERATIONS:
            operation = "convert"

            try:
                self.operation_selector.set_operation(
                    operation
                )

            except (
                AttributeError,
                TypeError,
            ):
                pass

        self.operation = operation

        workspace = self.workspaces.get(
            operation
        )

        if workspace is not None:
            index = self.workspace_stack.indexOf(
                workspace
            )

            if index >= 0:
                self.workspace_stack.setCurrentIndex(
                    index
                )

        # -----------------------------------------------------
        # IMPORTANT:
        #
        # Changing operation does NOT modify working_media.
        #
        # Working media are controlled explicitly by:
        #
        #   Select...
        #   Browse
        #   Remove Selected
        #   Move Up / Move Down
        # -----------------------------------------------------

        self._update_working_label()
        self._sync_workspaces()
        self._update_output_defaults()
        self._update_output_preview()
        self._update_stream_choices()

        self.operationChanged.emit(
            operation
        )

    # =========================================================
    # EXTRACT SETTINGS
    # =========================================================

    def _extract_settings_changed(self) -> None:
        """
        Extract settings can change the default suffix and output
        extension.

        Output Settings remains the owner of:
            - output directory
            - custom output name
        """

        if self.operation != "extract":
            return

        if not self.output_settings.user_modified_name:
            self._update_output_defaults()

        self._update_output_preview()

    # =========================================================
    # SUBTITLES
    # =========================================================

    def set_subtitle_files(
        self,
        files: list[Path],
    ) -> None:
        self.subtitle_files = []

        for path in files:
            path = Path(
                path
            )

            if not path.is_file():
                continue

            if path.suffix.lower() not in {
                ".srt",
                ".ass",
                ".ssa",
                ".vtt",
            }:
                continue

            if path not in self.subtitle_files:
                self.subtitle_files.append(
                    path
                )

        self._sync_workspaces()

    def add_subtitle_files(
        self,
        files: list[Path],
    ) -> None:
        current = list(
            self.subtitle_files
        )

        for path in files:
            path = Path(
                path
            )

            if (
                path.is_file()
                and path.suffix.lower()
                in {
                    ".srt",
                    ".ass",
                    ".ssa",
                    ".vtt",
                }
                and path not in current
            ):
                current.append(
                    path
                )

        self.set_subtitle_files(
            current
        )

    # =========================================================
    # OUTPUT
    # =========================================================

    def _output_settings_changed(self) -> None:
        self._update_output_preview()

    def _update_output_defaults(self) -> None:
        if not self.working_media:
            return

        self.output_settings.set_default_directory(
            self.working_media[0].parent
        )

        if self.output_settings.user_modified_name:
            return

        # -----------------------------------------------------
        # Extract suffix depends on extraction type.
        # -----------------------------------------------------

        if self.operation == "extract":
            workspace = self.workspaces.get(
                "extract"
            )

            extract_type = "audio"

            if workspace is not None:
                stream_type = getattr(
                    workspace,
                    "stream_type",
                    None,
                )

                if stream_type is not None:
                    extract_type = (
                        stream_type.currentData()
                        or "audio"
                    )

            suffix = {
                "audio": "_audio",
                "video": "_video",
                "subtitle": "_subtitle",
            }.get(
                extract_type,
                "_audio",
            )

        else:
            suffixes = {
                "convert": "_converted",
                "cut": "",
                "join": "_joined",
                "burn_subtitles": "_burned",
                "mux": "_muxed",
                "compress": "_compressed",
            }

            suffix = suffixes.get(
                self.operation,
                "",
            )

        # -----------------------------------------------------
        # Batch
        # -----------------------------------------------------

        if len(self.working_media) != 1:
            self.output_settings.set_name(
                "",
                force=True,
            )

            self.output_settings.output_name.setPlaceholderText(
                "Optional name; batch uses source names"
            )

            return

        source = self.working_media[0]

        self.output_settings.set_name(
            source.stem
            + suffix
        )

    def _update_output_preview(self) -> None:
        if not self.working_media:
            self.output_settings.set_preview(
                "Output: not configured."
            )
            return

        directory = (
            self.output_settings.directory
            or self.working_media[0].parent
        )

        # -----------------------------------------------------
        # CUT
        # -----------------------------------------------------

        if self.operation == "cut":
            self.output_settings.set_preview(
                "Output directory:\n"
                f"{directory}\n\n"
                "Each source creates its own numbered parts."
            )
            return

        workspace = self.workspaces.get(
            self.operation
        )

        if workspace is None:
            self.output_settings.set_preview(
                "Output: not configured."
            )
            return

        name = (
            self.output_settings.output_name.text()
            .strip()
        )

        # -----------------------------------------------------
        # JOIN / MUX
        # -----------------------------------------------------

        if self.operation in {
            "join",
            "mux",
        }:
            suffix = (
                "_joined"
                if self.operation == "join"
                else "_muxed"
            )

            base = name or (
                self.working_media[0].stem
                + suffix
            )

            extension = (
                self.working_media[0]
                .suffix
                .lstrip(".")
                or "mkv"
            )

            path = (
                directory
                / f"{base}.{extension}"
            )

            self.output_settings.set_preview(
                f"Output:\n{path}"
            )

            return

        # -----------------------------------------------------
        # PER-SOURCE OPERATIONS
        # -----------------------------------------------------

        previews: list[str] = []

        for source in self.working_media[:5]:

            # -------------------------------------------------
            # CONVERT
            # -------------------------------------------------

            if self.operation == "convert":
                extension = self._combo_extension(
                    getattr(
                        workspace,
                        "output_format",
                        None,
                    ),
                    fallback="mp4",
                )

                suffix = "_converted"

            # -------------------------------------------------
            # COMPRESS
            # -------------------------------------------------

            elif self.operation == "compress":
                selected = self._combo_text(
                    getattr(
                        workspace,
                        "output_format",
                        None,
                    )
                )

                audio_extensions = {
                    ".mp3",
                    ".wav",
                    ".flac",
                    ".aac",
                    ".m4a",
                    ".ogg",
                    ".opus",
                }

                if (
                    not selected
                    or selected.lower() == "auto"
                ):
                    extension = (
                        source.suffix.lstrip(".")
                        if source.suffix.lower()
                        in audio_extensions
                        else "mp4"
                    )

                else:
                    extension = selected.lstrip(
                        "."
                    )

                suffix = "_compressed"

            # -------------------------------------------------
            # EXTRACT
            # -------------------------------------------------

            elif self.operation == "extract":
                extension = self._combo_extension(
                    getattr(
                        workspace,
                        "output_format",
                        None,
                    ),
                    fallback="m4a",
                )

                stream_type_widget = getattr(
                    workspace,
                    "stream_type",
                    None,
                )

                stream_type = "audio"

                if stream_type_widget is not None:
                    stream_type = (
                        stream_type_widget.currentData()
                        or "audio"
                    )

                suffix = {
                    "audio": "_audio",
                    "video": "_video",
                    "subtitle": "_subtitle",
                }.get(
                    stream_type,
                    "_audio",
                )

            # -------------------------------------------------
            # BURN
            # -------------------------------------------------

            elif self.operation == "burn_subtitles":
                extension = (
                    source.suffix.lstrip(".")
                    or "mp4"
                )

                suffix = "_burned"

            # -------------------------------------------------
            # OTHER
            # -------------------------------------------------

            else:
                extension = (
                    source.suffix.lstrip(".")
                    or "mp4"
                )

                suffix = ""

            # -------------------------------------------------
            # OUTPUT NAME
            # -------------------------------------------------

            if name:
                if len(self.working_media) > 1:
                    base = (
                        f"{source.stem}_{name}"
                    )

                else:
                    base = name

            else:
                base = (
                    source.stem
                    + suffix
                )

            previews.append(
                str(
                    directory
                    / f"{base}.{extension}"
                )
            )

        text = (
            "Output preview:\n"
            + "\n".join(
                previews
            )
        )

        if len(self.working_media) > 5:
            text += (
                f"\n… and "
                f"{len(self.working_media) - 5} more"
            )

        self.output_settings.set_preview(
            text
        )

    @staticmethod
    def _combo_text(
        combo: Any,
    ) -> str:
        if combo is None:
            return ""

        try:
            return (
                combo.currentText()
                .strip()
            )

        except (
            AttributeError,
            TypeError,
        ):
            return ""

    @classmethod
    def _combo_extension(
        cls,
        combo: Any,
        *,
        fallback: str,
    ) -> str:
        text = cls._combo_text(
            combo
        )

        if not text:
            return fallback

        return text.lstrip(
            "."
        )

    # =========================================================
    # JOB BUILDING
    # =========================================================

    def _build_jobs(
        self,
    ) -> list[MediaEngineJob]:
        media = list(
            self.working_media
        )

        if not media:
            raise ValueError(
                "No media files have been selected."
            )

        if self.operation not in PROCESSING_OPERATIONS:
            raise ValueError(
                f"Unsupported operation: "
                f"{self.operation}"
            )

        workspace = self.workspaces.get(
            self.operation
        )

        if workspace is None:
            raise ValueError(
                f"Unsupported operation: "
                f"{self.operation}"
            )

        jobs = workspace.build_jobs(
            media,
            self.output_settings.directory,
            self.output_settings.output_name.text(),
            self.shared_settings.values(),
        )

        if jobs is None:
            return []

        return list(
            jobs
        )

    # =========================================================
    # RUN
    # =========================================================

    def _run(self) -> None:
        if self._processing:
            return

        try:
            jobs = self._build_jobs()

        except Exception as exc:
            QMessageBox.warning(
                self,
                "Cannot Start",
                str(exc),
            )
            return

        if not jobs:
            QMessageBox.warning(
                self,
                "No Jobs",
                "There is nothing to process.",
            )
            return

        jobs = self._resolve_output_conflicts(
            jobs
        )

        if jobs is None:
            return

        self._batch_total = len(
            jobs
        )

        self._batch_completed = 0
        self._batch_current = 0
        self._batch_current_name = ""

        self._set_processing_state(
            True
        )

        self.progress_panel.set_progress(
            0,
            f"Starting batch: {len(jobs)} job(s)...",
        )

        thread = QThread(
            self
        )

        worker = MediaEngineWorker(
            jobs,
            ffmpeg=self.ffmpeg,
            ffprobe=self.ffprobe,
        )

        worker.moveToThread(
            thread
        )

        self._worker_thread = thread
        self._worker = worker

        # -----------------------------------------------------
        # START
        # -----------------------------------------------------

        thread.started.connect(
            worker.run
        )

        # -----------------------------------------------------
        # WORKER EVENTS
        # -----------------------------------------------------

        worker.progress.connect(
            self._worker_progress
        )

        worker.error.connect(
            self._worker_error
        )

        worker.job_event.connect(
            self._worker_job_event
        )

        worker.finished.connect(
            self._worker_finished
        )

        worker.cancelled.connect(
            self._worker_cancelled
        )

        worker.failed.connect(
            self._worker_failed
        )

        # -----------------------------------------------------
        # TERMINAL EVENTS
        # -----------------------------------------------------

        worker.finished.connect(
            thread.quit
        )

        worker.cancelled.connect(
            thread.quit
        )

        worker.failed.connect(
            thread.quit
        )

        # -----------------------------------------------------
        # WORKER CLEANUP
        # -----------------------------------------------------

        worker.finished.connect(
            worker.deleteLater
        )

        worker.cancelled.connect(
            worker.deleteLater
        )

        worker.failed.connect(
            worker.deleteLater
        )

        # -----------------------------------------------------
        # THREAD CLEANUP
        # -----------------------------------------------------

        thread.finished.connect(
            thread.deleteLater
        )

        thread.finished.connect(
            self._worker_thread_finished
        )

        thread.start()

    # =========================================================
    # PROCESSING STATE
    # =========================================================

    def _set_processing_state(
        self,
        processing: bool,
    ) -> None:
        self._processing = processing

        self.start_button.setEnabled(
            not processing
        )

        self.cancel_button.setEnabled(
            processing
        )

        self.operation_selector.set_enabled(
            not processing
        )

        self.media_library.set_enabled(
            not processing
        )

        self.working_media_column.set_enabled(
            not processing
        )

    # =========================================================
    # CONFLICTS
    # =========================================================

    def _resolve_output_conflicts(
        self,
        jobs: list[MediaEngineJob],
    ) -> list[MediaEngineJob] | None:
        if self.shared_settings.overwrite.isChecked():
            return jobs

        conflicts: list[Path] = []

        for job in jobs:
            output = job.output

            if isinstance(
                output,
                Path,
            ) and output.exists():
                conflicts.append(
                    output
                )

        # Cut outputs are generated internally by the cutter.
        if self.operation == "cut":
            return jobs

        if not conflicts:
            return jobs

        preview = "\n".join(
            str(path)
            for path in conflicts[:10]
        )

        if len(conflicts) > 10:
            preview += (
                f"\n… and {len(conflicts) - 10} more"
            )

        answer = QMessageBox.question(
            self,
            "Files Already Exist",
            "The following output files already exist:\n\n"
            + preview
            + "\n\nOverwrite them?",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if answer != QMessageBox.StandardButton.Yes:
            return None

        replaced: list[MediaEngineJob] = []

        for job in jobs:
            settings = job.settings

            if (
                settings is not None
                and hasattr(
                    settings,
                    "overwrite",
                )
            ):
                try:
                    settings = dataclasses.replace(
                        settings,
                        overwrite=True,
                    )

                except (
                    TypeError,
                    ValueError,
                ):
                    pass

            replaced.append(
                MediaEngineJob(
                    operation=job.operation,
                    inputs=job.inputs,
                    output=job.output,
                    settings=settings,
                    options=job.options,
                )
            )

        return replaced

    # =========================================================
    # PROGRESS
    # =========================================================

    def _worker_progress(
        self,
        percent: int,
        message: str,
    ) -> None:
        total = self._batch_total

        if total <= 0:
            return

        completed = min(
            self._batch_completed,
            total,
        )

        overall = int(
            (
                completed * 100
                + percent
            )
            / total
        )

        overall = max(
            0,
            min(
                100,
                overall,
            ),
        )

        if self._batch_current_name:
            prefix = (
                f"Job "
                f"{self._batch_current}/"
                f"{total} — "
                f"{self._batch_current_name}"
            )

        else:
            prefix = (
                f"Job "
                f"{max(1, self._batch_current)}/"
                f"{total}"
            )

        if message:
            text = (
                f"{prefix}: {message}"
            )

        else:
            text = (
                f"{prefix}: {percent}%"
            )

        self.progress_panel.set_progress(
            overall,
            text,
        )

    # =========================================================
    # JOB EVENTS
    # =========================================================

    def _worker_job_event(
        self,
        event: str,
        data: Any,
    ) -> None:
        event_name = str(
            event
        ).lower()

        # -----------------------------------------------------
        # STARTED
        # -----------------------------------------------------

        if event_name == "started":
            self._batch_current = min(
                self._batch_current + 1,
                self._batch_total,
            )

            self._batch_current_name = (
                self._job_name(data)
            )

            self.progress_panel.set_message(
                f"Processing job "
                f"{self._batch_current}/"
                f"{self._batch_total}"
                + (
                    f": {self._batch_current_name}"
                    if self._batch_current_name
                    else ""
                )
            )

            return

        # -----------------------------------------------------
        # TERMINAL JOB EVENTS
        # -----------------------------------------------------

        if event_name in {
            "completed",
            "failed",
            "cancelled",
        }:
            self._batch_completed = min(
                self._batch_completed + 1,
                self._batch_total,
            )

            if self._batch_total > 0:
                percent = int(
                    self._batch_completed
                    / self._batch_total
                    * 100
                )

            else:
                percent = 0

            if event_name == "failed":
                message = (
                    f"Job failed. Continuing batch "
                    f"({self._batch_completed}/"
                    f"{self._batch_total})..."
                )

            elif event_name == "cancelled":
                message = (
                    "Cancelling remaining jobs..."
                )

            else:
                message = (
                    f"Completed "
                    f"{self._batch_completed}/"
                    f"{self._batch_total}"
                )

            self.progress_panel.set_progress(
                percent,
                message,
            )

            return

        # -----------------------------------------------------
        # Do not count a secondary failure-record event.
        # -----------------------------------------------------

        if event_name == "failed_recorded":
            return

    @staticmethod
    def _job_name(
        data: Any,
    ) -> str:
        value = data

        if (
            isinstance(
                value,
                tuple,
            )
            and value
        ):
            value = value[0]

        if isinstance(
            value,
            MediaEngineJob,
        ):
            if value.inputs:
                return Path(
                    value.inputs[0]
                ).name

        inputs = getattr(
            value,
            "inputs",
            (),
        )

        if inputs:
            try:
                return Path(
                    inputs[0]
                ).name

            except (
                TypeError,
                ValueError,
            ):
                pass

        return ""

    # =========================================================
    # ERRORS
    # =========================================================

    def _worker_error(
        self,
        error: Any,
    ) -> None:
        """
        Display the latest non-modal processing error.

        A normal job failure does not stop the remaining batch.
        """

        self.progress_panel.set_message(
            str(error)
        )

    # =========================================================
    # FINISHED
    # =========================================================

    def _worker_finished(
        self,
        results: Any,
    ) -> None:
        """
        Process the complete batch result.

        The processor returns one MediaEngineJobResult per submitted
        job, including failed jobs.
        """

        self._set_processing_state(
            False
        )

        if not isinstance(
            results,
            (list, tuple),
        ):
            results = [
                results
            ]

        total = self._batch_total

        successful = 0
        failed = 0

        outputs: list[str] = []
        errors: list[str] = []

        for result in results:
            if not isinstance(
                result,
                MediaEngineJobResult,
            ):
                failed += 1

                errors.append(
                    "Invalid job result: "
                    f"{type(result).__name__}"
                )

                continue

            if result.error is not None:
                failed += 1

                errors.append(
                    f"{result.operation}: "
                    f"{result.error}"
                )

                continue

            if result.result is None:
                failed += 1

                errors.append(
                    f"{result.operation} returned no result."
                )

                continue

            successful += 1

            value = result.result

            # -------------------------------------------------
            # Single output
            # -------------------------------------------------

            output = getattr(
                value,
                "output",
                None,
            )

            if output:
                outputs.append(
                    str(output)
                )

            # -------------------------------------------------
            # Multiple outputs
            # -------------------------------------------------

            result_outputs = getattr(
                value,
                "outputs",
                None,
            )

            if result_outputs:
                outputs.extend(
                    str(item)
                    for item in result_outputs
                )

        # -----------------------------------------------------
        # Defensive invariant check.
        # -----------------------------------------------------

        returned_results = len(
            results
        )

        if returned_results < total:
            missing = (
                total
                - returned_results
            )

            failed += missing

            errors.append(
                f"{missing} job result(s) were not returned."
            )

        summary = (
            f"Total jobs: {total}\n"
            f"Completed: {successful}\n"
            f"Failed: {failed}"
        )

        # -----------------------------------------------------
        # OUTPUTS
        # -----------------------------------------------------

        if outputs:
            summary += (
                "\n\nOutputs:\n"
                + "\n".join(
                    outputs[:15]
                )
            )

            if len(outputs) > 15:
                summary += (
                    f"\n… and {len(outputs) - 15} more"
                )

        # -----------------------------------------------------
        # ERRORS
        # -----------------------------------------------------

        if errors:
            summary += (
                "\n\nErrors:\n"
                + "\n".join(
                    f"• {error}"
                    for error in errors[:10]
                )
            )

            if len(errors) > 10:
                summary += (
                    f"\n… and {len(errors) - 10} more"
                )

        # -----------------------------------------------------
        # PROGRESS
        # -----------------------------------------------------

        if failed:
            self.progress_panel.set_progress(
                100,
                "Batch complete with failures.",
            )

        else:
            self.progress_panel.set_progress(
                100,
                "Processing complete.",
            )

        # -----------------------------------------------------
        # MESSAGE
        # -----------------------------------------------------

        if failed and successful:
            QMessageBox.warning(
                self,
                "Batch Processing Complete",
                summary,
            )

        elif failed:
            QMessageBox.critical(
                self,
                "Batch Processing Complete",
                summary,
            )

        else:
            QMessageBox.information(
                self,
                "Processing Complete",
                summary,
            )

    # =========================================================
    # STREAM DATA
    # =========================================================

    def _update_stream_choices(self) -> None:
        """
        Give ExtractWorkspace the complete inspection data.

        ExtractWorkspace owns:
            - stream type
            - valid stream indexes
            - stream labels
            - stream selection

        MediaEnginePage does not manually manipulate the stream
        index anymore.
        """

        workspace = self.workspaces.get(
            "extract"
        )

        if workspace is None:
            return

        setter = getattr(
            workspace,
            "set_inspection_data",
            None,
        )

        if not callable(
            setter
        ):
            return

        if not self.working_media:
            setter(
                None
            )
            return

        source = Path(
            self.working_media[0]
        )

        data = self.inspection_cache.get(
            source
        )

        if isinstance(
            data,
            dict,
        ):
            setter(
                data
            )

        else:
            setter(
                None
            )

    # =========================================================
    # CANCEL
    # =========================================================

    def _cancel(self) -> None:
        if not self._processing:
            return

        worker = self._worker

        if worker is not None:
            worker.cancel()

        self.progress_panel.set_message(
            "Cancelling remaining jobs..."
        )

        self.cancel_button.setEnabled(
            False
        )

    def _worker_cancelled(self) -> None:
        self._set_processing_state(
            False
        )

        self.progress_panel.set_progress(
            0,
            "Processing cancelled.",
        )

    def _worker_failed(
        self,
        error: Any,
    ) -> None:
        self._set_processing_state(
            False
        )

        self.progress_panel.set_message(
            "Processing failed."
        )

        QMessageBox.critical(
            self,
            "Processing Failed",
            str(error),
        )

    # =========================================================
    # THREAD CLEANUP
    # =========================================================

    def _worker_thread_finished(self) -> None:
        """
        Final processing cleanup.

        Guarantees that Start Processing is available again after
        the worker thread has actually terminated.
        """

        self._set_processing_state(
            False
        )

        self._worker = None
        self._worker_thread = None

    # =========================================================
    # RESET
    # =========================================================

    def reset_page(self) -> None:
        if self._processing:
            self._cancel()

        self._cancel_inspection()

        self.media_library.clear()

        self.working_media.clear()
        self.working_media_column.clear()
        self.subtitle_files.clear()
        self.selected_media = None

        self.inspection_cache.clear()

        self.inspection_panel.clear()

        self._update_working_label()

        self.shared_settings.reset()

        for workspace in self.workspaces.values():
            reset = getattr(
                workspace,
                "reset",
                None,
            )

            if callable(
                reset
            ):
                reset()

        self.output_settings.reset()

        self.operation_selector.set_operation(
            "convert"
        )

        self.progress_panel.reset()

        self._set_processing_state(
            False
        )