from __future__ import annotations

import signal
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from media.models import (
    BurnerSettings,
    CompressorSettings,
    ConverterSettings,
    CutterSettings,
    ExtractorSettings,
    JoinerSettings,
    MuxerSettings,
)

from services.media_engine_services import MediaEngineService


# ============================================================
# ERRORS
# ============================================================


class JobCancelled(Exception):
    """
    Raised when a media engine job is cancelled.
    """


# ============================================================
# JOB
# ============================================================


@dataclass(frozen=True, slots=True)
class MediaEngineJob:
    """
    One executable media engine operation.
    """

    operation: str
    inputs: tuple[Path, ...]
    output: Path | None = None
    settings: Any = None
    options: dict[str, Any] | None = None


# ============================================================
# JOB RESULT
# ============================================================


@dataclass(frozen=True, slots=True)
class MediaEngineJobResult:
    """
    Result returned for every submitted job.

    A job can either have:

        result
            Successful operation result.

    or:

        error
            Exception raised by the operation.

    This guarantees that batch results always preserve the
    relationship between submitted jobs and returned results.
    """

    operation: str
    inputs: tuple[Path, ...]
    output: Path | None
    result: Any = None
    error: Exception | None = None

    @property
    def succeeded(self) -> bool:
        """
        Return True when the job completed successfully.
        """

        return self.error is None and self.result is not None

    @property
    def failed(self) -> bool:
        """
        Return True when the job failed.
        """

        return self.error is not None


# ============================================================
# PROCESSOR
# ============================================================


class MediaEngineProcessor:
    """
    Processes MediaEngineJob objects.

    Responsibilities:

        - single job processing
        - batch processing
        - progress callbacks
        - error callbacks
        - cancellation
        - Ctrl+C / SIGINT
        - creating MediaEngineService
        - dispatching through MediaEngineService
        - preserving operation-specific settings

    The processor does not perform media operations itself.

    All actual media work is delegated to MediaEngineService.
    """

    def __init__(
        self,
        *,
        ffmpeg: str = "ffmpeg",
        ffprobe: str = "ffprobe",
        progress_callback: Callable[..., None] | None = None,
        error_callback: Callable[[Any], None] | None = None,
        job_callback: Callable[..., None] | None = None,
    ) -> None:

        self.ffmpeg = ffmpeg
        self.ffprobe = ffprobe

        self.progress_callback = progress_callback
        self.error_callback = error_callback
        self.job_callback = job_callback

        self.cancelled = False

        self._original_sigint_handler = None

    # ==========================================================
    # CANCELLATION
    # ==========================================================

    def cancel(self) -> None:
        """
        Request cancellation.
        """

        self.cancelled = True

    def reset_cancellation(self) -> None:
        """
        Reset cancellation before starting a new processing session.
        """

        self.cancelled = False

    def check_cancelled(self) -> None:
        """
        Raise JobCancelled when cancellation has been requested.
        """

        if self.cancelled:
            raise JobCancelled(
                "Media processing cancelled."
            )

    # ==========================================================
    # SIGNAL HANDLING
    # ==========================================================

    def _install_signal_handler(self) -> None:
        """
        Install Ctrl+C handling when running from the main thread.
        """

        try:
            if (
                threading.current_thread()
                is not threading.main_thread()
            ):
                return

            self._original_sigint_handler = signal.getsignal(
                signal.SIGINT
            )

            signal.signal(
                signal.SIGINT,
                self._handle_sigint,
            )

        except (
            ValueError,
            AttributeError,
            RuntimeError,
        ):
            pass

    def _restore_signal_handler(self) -> None:
        """
        Restore the original SIGINT handler.
        """

        if self._original_sigint_handler is None:
            return

        try:
            signal.signal(
                signal.SIGINT,
                self._original_sigint_handler,
            )

        except (
            ValueError,
            AttributeError,
            RuntimeError,
        ):
            pass

        finally:
            self._original_sigint_handler = None

    def _handle_sigint(
        self,
        signum: int,
        frame: Any,
    ) -> None:
        """
        Handle Ctrl+C.
        """

        self.cancel()

        self._emit_error(
            "KeyboardInterrupt: "
            "Media processing interrupted by user."
        )

    # ==========================================================
    # CALLBACKS
    # ==========================================================

    def _emit_progress(
        self,
        *args: Any,
    ) -> None:
        if self.progress_callback is None:
            return

        try:
            self.progress_callback(*args)

        except Exception:
            pass

    def _emit_error(
        self,
        error: Any,
    ) -> None:
        if self.error_callback is None:
            return

        try:
            self.error_callback(error)

        except Exception:
            pass

    def _emit_job(
        self,
        *args: Any,
    ) -> None:
        if self.job_callback is None:
            return

        try:
            self.job_callback(*args)

        except Exception:
            pass

    # ==========================================================
    # SERVICE
    # ==========================================================

    def _create_service(
        self,
        job: MediaEngineJob,
    ) -> MediaEngineService:
        """
        Create a MediaEngineService for the current job.
        """

        def on_progress(progress: float) -> None:
            self._emit_progress(
                job,
                progress,
                "Processing",
            )

        return MediaEngineService(
            ffmpeg=self.ffmpeg,
            ffprobe=self.ffprobe,
            progress_callback=on_progress,
            cancellation_callback=self.check_cancelled,
        )

    # ==========================================================
    # SINGLE JOB
    # ==========================================================

    def process(
        self,
        job: MediaEngineJob,
    ) -> MediaEngineJobResult:
        """
        Process a single media engine job.

        A normal exception is raised to the caller so that batch
        processing can record the failure.

        Cancellation remains separate from ordinary failure.
        """

        self.check_cancelled()

        if not isinstance(
            job,
            MediaEngineJob,
        ):
            raise TypeError(
                "Expected MediaEngineJob."
            )

        self._emit_job(
            "started",
            job,
        )

        self._emit_progress(
            job,
            0.0,
            "Starting",
        )

        try:
            # --------------------------------------------------
            # CREATE SERVICE
            # --------------------------------------------------

            service = self._create_service(
                job,
            )

            self.check_cancelled()

            # --------------------------------------------------
            # DISPATCH
            # --------------------------------------------------

            result = self._dispatch(
                service,
                job,
            )

            self.check_cancelled()

            # --------------------------------------------------
            # RESULT
            # --------------------------------------------------

            output = MediaEngineJobResult(
                operation=job.operation,
                inputs=job.inputs,
                output=job.output,
                result=result,
                error=None,
            )

            self._emit_progress(
                job,
                1.0,
                "Completed",
            )

            self._emit_job(
                "completed",
                output,
            )

            return output

        except JobCancelled:
            self._emit_job(
                "cancelled",
                job,
            )

            raise

        except KeyboardInterrupt:
            self.cancel()

            self._emit_job(
                "cancelled",
                job,
            )

            raise JobCancelled(
                "Media processing cancelled by user."
            )

        except Exception as exc:
            self._emit_job(
                "failed",
                job,
                exc,
            )

            self._emit_error(
                exc,
            )

            raise

    # ==========================================================
    # DISPATCH
    # ==========================================================

    def _dispatch(
        self,
        service: MediaEngineService,
        job: MediaEngineJob,
    ) -> Any:
        """
        Dispatch the job through MediaEngineService.
        """

        self.check_cancelled()

        operation = job.operation
        options = job.options or {}

        # ======================================================
        # INSPECT
        # ======================================================

        if operation == "inspect":
            self._require_inputs(
                job,
                1,
            )

            return service.inspect(
                job.inputs[0],
                include_subtitle_text=options.get(
                    "include_subtitle_text",
                    False,
                ),
                include_raw=options.get(
                    "include_raw",
                    False,
                ),
            )

        # ======================================================
        # INSPECT JSON
        # ======================================================

        if operation == "inspect_json":
            self._require_inputs(
                job,
                1,
            )

            return service.inspect_json(
                job.inputs[0],
                include_subtitle_text=options.get(
                    "include_subtitle_text",
                    False,
                ),
                include_raw=options.get(
                    "include_raw",
                    False,
                ),
                indent=options.get(
                    "indent",
                    2,
                ),
            )

        # ======================================================
        # CONVERT
        # ======================================================

        if operation == "convert":
            self._require_inputs(
                job,
                1,
            )

            self._require_output(
                job,
            )

            settings = job.settings

            if settings is None:
                settings = ConverterSettings()

            if not isinstance(
                settings,
                ConverterSettings,
            ):
                raise TypeError(
                    "convert requires ConverterSettings."
                )

            return service.convert(
                input_path=job.inputs[0],
                output_path=job.output,
                settings=settings,
            )

        # ======================================================
        # CUT
        # ======================================================

        if operation == "cut":
            self._require_inputs(
                job,
                1,
            )

            settings = job.settings

            if settings is None:
                settings = CutterSettings()

            if not isinstance(
                settings,
                CutterSettings,
            ):
                raise TypeError(
                    "cut requires CutterSettings."
                )

            return service.cut(
                input_path=job.inputs[0],
                settings=settings,
            )

        # ======================================================
        # JOIN
        # ======================================================

        if operation == "join":
            if not job.inputs:
                raise ValueError(
                    "join requires at least one input."
                )

            self._require_output(
                job,
            )

            settings = job.settings

            if settings is None:
                settings = JoinerSettings()

            if not isinstance(
                settings,
                JoinerSettings,
            ):
                raise TypeError(
                    "join requires JoinerSettings."
                )

            return service.join(
                inputs=job.inputs,
                output=job.output,
                settings=settings,
            )

        # ======================================================
        # MUX
        # ======================================================

        if operation == "mux":
            if len(job.inputs) < 2:
                raise ValueError(
                    "mux requires at least two inputs."
                )

            self._require_output(
                job,
            )

            settings = job.settings

            if settings is None:
                settings = MuxerSettings()

            if not isinstance(
                settings,
                MuxerSettings,
            ):
                raise TypeError(
                    "mux requires MuxerSettings."
                )

            return service.mux(
                inputs=job.inputs,
                output=job.output,
                settings=settings,
            )

        # ======================================================
        # COMPRESS
        # ======================================================

        if operation == "compress":
            self._require_inputs(
                job,
                1,
            )

            self._require_output(
                job,
            )

            settings = job.settings

            if settings is None:
                settings = CompressorSettings()

            if not isinstance(
                settings,
                CompressorSettings,
            ):
                raise TypeError(
                    "compress requires CompressorSettings."
                )

            return service.compress(
                input_path=job.inputs[0],
                output_path=job.output,
                settings=settings,
            )

        # ======================================================
        # EXTRACT
        # ======================================================

        if operation == "extract":
            self._require_inputs(
                job,
                1,
            )

            self._require_output(
                job,
            )

            settings = job.settings

            if settings is None:
                settings = ExtractorSettings()

            if not isinstance(
                settings,
                ExtractorSettings,
            ):
                raise TypeError(
                    "extract requires ExtractorSettings."
                )

            return service.extract(
                input_path=job.inputs[0],
                output_path=job.output,
                settings=settings,
            )

        # ======================================================
        # BURN SUBTITLES
        # ======================================================

        if operation == "burn_subtitles":
            self._require_inputs(
                job,
                2,
            )

            self._require_output(
                job,
            )

            settings = job.settings

            if settings is None:
                settings = BurnerSettings()

            if not isinstance(
                settings,
                BurnerSettings,
            ):
                raise TypeError(
                    "burn_subtitles requires BurnerSettings."
                )

            return service.burn_subtitles(
                video=job.inputs[0],
                subtitle=job.inputs[1],
                output=job.output,
                settings=settings,
            )

        # ======================================================
        # UNKNOWN OPERATION
        # ======================================================

        raise ValueError(
            f"Unsupported media operation: {operation}"
        )

    # ==========================================================
    # VALIDATION
    # ==========================================================

    @staticmethod
    def _require_inputs(
        job: MediaEngineJob,
        count: int,
    ) -> None:
        """
        Require an exact number of inputs.
        """

        if len(job.inputs) != count:
            raise ValueError(
                f"{job.operation} requires exactly "
                f"{count} input(s), got "
                f"{len(job.inputs)}."
            )

    @staticmethod
    def _require_output(
        job: MediaEngineJob,
    ) -> None:
        """
        Require an output path.
        """

        if job.output is None:
            raise ValueError(
                f"{job.operation} requires an output path."
            )

    # ==========================================================
    # BATCH
    # ==========================================================

    def process_jobs(
        self,
        jobs: Iterable[MediaEngineJob],
    ) -> list[MediaEngineJobResult]:
        """
        Process jobs sequentially.

        Every submitted job produces exactly one result unless the
        entire batch is cancelled.

        Individual failures are recorded in MediaEngineJobResult
        and processing continues with the remaining jobs.

        Cancellation stops the entire batch.
        """

        job_list = list(jobs)

        if not job_list:
            return []

        self.reset_cancellation()
        self._install_signal_handler()

        results: list[MediaEngineJobResult] = []

        try:
            total = len(job_list)

            for index, job in enumerate(
                job_list,
                start=1,
            ):
                self.check_cancelled()

                self._emit_progress(
                    job,
                    0.0,
                    f"Processing job {index} of {total}",
                )

                try:
                    result = self.process(
                        job,
                    )

                    results.append(
                        result,
                    )

                except JobCancelled:
                    raise

                except KeyboardInterrupt:
                    self.cancel()

                    raise JobCancelled(
                        "Media processing cancelled by user."
                    )

                except Exception as exc:
                    # ------------------------------------------
                    # IMPORTANT:
                    #
                    # Do NOT discard the failed job.
                    #
                    # The GUI needs one result for every submitted
                    # job so it can correctly report:
                    #
                    # Total jobs
                    # Completed
                    # Failed
                    # ------------------------------------------

                    failed_result = MediaEngineJobResult(
                        operation=job.operation,
                        inputs=job.inputs,
                        output=job.output,
                        result=None,
                        error=exc,
                    )

                    results.append(
                        failed_result,
                    )

                    self._emit_job(
                        "failed_recorded",
                        failed_result,
                    )

                    self._emit_error(
                        exc,
                    )

                    # Continue with the next job.
                    continue

        finally:
            self._restore_signal_handler()

        return results