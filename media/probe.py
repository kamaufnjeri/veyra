from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .exceptions import MediaProbeError, MediaValidationError
from .models import MediaInfo, MediaStream
from .runner import CommandRunner
from .toolchain import FFmpegToolchain


class MediaProbe:
    """Inspect media files using ffprobe."""

    def __init__(
        self,
        toolchain: FFmpegToolchain | None = None,
        runner: CommandRunner | None = None,
    ) -> None:
        self.toolchain = toolchain or FFmpegToolchain()
        self.runner = runner or CommandRunner()

    def inspect(self, path: str | Path) -> MediaInfo:
        """Return complete ffprobe information."""

        path = Path(path).expanduser().resolve()

        if not path.exists():
            raise MediaValidationError(
                f"Media file does not exist: {path}"
            )

        if not path.is_file():
            raise MediaValidationError(
                f"Media path is not a file: {path}"
            )

        command = [
            self.toolchain.ffprobe,
            "-v",
            "error",
            "-show_format",
            "-show_streams",
            "-of",
            "json",
            str(path),
        ]

        try:
            result = self.runner.run(command)
        except Exception as exc:
            if isinstance(exc, MediaProbeError):
                raise

            raise MediaProbeError(
                f"Unable to probe media file: {path}"
            ) from exc

        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise MediaProbeError(
                f"ffprobe returned invalid JSON for: {path}"
            ) from exc

        return self._parse(path, payload)

    def duration(self, path: str | Path) -> float:
        return self.inspect(path).duration

    def streams(
        self,
        path: str | Path,
    ) -> tuple[MediaStream, ...]:
        return self.inspect(path).streams

    def video_streams(
        self,
        path: str | Path,
    ) -> tuple[MediaStream, ...]:
        return self.inspect(path).video_streams

    def audio_streams(
        self,
        path: str | Path,
    ) -> tuple[MediaStream, ...]:
        return self.inspect(path).audio_streams

    def subtitle_streams(
        self,
        path: str | Path,
    ) -> tuple[MediaStream, ...]:
        return self.inspect(path).subtitle_streams

    def _parse(
        self,
        path: Path,
        payload: dict[str, Any],
    ) -> MediaInfo:
        format_data = payload.get("format", {})
        streams_data = payload.get("streams", [])

        duration = self._float_or_zero(
            format_data.get("duration")
        )

        size = self._int_or_none(
            format_data.get("size")
        )

        bitrate = self._int_or_none(
            format_data.get("bit_rate")
        )

        streams = tuple(
            self._parse_stream(stream)
            for stream in streams_data
        )

        return MediaInfo(
            path=path,
            format_name=format_data.get("format_name"),
            format_long_name=format_data.get("format_long_name"),
            duration=duration,
            size=size,
            bitrate=bitrate,
            streams=streams,
            metadata=format_data.get("tags", {}),
        )

    def _parse_stream(
        self,
        data: dict[str, Any],
    ) -> MediaStream:
        return MediaStream(
            index=int(data.get("index", 0)),
            codec_type=data.get("codec_type", "unknown"),
            codec_name=data.get("codec_name"),
            codec_long_name=data.get("codec_long_name"),
            language=self._language(data),
            title=self._title(data),
            width=self._int_or_none(data.get("width")),
            height=self._int_or_none(data.get("height")),
            sample_rate=self._int_or_none(
                data.get("sample_rate")
            ),
            channels=self._int_or_none(
                data.get("channels")
            ),
            channel_layout=data.get("channel_layout"),
            frame_rate=self._parse_frame_rate(data),
            bitrate=self._int_or_none(
                data.get("bit_rate")
            ),
            duration=self._float_or_none(
                data.get("duration")
            ),
            disposition=data.get("disposition", {}),
            metadata=data.get("tags", {}),
        )

    @staticmethod
    def _language(data: dict[str, Any]) -> str | None:
        tags = data.get("tags", {})

        return (
            tags.get("language")
            or tags.get("LANGUAGE")
        )

    @staticmethod
    def _title(data: dict[str, Any]) -> str | None:
        tags = data.get("tags", {})

        return (
            tags.get("title")
            or tags.get("TITLE")
        )

    @staticmethod
    def _float_or_zero(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _float_or_none(value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _int_or_none(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_frame_rate(
        data: dict[str, Any],
    ) -> float | None:
        value = (
            data.get("avg_frame_rate")
            or data.get("r_frame_rate")
        )

        if not value or value == "0/0":
            return None

        try:
            numerator, denominator = value.split("/", 1)

            denominator_value = float(denominator)

            if denominator_value == 0:
                return None

            return float(numerator) / denominator_value

        except (ValueError, ZeroDivisionError):
            return None