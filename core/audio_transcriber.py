from __future__ import annotations

import os
import time
import wave

from typing import (
    Any,
    Callable,
    List,
    Optional,
)

import speech_recognition as sr

from core.wav_converter import WavConverter


class AudioTranscriber:

    def __init__(
        self,
        language: str = "en",
        model_size: str = "unused",
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

        # Google chunk size.
        chunk_seconds: float = 8.0,
    ):

        self.language = (
            self._normalize_language(
                language
            )
        )

        self.task = (
            task.strip().lower()
            if task
            else "transcribe"
        )

        self.progress_callback = (
            progress_callback
        )

        self.error_callback = (
            error_callback
            or error_messages_callback
        )

        self.chunk_seconds = max(
            3.0,
            float(chunk_seconds),
        )

        # ------------------------------------------------------
        # Google recognizer
        # ------------------------------------------------------

        self.recognizer = sr.Recognizer()

        self.recognizer.dynamic_energy_threshold = True

        self.recognizer.pause_threshold = 0.6

        self.recognizer.non_speaking_duration = 0.3

        # ------------------------------------------------------
        # WAV
        # ------------------------------------------------------

        self.wav_converter = WavConverter(
            channels=1,
            rate=16000,
            progress_callback=self._core_progress,
            error_messages_callback=self._error,
        )

    # ==========================================================
    # LANGUAGE
    # ==========================================================

    @staticmethod
    def _normalize_language(
        language: Optional[str],
    ) -> str:

        if not language:
            return "en-US"

        language = (
            str(language)
            .strip()
            .replace("_", "-")
        )

        if "-" in language:
            return language

        mapping = {

            "en": "en-US",
            "es": "es-ES",
            "fr": "fr-FR",
            "de": "de-DE",
            "it": "it-IT",
            "pt": "pt-PT",

            "sw": "sw-KE",
            "af": "af-ZA",

            "nl": "nl-NL",
            "pl": "pl-PL",
            "ru": "ru-RU",
            "tr": "tr-TR",

            "ar": "ar-SA",
            "hi": "hi-IN",
            "ja": "ja-JP",
            "ko": "ko-KR",
            "zh": "zh-CN",
        }

        return mapping.get(
            language.lower(),
            language,
        )

    # ==========================================================
    # TRANSCRIBE
    # ==========================================================

    def __call__(
        self,
        audio_input: str,
    ) -> List[dict]:

        if not audio_input:
            return []

        if not os.path.isfile(
            audio_input
        ):
            raise FileNotFoundError(
                audio_input
            )

        wav_path = None

        try:

            # --------------------------------------------------
            # Convert media
            # --------------------------------------------------

            self._progress(
                "Extracting speech audio",
                5,
            )

            wav_path, sample_rate = (
                self.wav_converter(
                    audio_input
                )
            )

            if not wav_path:
                raise RuntimeError(
                    "Failed to create WAV audio."
                )

            # --------------------------------------------------
            # Get WAV information
            # --------------------------------------------------

            with wave.open(
                wav_path,
                "rb",
            ) as wav:

                frames = wav.getnframes()
                rate = wav.getframerate()

            duration = (
                frames / float(rate)
                if rate
                else 0
            )

            # --------------------------------------------------
            # Number of chunks
            # --------------------------------------------------

            chunk_frames = int(
                rate
                * self.chunk_seconds
            )

            total_chunks = max(
                1,
                (
                    frames
                    + chunk_frames
                    - 1
                )
                // chunk_frames,
            )

            results: List[dict] = []

            # --------------------------------------------------
            # Process chunks
            # --------------------------------------------------

            with wave.open(
                wav_path,
                "rb",
            ) as wav:

                for index in range(
                    total_chunks
                ):

                    start_frame = (
                        index
                        * chunk_frames
                    )

                    wav.setpos(
                        start_frame
                    )

                    audio_frames = (
                        wav.readframes(
                            chunk_frames
                        )
                    )

                    if not audio_frames:
                        break

                    actual_frames = (
                        len(audio_frames)
                        // wav.getsampwidth()
                        // wav.getnchannels()
                    )

                    start = (
                        start_frame
                        / float(rate)
                    )

                    end = (
                        start
                        + actual_frames
                        / float(rate)
                    )

                    # --------------------------------------------------
                    # Create SpeechRecognition AudioData
                    # --------------------------------------------------

                    audio = sr.AudioData(
                        audio_frames,
                        rate,
                        wav.getsampwidth(),
                    )

                    text = ""

                    try:

                        text = (
                            self.recognizer
                            .recognize_google(
                                audio,
                                language=self.language,
                                show_all=False,
                            )
                        )

                    except sr.UnknownValueError:

                        # No understandable speech.
                        text = ""

                    except sr.RequestError as exc:

                        raise RuntimeError(
                            "Google speech recognition "
                            f"request failed: {exc}"
                        ) from exc

                    if text:

                        text = text.strip()

                        if text:

                            results.append(
                                {
                                    "region": (
                                        start,
                                        end,
                                    ),
                                    "text": text,
                                }
                            )

                    # --------------------------------------------------
                    # Progress
                    # --------------------------------------------------

                    percentage = int(
                        (
                            (index + 1)
                            / total_chunks
                        )
                        * 100
                    )

                    mapped = (
                        15
                        + int(
                            percentage
                            * 0.45
                        )
                    )

                    self._progress(
                        "Recognizing speech with Google",
                        mapped,
                    )

            self._progress(
                "Transcription complete",
                60,
            )

            return results

        except KeyboardInterrupt:

            self._error(
                "Cancelling transcription"
            )

            raise

        except Exception as exc:

            self._error(
                f"Transcription Error: {exc}"
            )

            return []

        finally:

            if wav_path:

                try:
                    os.unlink(
                        wav_path
                    )
                except OSError:
                    pass

    # ==========================================================
    # ALIAS
    # ==========================================================

    def transcribe(
        self,
        audio_input,
    ):

        return self(
            audio_input
        )

    # ==========================================================
    # PROGRESS
    # ==========================================================

    def _progress(
        self,
        info: str,
        percentage: int,
    ):

        if not self.progress_callback:
            return

        try:

            self.progress_callback(
                info,
                "",
                max(
                    0,
                    min(
                        100,
                        int(percentage),
                    ),
                ),
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
    # WAV PROGRESS
    # ==========================================================

    def _core_progress(
        self,
        info,
        filename,
        percentage,
        start_time=None,
    ):

        self._progress(
            info,
            min(
                15,
                int(
                    percentage * 0.15
                ),
            ),
        )

    # ==========================================================
    # ERROR
    # ==========================================================

    def _error(
        self,
        error: Any,
    ):

        if self.error_callback:

            try:
                self.error_callback(
                    error
                )
            except Exception:
                pass

        else:
            print(error)

# from __future__ import annotations

# import io
# import torch

# from typing import (
#     Any,
#     BinaryIO,
#     Callable,
#     List,
#     Optional,
#     Union,
# )

# from faster_whisper import WhisperModel


# class AudioTranscriber:
#     """
#     Local speech transcription using faster-whisper.

#     Supports two modes:

#         task="transcribe"
#             Speech -> original language text

#         task="translate"
#             Speech -> English text

#     The service decides which mode should be used.

#     Examples:

#         Spanish -> English
#             task="translate"

#         French -> English
#             task="translate"

#         Spanish -> French
#             task="transcribe"

#         English -> Swahili
#             task="transcribe"
#     """

#     def __init__(
#         self,
#         language: str = "en",
#         model_size: str = "tiny",
#         device: Optional[str] = None,
#         compute_type: Optional[str] = None,
#         cpu_threads: int = 4,
#         task: str = "transcribe",
#         progress_callback: Optional[
#             Callable[..., None]
#         ] = None,
#         error_callback: Optional[
#             Callable[[Any], None]
#         ] = None,
#         error_messages_callback: Optional[
#             Callable[[Any], None]
#         ] = None,
#     ):
#         self.language = self._normalize_language(language)

#         self.task = (
#             task.strip().lower()
#             if task
#             else "transcribe"
#         )

#         if self.task not in {
#             "transcribe",
#             "translate",
#         }:
#             self.task = "transcribe"

#         # Support both callback naming conventions.
#         self.progress_callback = progress_callback

#         self.error_callback = (
#             error_callback
#             or error_messages_callback
#         )

#         # ------------------------------------------------------
#         # Device
#         # ------------------------------------------------------

#         if device is None:
#             device = (
#                 "cuda"
#                 if torch.cuda.is_available()
#                 else "cpu"
#             )

#         self.device = device

#         # ------------------------------------------------------
#         # Compute type
#         # ------------------------------------------------------

#         if compute_type is None:
#             if device == "cuda":
#                 compute_type = "float16"
#             else:
#                 compute_type = "int8"

#         self.compute_type = compute_type

#         # ------------------------------------------------------
#         # Load model
#         # ------------------------------------------------------

#         try:
#             self.model = WhisperModel(
#                 model_size_or_path=model_size,
#                 device=device,
#                 compute_type=compute_type,
#                 cpu_threads=cpu_threads,
#             )

#         except Exception as exc:
#             self._error(
#                 "Failed to initialize WhisperModel: "
#                 f"{exc}"
#             )

#             self.model = None

#     # ==========================================================
#     # Language
#     # ==========================================================

#     @staticmethod
#     def _normalize_language(
#         language: Optional[str],
#     ) -> str:
#         if not language:
#             return ""

#         return (
#             str(language)
#             .strip()
#             .lower()
#             .replace("_", "-")
#             .split("-")[0]
#         )

#     # ==========================================================
#     # Transcription
#     # ==========================================================

#     def __call__(
#         self,
#         audio_input: Union[
#             str,
#             bytes,
#             BinaryIO,
#         ],
#     ) -> List[dict]:
#         """
#         Transcribe or translate audio.

#         Returns:

#             [
#                 {
#                     "region": (start, end),
#                     "text": "..."
#                 }
#             ]
#         """

#         if not audio_input:
#             return []

#         if self.model is None:
#             return []

#         try:
#             # --------------------------------------------------
#             # Progress
#             # --------------------------------------------------

#             if self.task == "translate":
#                 self._progress(
#                     "Starting speech translation",
#                     10,
#                 )
#             else:
#                 self._progress(
#                     "Starting transcription",
#                     10,
#                 )

#             # --------------------------------------------------
#             # Convert bytes to file-like object.
#             # --------------------------------------------------

#             if isinstance(audio_input, bytes):
#                 audio_input = io.BytesIO(
#                     audio_input
#                 )

#             # --------------------------------------------------
#             # Faster-whisper
#             # --------------------------------------------------

#             segments, info = self.model.transcribe(
#                 audio_input,

#                 # ------------------------------------------------------
#                 # Language
#                 # ------------------------------------------------------
#                 language=self.language or None,

#                 # transcribe = original language
#                 # translate  = English
#                 task=self.task,

#                 # ------------------------------------------------------
#                 # CPU SPEED
#                 # ------------------------------------------------------
#                 beam_size=3,

#                 # Prevent previous bad text from propagating.
#                 # This is especially important for your repeated
#                 # "y aquí está un barco" problem.
#                 condition_on_previous_text=False,

#                 # ------------------------------------------------------
#                 # VAD
#                 # ------------------------------------------------------
#                 vad_filter=True,
#                 vad_parameters={
#                     "threshold": 0.5,
#                     "min_speech_duration_ms": 250,
#                     "min_silence_duration_ms": 500,
#                     "speech_pad_ms": 200,
#                 },

#                 # ------------------------------------------------------
#                 # Decoding
#                 # ------------------------------------------------------
#                 temperature=0,

#                 # ------------------------------------------------------
#                 # Hallucination protection
#                 # ------------------------------------------------------
#                 compression_ratio_threshold=2.4,
#                 log_prob_threshold=-1.0,
#                 no_speech_threshold=0.6,

#                 # ------------------------------------------------------
#                 # Repetition protection
#                 # ------------------------------------------------------
#                 repetition_penalty=1.02,
#                 no_repeat_ngram_size=3,

#                 # Keep decoding from becoming excessively long.
#                 max_new_tokens=96,
#             )
#             raw_segments: List[dict] = []

#             total_duration = getattr(
#                 info,
#                 "duration",
#                 None,
#             )

#             # --------------------------------------------------
#             # Read segments.
#             #
#             # faster-whisper is lazy, so actual processing
#             # happens while iterating over segments.
#             # --------------------------------------------------

#             for seg in segments:

#                 text = (
#                     seg.text.strip()
#                     if seg.text
#                     else ""
#                 )

#                 if not text:
#                     continue

#                 raw_segments.append(
#                     {
#                         "region": (
#                             float(seg.start),
#                             float(seg.end),
#                         ),
#                         "text": text,
#                     }
#                 )

#                 # ------------------------------------------------
#                 # Progress
#                 # ------------------------------------------------

#                 if (
#                     total_duration
#                     and total_duration > 0
#                 ):
#                     percentage = int(
#                         (
#                             seg.end
#                             / total_duration
#                         )
#                         * 100
#                     )

#                     percentage = max(
#                         0,
#                         min(
#                             100,
#                             percentage,
#                         ),
#                     )

#                     # Transcription/translation occupies
#                     # 10 -> 60.
#                     mapped_percentage = (
#                         10
#                         + int(
#                             percentage
#                             * 0.50
#                         )
#                     )

#                     if self.task == "translate":
#                         message = (
#                             "Translating speech"
#                         )
#                     else:
#                         message = (
#                             "Transcribing audio"
#                         )

#                     self._progress(
#                         message,
#                         mapped_percentage,
#                     )

#             # --------------------------------------------------
#             # Complete
#             # --------------------------------------------------

#             if self.task == "translate":
#                 self._progress(
#                     "Speech translation complete",
#                     60,
#                 )
#             else:
#                 self._progress(
#                     "Transcribing complete",
#                     60,
#                 )

#             return raw_segments

#         except Exception as exc:

#             self._error(
#                 f"Transcription Error: {exc}"
#             )

#             return []

#     # ==========================================================
#     # Alias
#     # ==========================================================

#     def transcribe(
#         self,
#         audio_input,
#     ):
#         """Compatibility alias for __call__."""
#         return self(audio_input)

#     # ==========================================================
#     # Progress
#     # ==========================================================

#     def _progress(
#         self,
#         info: str,
#         percentage: int,
#     ) -> None:

#         if not self.progress_callback:
#             return

#         percentage = max(
#             0,
#             min(
#                 100,
#                 int(percentage),
#             ),
#         )

#         try:
#             self.progress_callback(
#                 info,
#                 "",
#                 percentage,
#             )

#         except TypeError:

#             try:
#                 self.progress_callback(
#                     info,
#                     "",
#                     percentage,
#                     None,
#                 )

#             except Exception:
#                 pass

#         except Exception:
#             pass

#     # ==========================================================
#     # Error
#     # ==========================================================

#     def _error(
#         self,
#         error: Any,
#     ) -> None:

#         if self.error_callback:

#             try:
#                 self.error_callback(
#                     error
#                 )

#             except Exception:
#                 pass

#         else:
#             print(error)