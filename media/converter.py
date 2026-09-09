from __future__ import annotations

from pathlib import Path

from .ffmpeg import FFmpeg
from .ffprobe import FFProbe
from .models import (
    ConvertResult,
    ConverterSettings,
)


class MediaConverter:

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

    def convert(
        self,
        input_path: str | Path,
        output_path: str | Path,
        settings: ConverterSettings | None = None,
    ) -> ConvertResult:

        settings = settings or ConverterSettings()

        settings.validate()

        source = Path(input_path)

        output = Path(output_path).with_suffix(
            f".{settings.output_format.lstrip('.')}"
        )

        self.ff.validate_input(source)

        self.ff.validate_output(
            source,
            output,
            settings.overwrite,
        )

        duration = self.ffprobe.duration(
            source
        )

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

            command += [
                "-map_metadata",
                "0" if settings.keep_metadata else "-1",
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

                output_format = output.suffix.lower()

                if output_format in {
                    ".mp4",
                    ".m4v",
                    ".mov",
                }:

                    command += [
                        "-c:s",
                        "mov_text",
                    ]

                elif output_format in {
                    ".mkv",
                    ".webm",
                }:

                    command += [
                        "-c:s",
                        "ass",
                    ]

                else:

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

            command.append(
                str(temp)
            )

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
