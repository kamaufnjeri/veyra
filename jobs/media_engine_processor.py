from __future__ import annotations

import signal
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from services.media_engine_services import MediaEngineService
from media.models import (
    BurnerSettings,
    ConverterSettings,
    CutterSettings,
    JoinerSettings,
)


# ============================================================
# ERRORS
# ============================================================


class JobCancelled(Exception):
    """Raised when a media engine job is cancelled."""


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


@dataclass(frozen=True, slots=True)
class MediaEngineJobResult:
    """
    Result returned after a successful operation.
    """

    operation: str
    inputs: tuple[Path, ...]
    output: Path | None
    result: Any = None


# ============================================================
# PROCESSOR
# ============================================================


class MediaEngineProcessor:
    """
    Processes media engine jobs.

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

    def _create_service(self) -> MediaEngineService:
        """
        Create a fresh MediaEngineService for the current
        processing operation.

        This follows the same pattern as:

            service = SubtitleService(...)

        inside SubtitleProcessor.process().
        """

        return MediaEngineService(
            ffmpeg=self.ffmpeg,
            ffprobe=self.ffprobe,
            progress_callback=self.progress_callback,
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

        MediaEngineService is created here and all operations
        are executed through its public API.
        """

        self.check_cancelled()

        if not isinstance(job, MediaEngineJob):
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

            service = self._create_service()

            self.check_cancelled()

            # --------------------------------------------------
            # DISPATCH THROUGH SERVICE
            # --------------------------------------------------

            result = self._dispatch(
                service,
                job,
            )

            self.check_cancelled()

            output = MediaEngineJobResult(
                operation=job.operation,
                inputs=job.inputs,
                output=job.output,
                result=result,
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

            self._emit_error(exc)

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

        The processor does NOT access:

            service.converter
            service.cutter
            service.joiner
            service.burner

        directly.

        Everything goes through the public MediaEngineService API.
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

            self._require_output(job)

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

            self._require_output(job)

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
        # BURN SUBTITLES
        # ======================================================

        if operation == "burn_subtitles":
            self._require_inputs(
                job,
                2,
            )

            self._require_output(job)

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

        Individual failures are reported and processing continues.

        Cancellation stops the batch.
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
                    result = self.process(job)

                    results.append(result)

                except JobCancelled:
                    raise

                except KeyboardInterrupt:
                    self.cancel()

                    raise JobCancelled(
                        "Media processing cancelled by user."
                    )

                except Exception as exc:
                    self._emit_error(exc)

                    # Continue processing the remaining jobs.
                    continue

        finally:
            self._restore_signal_handler()

        return results
