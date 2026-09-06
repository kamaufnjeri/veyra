from __future__ import annotations

import time
from typing import Any, Callable, Optional

from srtranslator import SrtFile
from srtranslator.translators.translatepy import TranslatePy

class SubtitlesTranslator:
    """
    Subtitle translator using SRTranslator + TranslatePy.

    Translation strategy:

        1. Load the complete SRT.
        2. Split subtitles into batches.
        3. Translate each batch using SrtFile.translate().
        4. If a batch fails, translate that batch individually.
        5. Continue until the entire file is processed.

    Example:

        1-200       -> bulk
        201-400     -> bulk
        401-600     -> bulk
        ...

    Individual translation is only used as a fallback for a
    failed batch.
    """

    def __init__(
        self,
        source_language: str,
        target_language: str,
        error_messages_callback: Optional[
            Callable[[str], None]
        ] = None,
        progress_callback: Optional[
            Callable[[int], None]
        ] = None,
        batch_size: int = 100,
        retry_count: int = 3,
        retry_delay: float = 1.0,
    ):
        self.source_language = self._normalize_language(
            source_language
        )

        self.target_language = self._normalize_language(
            target_language
        )

        self.error_messages_callback = (
            error_messages_callback
        )

        self.progress_callback = progress_callback

        self.batch_size = max(
            1,
            int(batch_size),
        )

        self.retry_count = max(
            1,
            int(retry_count),
        )

        self.retry_delay = max(
            0.0,
            float(retry_delay),
        )

        self.translator = TranslatePy()

    # ------------------------------------------------------------------
    # Language
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_language(
        language: str,
    ) -> str:

        if not language:
            return ""

        return (
            str(language)
            .strip()
            .lower()
            .replace("_", "-")
            .split("-", 1)[0]
        )

    # ------------------------------------------------------------------
    # Availability
    # ------------------------------------------------------------------

    @property
    def is_available(self) -> bool:
        return bool(
            self.source_language
            and self.target_language
            and self.translator
        )

    # ------------------------------------------------------------------
    # Main SRT translation
    # ------------------------------------------------------------------

    def translate_srt(
        self,
        input_srt: str,
        output_srt: str,
    ) -> str:

        subtitles = SrtFile(input_srt)

        print("SRT loaded successfully")

        total = len(subtitles.subtitles)

        if total == 0:
            print("SRT contains no subtitles.")

            subtitles.save(output_srt)

            return output_srt

        print(
            f"Total subtitles: {total}"
        )

        print(
            f"Batch size: {self.batch_size}"
        )

        print()

        # Keep the complete subtitle list.
        all_subtitles = subtitles.subtitles

        # --------------------------------------------------------------
        # Calculate number of batches
        # --------------------------------------------------------------

        batch_count = (
            total + self.batch_size - 1
        ) // self.batch_size

        print(
            f"Translation batches: {batch_count}"
        )

        print()

        # --------------------------------------------------------------
        # Process batches
        # --------------------------------------------------------------

        for batch_number in range(
            batch_count
        ):

            start = (
                batch_number
                * self.batch_size
            )

            end = min(
                start + self.batch_size,
                total,
            )

            batch = all_subtitles[
                start:end
            ]

            print(
                "=" * 60
            )

            print(
                f"TRANSLATING BATCH "
                f"{batch_number + 1}/{batch_count}"
            )

            print(
                f"Subtitles "
                f"{start + 1}-{end}"
            )

            print(
                "=" * 60
            )

            # ----------------------------------------------------------
            # IMPORTANT:
            #
            # Give SrtFile.translate() ONLY this batch.
            # ----------------------------------------------------------

            subtitles.subtitles = batch

            # Save original text in case bulk translation partially
            # modifies the batch before failing.
            original_contents = [
                subtitle.content
                for subtitle in batch
            ]

            try:

                print(
                    "Starting bulk translation..."
                )

                subtitles.translate(
                    self.translator,
                    self.source_language,
                    self.target_language,
                )

                print(
                    f"Batch {batch_number + 1} "
                    f"translated successfully."
                )

                # Report progress based on completed batch.
                self._report_progress(
                    end,
                    total,
                )

            except Exception as exc:

                print(
                    f"Bulk translation failed "
                    f"for batch "
                    f"{batch_number + 1}: "
                    f"{type(exc).__name__}: {exc}"
                )

                self._report_error(
                    "Bulk translation failed "
                    f"for subtitles "
                    f"{start + 1}-{end}: "
                    f"{type(exc).__name__}: {exc}"
                )

                # ------------------------------------------------------
                # Restore the original text.
                #
                # SrtFile.translate() may have translated some
                # subtitles before throwing an exception.
                # ------------------------------------------------------

                for subtitle, original in zip(
                    batch,
                    original_contents,
                ):
                    subtitle.content = original

                # ------------------------------------------------------
                # Fallback: translate this batch individually.
                # ------------------------------------------------------

                print(
                    f"Falling back to individual "
                    f"translation for subtitles "
                    f"{start + 1}-{end}..."
                )

                self._translate_batch_individually(
                    batch,
                    start,
                    total,
                )

            # Restore complete subtitle list.
            subtitles.subtitles = all_subtitles

        # --------------------------------------------------------------
        # Final formatting
        # --------------------------------------------------------------

        subtitles.subtitles = all_subtitles

        print()
        print(
            "Wrapping subtitle lines..."
        )

        try:
            subtitles.wrap_lines()
        except Exception as exc:
            self._report_error(
                "Failed to wrap subtitle lines: "
                f"{type(exc).__name__}: {exc}"
            )

        # --------------------------------------------------------------
        # Save
        # --------------------------------------------------------------

     
        subtitles.save(output_srt)

        self._report_progress(
            total,
            total,
        )

        print()
        print(
            "Translation complete."
        )

        return output_srt

    # ------------------------------------------------------------------
    # Individual batch fallback
    # ------------------------------------------------------------------

    def _translate_batch_individually(
        self,
        batch: list[Any],
        start_index: int,
        total: int,
    ) -> None:

        batch_total = len(batch)

        for index, subtitle in enumerate(
            batch
        ):

            original = subtitle.content

            if not original or not original.strip():

                self._report_progress(
                    start_index + index + 1,
                    total,
                )

                continue

            translated = (
                self._translate_individual(
                    original
                )
            )

            if translated:
                subtitle.content = translated

            self._report_progress(
                start_index + index + 1,
                total,
            )

    # ------------------------------------------------------------------
    # Individual translation
    # ------------------------------------------------------------------

    def _translate_individual(
        self,
        text: str,
    ) -> Optional[str]:

        for attempt in range(
            1,
            self.retry_count + 1,
        ):

            try:

                translated = (
                    self.translator.translate(
                        text,
                        self.source_language,
                        self.target_language,
                    )
                )

                # TranslatePy adapter returns a string.
                if isinstance(
                    translated,
                    str,
                ):
                    translated = (
                        translated.strip()
                    )

                if translated:
                    return translated

                raise RuntimeError(
                    "Translator returned "
                    "an empty result"
                )

            except Exception as exc:

                if attempt >= self.retry_count:

                    self._report_error(
                        "Individual translation "
                        "failed after "
                        f"{self.retry_count} attempts: "
                        f"{type(exc).__name__}: {exc}\n"
                        f"Text: {text!r}"
                    )

                    # Preserve original subtitle.
                    return text

                print(
                    f"Translation attempt "
                    f"{attempt}/{self.retry_count} "
                    f"failed. Retrying..."
                )

                time.sleep(
                    self.retry_delay
                )

        return text

    # ------------------------------------------------------------------
    # Progress
    # ------------------------------------------------------------------

    def _report_progress(
        self,
        current: int,
        total: int,
    ) -> None:

        if total <= 0:
            percent = 100
        else:
            percent = int(
                (current / total) * 100
            )

        if self.progress_callback:

            try:
                self.progress_callback(
                    percent
                )
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Errors
    # ------------------------------------------------------------------

    def _report_error(
        self,
        message: str,
    ) -> None:

        if self.error_messages_callback:

            try:
                self.error_messages_callback(
                    message
                )
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Close
    # ------------------------------------------------------------------

    def close(self) -> None:

        try:
            self.translator.quit()
        except Exception:
            pass