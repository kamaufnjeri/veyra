from __future__ import annotations

from pathlib import Path
from typing import Optional

from .ffmpeg import FFmpeg
from .ffprobe import FFProbe
from .models import (
    CutResult,
    CutterSettings,
    MediaPart,
)
from .subtitles import SubtitleManager


class MediaCutter:

    EPSILON = 1e-6

    def __init__(
        self,
        *,
        ffmpeg: str = "ffmpeg",
        ffprobe: str = "ffprobe",
        progress_callback=None,
        cancellation_callback=None,
    ):
        self.ff = FFmpeg(
            ffmpeg=ffmpeg,
            progress_callback=progress_callback,
            cancellation_callback=cancellation_callback,
        )

        self.ffprobe = FFProbe(
            executable=ffprobe,
        )

        self.subtitles = SubtitleManager(
            ffmpeg=self.ff,
            ffprobe=self.ffprobe,
        )

    # ========================================================
    # PUBLIC
    # ========================================================

    def cut(
        self,
        input_path: str | Path,
        settings: Optional[CutterSettings] = None,
    ) -> CutResult:

        settings = settings or CutterSettings()

        settings.validate()

        source = Path(input_path)

        self.ff.validate_input(source)

        duration = self.ffprobe.duration(source)

        ranges = self._build_ranges(
            duration,
            settings,
        )

        output_dir = Path(
            settings.output_directory
            if hasattr(settings, "output_directory")
            else source.parent
        )

        output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        tracks = self.subtitles.discover(
            source
        )

        tracks = self.subtitles.filter(
            tracks,
            settings.subtitle,
        )

        parts = []

        try:
            for index, (start, end) in enumerate(
                ranges,
                1,
            ):

                output = self._output_path(
                    source,
                    start,
                    end,
                    index,
                    len(ranges),
                    settings,
                    output_dir,
                )

                self.ff.validate_output(
                    source,
                    output,
                    settings.overwrite,
                )

                self._cut_video(
                    source,
                    output,
                    start,
                    end,
                    settings,
                )

                subtitle_outputs = []

                if settings.cut_subtitles:
                    for track in tracks:

                        subtitle_output = (
                            output.with_suffix(
                                f".{track.language or 'sub'}"
                                f"{self._subtitle_extension(track, settings)}"
                            )
                        )

                        self.subtitles.cut(
                            track,
                            start,
                            end,
                            subtitle_output,
                            settings.subtitle,
                        )

                        subtitle_outputs.append(
                            subtitle_output
                        )

                parts.append(
                    MediaPart(
                        index=index,
                        total=len(ranges),
                        source=source,
                        output=output,
                        start=start,
                        end=end,
                        duration=end - start,
                        subtitle_outputs=tuple(
                            subtitle_outputs
                        ),
                    )
                )

            return CutResult(
                source=source,
                outputs=tuple(
                    part.output
                    for part in parts
                ),
                parts=tuple(parts),
                duration=duration,
            )

        finally:
            self.ff.cleanup()

    # ========================================================
    # VIDEO
    # ========================================================

    def _cut_video(
        self,
        source: Path,
        output: Path,
        start: float,
        end: float,
        settings: CutterSettings,
    ) -> None:

        duration = end - start

        temp = self.ff.temporary_path(
            output.suffix or ".mp4"
        )

        command = [
            self.ff.ffmpeg,

            "-hide_banner",
            "-y",
            "-nostdin",

            "-ss",
            self._seconds(start),

            "-i",
            str(source),

            "-t",
            self._seconds(duration),

            "-map",
            "0:v:0?",
            "-map",
            "0:a?",
            "-sn",
            "-dn",
        ]

        if settings.video_mode == "fast_copy":

            command += [
                "-c:v",
                "copy",
            ]

        else:

            command += [
                "-c:v",
                settings.video_codec,
                "-preset",
                settings.preset,
                "-crf",
                str(settings.crf),
                "-pix_fmt",
                settings.pixel_format,
            ]

        if settings.audio_mode == "fast_copy":

            command += [
                "-c:a",
                "copy",
            ]

        else:

            command += [
                "-c:a",
                settings.audio_codec,
                "-b:a",
                settings.audio_bitrate,
            ]

        if (
            settings.faststart
            and output.suffix.lower()
            in {".mp4", ".m4v", ".mov"}
        ):
            command += [
                "-movflags",
                "+faststart",
            ]

        command.append(
            str(temp)
        )

        self.ff.run(
            command,
            message="Cutting video",
            duration=duration,
        )

        self.ff.atomic_replace(
            temp,
            output,
        )

    # ========================================================
    # RANGES
    # ========================================================

    def _build_ranges(
        self,
        duration: float,
        settings: CutterSettings,
    ) -> list[tuple[float, float]]:

        mode = settings.mode

        # ====================================================
        # SPLIT INTO EQUAL PARTS
        # ====================================================

        if mode == "parts":

            if (
                not settings.parts
                or settings.parts < 1
            ):
                raise ValueError(
                    "parts must be at least 1."
                )

            return [
                (
                    duration * i / settings.parts,
                    duration * (i + 1) / settings.parts,
                )
                for i in range(settings.parts)
            ]

        # ====================================================
        # FIXED DURATION
        # ====================================================

        if mode == "duration":

            if (
                not settings.duration
                or settings.duration <= 0
            ):
                raise ValueError(
                    "duration must be greater than zero."
                )

            return self._fixed_ranges(
                duration,
                settings.duration,
            )

        # ====================================================
        # EXPLICIT DURATIONS
        # ====================================================

        if mode == "durations":

            return self._explicit_ranges(
                duration,
                settings.durations,
            )

        # ====================================================
        # TIMESTAMPS
        # ====================================================

        if mode == "timestamps":

            return self._timestamp_ranges(
                duration,
                settings.timestamps,
            )

        # ====================================================
        # START / END RANGE
        #
        # "start_end" is the UI name.
        # "range" is the original backend name.
        #
        # Both mean:
        #     cut from start timestamp to end timestamp.
        # ====================================================

        if mode in {
            "range",
            "start_end",
        }:

            start = settings.start

            end = (
                settings.end
                if settings.end is not None
                else duration
            )

            self._validate_range(
                start,
                end,
                duration,
            )

            return [
                (
                    start,
                    end,
                )
            ]

        # ====================================================
        # UNKNOWN MODE
        # ====================================================

        raise ValueError(
            f"Unknown cut mode: {mode}"
        )


    @classmethod
    def _fixed_ranges(
        cls,
        duration: float,
        size: float,
    ):
        result = []

        start = 0.0

        while start < duration - cls.EPSILON:

            end = min(
                start + size,
                duration,
            )

            result.append(
                (start, end)
            )

            start = end

        return result

    @classmethod
    def _explicit_ranges(
        cls,
        duration: float,
        durations,
    ):
        result = []

        start = 0.0

        for size in durations:

            if size <= 0:
                raise ValueError(
                    "All durations must be positive."
                )

            if start >= duration:
                break

            end = min(
                start + size,
                duration,
            )

            result.append(
                (start, end)
            )

            start = end

        if not result:
            raise ValueError(
                "No valid durations supplied."
            )

        result[-1] = (
            result[-1][0],
            duration,
        )

        return result

    @classmethod
    def _timestamp_ranges(
        cls,
        duration: float,
        timestamps,
    ):
        points = [0.0]

        previous = 0.0

        for value in timestamps:

            value = float(value)

            if value <= previous:
                raise ValueError(
                    "Timestamps must be strictly increasing."
                )

            if value >= duration:

                if abs(value - duration) <= cls.EPSILON:
                    value = duration

                else:
                    raise ValueError(
                        "Timestamp exceeds media duration."
                    )

            points.append(value)

            previous = value

        points.append(duration)

        return [
            (a, b)
            for a, b in zip(
                points,
                points[1:],
            )
            if b - a > cls.EPSILON
        ]

    @staticmethod
    def _validate_range(
        start,
        end,
        duration,
    ):
        if start < 0:
            raise ValueError(
                "start cannot be negative."
            )

        if end <= start:
            raise ValueError(
                "end must be greater than start."
            )

        if end > duration:
            raise ValueError(
                "end exceeds media duration."
            )

    # ========================================================
    # OUTPUT
    # ========================================================

    @staticmethod
    def _output_path(
        source,
        start,
        end,
        index,
        total,
        settings,
        directory,
    ):

        if settings.mode in {
            "range",
            "start_end",
        }:

            name = (
                f"{source.stem}-"
                f"{MediaCutter._time_name(start)}-"
                f"{MediaCutter._time_name(end)}"
                f"{source.suffix}"
            )

        else:

            name = (
                f"{source.stem}_"
                f"{index}"
                f"{settings.numbered_suffix}"
                f"{total}"
                f"{source.suffix}"
            )

        return directory / name

    @staticmethod
    def _time_name(seconds):

        seconds = int(
            round(seconds)
        )

        hours, remainder = divmod(
            seconds,
            3600,
        )

        minutes, seconds = divmod(
            remainder,
            60,
        )

        if hours:
            return (
                f"{hours}h"
                f"{minutes:02d}m"
                f"{seconds:02d}s"
            )

        return (
            f"{minutes}m"
            f"{seconds:02d}s"
        )

    @staticmethod
    def _seconds(value):
        return f"{value:.6f}"

    @staticmethod
    def _subtitle_extension(
        track,
        settings,
    ):

        if settings.subtitle.output_format != "same":
            return "." + settings.subtitle.output_format

        if track.source.suffix:
            return track.source.suffix.lower()

        return ".srt"
