from __future__ import annotations

import os
import signal
import sys
import threading
from typing import Any, Callable, Dict, List, Optional

from services.subtitle_service import SubtitleService


class JobCancelled(Exception):
    """Raised when a subtitle job is cancelled."""


class JobProcessor:
    """
    Processes subtitle jobs.

    Supports:

        overwrite_mode:
            "keep"       -> keep existing subtitle
            "ask"        -> ask through overwrite_callback
            "overwrite"  -> automatically overwrite

        translation_mode:
            "translate"  -> always translate
            "ask"        -> ask through translate_callback
            "skip"       -> never translate

    Also handles:
        - single media files
        - batch processing
        - progress callbacks
        - error callbacks
        - cancellation
        - Ctrl+C / SIGINT
    """

    def __init__(
        self,
        source_language: str = "en",
        target_language: Optional[str] = None,
        subtitle_format: str = "srt",
        progress_callback: Optional[Callable[..., None]] = None,
        error_callback: Optional[Callable[[Any], None]] = None,
        overwrite_callback: Optional[Callable[[str, str], bool]] = None,
        translate_callback: Optional[Callable[..., bool]] = None,
        overwrite_mode: str = "keep",
        translation_mode: str = "translate",
        overwrite_existing: Optional[bool] = None,
    ):
        self.source_language = source_language
        self.target_language = target_language
        self.subtitle_format = subtitle_format

        self.progress_callback = progress_callback
        self.error_callback = error_callback
        self.overwrite_callback = overwrite_callback
        self.translate_callback = translate_callback

        self.cancelled = False

        self._original_sigint_handler = None

        # ------------------------------------------------------
        # Backwards compatibility
        #
        # Old code may still pass:
        #
        #     overwrite_existing=True
        #
        # ------------------------------------------------------

        if overwrite_existing is not None:
            overwrite_mode = (
                "overwrite"
                if overwrite_existing
                else "keep"
            )

        valid_overwrite_modes = {
            "keep",
            "ask",
            "overwrite",
        }

        valid_translation_modes = {
            "translate",
            "ask",
            "skip",
        }

        if overwrite_mode not in valid_overwrite_modes:
            raise ValueError(
                "Invalid overwrite_mode. "
                "Expected 'keep', 'ask', or 'overwrite'."
            )

        if translation_mode not in valid_translation_modes:
            raise ValueError(
                "Invalid translation_mode. "
                "Expected 'translate', 'ask', or 'skip'."
            )

        self.overwrite_mode = overwrite_mode
        self.translation_mode = translation_mode

    # ==========================================================
    # CANCELLATION
    # ==========================================================

    def cancel(self) -> None:
        """Request cancellation."""

        self.cancelled = True

    def check_cancelled(self) -> None:
        """Raise JobCancelled if cancellation was requested."""

        if self.cancelled:
            raise JobCancelled(
                "Subtitle processing cancelled."
            )

    # ==========================================================
    # SIGNAL HANDLING
    # ==========================================================

    def _install_signal_handler(self) -> None:
        """
        Install a graceful Ctrl+C handler.

        SIGINT can only safely be installed from the main thread.
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
        """Restore the previous SIGINT handler."""

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
        """Handle Ctrl+C."""

        self.cancel()

        if self.error_callback:
            try:
                self.error_callback(
                    "KeyboardInterrupt: "
                    "Interrupted by user (Ctrl+C)."
                )
            except Exception:
                pass

    # ==========================================================
    # OVERWRITE DECISION
    # ==========================================================

    def should_overwrite(
        self,
        filepath: str,
        subtitle_type: str = "subtitle",
    ) -> bool:
        """
        Decide whether an existing subtitle should be overwritten.
        """

        self.check_cancelled()

        # ------------------------------------------------------
        # KEEP
        # ------------------------------------------------------

        if self.overwrite_mode == "keep":
            return False

        # ------------------------------------------------------
        # ALWAYS OVERWRITE
        # ------------------------------------------------------

        if self.overwrite_mode == "overwrite":
            return True

        # ------------------------------------------------------
        # ASK
        # ------------------------------------------------------

        if self.overwrite_mode == "ask":

            if self.overwrite_callback is None:
                # Safe fallback: keep existing.
                return False

            try:
                return bool(
                    self.overwrite_callback(
                        filepath,
                        subtitle_type,
                    )
                )

            except JobCancelled:
                raise

            except Exception as exc:

                if self.error_callback:
                    try:
                        self.error_callback(exc)
                    except Exception:
                        pass

                return False

        return False

    # ==========================================================
    # TRANSLATION DECISION
    # ==========================================================

    def should_translate(
        self,
        source_subtitle: str,
        translated_subtitle: str,
    ) -> bool:
        """
        Decide whether translation should happen.
        """

        self.check_cancelled()

        # No target = translation impossible.
        if not self.target_language:
            return False

        # ------------------------------------------------------
        # NEVER TRANSLATE
        # ------------------------------------------------------

        if self.translation_mode == "skip":
            return False

        # ------------------------------------------------------
        # ALWAYS TRANSLATE
        # ------------------------------------------------------

        if self.translation_mode == "translate":
            return True

        # ------------------------------------------------------
        # ASK
        # ------------------------------------------------------

        if self.translation_mode == "ask":

            if self.translate_callback is None:
                return False

            try:
                return bool(
                    self.translate_callback(
                        self.source_language,
                        self.target_language,
                        source_subtitle,
                        translated_subtitle,
                    )
                )

            except JobCancelled:
                raise

            except Exception as exc:

                if self.error_callback:
                    try:
                        self.error_callback(exc)
                    except Exception:
                        pass

                return False

        return False

    # ==========================================================
    # PROCESS ONE FILE
    # ==========================================================

    def process(
        self,
        media_filepath: str,
    ) -> Dict[str, Any]:
        """Process a single media file."""

        self.check_cancelled()

        if not media_filepath:
            raise ValueError(
                "Media filepath cannot be empty."
            )

        if not os.path.isfile(media_filepath):
            raise FileNotFoundError(
                f"Media file does not exist: "
                f"{media_filepath}"
            )

        service = SubtitleService(
            source_language=self.source_language,
            target_language=self.target_language,
            subtitle_format=self.subtitle_format,
            progress_callback=self.progress_callback,
            error_callback=self.error_callback,
            overwrite_callback=self.should_overwrite,
            translate_callback=self.should_translate,
            overwrite_existing=(
                self.overwrite_mode == "overwrite"
            ),
        )

        self.check_cancelled()

        result = service.create_subtitles(
            media_filepath
        )

        self.check_cancelled()

        if result is None:
            return {
                "media": media_filepath,
            }

        if not isinstance(result, dict):
            return {
                "media": media_filepath,
                "result": result,
            }

        return result

    # ==========================================================
    # PROCESS MANY FILES
    # ==========================================================

    def process_files(
        self,
        media_files: List[str],
    ) -> List[Dict[str, Any]]:
        """Process multiple media files sequentially."""

        results: List[Dict[str, Any]] = []

        total_files = len(media_files)

        if total_files == 0:
            return results

        self._install_signal_handler()

        try:

            for index, media_filepath in enumerate(
                media_files,
                start=1,
            ):

                self.check_cancelled()

                # --------------------------------------------------
                # File-level progress
                # --------------------------------------------------

                if self.progress_callback:

                    try:
                        self.progress_callback(
                            (
                                f"Processing file "
                                f"{index} of "
                                f"{total_files}"
                            ),
                            os.path.basename(
                                media_filepath
                            ),
                            0,
                        )

                    except Exception:
                        pass

                try:

                    result = self.process(
                        media_filepath
                    )

                    self.check_cancelled()

                    results.append(result)

                except JobCancelled:
                    raise

                except KeyboardInterrupt:
                    self.cancel()

                    raise JobCancelled(
                        "Subtitle processing "
                        "cancelled by user."
                    )

                except Exception as exc:

                    if self.cancelled:
                        raise JobCancelled(
                            "Subtitle processing "
                            "cancelled."
                        )

                    if self.error_callback:

                        try:
                            self.error_callback(
                                exc
                            )
                        except Exception:
                            pass

                    else:

                        print(
                            f"Error processing "
                            f"{media_filepath}: "
                            f"{exc}",
                            file=sys.stderr,
                        )

                    # Continue with next file.
                    continue

        finally:
            self._restore_signal_handler()

        return results


# ==============================================================
# COMPATIBILITY FUNCTION
# ==============================================================

def process(
    media_filepath: str,
    source_language: str = "en",
    target_language: Optional[str] = None,
    subtitle_format: str = "srt",
    progress_callback: Optional[Callable[..., None]] = None,
    error_callback: Optional[Callable[[Any], None]] = None,
    overwrite_callback: Optional[
        Callable[[str, str], bool]
    ] = None,
    translate_callback: Optional[
        Callable[..., bool]
    ] = None,
    overwrite_mode: str = "keep",
    translation_mode: str = "translate",
) -> Dict[str, Any]:
    """
    Compatibility helper for processing one file.
    """

    processor = JobProcessor(
        source_language=source_language,
        target_language=target_language,
        subtitle_format=subtitle_format,
        progress_callback=progress_callback,
        error_callback=error_callback,
        overwrite_callback=overwrite_callback,
        translate_callback=translate_callback,
        overwrite_mode=overwrite_mode,
        translation_mode=translation_mode,
    )

    return processor.process(
        media_filepath
    )