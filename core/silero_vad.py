from __future__ import annotations

import math
import subprocess
from typing import List, Tuple

import torch

from silero_vad import (
    load_silero_vad,
    get_speech_timestamps,
)


class SileroVAD:

    def __init__(
        self,
        sampling_rate: int = 16000,
        threshold: float = 0.5,

        # ------------------------------------------------------
        # SILERO VAD
        # ------------------------------------------------------

        # Do not make this too large.
        #
        # A subtitle such as:
        #
        #   "Oh"
        #   "When?"
        #   "Santiago"
        #
        # can legitimately be very short.
        min_speech_duration_ms: int = 100,

        min_silence_duration_ms: int = 350,

        speech_pad_ms: int = 150,

        # ------------------------------------------------------
        # SEGMENTATION
        # ------------------------------------------------------

        # Speech regions separated by <= this amount of silence
        # are treated as one ASR segment.
        merge_gap: float = 0.50,

        # IMPORTANT:
        #
        # This is NOT used to delete speech anymore.
        #
        # It is kept only for backwards compatibility / API
        # compatibility.
        min_segment_duration: float = 0.0,

        # Maximum amount of audio sent to ASR at once.
        max_segment_duration: float = 8.0,

        error_callback=None,
    ):

        self.sampling_rate = int(
            sampling_rate
        )

        self.threshold = float(
            threshold
        )

        self.min_speech_duration_ms = int(
            min_speech_duration_ms
        )

        self.min_silence_duration_ms = int(
            min_silence_duration_ms
        )

        self.speech_pad_ms = int(
            speech_pad_ms
        )

        self.merge_gap = float(
            merge_gap
        )

        self.min_segment_duration = float(
            min_segment_duration
        )

        self.max_segment_duration = float(
            max_segment_duration
        )

        self.error_callback = (
            error_callback
        )

        if self.sampling_rate <= 0:
            raise ValueError(
                "sampling_rate must be greater than 0."
            )

        if not 0.0 <= self.threshold <= 1.0:
            raise ValueError(
                "threshold must be between 0.0 and 1.0."
            )

        if self.min_speech_duration_ms < 0:
            raise ValueError(
                "min_speech_duration_ms cannot be negative."
            )

        if self.min_silence_duration_ms < 0:
            raise ValueError(
                "min_silence_duration_ms cannot be negative."
            )

        if self.speech_pad_ms < 0:
            raise ValueError(
                "speech_pad_ms cannot be negative."
            )

        if self.merge_gap < 0:
            raise ValueError(
                "merge_gap cannot be negative."
            )

        if self.max_segment_duration <= 0:
            raise ValueError(
                "max_segment_duration must be greater than 0."
            )

        # ------------------------------------------------------
        # Silero VAD
        # ------------------------------------------------------

        self.model = load_silero_vad()

        self.model.eval()

    # ==========================================================
    # AUDIO LOADING
    # ==========================================================

    def _load_audio(
        self,
        wav_filepath: str,
    ) -> torch.Tensor:

        """
        Decode audio through FFmpeg.

        Output:
            mono float32 tensor
            at self.sampling_rate
        """

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
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )

        except FileNotFoundError as exc:

            raise RuntimeError(
                "FFmpeg was not found. "
                "Please make sure ffmpeg is installed."
            ) from exc

        except subprocess.CalledProcessError as exc:

            stderr = (
                exc.stderr.decode(
                    "utf-8",
                    errors="replace",
                )
                if exc.stderr
                else ""
            )

            raise RuntimeError(
                "FFmpeg failed to decode audio:\n"
                f"{stderr}"
            ) from exc

        if not result.stdout:

            raise RuntimeError(
                f"FFmpeg produced no audio data for: "
                f"{wav_filepath}"
            )

        audio = torch.frombuffer(
            result.stdout,
            dtype=torch.float32,
        ).clone()

        if audio.numel() == 0:

            raise RuntimeError(
                f"Decoded audio is empty: "
                f"{wav_filepath}"
            )

        return audio

    # ==========================================================
    # RAW SILERO DETECTION
    # ==========================================================

    def _detect(
        self,
        audio: torch.Tensor,
    ) -> List[Tuple[float, float]]:

        timestamps = get_speech_timestamps(
            audio,
            self.model,

            sampling_rate=self.sampling_rate,

            threshold=self.threshold,

            min_speech_duration_ms=(
                self.min_speech_duration_ms
            ),

            min_silence_duration_ms=(
                self.min_silence_duration_ms
            ),

            speech_pad_ms=(
                self.speech_pad_ms
            ),

            return_seconds=True,
        )

        regions: List[
            Tuple[float, float]
        ] = []

        for item in timestamps:

            try:

                start = float(
                    item["start"]
                )

                end = float(
                    item["end"]
                )

            except (
                KeyError,
                TypeError,
                ValueError,
            ):

                continue

            if not (
                math.isfinite(start)
                and math.isfinite(end)
            ):

                continue

            if end <= start:

                continue

            # Never allow negative timestamps.
            start = max(
                0.0,
                start,
            )

            regions.append(
                (
                    start,
                    end,
                )
            )

        return regions

    # ==========================================================
    # MERGE NEARBY SPEECH
    # ==========================================================

    def _merge_regions(
        self,
        regions: List[Tuple[float, float]],
    ) -> List[Tuple[float, float]]:

        if not regions:
            return []

        # ------------------------------------------------------
        # Sort defensively.
        #
        # Silero normally returns ordered timestamps, but this
        # makes the method safe if the source changes.
        # ------------------------------------------------------

        ordered = sorted(
            regions,
            key=lambda item: item[0],
        )

        merged: List[
            Tuple[float, float]
        ] = []

        current_start, current_end = (
            ordered[0]
        )

        for start, end in ordered[1:]:

            gap = (
                start
                - current_end
            )

            # --------------------------------------------------
            # Important:
            #
            # gap <= merge_gap includes:
            #
            #   overlapping regions
            #   touching regions
            #   very small pauses
            #
            # This means speech is preserved.
            # --------------------------------------------------

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

    # ==========================================================
    # SPLIT LONG REGIONS
    # ==========================================================

    def _split_long_regions(
        self,
        regions: List[Tuple[float, float]],
    ) -> List[Tuple[float, float]]:

        """
        Split only regions longer than max_segment_duration.

        IMPORTANT:
            No audio is discarded.

        A 12.2 second region with an 8 second maximum becomes
        approximately:

            6.1 + 6.1

        rather than:

            8.0 + 4.2

        Likewise:

            16.2

        becomes approximately:

            8.1 + 8.1

        rather than:

            8.0 + 8.0 + 0.2

        This prevents tiny trailing chunks.
        """

        result: List[
            Tuple[float, float]
        ] = []

        for start, end in regions:

            duration = (
                end - start
            )

            if duration <= 0:
                continue

            # --------------------------------------------------
            # Normal region.
            #
            # Keep it exactly as detected.
            # --------------------------------------------------

            if (
                duration
                <= self.max_segment_duration
            ):

                result.append(
                    (
                        start,
                        end,
                    )
                )

                continue

            # --------------------------------------------------
            # Determine how many chunks are required.
            # --------------------------------------------------

            number_of_chunks = max(
                1,
                math.ceil(
                    duration
                    / self.max_segment_duration
                ),
            )

            # --------------------------------------------------
            # Distribute the complete region evenly.
            #
            # This guarantees:
            #
            #   sum(chunk durations) == duration
            #
            # and avoids a tiny final chunk.
            # --------------------------------------------------

            chunk_duration = (
                duration
                / number_of_chunks
            )

            current = start

            for index in range(
                number_of_chunks
            ):

                if (
                    index
                    == number_of_chunks - 1
                ):

                    chunk_end = end

                else:

                    chunk_end = (
                        start
                        + (
                            (
                                index
                                + 1
                            )
                            * chunk_duration
                        )
                    )

                if chunk_end <= current:
                    continue

                result.append(
                    (
                        current,
                        chunk_end,
                    )
                )

                current = chunk_end

        return result

    # ==========================================================
    # PUBLIC VAD
    # ==========================================================

    def __call__(
        self,
        wav_filepath: str,
    ) -> List[Tuple[float, float]]:

        try:

            # --------------------------------------------------
            # 1. Decode once
            # --------------------------------------------------

            audio = self._load_audio(
                wav_filepath
            )

            # --------------------------------------------------
            # 2. Silero speech detection
            # --------------------------------------------------

            raw_regions = self._detect(
                audio
            )

            if not raw_regions:
                return []

            # --------------------------------------------------
            # 3. Merge nearby speech
            #
            # Short speech is NOT removed.
            #
            # If a short utterance is close to another speech
            # region, it gets combined.
            #
            # If it is isolated, it remains intact.
            # --------------------------------------------------

            merged_regions = (
                self._merge_regions(
                    raw_regions
                )
            )

            # --------------------------------------------------
            # 4. Split ONLY long regions
            #
            # No short-region filtering.
            # No audio is discarded.
            # --------------------------------------------------

            final_regions = (
                self._split_long_regions(
                    merged_regions
                )
            )

            return final_regions

        except KeyboardInterrupt:

            raise

        except Exception as exc:

            self._error(
                exc
            )

            return []

    # ==========================================================
    # ERROR HANDLING
    # ==========================================================

    def _error(
        self,
        error,
    ):

        if self.error_callback:

            try:

                self.error_callback(
                    error
                )

                return

            except Exception:

                pass

        print(
            error
        )