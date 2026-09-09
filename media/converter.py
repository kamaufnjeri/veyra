from __future__ import annotations

from pathlib import Path

from .ffmpeg import FFmpeg
from .models import (
    ConvertResult,
    ConverterSettings,
)


class MediaConverter:

    def __init__(
        self,
        *,
        ffmpeg="ffmpeg",
        ffprobe="ffprobe",
        progress_callback=None,
        cancellation_callback=None,
    ):
        self.ff = FFmpeg(
            ffmpeg=ffmpeg,
            ffprobe=ffprobe,
            progress_callback=progress_callback,
            cancellation_callback=cancellation_callback,
        )

    def convert(
        self,
        input_path: str | Path,
        output_path: str | Path,
        settings: ConverterSettings | None = None,
    ) -> ConvertResult:

        settings = settings or ConverterSettings()
        settings.validate()

        source = Path(input_path)
        output = Path(output_path)

        # Output format is controlled by ConverterSettings.
        output = output.with_suffix(
            f".{settings.output_format.lstrip('.')}"
        )

        self.ff.validate_input(source)

        self.ff.validate_output(
            source,
            output,
            settings.overwrite,
        )

        duration = self.ff.duration(source)

        temp = self.ff.temporary_path(
            output.suffix or ".tmp"
        )

        try:
            command = [
                self.ff.ffmpeg,
                "-hide_banner",
                "-y",
                "-nostdin",

                "-i",
                str(source),

                "-map",
                "0:v:0?",
                "-map",
                "0:a?",
            ]

            # ------------------------------------------------
            # SUBTITLES
            # ------------------------------------------------

            if settings.keep_subtitles:
                command += [
                    "-map",
                    "0:s?",
                ]
            else:
                command += [
                    "-sn",
                ]

            # ------------------------------------------------
            # METADATA
            # ------------------------------------------------

            if settings.keep_metadata:
                command += [
                    "-map_metadata",
                    "0",
                ]
            else:
                command += [
                    "-map_metadata",
                    "-1",
                ]

            # ------------------------------------------------
            # VIDEO
            # ------------------------------------------------

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

            # ------------------------------------------------
            # AUDIO
            # ------------------------------------------------

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

            # ------------------------------------------------
            # SUBTITLE CODEC
            # ------------------------------------------------

            if settings.keep_subtitles:
                command += [
                    "-c:s",
                    "copy",
                ]

            # ------------------------------------------------
            # FASTSTART
            # ------------------------------------------------

            if (
                settings.faststart
                and output.suffix.lower()
                in {".mp4", ".m4v", ".mov"}
            ):
                command += [
                    "-movflags",
                    "+faststart",
                ]

            command.append(str(temp))

            self.ff.run(
                command,
                message="Converting media",
                duration=duration,
            )

            self.ff.atomic_replace(
                temp,
                output,
            )

            return ConvertResult(
                source=source,
                output=output,
                duration=duration,
            )

        finally:
            self.ff.cleanup()
