from __future__ import annotations

import io
import torch

from typing import (
    Any,
    BinaryIO,
    Callable,
    List,
    Optional,
    Union,
)

from faster_whisper import WhisperModel


class AudioTranscriber:
    """
    Local speech transcription using faster-whisper.

    Supports two modes:

        task="transcribe"
            Speech -> original language text

        task="translate"
            Speech -> English text

    The service decides which mode should be used.

    Examples:

        Spanish -> English
            task="translate"

        French -> English
            task="translate"

        Spanish -> French
            task="transcribe"

        English -> Swahili
            task="transcribe"
    """

    def __init__(
        self,
        language: str = "en",
        model_size: str = "tiny",
        device: Optional[str] = None,
        compute_type: Optional[str] = None,
        cpu_threads: int = 4,
        task: str = "transcribe",
        progress_callback: Optional[
            Callable[..., None]
        ] = None,
        error_callback: Optional[
            Callable[[Any], None]
        ] = None,
        error_messages_callback: Optional[
            Callable[[Any], None]
        ] = None,
    ):
        self.language = self._normalize_language(language)

        self.task = (
            task.strip().lower()
            if task
            else "transcribe"
        )

        if self.task not in {
            "transcribe",
            "translate",
        }:
            self.task = "transcribe"

        # Support both callback naming conventions.
        self.progress_callback = progress_callback

        self.error_callback = (
            error_callback
            or error_messages_callback
        )

        # ------------------------------------------------------
        # Device
        # ------------------------------------------------------

        if device is None:
            device = (
                "cuda"
                if torch.cuda.is_available()
                else "cpu"
            )

        self.device = device

        # ------------------------------------------------------
        # Compute type
        # ------------------------------------------------------

        if compute_type is None:
            if device == "cuda":
                compute_type = "float16"
            else:
                compute_type = "int8"

        self.compute_type = compute_type

        # ------------------------------------------------------
        # Load model
        # ------------------------------------------------------

        try:
            self.model = WhisperModel(
                model_size_or_path=model_size,
                device=device,
                compute_type=compute_type,
                cpu_threads=cpu_threads,
            )

        except Exception as exc:
            self._error(
                "Failed to initialize WhisperModel: "
                f"{exc}"
            )

            self.model = None

    # ==========================================================
    # Language
    # ==========================================================

    @staticmethod
    def _normalize_language(
        language: Optional[str],
    ) -> str:
        if not language:
            return ""

        return (
            str(language)
            .strip()
            .lower()
            .replace("_", "-")
            .split("-")[0]
        )

    # ==========================================================
    # Transcription
    # ==========================================================

    def __call__(
        self,
        audio_input: Union[
            str,
            bytes,
            BinaryIO,
        ],
    ) -> List[dict]:
        """
        Transcribe or translate audio.

        Returns:

            [
                {
                    "region": (start, end),
                    "text": "..."
                }
            ]
        """

        if not audio_input:
            return []

        if self.model is None:
            return []

        try:
            # --------------------------------------------------
            # Progress
            # --------------------------------------------------

            if self.task == "translate":
                self._progress(
                    "Starting speech translation",
                    10,
                )
            else:
                self._progress(
                    "Starting transcription",
                    10,
                )

            # --------------------------------------------------
            # Convert bytes to file-like object.
            # --------------------------------------------------

            if isinstance(audio_input, bytes):
                audio_input = io.BytesIO(
                    audio_input
                )

            # --------------------------------------------------
            # Faster-whisper
            # --------------------------------------------------

            segments, info = self.model.transcribe(
                audio_input,

                # Source language.
                language=(
                    self.language
                    if self.language
                    else None
                ),

                # IMPORTANT:
                #
                # "translate" means:
                #   speech -> English
                #
                # "transcribe" means:
                #   speech -> original language
                #
                task=self.task,

                # Fast decoding.
                beam_size=1,

                # VAD avoids wasting time processing silence.
                vad_filter=True,

                vad_parameters={
                    "min_silence_duration_ms": 500,
                },

                # Do not unnecessarily generate multiple
                # candidate results.
                best_of=1,

                # Faster than more expensive decoding options.
                temperature=0,

                # Prevent excessive hallucination in silence.
                condition_on_previous_text=True,
            )

            raw_segments: List[dict] = []

            total_duration = getattr(
                info,
                "duration",
                None,
            )

            # --------------------------------------------------
            # Read segments.
            #
            # faster-whisper is lazy, so actual processing
            # happens while iterating over segments.
            # --------------------------------------------------

            for seg in segments:

                text = (
                    seg.text.strip()
                    if seg.text
                    else ""
                )

                if not text:
                    continue

                raw_segments.append(
                    {
                        "region": (
                            float(seg.start),
                            float(seg.end),
                        ),
                        "text": text,
                    }
                )

                # ------------------------------------------------
                # Progress
                # ------------------------------------------------

                if (
                    total_duration
                    and total_duration > 0
                ):
                    percentage = int(
                        (
                            seg.end
                            / total_duration
                        )
                        * 100
                    )

                    percentage = max(
                        0,
                        min(
                            100,
                            percentage,
                        ),
                    )

                    # Transcription/translation occupies
                    # 10 -> 60.
                    mapped_percentage = (
                        10
                        + int(
                            percentage
                            * 0.50
                        )
                    )

                    if self.task == "translate":
                        message = (
                            "Translating speech"
                        )
                    else:
                        message = (
                            "Transcribing audio"
                        )

                    self._progress(
                        message,
                        mapped_percentage,
                    )

            # --------------------------------------------------
            # Complete
            # --------------------------------------------------

            if self.task == "translate":
                self._progress(
                    "Speech translation complete",
                    60,
                )
            else:
                self._progress(
                    "Transcribing complete",
                    60,
                )

            return raw_segments

        except Exception as exc:

            self._error(
                f"Transcription Error: {exc}"
            )

            return []

    # ==========================================================
    # Alias
    # ==========================================================

    def transcribe(
        self,
        audio_input,
    ):
        """Compatibility alias for __call__."""
        return self(audio_input)

    # ==========================================================
    # Progress
    # ==========================================================

    def _progress(
        self,
        info: str,
        percentage: int,
    ) -> None:

        if not self.progress_callback:
            return

        percentage = max(
            0,
            min(
                100,
                int(percentage),
            ),
        )

        try:
            self.progress_callback(
                info,
                "",
                percentage,
            )

        except TypeError:

            try:
                self.progress_callback(
                    info,
                    "",
                    percentage,
                    None,
                )

            except Exception:
                pass

        except Exception:
            pass

    # ==========================================================
    # Error
    # ==========================================================

    def _error(
        self,
        error: Any,
    ) -> None:

        if self.error_callback:

            try:
                self.error_callback(
                    error
                )

            except Exception:
                pass

        else:
            print(error)