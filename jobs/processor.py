from __future__ import annotations

import os
import signal
import sys
from typing import Any, Callable, Dict, List, Optional

from services.subtitle_service import SubtitleService


class JobCancelled(Exception):
    """Raised when a subtitle job is cancelled."""


class JobProcessor:
    """
    Processes subtitle jobs.

    Handles:
        - single media file processing
        - batch media file processing
        - progress tracking
        - error reporting
        - clean job cancellation & SIGINT (Ctrl+C) handling
    """

    def __init__(
        self,
        source_language: str = "en",
        target_language: Optional[str] = None,
        subtitle_format: str = "srt",
        progress_callback: Optional[Callable[..., None]] = None,
        error_callback: Optional[Callable[[Any], None]] = None,
        overwrite_callback: Optional[Callable[[str], bool]] = None,
    ):
        self.source_language = source_language
        self.target_language = target_language
        self.subtitle_format = subtitle_format

        self.progress_callback = progress_callback
        self.error_callback = error_callback
        self.overwrite_callback = overwrite_callback

        self.cancelled = False
        self._original_sigint_handler = None

    # ==========================================================
    # CANCELLATION & SIGNAL HANDLING
    # ==========================================================

    def cancel(self) -> None:
        """Request cancellation of the current and pending jobs."""
        if not self.cancelled:
            self.cancelled = True

    def check_cancelled(self) -> None:
        """Stop processing if cancellation was requested."""
        if self.cancelled:
            raise JobCancelled("Job cancelled.")

    def _install_signal_handler(self) -> None:
        """Capture Ctrl+C (SIGINT) to allow graceful job cancellation."""
        if sys.platform != "win32" or threading.current_thread() is threading.main_thread():
            try:
                self._original_sigint_handler = signal.getsignal(signal.SIGINT)
                signal.signal(signal.SIGINT, self._handle_sigint)
            except (ValueError, AttributeError):
                pass

    def _restore_signal_handler(self) -> None:
        """Restore previous SIGINT handler."""
        if self._original_sigint_handler is not None:
            try:
                signal.signal(signal.SIGINT, self._original_sigint_handler)
            except (ValueError, AttributeError):
                pass

    def _handle_sigint(self, signum: int, frame: Any) -> None:
        """Signal handler callback for Ctrl+C."""
        self.cancel()
        if self.error_callback:
            try:
                self.error_callback("KeyboardInterrupt: Interrupted by user (Ctrl+C).")
            except Exception:
                pass

    # ==========================================================
    # PROCESS ONE FILE
    # ==========================================================

    def process(self, media_filepath: str) -> Dict[str, Any]:
        """Process a single media file."""
        self.check_cancelled()

        service = SubtitleService(
            source_language=self.source_language,
            target_language=self.target_language,
            subtitle_format=self.subtitle_format,
            progress_callback=self.progress_callback,
            error_callback=self.error_callback,
            overwrite_callback=self.overwrite_callback,
            translate_callback=self.overwrite_callback
        )

        self.check_cancelled()
        result = service.create_subtitles(media_filepath)
        self.check_cancelled()

        return result

    # ==========================================================
    # PROCESS MANY FILES
    # ==========================================================

    def process_files(self, media_files: List[str]) -> List[Dict[str, Any]]:
        """Process multiple media files in sequence."""
        results: List[Dict[str, Any]] = []
        total_files = len(media_files)

        self._install_signal_handler()

        try:
            for index, media_filepath in enumerate(media_files, start=1):
                self.check_cancelled()

                if self.progress_callback:
                    try:
                        self.progress_callback(
                            f"Processing file {index} of {total_files}",
                            os.path.basename(media_filepath),
                            0,
                        )
                    except Exception:
                        pass

                try:
                    result = self.process(media_filepath)

                    if self.cancelled:
                        break

                    results.append(result)

                except JobCancelled:
                    break

                except KeyboardInterrupt:
                    self.cancel()
                    break

                except Exception as exc:
                    if self.cancelled:
                        break

                    if self.error_callback:
                        try:
                            self.error_callback(exc)
                        except Exception:
                            pass
                    else:
                        print(f"Error processing {media_filepath}: {exc}")

        finally:
            self._restore_signal_handler()

        return results


# ==============================================================
# COMPATIBILITY FUNCTIONS
# ==============================================================

def process(
    media_filepath: str,
    source_language: str = "en",
    target_language: Optional[str] = None,
    subtitle_format: str = "srt",
    progress_callback: Optional[Callable[..., None]] = None,
    error_callback: Optional[Callable[[Any], None]] = None,
    overwrite_callback: Optional[Callable[[str], bool]] = None,
) -> Dict[str, Any]:
    """Process a single file using a JobProcessor instance."""
    processor = JobProcessor(
        source_language=source_language,
        target_language=target_language,
        subtitle_format=subtitle_format,
        progress_callback=progress_callback,
        error_callback=error_callback,
        overwrite_callback=overwrite_callback,
    )
    return processor.process(media_filepath)