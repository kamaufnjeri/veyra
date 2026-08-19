from __future__ import annotations

import audioop
import math
import os
import wave

from concurrent.futures import (
    ThreadPoolExecutor,
    as_completed,
)

from typing import (
    Any,
    Callable,
    List,
    Optional,
    Tuple,
)

import speech_recognition as sr

from core.wav_converter import WavConverter


# ==============================================================
# SPEECH REGION FINDER
# ==============================================================

class SpeechRegionFinder:
    """
    Detect speech regions using RMS energy analysis.

    This is intentionally lightweight. It scans the WAV once
    and avoids creating an FFmpeg process for every region.
    """

    def __init__(
        self,
        frame_width: int = 4096,
        min_region_size: float = 0.5,
        max_region_size: float = 6.0,
        error_messages_callback=None,
    ):
        self.frame_width = frame_width
        self.min_region_size = min_region_size
        self.max_region_size = max_region_size
        self.error_messages_callback = (
            error_messages_callback
        )

    @staticmethod
    def percentile(
        arr: List[float],
        percent: float,
    ) -> float:

        if not arr:
            return 0.0

        arr = sorted(arr)

        k = (len(arr) - 1) * percent

        f = math.floor(k)
        c = math.ceil(k)

        if f == c:
            return arr[int(k)]

        d0 = arr[int(f)] * (c - k)
        d1 = arr[int(c)] * (k - f)

        return d0 + d1

    def __call__(
        self,
        wav_filepath: str,
    ) -> List[Tuple[float, float]]:

        try:

            with wave.open(
                wav_filepath,
                "rb",
            ) as reader:

                sample_width = reader.getsampwidth()
                rate = reader.getframerate()
                total_frames = reader.getnframes()

                if rate <= 0:
                    return []

                total_duration = (
                    total_frames / float(rate)
                )

                chunk_duration = (
                    float(self.frame_width)
                    / float(rate)
                )

                n_chunks = int(
                    math.ceil(
                        total_duration
                        / chunk_duration
                    )
                )

                energies = []

                for _ in range(n_chunks):

                    chunk = reader.readframes(
                        self.frame_width
                    )

                    if not chunk:
                        break

                    energy = audioop.rms(
                        chunk,
                        sample_width,
                    )

                    energies.append(energy)

        except KeyboardInterrupt:

            self._error(
                "Cancelling speech detection"
            )

            raise

        except Exception as exc:

            self._error(exc)

            return []

        if not energies:
            return []

        threshold = self.percentile(
            energies,
            0.20,
        )

        elapsed_time = 0.0

        regions = []

        region_start = None

        for energy in energies:

            is_silence = (
                energy <= threshold
            )

            max_exceeded = (
                region_start is not None
                and (
                    elapsed_time
                    - region_start
                    >= self.max_region_size
                )
            )

            if max_exceeded or is_silence:

                if region_start is not None:

                    duration = (
                        elapsed_time
                        - region_start
                    )

                    if duration >= self.min_region_size:

                        regions.append(
                            (
                                region_start,
                                elapsed_time,
                            )
                        )

                    region_start = None

            elif region_start is None:

                region_start = elapsed_time

            elapsed_time += chunk_duration

        # Close final region.

        if region_start is not None:

            duration = (
                elapsed_time
                - region_start
            )

            if duration >= self.min_region_size:

                regions.append(
                    (
                        region_start,
                        min(
                            elapsed_time,
                            total_duration,
                        ),
                    )
                )

        return regions

    def _error(self, error):

        if self.error_messages_callback:

            try:
                self.error_messages_callback(
                    error
                )
            except Exception:
                pass

        else:
            print(error)


# ==============================================================
# AUDIO TRANSCRIBER
# ==============================================================

class AudioTranscriber:

    def __init__(
        self,
        language: str = "en",
        model_size: str = "unused",
        device: Optional[str] = None,
        compute_type: Optional[str] = None,
        cpu_threads: int = 4,
        task: str = "transcribe",
        progress_callback=None,
        error_callback=None,
        error_messages_callback=None,

        frame_width: int = 4096,
        min_region_size: float = 0.5,
        max_region_size: float = 6.0,

        include_before: float = 0.25,
        include_after: float = 0.25,

        # Google requests running concurrently.
        workers: int = 6,
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

        if self.task != "transcribe":

            raise ValueError(
                "AudioTranscriber only supports "
                "task='transcribe'."
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

        self.workers = max(
            1,
            int(workers),
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

        self.region_finder = (
            SpeechRegionFinder(
                frame_width=frame_width,
                min_region_size=min_region_size,
                max_region_size=max_region_size,
                error_messages_callback=self._error,
            )
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
            # 3. PARALLEL GOOGLE RECOGNITION
            # ==================================================

            workers = min(
                self.workers,
                total_regions,
            )

            self._progress(
                (
                    f"Recognizing speech using "
                    f"{workers} workers"
                ),
                20,
            )

            results_by_index = {}

            with ThreadPoolExecutor(
                max_workers=workers
            ) as executor:

                futures = {}

                for index, region in enumerate(
                    regions
                ):

                    future = executor.submit(
                        self._recognize_region,
                        index,
                        region,
                        wav_path,
                    )

                    futures[future] = index

                completed = 0

                for future in as_completed(
                    futures
                ):

                    completed += 1

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
                        "Recognizing speech with Google",
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