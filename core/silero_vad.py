from __future__ import annotations

import math
import os
import subprocess
from typing import Callable, List, Optional, Tuple


# ---------------------------------------------------------------------------
# PyTorch environment configuration
# ---------------------------------------------------------------------------
#
# These MUST be set before importing torch.
#
# Your Intel i3-3110M does not support the CPU instructions expected by
# NNPACK. PyTorch can still run using other CPU implementations, but without
# this setting it may repeatedly print:
#
#   Could not initialize NNPACK! Reason: Unsupported hardware.
#
# TORCH_CPP_LOG_LEVEL=ERROR suppresses that noisy warning.
#
os.environ["OMP_NUM_THREADS"] = "2"
os.environ["MKL_NUM_THREADS"] = "2"
os.environ["ATEN_CPU_CAPABILITY"] = "default"
os.environ["TORCH_CPP_LOG_LEVEL"] = "ERROR"


import torch
from silero_vad import load_silero_vad, get_speech_timestamps


# Keep CPU usage reasonable on older machines.
torch.set_num_threads(2)

try:
    torch.set_num_interop_threads(1)
except RuntimeError:
    # PyTorch only allows this to be configured before certain work has
    # started. If another part of the application already initialized
    # PyTorch, simply keep the existing setting.
    pass


class SileroVAD:
    """
    Voice Activity Detection with selectable segmentation mode.

    Modes
    -----
    "silero"
        Try Silero VAD first.

        If Silero cannot be loaded OR Silero timestamp detection fails,
        automatically fall back to fixed-duration segmentation.

    "fixed"
        Do not load or run Silero VAD.

        The complete audio is divided into fixed-duration chunks using
        fallback_chunk_duration.

    Default
    -------
    "silero"

    Normal Silero path
    ------------------
    1. Load Silero VAD.
    2. Run get_speech_timestamps().
    3. Merge nearby speech regions.
    4. Split excessively long regions.

    Silero fallback path
    --------------------
    If Silero cannot be loaded OR timestamp detection fails, the complete
    audio is divided into fixed-duration chunks.

    Fixed path
    ----------
    If vad_mode="fixed", Silero is skipped entirely and the complete audio
    is divided into fixed-duration chunks.

    Important
    ---------
    A successful Silero result of [] means no speech was detected.
    In that case we return [] and DO NOT use the fallback.

    No audio is discarded by fixed-duration segmentation.
    """

    def __init__(
        self,
        sampling_rate: int = 16000,
        threshold: float = 0.5,
        min_speech_duration_ms: int = 100,
        min_silence_duration_ms: int = 350,
        speech_pad_ms: int = 150,
        merge_gap: float = 0.50,
        min_segment_duration: float = 0.0,
        max_segment_duration: float = 8.0,
        fallback_chunk_duration: float = 10.0,
        vad_mode: str = "silero",
        error_callback: Optional[Callable[[object], None]] = None,
    ) -> None:

        # ------------------------------------------------------------------
        # Validate configuration
        # ------------------------------------------------------------------

        if sampling_rate not in (8000, 16000):
            raise ValueError(
                "sampling_rate must be either 8000 or 16000."
            )

        if not 0.0 <= threshold <= 1.0:
            raise ValueError(
                "threshold must be between 0.0 and 1.0."
            )

        if min_speech_duration_ms < 0:
            raise ValueError(
                "min_speech_duration_ms cannot be negative."
            )

        if min_silence_duration_ms < 0:
            raise ValueError(
                "min_silence_duration_ms cannot be negative."
            )

        if speech_pad_ms < 0:
            raise ValueError(
                "speech_pad_ms cannot be negative."
            )

        if merge_gap < 0:
            raise ValueError(
                "merge_gap cannot be negative."
            )

        if min_segment_duration < 0:
            raise ValueError(
                "min_segment_duration cannot be negative."
            )

        if max_segment_duration <= 0:
            raise ValueError(
                "max_segment_duration must be greater than zero."
            )

        if fallback_chunk_duration <= 0:
            raise ValueError(
                "fallback_chunk_duration must be greater than zero."
            )

        # ------------------------------------------------------------------
        # VAD mode
        # ------------------------------------------------------------------
        #
        # "silero" = Silero first, fixed-duration fallback on failure.
        # "fixed"  = always use fixed-duration segmentation.
        #
        normalized_vad_mode = str(vad_mode).strip().lower()

        if normalized_vad_mode not in ("silero", "fixed"):
            raise ValueError(
                "vad_mode must be either 'silero' or 'fixed'."
            )

        self.vad_mode = normalized_vad_mode

        self.sampling_rate = sampling_rate
        self.threshold = threshold
        self.min_speech_duration_ms = min_speech_duration_ms
        self.min_silence_duration_ms = min_silence_duration_ms
        self.speech_pad_ms = speech_pad_ms
        self.merge_gap = merge_gap
        self.min_segment_duration = min_segment_duration
        self.max_segment_duration = max_segment_duration
        self.fallback_chunk_duration = fallback_chunk_duration
        self.error_callback = error_callback

        # ------------------------------------------------------------------
        # Silero state
        # ------------------------------------------------------------------

        self.model = None
        self.vad_available = False

        # ------------------------------------------------------------------
        # ALWAYS TRY SILERO FIRST ONLY WHEN REQUESTED
        # ------------------------------------------------------------------
        #
        # Fixed mode deliberately skips model loading.
        # ------------------------------------------------------------------

        if self.vad_mode == "fixed":
            return

        try:
            self.model = load_silero_vad()

            if self.model is None:
                raise RuntimeError(
                    "load_silero_vad() returned None."
                )

            self.model.eval()

            self.vad_available = True

        except Exception as exc:
            self.model = None
            self.vad_available = False

            self._error(
                "Silero VAD unavailable: "
                f"{exc}. "
                "Falling back to fixed 10-second segmentation."
            )

    # ======================================================================
    # Error handling
    # ======================================================================

    def _error(self, error: object) -> None:
        """
        Send an error/warning to the application's callback.

        If no callback is configured, print it to the terminal.
        """

        if self.error_callback:
            try:
                self.error_callback(error)
                return
            except Exception:
                pass

        print(error)

    # ======================================================================
    # Audio loading
    # ======================================================================

    def _load_audio(self, wav_filepath: str) -> torch.Tensor:
        """
        Load WAV audio through FFmpeg and return a float32 mono tensor.

        The WAV is converted to:
            mono
            configured sampling rate
            raw float32 PCM

        No temporary audio region files are created here.
        """

        if not wav_filepath:
            raise ValueError("wav_filepath cannot be empty.")

        if not os.path.isfile(wav_filepath):
            raise FileNotFoundError(
                f"WAV file does not exist: '{wav_filepath}'"
            )

        command = [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            wav_filepath,
            "-ac",
            "1",
            "-ar",
            str(self.sampling_rate),
            "-f",
            "f32le",
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

        except FileNotFoundError as exc:
            raise RuntimeError(
                "FFmpeg executable was not found."
            ) from exc

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
                "FFmpeg failed while loading audio"
                + (f": {stderr}" if stderr else ".")
            ) from exc

        if not result.stdout:
            raise RuntimeError(
                "FFmpeg returned no audio data."
            )

        # Raw float32 PCM requires complete 4-byte samples.
        usable_bytes = len(result.stdout) - (
            len(result.stdout) % 4
        )

        if usable_bytes <= 0:
            raise RuntimeError(
                "FFmpeg returned incomplete float32 audio data."
            )

        audio_bytes = bytearray(
            result.stdout[:usable_bytes]
        )

        audio = torch.frombuffer(
            audio_bytes,
            dtype=torch.float32,
        ).clone()

        if audio.numel() == 0:
            raise RuntimeError(
                "Loaded audio contains no samples."
            )

        return audio

    # ======================================================================
    # Silero timestamp detection
    # ======================================================================

    def _detect(
        self,
        audio: torch.Tensor,
    ) -> List[Tuple[float, float]]:
        """
        Run Silero get_speech_timestamps().

        This method is ONLY called when Silero successfully loaded.
        """

        if self.model is None:
            raise RuntimeError(
                "Silero model is not loaded."
            )

        if audio.numel() == 0:
            return []

        timestamps = get_speech_timestamps(
            audio,
            self.model,
            threshold=self.threshold,
            sampling_rate=self.sampling_rate,
            min_speech_duration_ms=self.min_speech_duration_ms,
            min_silence_duration_ms=self.min_silence_duration_ms,
            speech_pad_ms=self.speech_pad_ms,
            return_seconds=True,
        )

        regions: List[Tuple[float, float]] = []

        for timestamp in timestamps:
            try:
                start = float(timestamp["start"])
                end = float(timestamp["end"])
            except (KeyError, TypeError, ValueError) as exc:
                raise RuntimeError(
                    f"Invalid Silero timestamp: {timestamp!r}"
                ) from exc

            if not math.isfinite(start) or not math.isfinite(end):
                continue

            start = max(0.0, start)
            end = max(0.0, end)

            if end > start:
                regions.append((start, end))

        return regions

    # ======================================================================
    # Fallback segmentation
    # ======================================================================

    def _fallback_segments(
        self,
        duration: float,
    ) -> List[Tuple[float, float]]:
        """
        Divide the COMPLETE audio into fixed-size chunks.

        Default:
            10 seconds

        Example:
            31.2 seconds becomes:

                0.0  -> 10.0
                10.0 -> 20.0
                20.0 -> 30.0
                30.0 -> 31.2

        No audio is discarded.
        """

        if duration <= 0:
            return []

        segments: List[Tuple[float, float]] = []

        start = 0.0

        while start < duration:
            end = min(
                start + self.fallback_chunk_duration,
                duration,
            )

            if end > start:
                segments.append(
                    (
                        round(start, 6),
                        round(end, 6),
                    )
                )

            start = end

        return segments

    # ======================================================================
    # Merge speech regions
    # ======================================================================

    def _merge_regions(
        self,
        regions: List[Tuple[float, float]],
    ) -> List[Tuple[float, float]]:
        """
        Merge overlapping or nearby speech regions.

        Regions are merged when the silence/gap between them is less than
        or equal to merge_gap.

        This preserves short pauses and prevents excessive fragmentation.
        """

        if not regions:
            return []

        sorted_regions = sorted(
            regions,
            key=lambda region: region[0],
        )

        merged: List[Tuple[float, float]] = []

        current_start, current_end = sorted_regions[0]

        for start, end in sorted_regions[1:]:

            gap = start - current_end

            if gap <= self.merge_gap:
                current_end = max(
                    current_end,
                    end,
                )
            else:
                merged.append(
                    (
                        current_start,
                        current_end,
                    )
                )

                current_start = start
                current_end = end

        merged.append(
            (
                current_start,
                current_end,
            )
        )

        return merged

    # ======================================================================
    # Split long speech regions
    # ======================================================================

    def _split_long_regions(
        self,
        regions: List[Tuple[float, float]],
    ) -> List[Tuple[float, float]]:
        """
        Split regions longer than max_segment_duration.

        The split is performed evenly.

        Example with max_segment_duration=8:

            12 seconds
            ->
            6 + 6

        16 seconds
            ->
            8 + 8

        No audio is discarded.
        """

        if not regions:
            return []

        result: List[Tuple[float, float]] = []

        for start, end in regions:

            duration = end - start

            if duration <= self.max_segment_duration:
                result.append(
                    (
                        start,
                        end,
                    )
                )
                continue

            # Number of chunks required.
            chunk_count = math.ceil(
                duration / self.max_segment_duration
            )

            # Divide evenly so that the final segment is not tiny.
            chunk_duration = duration / chunk_count

            for index in range(chunk_count):

                chunk_start = (
                    start + index * chunk_duration
                )

                chunk_end = (
                    start + (index + 1) * chunk_duration
                )

                # Prevent tiny floating-point errors.
                if index == chunk_count - 1:
                    chunk_end = end

                if chunk_end > chunk_start:
                    result.append(
                        (
                            chunk_start,
                            chunk_end,
                        )
                    )

        return result

    # ======================================================================
    # Main entry point
    # ======================================================================

    def __call__(
        self,
        wav_filepath: str,
    ) -> List[Tuple[float, float]]:
        """
        Detect speech regions.

        Priority:

            vad_mode="silero":

                1. Load audio
                2. Try Silero VAD
                3. If Silero fails -> fixed-duration fallback
                4. If Silero succeeds with no speech -> []
                5. Merge regions
                6. Split long regions

            vad_mode="fixed":

                1. Load audio
                2. Divide complete audio into fixed-duration chunks
                3. Return chunks

        Returns:
            List of (start_seconds, end_seconds)
        """

        # --------------------------------------------------------------
        # Load audio first.
        #
        # This is NOT a VAD failure. If FFmpeg/audio loading fails,
        # don't fabricate speech regions.
        # --------------------------------------------------------------

        try:
            audio = self._load_audio(wav_filepath)

        except KeyboardInterrupt:
            self._error(
                "Silero VAD cancelled."
            )
            raise

        except Exception as exc:
            self._error(
                f"Failed to load audio for VAD: {exc}"
            )
            return []

        # --------------------------------------------------------------
        # Determine complete audio duration.
        # --------------------------------------------------------------

        duration = (
            audio.numel() / self.sampling_rate
        )

        if duration <= 0:
            return []

        # --------------------------------------------------------------
        # FIXED MODE
        #
        # Explicitly selected by the caller.
        #
        # Silero is not used at all.
        # --------------------------------------------------------------

        if self.vad_mode == "fixed":

            return self._fallback_segments(
                duration
            )

        # --------------------------------------------------------------
        # SILERO MODE
        #
        # If model loading failed in __init__, use fallback.
        # --------------------------------------------------------------

        if not self.vad_available or self.model is None:

            self._error(
                "Silero VAD is unavailable. "
                "Using fixed-duration segmentation."
            )

            return self._fallback_segments(
                duration
            )

        # --------------------------------------------------------------
        # Silero is available.
        #
        # Try actual Silero speech detection.
        # --------------------------------------------------------------

        try:
            raw_regions = self._detect(audio)

        except KeyboardInterrupt:
            self._error(
                "Silero VAD cancelled."
            )
            raise

        except Exception as exc:

            self._error(
                "Silero VAD timestamp detection failed: "
                f"{exc}. "
                "Falling back to fixed-duration segmentation."
            )

            return self._fallback_segments(
                duration
            )

        # --------------------------------------------------------------
        # IMPORTANT:
        #
        # Silero successfully ran and found no speech.
        #
        # DO NOT fallback here.
        #
        # [] is a legitimate Silero result.
        # --------------------------------------------------------------

        if not raw_regions:
            return []

        # --------------------------------------------------------------
        # Merge nearby regions.
        # --------------------------------------------------------------

        merged_regions = self._merge_regions(
            raw_regions
        )

        if not merged_regions:
            return []

        # --------------------------------------------------------------
        # Split excessively long speech regions.
        # --------------------------------------------------------------

        final_regions = self._split_long_regions(
            merged_regions
        )

        return final_regions
