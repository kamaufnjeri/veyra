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

from core.temp_manager import remove_temp_file
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

        workers: int = 4,

        vad_mode: str = "silero",
        audio_source: str = "wav",

        batch_size: int = 20,
    ):

        self.language = self._normalize_language(
            language
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

        self.vad_mode = (
            str(vad_mode)
            .strip()
            .lower()
        )

        self.audio_source = (
            str(audio_source)
            .strip()
            .lower()
        )

        self.batch_size = max(
            1,
            int(batch_size),
        )

        # ------------------------------------------------------
        # WAV converter
        #
        # Only used when audio_source == "wav".
        # ------------------------------------------------------

        self.wav_converter = WavConverter(
            channels=1,
            rate=16000,
            audio_source="wav",
            progress_callback=self._core_progress,
            error_messages_callback=self._error,
        )

        # ------------------------------------------------------
        # Silero VAD
        #
        # VAD always requires an actual WAV file.
        # ------------------------------------------------------

        self.region_finder = SileroVAD(
            vad_mode=self.vad_mode,
            sampling_rate=16000,

            threshold=0.5,

            min_speech_duration_ms=250,

            min_silence_duration_ms=400,

            speech_pad_ms=200,

            merge_gap=0.65,

            min_segment_duration=0.80,

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

        original_media = audio_input

        wav_path = None

        # ------------------------------------------------------
        # IMPORTANT:
        #
        # Decide whether the input is actually WAV.
        #
        # Do NOT trust audio_source alone.
        # ------------------------------------------------------

        is_wav_input = (
            str(audio_input)
            .lower()
            .endswith(".wav")
        )

        try:

            # ==================================================
            # 1. DETERMINE AUDIO PATH
            # ==================================================

            # --------------------------------------------------
            # VIDEO MODE
            #
            # Never use WavConverter.
            # Never use wave.open().
            # --------------------------------------------------

            if self.audio_source == "video":

                self._progress(
                    "Using video/audio media directly",
                    5,
                )

                media_for_recognition = (
                    original_media
                )

                # ------------------------------------------------
                # No WAV exists, therefore no Silero processing.
                #
                # Video recognition uses _recognize_video_region().
                # ------------------------------------------------

                return self._transcribe_video(
                    media_for_recognition
                )

            # --------------------------------------------------
            # ALREADY A WAV FILE
            #
            # Use it directly.
            # --------------------------------------------------

            if is_wav_input:

                wav_path = original_media

            # --------------------------------------------------
            # NON-WAV INPUT
            #
            # Try WAV conversion.
            #
            # If conversion fails, fall back to the original
            # media file and use video recognition.
            # --------------------------------------------------

            else:

                self._progress(
                    "Extracting speech audio",
                    5,
                )

                try:

                    wav_path, sample_rate = (
                        self.wav_converter(
                            original_media
                        )
                    )

                except Exception as exc:

                    self._error(
                        (
                            "WAV conversion failed; "
                            "falling back to video "
                            f"recognition: {exc}"
                        )
                    )

                    return self._transcribe_video(
                        original_media
                    )

                if not wav_path:

                    self._error(
                        (
                            "WAV conversion returned "
                            "no file; falling back to "
                            "video recognition."
                        )
                    )

                    return self._transcribe_video(
                        original_media
                    )

                # ------------------------------------------------
                # Safety check.
                #
                # If converter somehow returns the original
                # non-WAV media, NEVER send it to wave.open().
                # ------------------------------------------------

                if not str(
                    wav_path
                ).lower().endswith(".wav"):

                    self._error(
                        (
                            "Audio converter did not "
                            "return a WAV file; "
                            "falling back to video "
                            "recognition."
                        )
                    )

                    return self._transcribe_video(
                        original_media
                    )

            # ==================================================
            # 2. WAV VALIDATION
            # ==================================================

            if not os.path.isfile(
                wav_path
            ):

                self._error(
                    (
                        "WAV file does not exist; "
                        "falling back to video "
                        "recognition."
                    )
                )

                return self._transcribe_video(
                    original_media
                )

            # --------------------------------------------------
            # Validate RIFF/WAV before Silero or wave.open().
            # --------------------------------------------------

            if not self._is_valid_wav(
                wav_path
            ):

                self._error(
                    (
                        "Invalid WAV file; "
                        "falling back to video "
                        "recognition."
                    )
                )

                # Only remove generated temporary files.
                if wav_path != original_media:
                    remove_temp_file(
                        wav_path
                    )
                    wav_path = None

                return self._transcribe_video(
                    original_media
                )

            # ==================================================
            # 3. DETECT SPEECH
            # ==================================================

            self._progress(
                "Detecting speech regions",
                16,
            )

            regions = self.region_finder(
                wav_path
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
            # 4. GOOGLE RECOGNITION
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

                        # ------------------------------------------------
                        # WAV input ALWAYS uses _recognize_region().
                        #
                        # This function uses wave.open(), so it receives
                        # only a verified WAV.
                        # ------------------------------------------------

                        future = executor.submit(
                            self._recognize_region,
                            index,
                            region,
                            wav_path,
                        )

                        futures[future] = index

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
            # 5. RESTORE ORIGINAL ORDER
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

            # ------------------------------------------------------
            # IMPORTANT:
            #
            # remove_temp_file() is responsible for deciding
            # whether a file is inside /tmp/veyra.
            #
            # The original user's media is therefore protected.
            # ------------------------------------------------------

            if wav_path != original_media:

                remove_temp_file(
                    wav_path
                )

    # ==========================================================
    # VALIDATE WAV
    # ==========================================================

    @staticmethod
    def _is_valid_wav(
        filepath: str,
    ) -> bool:

        if not filepath:
            return False

        if not os.path.isfile(
            filepath
        ):
            return False

        try:

            with open(
                filepath,
                "rb",
            ) as file:

                header = file.read(
                    12
                )

            if len(header) < 12:
                return False

            return (
                header[0:4] == b"RIFF"
                and
                header[8:12] == b"WAVE"
            )

        except OSError:
            return False

    # ==========================================================
    # VIDEO TRANSCRIPTION
    # ==========================================================

    def _transcribe_video(
        self,
        media_filepath: str,
    ) -> List[dict]:

        """
        Transcribe a non-WAV media file directly.

        This path MUST use _recognize_video_region().

        FFmpeg is responsible for extracting the requested
        audio region for Google recognition.
        """

        if not media_filepath:
            return []

        if not os.path.isfile(
            media_filepath
        ):
            raise FileNotFoundError(
                media_filepath
            )

        self._progress(
            "Recognizing speech from media",
            20,
        )

        # ------------------------------------------------------
        # For direct video recognition we first need the
        # duration.
        # ------------------------------------------------------

        duration = self._get_media_duration(
            media_filepath
        )

        if duration <= 0:

            self._error(
                "Could not determine media duration."
            )

            return []

        # ------------------------------------------------------
        # Fixed chunks for direct video recognition.
        #
        # No WAV conversion is performed here.
        # ------------------------------------------------------

        chunk_duration = 6.0

        regions = []

        start = 0.0

        while start < duration:

            end = min(
                start + chunk_duration,
                duration,
            )

            if end > start:

                regions.append(
                    (
                        start,
                        end,
                    )
                )

            start = end

        if not regions:
            return []

        total_regions = len(
            regions
        )

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

        results_by_index = {}

        completed = 0

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
                    f"Processing video recognition "
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

                    # ------------------------------------------------
                    # NON-WAV MEDIA ALWAYS USES:
                    #
                    # _recognize_video_region()
                    # ------------------------------------------------

                    future = executor.submit(
                        self._recognize_video_region,
                        index,
                        region,
                        media_filepath,
                    )

                    futures[future] = index

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

            self._error(
                "Google speech recognition "
                "produced no usable results."
            )

            return []

        self._progress(
            "Transcription complete",
            60,
        )

        return results

    # ==========================================================
    # GET MEDIA DURATION
    # ==========================================================

    @staticmethod
    def _get_media_duration(
        media_filepath: str,
    ) -> float:

        import subprocess

        command = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            media_filepath,
        ]

        try:

            result = subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
            )

            return max(
                0.0,
                float(
                    result.stdout.strip()
                ),
            )

        except Exception:
            return 0.0

    # ==========================================================
    # RECOGNIZE WAV REGION
    # ==========================================================

    def _recognize_region(
        self,
        index: int,
        region: Tuple[float, float],
        wav_path: str,
    ) -> Tuple[int, Optional[dict]]:

        start, end = region

        # ------------------------------------------------------
        # SAFETY:
        #
        # This method must only receive WAV files.
        # ------------------------------------------------------

        if not self._is_valid_wav(
            wav_path
        ):

            raise RuntimeError(
                (
                    "Refusing to open non-WAV "
                    f"file with wave.open(): {wav_path}"
                )
            )

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
    # RECOGNIZE VIDEO REGION
    # ==========================================================

    def _recognize_video_region(
        self,
        index: int,
        region: Tuple[float, float],
        media_filepath: str,
    ) -> Tuple[int, Optional[dict]]:

        """
        Recognize one region directly from a video/media file.

        FFmpeg extracts the requested audio to stdout.

        IMPORTANT:
        No .wav file is created and no wave.open() is used.
        """

        import subprocess

        start, end = region

        start_time = max(
            0.0,
            float(start)
            - self.include_before,
        )

        duration = (
            float(end)
            + self.include_after
            - start_time
        )

        if duration <= 0:
            return index, None

        command = [
            "ffmpeg",

            "-hide_banner",
            "-loglevel",
            "error",

            "-ss",
            str(start_time),

            "-i",
            media_filepath,

            "-t",
            str(duration),

            "-vn",

            "-ac",
            "1",

            "-ar",
            "16000",

            "-f",
            "s16le",

            "pipe:1",
        ]

        try:

            result = subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )

        except subprocess.CalledProcessError as exc:

            stderr = (
                exc.stderr.decode(
                    "utf-8",
                    errors="replace",
                ).strip()
                if exc.stderr
                else ""
            )

            raise RuntimeError(
                "FFmpeg failed extracting video "
                "audio"
                + (
                    f": {stderr}"
                    if stderr
                    else "."
                )
            ) from exc

        except FileNotFoundError as exc:

            raise RuntimeError(
                "FFmpeg executable was not found."
            ) from exc

        audio_frames = (
            result.stdout
        )

        if not audio_frames:
            return index, None

        # ------------------------------------------------------
        # 16-bit PCM = 2 bytes/sample.
        # ------------------------------------------------------

        usable_bytes = (
            len(audio_frames)
            - (
                len(audio_frames)
                % 2
            )
        )

        if usable_bytes <= 0:
            return index, None

        audio_frames = (
            audio_frames[
                :usable_bytes
            ]
        )

        audio = sr.AudioData(
            audio_frames,
            16000,
            2,
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
