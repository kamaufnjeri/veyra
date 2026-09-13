from __future__ import annotations

from pathlib import Path

from .ffmpeg import FFmpeg
from .ffprobe import FFProbe
from .models import (
    ExtractResult,
    ExtractorSettings,
)


class MediaExtractor:

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
    # EXTRACT
    # ========================================================

    def extract(
        self,
        input_path: str | Path,
        output_path: str | Path,
        settings: ExtractorSettings | None = None,
    ) -> ExtractResult:

        settings = (
            settings
            or ExtractorSettings()
        )

        settings.validate()

        source = Path(
            input_path
        ).expanduser()

        self.ff.validate_input(
            source
        )

        output = self._resolve_output(
            source,
            output_path,
            settings,
        )

        self.ff.validate_output(
            source,
            output,
            settings.overwrite,
        )

        probe = self.ffprobe.probe(
            source
        )

        stream_type = (
            settings.stream_type
            .lower()
        )

        stream = self._select_stream(
            probe,
            stream_type,
            settings.stream_index,
        )

        stream_index = int(
            stream["index"]
        )

        duration = self._stream_duration(
            stream,
            source,
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
                f"0:{stream_index}",
            ]

            if stream_type == "audio":

                self._configure_audio(
                    command,
                    output,
                    settings,
                    stream,
                )

            elif stream_type == "video":

                self._configure_video(
                    command,
                    settings,
                )

            elif stream_type == "subtitle":

                self._configure_subtitle(
                    command,
                    output,
                    settings,
                )

            command.append(
                str(temp)
            )

            self.ff.run(
                command,
                message=(
                    f"Extracting "
                    f"{stream_type}"
                ),
                duration=duration,
            )

            self.ff.atomic_replace(
                temp,
                output,
            )

            return ExtractResult(
                source=source,
                output=output,
                stream_type=stream_type,
                stream_index=stream_index,
                duration=duration,
            )

        finally:

            self.ff.cleanup()

    # ========================================================
    # OUTPUT
    # ========================================================

    @staticmethod
    def _resolve_output(
        source: Path,
        output: str | Path,
        settings: ExtractorSettings,
    ) -> Path:

        output = Path(
            output
        ).expanduser()

        if output.suffix:
            return output

        stream_type = (
            settings.stream_type
            .lower()
        )

        if settings.output_format:

            extension = (
                settings.output_format
                .lower()
                .lstrip(".")
            )

        elif stream_type == "audio":

            extension = "mp3"

        elif stream_type == "subtitle":

            extension = (
                settings.subtitle_format
                or "srt"
            )

        else:

            extension = "mkv"

        return output.with_suffix(
            f".{extension}"
        )

    # ========================================================
    # STREAM SELECTION
    # ========================================================

    @staticmethod
    def _select_stream(
        probe: dict,
        stream_type: str,
        stream_index: int | None,
    ) -> dict:

        streams = probe.get(
            "streams",
            []
        )

        matching = [
            stream
            for stream in streams
            if isinstance(stream, dict)
            and stream.get("codec_type")
            == stream_type
        ]

        if not matching:
            raise ValueError(
                f"No {stream_type} stream "
                "was found in the input."
            )

        if stream_index is not None:

            for stream in matching:

                if stream.get("index") == stream_index:
                    return stream

        return matching[0]

    # ========================================================
    # STREAM DURATION
    # ========================================================

    def _stream_duration(
        self,
        stream: dict,
        source: Path,
    ) -> float:

        value = stream.get(
            "duration"
        )

        try:

            if value is not None:

                duration = float(
                    value
                )

                if duration >= 0:
                    return duration

        except (
            TypeError,
            ValueError,
        ):
            pass

        return self.ffprobe.duration(
            source
        )

    # ========================================================
    # AUDIO
    # ========================================================

    @staticmethod
    def _configure_audio(
        command: list[str],
        output: Path,
        settings: ExtractorSettings,
        stream: dict,
    ) -> None:

        output_format = (
            output.suffix
            .lower()
            .lstrip(".")
        )

        codec = settings.audio_codec

        if codec is None:

            if output_format == "mp3":
                codec = "libmp3lame"

            elif output_format in {
                "m4a",
                "mp4",
            }:
                codec = "aac"

            elif output_format == "opus":
                codec = "libopus"

            elif output_format == "ogg":
                codec = "libvorbis"

            elif output_format == "flac":
                codec = "flac"

            else:

                codec = (
                    stream.get(
                        "codec_name"
                    )
                    or "aac"
                )

        command += [
            "-vn",
            "-c:a",
            codec,
        ]

        if settings.audio_bitrate:

            command += [
                "-b:a",
                settings.audio_bitrate,
            ]

    # ========================================================
    # VIDEO
    # ========================================================

    @staticmethod
    def _configure_video(
        command: list[str],
        settings: ExtractorSettings,
    ) -> None:

        command += [
            "-an",
            "-sn",
            "-dn",
        ]

        if settings.video_codec:

            command += [
                "-c:v",
                settings.video_codec,
            ]

        else:

            command += [
                "-c:v",
                "copy",
            ]

        if settings.video_pixel_format:

            command += [
                "-pix_fmt",
                settings.video_pixel_format,
            ]

    # ========================================================
    # SUBTITLE
    # ========================================================

    @staticmethod
    def _configure_subtitle(
        command: list[str],
        output: Path,
        settings: ExtractorSettings,
    ) -> None:

        output_format = (
            settings.subtitle_format
            or output.suffix
            .lower()
            .lstrip(".")
        )

        output_format = (
            output_format
            .lower()
            .lstrip(".")
        )

        codec_map = {
            "srt": "srt",
            "vtt": "webvtt",
            "ass": "ass",
            "ssa": "ssa",
        }

        codec = codec_map.get(
            output_format
        )

        if codec is None:

            raise ValueError(
                "Unsupported subtitle output "
                f"format: {output_format}"
            )

        command += [
            "-c:s",
            codec,
        ]