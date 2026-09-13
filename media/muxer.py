from __future__ import annotations

from pathlib import Path
from typing import Sequence

from .ffmpeg import FFmpeg
from .ffprobe import FFProbe
from .models import MuxResult, MuxerSettings


class MediaMuxer:
    """
    Combine independent media streams into a single output.

    MediaMuxer is different from MediaJoiner:

        MediaJoiner:
            video + video -> video
            audio + audio -> audio

        MediaMuxer:
            video + audio -> video
            video + subtitle -> video
            video + audio + subtitle -> video

    The inputs are not played sequentially. Their streams are combined
    into the same output container.
    """

    VIDEO_EXTENSIONS = {
        ".mp4",
        ".m4v",
        ".mov",
        ".mkv",
        ".webm",
        ".avi",
        ".ts",
        ".m2ts",
    }

    AUDIO_EXTENSIONS = {
        ".mp3",
        ".m4a",
        ".aac",
        ".wav",
        ".flac",
        ".ogg",
        ".opus",
        ".wma",
    }

    SUBTITLE_EXTENSIONS = {
        ".srt",
        ".vtt",
        ".ass",
        ".ssa",
        ".sub",
        ".ttml",
    }

    TEXT_SUBTITLE_CODECS = {
        "subrip",
        "webvtt",
        "ass",
        "ssa",
        "mov_text",
        "text",
        "sami",
        "ttml",
    }

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

    # ==============================================================
    # PUBLIC API
    # ==============================================================

    def mux(
        self,
        inputs: Sequence[str | Path],
        output: str | Path,
        settings: MuxerSettings | None = None,
    ) -> MuxResult:
        """
        Mux independent media inputs into one output file.

        Typical examples:

            mux(
                ["video.mp4", "audio.mp3"],
                "output.mp4",
            )

            mux(
                ["video.mp4", "audio.mp3", "english.srt"],
                "output.mkv",
            )

        The first input is normally the primary video/media source.
        """

        settings = settings or MuxerSettings()
        settings.validate()

        paths = tuple(Path(path) for path in inputs)

        if not paths:
            raise ValueError("At least one input is required.")

        if len(paths) < 2:
            raise ValueError(
                "MediaMuxer requires at least two inputs."
            )

        for path in paths:
            self.ff.validate_input(path)

        output = Path(output)

        self.ff.validate_output(
            paths[0],
            output,
            settings.overwrite,
        )

        try:
            probes = tuple(
                self.ffprobe.probe(path)
                for path in paths
            )

            primary = self._classify_inputs(
                paths,
                probes,
            )

            if primary["video"] == 0 and primary["audio"] == 0:
                raise ValueError(
                    "No video or audio input was found."
                )

            duration = self._calculate_duration(
                paths,
                probes,
            )

            command = [
                self.ff.ffmpeg,
                "-hide_banner",
                "-y",
                "-nostdin",
            ]

            # ------------------------------------------------------
            # INPUTS
            # ------------------------------------------------------

            for path in paths:
                if self._is_subtitle_file(path):
                    command += [
                        "-sub_charenc",
                        settings.subtitle_encoding,
                    ]

                command += [
                    "-i",
                    str(path),
                ]

            # ------------------------------------------------------
            # VIDEO
            # ------------------------------------------------------

            video_streams = self._video_streams(
                paths,
                probes,
            )

            if video_streams:
                video_input, video_index = video_streams[0]

                command += [
                    "-map",
                    f"{video_input}:{video_index}",
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
            else:
                command += [
                    "-vn",
                ]

            # ------------------------------------------------------
            # AUDIO
            # ------------------------------------------------------

            audio_streams = self._audio_streams(
                paths,
                probes,
            )

            for input_index, stream_index in audio_streams:
                command += [
                    "-map",
                    f"{input_index}:{stream_index}",
                ]

            if audio_streams:
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

            # ------------------------------------------------------
            # SUBTITLES
            # ------------------------------------------------------

            subtitle_streams = self._subtitle_streams(
                paths,
                probes,
            )

            external_subtitles = self._external_subtitles(
                paths,
            )

            total_subtitles = (
                len(subtitle_streams)
                + len(external_subtitles)
            )

            if total_subtitles > 0:
                for input_index, stream_index in subtitle_streams:
                    command += [
                        "-map",
                        f"{input_index}:{stream_index}",
                    ]

                for input_index in external_subtitles:
                    command += [
                        "-map",
                        f"{input_index}:0",
                    ]

                subtitle_codec = self._subtitle_codec(
                    output,
                    settings,
                )

                command += [
                    "-c:s",
                    subtitle_codec,
                ]

            # ------------------------------------------------------
            # DATA / ATTACHMENTS
            # ------------------------------------------------------

            command += [
                "-map_metadata",
                "0",
                "-map_chapters",
                "0",
            ]

            if not settings.keep_metadata:
                command += [
                    "-map_metadata",
                    "-1",
                    "-map_chapters",
                    "-1",
                ]

            command += [
                "-dn",
            ]

            # ------------------------------------------------------
            # FASTSTART
            # ------------------------------------------------------

            if (
                settings.faststart
                and output.suffix.lower()
                in {".mp4", ".m4v", ".mov"}
            ):
                command += [
                    "-movflags",
                    "+faststart",
                ]

            # ------------------------------------------------------
            # OUTPUT
            # ------------------------------------------------------

            temp = self.ff.temporary_path(
                output.suffix or ".mkv"
            )

            command.append(str(temp))

            self.ff.run(
                command,
                message="Muxing media",
                duration=duration,
            )

            self.ff.atomic_replace(
                temp,
                output,
            )

            return MuxResult(
                inputs=paths,
                output=output,
                duration=duration,
                video_streams=len(video_streams),
                audio_streams=len(audio_streams),
                subtitle_streams=total_subtitles,
            )

        finally:
            self.ff.cleanup()

    # ==============================================================
    # INPUT CLASSIFICATION
    # ==============================================================

    @classmethod
    def _classify_inputs(
        cls,
        paths: Sequence[Path],
        probes: Sequence[dict],
    ) -> dict[str, int]:
        result = {
            "video": 0,
            "audio": 0,
            "subtitle": 0,
        }

        for path, probe in zip(paths, probes):
            streams = probe.get("streams", [])

            has_video = any(
                stream.get("codec_type") == "video"
                for stream in streams
            )

            has_audio = any(
                stream.get("codec_type") == "audio"
                for stream in streams
            )

            has_subtitle_stream = any(
                stream.get("codec_type") == "subtitle"
                for stream in streams
            )

            if has_video:
                result["video"] += 1

            if has_audio:
                result["audio"] += 1

            if has_subtitle_stream or cls._is_subtitle_file(path):
                result["subtitle"] += 1

        return result

    # ==============================================================
    # STREAM DISCOVERY
    # ==============================================================

    @staticmethod
    def _video_streams(
        paths: Sequence[Path],
        probes: Sequence[dict],
    ) -> list[tuple[int, int]]:
        streams: list[tuple[int, int]] = []

        for input_index, probe in enumerate(probes):
            for stream in probe.get("streams", []):
                if stream.get("codec_type") != "video":
                    continue

                index = stream.get("index")

                if index is None:
                    continue

                streams.append(
                    (
                        input_index,
                        int(index),
                    )
                )

        return streams

    @staticmethod
    def _audio_streams(
        paths: Sequence[Path],
        probes: Sequence[dict],
    ) -> list[tuple[int, int]]:
        streams: list[tuple[int, int]] = []

        for input_index, probe in enumerate(probes):
            for stream in probe.get("streams", []):
                if stream.get("codec_type") != "audio":
                    continue

                index = stream.get("index")

                if index is None:
                    continue

                streams.append(
                    (
                        input_index,
                        int(index),
                    )
                )

        return streams

    @staticmethod
    def _subtitle_streams(
        paths: Sequence[Path],
        probes: Sequence[dict],
    ) -> list[tuple[int, int]]:
        streams: list[tuple[int, int]] = []

        for input_index, probe in enumerate(probes):
            for stream in probe.get("streams", []):
                if stream.get("codec_type") != "subtitle":
                    continue

                index = stream.get("index")

                if index is None:
                    continue

                streams.append(
                    (
                        input_index,
                        int(index),
                    )
                )

        return streams

    @staticmethod
    def _external_subtitles(
        paths: Sequence[Path],
    ) -> list[int]:
        """
        Return input indexes that are external subtitle files.
        """

        return [
            index
            for index, path in enumerate(paths)
            if MediaMuxer._is_subtitle_file(path)
        ]

    # ==============================================================
    # SUBTITLE HANDLING
    # ==============================================================

    @classmethod
    def _is_subtitle_file(
        cls,
        path: Path,
    ) -> bool:
        return path.suffix.lower() in cls.SUBTITLE_EXTENSIONS

    @classmethod
    def _subtitle_codec(
        cls,
        output: Path,
        settings: MuxerSettings,
    ) -> str:
        if settings.subtitle_codec:
            return settings.subtitle_codec

        suffix = output.suffix.lower()

        if suffix in {".mp4", ".m4v", ".mov"}:
            return "mov_text"

        if suffix in {".mkv", ".webm"}:
            return "copy"

        return "copy"

    # ==============================================================
    # DURATION
    # ==============================================================

    def _calculate_duration(
        self,
        paths: Sequence[Path],
        probes: Sequence[dict],
    ) -> float:
        durations: list[float] = []

        for path, probe in zip(paths, probes):
            duration = self._probe_duration(probe)

            if duration <= 0:
                duration = self.ffprobe.duration(path)

            if duration > 0:
                durations.append(duration)

        if not durations:
            return 0.0

        return max(durations)

    @staticmethod
    def _probe_duration(
        probe: dict,
    ) -> float:
        format_data = probe.get("format", {})

        value = format_data.get("duration")

        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                pass

        durations: list[float] = []

        for stream in probe.get("streams", []):
            value = stream.get("duration")

            if value is None:
                continue

            try:
                durations.append(float(value))
            except (TypeError, ValueError):
                continue

        return max(durations, default=0.0)