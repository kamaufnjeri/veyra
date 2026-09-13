from __future__ import annotations

from pathlib import Path

from .ffmpeg import FFmpeg
from .ffprobe import FFProbe
from .models import (
    CompressResult,
    CompressorSettings,
)


class MediaCompressor:

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

    # ========================================================
    # COMPRESS
    # ========================================================

    def compress(
        self,
        input_path: str | Path,
        output_path: str | Path,
        settings: CompressorSettings | None = None,
    ) -> CompressResult:

        settings = (
            settings
            or CompressorSettings()
        )

        settings.validate()

        source = Path(
            input_path
        ).expanduser()

        output = Path(
            output_path
        ).expanduser()

        self.ff.validate_input(
            source
        )

        self.ff.validate_output(
            source,
            output,
            settings.overwrite,
        )

        probe = self.ffprobe.probe(
            source
        )

        streams = probe.get(
            "streams",
            [],
        )

        has_video = any(
            isinstance(stream, dict)
            and stream.get("codec_type") == "video"
            for stream in streams
        )

        has_audio = any(
            isinstance(stream, dict)
            and stream.get("codec_type") == "audio"
            for stream in streams
        )

        if not has_video and not has_audio:
            raise ValueError(
                f"Input contains neither video "
                f"nor audio: {source}"
            )

        if (
            settings.compress_video
            and not has_video
        ):
            raise ValueError(
                "compress_video=True but the "
                "input contains no video stream."
            )

        if (
            settings.compress_audio
            and not has_audio
        ):
            raise ValueError(
                "compress_audio=True but the "
                "input contains no audio stream."
            )

        duration = self.ffprobe.duration(
            source
        )

        original_size = source.stat().st_size

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

                # First video stream only.
                "-map",
                "0:v:0?",

                # First audio stream only.
                "-map",
                "0:a:0?",
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

            if has_video:

                if settings.compress_video:

                    command += [
                        "-c:v",
                        settings.video_codec,

                        "-preset",
                        settings.video_preset,

                        "-crf",
                        str(settings.video_crf),

                        "-pix_fmt",
                        settings.pixel_format,
                    ]

                    if settings.resolution:

                        command += [
                            "-vf",
                            f"scale={settings.resolution}",
                        ]

                else:

                    command += [
                        "-c:v",
                        "copy",
                    ]

            # ------------------------------------------------
            # AUDIO
            # ------------------------------------------------

            if has_audio:

                if settings.compress_audio:

                    command += [
                        "-c:a",
                        settings.audio_codec,

                        "-b:a",
                        settings.audio_bitrate,
                    ]

                else:

                    command += [
                        "-c:a",
                        "copy",
                    ]

            # ------------------------------------------------
            # SUBTITLE CODEC
            # ------------------------------------------------

            if settings.keep_subtitles:

                output_format = (
                    output.suffix
                    .lower()
                )

                if output_format in {
                    ".mp4",
                    ".m4v",
                    ".mov",
                }:

                    command += [
                        "-c:s",
                        "mov_text",
                    ]

                elif output_format == ".mkv":

                    command += [
                        "-c:s",
                        "copy",
                    ]

                elif output_format == ".webm":

                    command += [
                        "-c:s",
                        "webvtt",
                    ]

            # ------------------------------------------------
            # FASTSTART
            # ------------------------------------------------

            if (
                settings.faststart
                and output.suffix.lower()
                in {
                    ".mp4",
                    ".m4v",
                    ".mov",
                }
            ):

                command += [
                    "-movflags",
                    "+faststart",
                ]

            # ------------------------------------------------
            # OUTPUT
            # ------------------------------------------------

            command.append(
                str(temp)
            )

            # ------------------------------------------------
            # RUN
            # ------------------------------------------------

            self.ff.run(
                command,
                message="Compressing media",
                duration=duration,
            )

            # ------------------------------------------------
            # VERIFY OUTPUT
            # ------------------------------------------------

            if not temp.exists():

                raise FileNotFoundError(
                    "FFmpeg completed successfully "
                    "but no output file was created."
                )

            output_size = temp.stat().st_size

            if output_size <= 0:

                raise ValueError(
                    "FFmpeg produced an empty output file."
                )

            # ------------------------------------------------
            # ATOMIC REPLACE
            # ------------------------------------------------

            self.ff.atomic_replace(
                temp,
                output,
            )

            return CompressResult(
                source=source,
                output=output,
                duration=duration,
                original_size=original_size,
                output_size=output_size,
            )

        finally:

            self.ff.cleanup()