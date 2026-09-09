from __future__ import annotations

from pathlib import Path

from .ffmpeg import FFmpeg
from .ffprobe import FFProbe
from .models import BurnResult, BurnerSettings


class SubtitleBurner:

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
            executable=ffprobe
        )

    def burn(
        self,
        video: str | Path,
        subtitle: str | Path,
        output: str | Path,
        settings: BurnerSettings | None = None,
    ) -> BurnResult:

        settings = settings or BurnerSettings()

        settings.validate()

        video = Path(video)
        subtitle = Path(subtitle)
        output = Path(output)

        self.ff.validate_input(video)
        self.ff.validate_input(subtitle)

        self.ff.validate_output(
            video,
            output,
            settings.overwrite,
        )

        duration = self.ffprobe.duration(
            video
        )

        temp = self.ff.temporary_path(
            output.suffix or ".mp4"
        )

        subtitle_filter = self._subtitle_filter(
            subtitle,
            settings,
        )

        command = [
            self.ff.ffmpeg,
            "-hide_banner",
            "-y",
            "-nostdin",

            "-i",
            str(video),

            "-vf",
            subtitle_filter,

            "-map",
            "0:v:0",
            "-map",
            "0:a?",
        ]

        # ----------------------------------------------------
        # VIDEO
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # AUDIO
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # FASTSTART
        # ----------------------------------------------------

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

        try:

            self.ff.run(
                command,
                message="Burning subtitles",
                duration=duration,
            )

            self.ff.atomic_replace(
                temp,
                output,
            )

            return BurnResult(
                source=video,
                subtitle=subtitle,
                output=output,
                duration=duration,
            )

        finally:

            self.ff.cleanup()

    # ========================================================
    # FILTER
    # ========================================================
    @staticmethod
    def _ass_color(hex_color: str) -> str:
        hex_color = hex_color.lstrip("#")

        if len(hex_color) != 6:
            raise ValueError("Color must be #RRGGBB")

        rr = hex_color[0:2]
        gg = hex_color[2:4]
        bb = hex_color[4:6]

        return f"&H00{bb}{gg}{rr}"


    @staticmethod
    def _subtitle_filter(
        
        subtitle: Path,
        settings: BurnerSettings,
    ) -> str:

        path = (
            str(subtitle.resolve())
            .replace("\\", "/")
            .replace(":", r"\:")
            .replace("'", r"\'")
        )

        extension = subtitle.suffix.lower()

        if extension in {".ass", ".ssa"}:
            return f"subtitles='{path}'"

        options = []

        if settings.subtitle_font:

            options.append(
                f"FontName={settings.subtitle_font}"
            )

        if settings.subtitle_font_size:

            options.append(
                f"FontSize={settings.subtitle_font_size}"
            )

        if settings.subtitle_color:

            color = SubtitleBurner._ass_color(
                settings.subtitle_color
            )

            options.append(
                f"PrimaryColour={color}"
    )


        if options:

            force_style = ",".join(
                options
            )

            return (
                f"subtitles='{path}':"
                f"force_style='{force_style}'"
            )

        return f"subtitles='{path}'"
