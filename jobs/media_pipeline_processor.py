from __future__ import annotations

import signal
import threading

from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from services import MediaPipelineService


class JobCancelled(Exception):
    """Raised when a media processing job is cancelled."""


class MediaPipelineServiceProcessor:
    """
    High-level media job processor.

    This class is an orchestration layer only.

    All actual media functionality belongs to MediaPipelineService.

        MediaPipelineServiceProcessor
                    |
                    v
        MediaPipelineService
                    |
                    +-- Probe
                    +-- Converter
                    +-- Concatenator
                    +-- Joiner
                    +-- Muxer
                    +-- Extractor
                    +-- Cutter
                    +-- SubtitleBurner

    This class deliberately does NOT import or instantiate any
    lower-level media classes.

    Progress callbacks are represented using Callable rather than
    relying on a separate ProgressCallback type.
    """

    OPERATIONS = {
        "inspect",
        "duration",
        "convert",
        "concatenate",
        "join",
        "mux",
        "extract_audio",
        "extract_subtitle",
        "trim",
        "burn_subtitles",
    }

    def __init__(
        self,
        pipeline: MediaPipelineService | None = None,
        *,
        progress_callback: Callable[..., None] | None = None,
        error_callback: Callable[[Exception], None] | None = None,
        overwrite_callback: Callable[[str], bool] | None = None,
        overwrite_mode: str = "overwrite",
    ) -> None:
        self.pipeline = (
            pipeline
            if pipeline is not None
            else MediaPipelineService()
        )

        self.progress_callback = progress_callback
        self.error_callback = error_callback
        self.overwrite_callback = overwrite_callback

        self.overwrite_mode = (
            self._validate_overwrite_mode(
                overwrite_mode
            )
        )

        self.cancelled = False
        self._cancel_event = threading.Event()

        self._original_sigint_handler: Any = None

    # ==========================================================
    # VALIDATION
    # ==========================================================

    @classmethod
    def _validate_operation(
        cls,
        operation: str,
    ) -> str:
        operation = (
            str(operation)
            .strip()
            .lower()
        )

        if operation not in cls.OPERATIONS:
            raise ValueError(
                f"Unsupported media operation: "
                f"{operation!r}. "
                f"Supported operations: "
                f"{', '.join(sorted(cls.OPERATIONS))}"
            )

        return operation

    @staticmethod
    def _validate_overwrite_mode(
        mode: str,
    ) -> str:
        mode = (
            str(mode)
            .strip()
            .lower()
        )

        if mode not in {
            "keep",
            "ask",
            "overwrite",
        }:
            raise ValueError(
                "overwrite_mode must be "
                "'keep', 'ask', or 'overwrite'."
            )

        return mode

    # ==========================================================
    # CANCELLATION
    # ==========================================================

    def cancel(self) -> None:
        """
        Cancel the current job.

        If MediaPipelineService exposes a cancel() method, forward
        cancellation to it as well.
        """

        self.cancelled = True
        self._cancel_event.set()

        cancel = getattr(
            self.pipeline,
            "cancel",
            None,
        )

        if callable(cancel):
            try:
                cancel()
            except Exception:
                pass

    def check_cancelled(self) -> None:
        """Raise JobCancelled if cancellation was requested."""

        if (
            self.cancelled
            or self._cancel_event.is_set()
        ):
            raise JobCancelled(
                "Media processing was cancelled."
            )

    # ==========================================================
    # SIGNAL HANDLING
    # ==========================================================

    def _install_signal_handler(self) -> None:
        """
        Install a SIGINT handler when running in the main thread.
        """

        if (
            threading.current_thread()
            is not threading.main_thread()
        ):
            return

        try:
            self._original_sigint_handler = (
                signal.getsignal(signal.SIGINT)
            )

            signal.signal(
                signal.SIGINT,
                self._handle_sigint,
            )

        except (
            ValueError,
            RuntimeError,
        ):
            pass

    def _restore_signal_handler(self) -> None:
        """Restore the original SIGINT handler."""

        if self._original_sigint_handler is None:
            return

        try:
            signal.signal(
                signal.SIGINT,
                self._original_sigint_handler,
            )

        except (
            ValueError,
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
        """Handle Ctrl+C."""

        self.cancel()

    # ==========================================================
    # PROGRESS
    # ==========================================================

    def _progress(
        self,
        info: str = "",
        filename: str = "",
        percentage: float | int = 0,
        downloaded: Any = "--",
        speed: Any = "--",
        eta: Any = "--:--",
    ) -> None:
        """
        Send progress information to the configured callback.

        Preferred callback signature:

            callback(
                info,
                filename,
                percentage,
                downloaded,
                speed,
                eta,
            )

        Older 3-argument callbacks are also supported:

            callback(
                info,
                filename,
                percentage,
            )
        """

        callback = self.progress_callback

        if callback is None:
            return

        try:
            callback(
                info,
                filename,
                percentage,
                downloaded,
                speed,
                eta,
            )

        except TypeError:
            # Backwards compatibility with older callbacks.
            try:
                callback(
                    info,
                    filename,
                    percentage,
                )
            except Exception:
                pass

        except Exception:
            # Progress reporting must never break media processing.
            pass

    # ==========================================================
    # ERROR
    # ==========================================================

    def _report_error(
        self,
        error: Exception,
    ) -> None:
        """Send an exception to the configured error callback."""

        callback = self.error_callback

        if callback is None:
            return

        try:
            callback(error)
        except Exception:
            pass

    # ==========================================================
    # OUTPUT
    # ==========================================================

    @staticmethod
    def _output_path(
        value: str | Path,
    ) -> Path:
        """
        Normalize an output path and create its parent directory.
        """

        path = Path(
            value
        ).expanduser()

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        return path

    def _can_write(
        self,
        output: str | Path,
    ) -> bool:
        """
        Determine whether an existing output may be replaced.
        """

        path = Path(
            output
        ).expanduser()

        if not path.exists():
            return True

        if self.overwrite_mode == "overwrite":
            return True

        if self.overwrite_mode == "keep":
            return False

        if self.overwrite_callback is None:
            return False

        try:
            return bool(
                self.overwrite_callback(
                    str(path)
                )
            )
        except Exception:
            return False

    # ==========================================================
    # SINGLE OPERATION
    # ==========================================================

    def process(
        self,
        operation: str,
        **kwargs: Any,
    ) -> Any:
        """
        Execute one MediaPipelineService operation.

        The processor performs orchestration only and delegates the
        actual media operation to MediaPipelineService.
        """

        self.check_cancelled()

        operation = self._validate_operation(
            operation
        )

        handler = getattr(
            self,
            f"_process_{operation}",
        )

        try:
            return handler(
                **kwargs
            )

        except JobCancelled:
            raise

        except Exception as exc:
            self._report_error(exc)
            raise

    # ==========================================================
    # INSPECT
    # ==========================================================

    def _process_inspect(
        self,
        path: str | Path,
    ) -> Any:
        """Inspect a media file."""

        self.check_cancelled()

        media_path = Path(
            path
        ).expanduser()

        self._progress(
            "Inspecting media",
            media_path.name,
            0,
        )

        result = self.pipeline.inspect(
            media_path
        )

        self._progress(
            "Media inspection complete",
            media_path.name,
            100,
        )

        return result

    # ==========================================================
    # DURATION
    # ==========================================================

    def _process_duration(
        self,
        path: str | Path,
    ) -> float:
        """Return media duration."""

        self.check_cancelled()

        return self.pipeline.duration(
            Path(path).expanduser()
        )

    # ==========================================================
    # CONVERT
    # ==========================================================

    def _process_convert(
        self,
        input_path: str | Path,
        output_path: str | Path,
        **kwargs: Any,
    ) -> Any:
        """Convert/transcode media."""

        self.check_cancelled()

        output = self._output_path(
            output_path
        )

        if not self._can_write(output):
            return {
                "skipped": True,
                "operation": "convert",
                "output": str(output),
                "reason": "output_exists",
            }

        kwargs.setdefault(
            "overwrite",
            self.overwrite_mode == "overwrite",
        )

        kwargs.setdefault(
            "progress_callback",
            self._progress,
        )

        self._progress(
            "Converting media",
            Path(input_path).name,
            0,
        )

        result = self.pipeline.convert(
            input_path,
            output,
            **kwargs,
        )

        self.check_cancelled()

        self._progress(
            "Conversion complete",
            output.name,
            100,
        )

        return result

    # ==========================================================
    # CONCATENATE
    # ==========================================================

    def _process_concatenate(
        self,
        inputs: Sequence[str | Path],
        output: str | Path,
        **kwargs: Any,
    ) -> Any:
        """Concatenate video files."""

        self.check_cancelled()

        output_path = self._output_path(
            output
        )

        if not self._can_write(
            output_path
        ):
            return {
                "skipped": True,
                "operation": "concatenate",
                "output": str(output_path),
                "reason": "output_exists",
            }

        kwargs.setdefault(
            "overwrite",
            self.overwrite_mode == "overwrite",
        )

        kwargs.setdefault(
            "progress_callback",
            self._progress,
        )

        self._progress(
            "Concatenating media",
            output_path.name,
            0,
        )

        result = self.pipeline.concatenate(
            inputs,
            output_path,
            **kwargs,
        )

        self.check_cancelled()

        self._progress(
            "Concatenation complete",
            output_path.name,
            100,
        )

        return result

    # ==========================================================
    # JOIN
    # ==========================================================

    def _process_join(
        self,
        parts: Sequence[Any],
        output_video: str | Path,
        **kwargs: Any,
    ) -> Any:
        """Join video/subtitle parts."""

        self.check_cancelled()

        output_path = self._output_path(
            output_video
        )

        if not self._can_write(
            output_path
        ):
            return {
                "skipped": True,
                "operation": "join",
                "output": str(output_path),
                "reason": "output_exists",
            }

        kwargs.setdefault(
            "overwrite",
            self.overwrite_mode == "overwrite",
        )

        kwargs.setdefault(
            "progress_callback",
            self._progress,
        )

        self._progress(
            "Joining media",
            output_path.name,
            0,
        )

        result = self.pipeline.join(
            parts,
            output_path,
            **kwargs,
        )

        self.check_cancelled()

        self._progress(
            "Join complete",
            output_path.name,
            100,
        )

        return result

    # ==========================================================
    # MUX
    # ==========================================================

    def _process_mux(
        self,
        video: str | Path,
        *,
        output: str | Path,
        **kwargs: Any,
    ) -> Any:
        """Mux video, audio and subtitles."""

        self.check_cancelled()

        output_path = self._output_path(
            output
        )

        if not self._can_write(
            output_path
        ):
            return {
                "skipped": True,
                "operation": "mux",
                "output": str(output_path),
                "reason": "output_exists",
            }

        kwargs.setdefault(
            "overwrite",
            self.overwrite_mode == "overwrite",
        )

        self._progress(
            "Muxing media",
            output_path.name,
            0,
        )

        result = self.pipeline.mux(
            video,
            output=output_path,
            **kwargs,
        )

        self.check_cancelled()

        self._progress(
            "Mux complete",
            output_path.name,
            100,
        )

        return result

    # ==========================================================
    # EXTRACT AUDIO
    # ==========================================================

    def _process_extract_audio(
        self,
        video: str | Path,
        output: str | Path,
        **kwargs: Any,
    ) -> Any:
        """Extract an audio stream."""

        self.check_cancelled()

        output_path = self._output_path(
            output
        )

        if not self._can_write(
            output_path
        ):
            return {
                "skipped": True,
                "operation": "extract_audio",
                "output": str(output_path),
                "reason": "output_exists",
            }

        kwargs.setdefault(
            "overwrite",
            self.overwrite_mode == "overwrite",
        )

        self._progress(
            "Extracting audio",
            Path(video).name,
            0,
        )

        result = self.pipeline.extract_audio(
            video,
            output_path,
            **kwargs,
        )

        self.check_cancelled()

        self._progress(
            "Audio extraction complete",
            output_path.name,
            100,
        )

        return result

    # ==========================================================
    # EXTRACT SUBTITLE
    # ==========================================================

    def _process_extract_subtitle(
        self,
        video: str | Path,
        output: str | Path,
        **kwargs: Any,
    ) -> Any:
        """Extract a subtitle stream."""

        self.check_cancelled()

        output_path = self._output_path(
            output
        )

        if not self._can_write(
            output_path
        ):
            return {
                "skipped": True,
                "operation": "extract_subtitle",
                "output": str(output_path),
                "reason": "output_exists",
            }

        kwargs.setdefault(
            "overwrite",
            self.overwrite_mode == "overwrite",
        )

        self._progress(
            "Extracting subtitles",
            Path(video).name,
            0,
        )

        result = self.pipeline.extract_subtitle(
            video,
            output_path,
            **kwargs,
        )

        self.check_cancelled()

        self._progress(
            "Subtitle extraction complete",
            output_path.name,
            100,
        )

        return result

    # ==========================================================
    # TRIM
    # ==========================================================

    def _process_trim(
        self,
        input_path: str | Path,
        output_path: str | Path,
        **kwargs: Any,
    ) -> Any:
        """Trim media."""

        self.check_cancelled()

        output = self._output_path(
            output_path
        )

        if not self._can_write(
            output
        ):
            return {
                "skipped": True,
                "operation": "trim",
                "output": str(output),
                "reason": "output_exists",
            }

        kwargs.setdefault(
            "overwrite",
            self.overwrite_mode == "overwrite",
        )

        self._progress(
            "Trimming media",
            Path(input_path).name,
            0,
        )

        result = self.pipeline.trim(
            input_path,
            output,
            **kwargs,
        )

        self.check_cancelled()

        self._progress(
            "Trim complete",
            output.name,
            100,
        )

        return result

    # ==========================================================
    # BURN SUBTITLES
    # ==========================================================

    def _process_burn_subtitles(
        self,
        video: str | Path,
        subtitle: str | Path,
        output: str | Path,
        **kwargs: Any,
    ) -> Any:
        """Permanently burn subtitles into video."""

        self.check_cancelled()

        output_path = self._output_path(
            output
        )

        if not self._can_write(
            output_path
        ):
            return {
                "skipped": True,
                "operation": "burn_subtitles",
                "output": str(output_path),
                "reason": "output_exists",
            }

        kwargs.setdefault(
            "overwrite",
            self.overwrite_mode == "overwrite",
        )

        self._progress(
            "Burning subtitles",
            Path(video).name,
            0,
        )

        result = self.pipeline.burn_subtitles(
            video,
            subtitle,
            output_path,
            **kwargs,
        )

        self.check_cancelled()

        self._progress(
            "Subtitle burning complete",
            output_path.name,
            100,
        )

        return result

    # ==========================================================
    # BATCH PROCESSING
    # ==========================================================

    def process_items(
        self,
        items: Sequence[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        """Process multiple media jobs."""

        if not items:
            return []

        results: list[dict[str, Any]] = []

        self.cancelled = False
        self._cancel_event.clear()

        self._install_signal_handler()

        try:
            total = len(items)

            for index, item in enumerate(
                items,
                start=1,
            ):
                self.check_cancelled()

                operation = item.get(
                    "operation"
                )

                if not operation:
                    raise ValueError(
                        "Media job is missing "
                        "'operation'."
                    )

                operation = self._validate_operation(
                    str(operation)
                )

                kwargs = dict(item)

                kwargs.pop(
                    "operation",
                    None,
                )

                filename = (
                    kwargs.get(
                        "output",
                        kwargs.get(
                            "output_path",
                            kwargs.get(
                                "input_path",
                                "",
                            ),
                        ),
                    )
                )

                self._progress(
                    f"Processing "
                    f"{operation} "
                    f"({index}/{total})",
                    str(filename),
                    0,
                )

                try:
                    result = self.process(
                        operation,
                        **kwargs,
                    )

                    results.append(
                        {
                            "operation": operation,
                            "success": True,
                            "result": result,
                            "index": index,
                        }
                    )

                except JobCancelled:
                    raise

                except Exception as exc:
                    self._report_error(exc)

                    results.append(
                        {
                            "operation": operation,
                            "success": False,
                            "error": str(exc),
                            "index": index,
                        }
                    )

        finally:
            self._restore_signal_handler()

        return results

    # ==========================================================
    # SETTINGS
    # ==========================================================

    def process_settings(
        self,
        settings: Mapping[str, Any],
    ) -> Any:
        """
        Process either:

        {
            "operation": "convert",
            ...
        }

        or:

        {
            "items": [
                {
                    "operation": "convert",
                    ...
                },
                ...
            ]
        }

        or:

        {
            "operations": [
                {
                    "operation": "convert",
                    ...
                },
                ...
            ]
        }
        """

        if not isinstance(
            settings,
            Mapping,
        ):
            raise TypeError(
                "settings must be a mapping."
            )

        # ------------------------------------------------------
        # Batch
        # ------------------------------------------------------

        items = settings.get(
            "items"
        )

        if (
            isinstance(items, Sequence)
            and not isinstance(
                items,
                (str, bytes),
            )
        ):
            return self.process_items(
                items
            )

        # ------------------------------------------------------
        # Multiple jobs
        # ------------------------------------------------------

        operations = settings.get(
            "operations"
        )

        if (
            isinstance(operations, Sequence)
            and not isinstance(
                operations,
                (str, bytes),
            )
        ):
            return self.process_items(
                operations
            )

        # ------------------------------------------------------
        # Single operation
        # ------------------------------------------------------

        operation = settings.get(
            "operation"
        )

        if not operation:
            raise ValueError(
                "settings must contain "
                "'operation'."
            )

        kwargs = dict(
            settings
        )

        kwargs.pop(
            "operation",
            None,
        )

        return self.process(
            str(operation),
            **kwargs,
        )