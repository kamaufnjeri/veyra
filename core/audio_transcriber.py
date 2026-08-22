from __future__ import annotations

import math
import os
import wave

from concurrent.futures import (
    ThreadPoolExecutor,
    as_completed,
)

from typing import (
    Any,
    List,
    Optional,
    Tuple,
)

import speech_recognition as sr

from core.wav_converter import WavConverter
from core.silero_vad import SileroVAD


# ==============================================================
# AUDIO TRANSCRIBER
# ==============================================================

class AudioTranscriber:

    def __init__(
        self,
        language: str = "en",
        progress_callback=None,
        error_callback=None,
        error_messages_callback=None,

        include_before: float = 0.25,
        include_after: float = 0.25,

        # ------------------------------------------------------
        # Google recognition concurrency.
        # ------------------------------------------------------
        workers: int = 4,

        # ------------------------------------------------------
        # Number of speech regions submitted to the executor
        # at one time.
        #
        # IMPORTANT:
        # This does NOT send multiple regions in one Google
        # request. Google recognition is still performed one
        # AudioData object at a time.
        #
        # batch_size simply prevents thousands of futures from
        # being created simultaneously.
        # ------------------------------------------------------
        batch_size: int = 20,
    ):

        self.language = (
            self._normalize_language(
                language
            )
        )

        self.progress_callback = (
            progress_callback
        )

        self.error_callback = (
            error_callback
            or error_messages_callback
        )

        self.include_before = float(
            include_before
        )

        self.include_after = float(
            include_after
        )

        # ------------------------------------------------------
        # Google worker count.
        # ------------------------------------------------------

        self.workers = max(
            1,
            int(workers),
        )

        # ------------------------------------------------------
        # Google recognition batch size.
        # ------------------------------------------------------

        self.batch_size = max(
            1,
            int(batch_size),
        )

        # ------------------------------------------------------
        # WAV converter
        # ------------------------------------------------------

        self.wav_converter = WavConverter(
            channels=1,
            rate=16000,
            progress_callback=self._core_progress,
            error_messages_callback=self._error,
        )

        # ------------------------------------------------------
        # Speech detector
        # ------------------------------------------------------

        self.region_finder = SileroVAD(
            sampling_rate=16000,

            threshold=0.5,

            min_speech_duration_ms=250,

            # Give natural dialogue pauses a little room.
            min_silence_duration_ms=400,

            speech_pad_ms=200,

            # Merge nearby speech regions.
            merge_gap=0.65,

            # Ignore extremely short fragments.
            min_segment_duration=0.80,

            # Don't send huge chunks to ASR.
            max_segment_duration=6.0,

            error_callback=self._error,
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

            # ==================================================
            # 1. CONVERT MEDIA ONCE
            # ==================================================

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

            # ==================================================
            # 2. DETECT SPEECH
            # ==================================================

            self._progress(
                "Detecting speech regions",
                16,
            )

            regions = (
                self.region_finder(
                    wav_path
                )
            )

            if not regions:

                raise RuntimeError(
                    "No speech regions were detected."
                )

            total_regions = len(
                regions
            )

            self._progress(
                (
                    f"Detected {total_regions} "
                    "speech regions"
                ),
                20,
            )

            # ==================================================
            # 3. BATCHED PARALLEL GOOGLE RECOGNITION
            # ==================================================

            workers = min(
                self.workers,
                total_regions,
            )

            batch_size = min(
                self.batch_size,
                total_regions,
            )

            total_batches = math.ceil(
                total_regions
                / batch_size
            )

            self._progress(
                (
                    f"Recognizing speech using "
                    f"{workers} workers "
                    f"(batch size: {batch_size})"
                ),
                20,
            )

            results_by_index = {}

            completed = 0

            # --------------------------------------------------
            # Process regions in batches.
            #
            # Only one batch is submitted at a time.
            # Within each batch, workers process regions
            # concurrently.
            # --------------------------------------------------

            for batch_number, batch_start in enumerate(
                range(
                    0,
                    total_regions,
                    batch_size,
                ),
                start=1,
            ):

                batch_end = min(
                    batch_start + batch_size,
                    total_regions,
                )

                batch = regions[
                    batch_start:batch_end
                ]

                self._progress(
                    (
                        f"Processing recognition "
                        f"batch {batch_number}/"
                        f"{total_batches}"
                    ),
                    20 + int(
                        (
                            completed
                            / total_regions
                        )
                        * 40
                    ),
                )

                # ------------------------------------------------
                # Executor exists only for this batch.
                # ------------------------------------------------

                with ThreadPoolExecutor(
                    max_workers=workers
                ) as executor:

                    futures = {}

                    for offset, region in enumerate(
                        batch
                    ):

                        index = (
                            batch_start
                            + offset
                        )

                        future = executor.submit(
                            self._recognize_region,
                            index,
                            region,
                            wav_path,
                        )

                        futures[future] = index

                    # --------------------------------------------
                    # Collect completed requests.
                    # --------------------------------------------

                    for future in as_completed(
                        futures
                    ):

                        try:

                            index, result = (
                                future.result()
                            )

                            if result is not None:

                                results_by_index[
                                    index
                                ] = result

                        except Exception as exc:

                            self._error(
                                exc
                            )

                        completed += 1

                        percentage = int(
                            (
                                completed
                                / total_regions
                            )
                            * 100
                        )

                        mapped = (
                            20
                            + int(
                                percentage
                                * 0.40
                            )
                        )

                        self._progress(
                            (
                                "Recognizing speech "
                                "with Google"
                            ),
                            mapped,
                        )

            # ==================================================
            # 4. RESTORE ORIGINAL ORDER
            # ==================================================

            results = []

            for index in sorted(
                results_by_index
            ):

                result = (
                    results_by_index[index]
                )

                if result:
                    results.append(
                        result
                    )

            if not results:

                raise RuntimeError(
                    "Google speech recognition "
                    "produced no usable results."
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
    # RECOGNIZE ONE REGION
    # ==========================================================

    def _recognize_region(
        self,
        index: int,
        region: Tuple[float, float],
        wav_path: str,
    ) -> Tuple[int, Optional[dict]]:

        start, end = region

        # ------------------------------------------------------
        # Read only the required WAV section.
        #
        # IMPORTANT:
        # No FFmpeg process is created here.
        # ------------------------------------------------------

        with wave.open(
            wav_path,
            "rb",
        ) as wav:

            rate = wav.getframerate()
            sample_width = wav.getsampwidth()

            start_time = max(
                0.0,
                float(start)
                - self.include_before,
            )

            end_time = (
                float(end)
                + self.include_after
            )

            start_frame = int(
                start_time * rate
            )

            end_frame = int(
                end_time * rate
            )

            frame_count = max(
                1,
                end_frame - start_frame,
            )

            wav.setpos(
                min(
                    start_frame,
                    wav.getnframes(),
                )
            )

            audio_frames = (
                wav.readframes(
                    frame_count
                )
            )

        if not audio_frames:
            return index, None

        # ------------------------------------------------------
        # SpeechRecognition AudioData
        #
        # WAV is already:
        #   mono
        #   16 kHz
        #
        # so we can send the raw PCM directly.
        # ------------------------------------------------------

        audio = sr.AudioData(
            audio_frames,
            rate,
            sample_width,
        )

        recognizer = sr.Recognizer()

        try:

            text = recognizer.recognize_google(
                audio,
                language=self.language,
                show_all=False,
            )

        except sr.UnknownValueError:

            return index, None

        except sr.RequestError as exc:

            raise RuntimeError(
                "Google speech recognition "
                f"request failed: {exc}"
            ) from exc

        if not text:
            return index, None

        text = str(
            text
        ).strip()

        if not text:
            return index, None

        return index, {
            "region": (
                start,
                end,
            ),
            "text": text,
        }

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