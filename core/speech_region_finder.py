from __future__ import annotations

import math
import wave

try:
    import audioop
except ImportError:
    audioop = None


class SpeechRegionFinder:

    def percentile(self, arr, percent):
        arr = sorted(arr)

        if not arr:
            return 0

        k = (len(arr) - 1) * percent
        f = math.floor(k)
        c = math.ceil(k)

        if f == c:
            return arr[int(k)]

        d0 = arr[int(f)] * (c - k)
        d1 = arr[int(c)] * (k - f)

        return d0 + d1

    def __init__(
        self,
        frame_width=4096,
        min_region_size=0.5,
        max_region_size=6,
        error_messages_callback=None,
    ):
        self.frame_width = frame_width
        self.min_region_size = min_region_size
        self.max_region_size = max_region_size
        self.error_messages_callback = error_messages_callback

    def __call__(self, wav_filepath):
        try:
            with wave.open(wav_filepath, "rb") as reader:

                sample_width = reader.getsampwidth()
                rate = reader.getframerate()

                total_duration = (
                    reader.getnframes() / rate
                )

                chunk_duration = (
                    float(self.frame_width) / rate
                )

                n_chunks = int(
                    total_duration / chunk_duration
                )

                energies = []

                for _ in range(n_chunks):
                    chunk = reader.readframes(
                        self.frame_width
                    )

                    if not chunk:
                        break

                    energies.append(
                        audioop.rms(
                            chunk,
                            sample_width,
                        )
                    )

            if not energies:
                return []

            threshold = self.percentile(
                energies,
                0.2,
            )

            elapsed_time = 0
            regions = []
            region_start = None

            for energy in energies:

                is_silence = energy <= threshold

                max_exceeded = (
                    region_start is not None
                    and elapsed_time - region_start
                    >= self.max_region_size
                )

                if (
                    max_exceeded or is_silence
                ) and region_start is not None:

                    if (
                        elapsed_time - region_start
                        >= self.min_region_size
                    ):
                        regions.append(
                            (
                                region_start,
                                elapsed_time,
                            )
                        )

                    region_start = None

                elif (
                    region_start is None
                    and not is_silence
                ):
                    region_start = elapsed_time

                elapsed_time += chunk_duration

            # Close a region that reaches the end
            # of the audio.
            if region_start is not None:
                if (
                    elapsed_time - region_start
                    >= self.min_region_size
                ):
                    regions.append(
                        (
                            region_start,
                            elapsed_time,
                        )
                    )

            return regions

        except KeyboardInterrupt:
            if self.error_messages_callback:
                self.error_messages_callback(
                    "Cancelling all tasks"
                )
            else:
                print("Cancelling all tasks")

            return []

        except Exception as e:
            if self.error_messages_callback:
                self.error_messages_callback(e)
            else:
                print(e)

            return []