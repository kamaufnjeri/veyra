from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path
from typing import Any, Optional
from .ffprobe import FFProbe


class InspectionError(Exception):
    """Raised when media inspection fails."""



class MediaInspector:
    """
    Convert FFprobe information into a clean, JSON-friendly structure.

    Handles:
        - video
        - audio
        - embedded subtitles
        - external subtitle files
        - format/container information
        - useful summary information
    """

    SUBTITLE_EXTENSIONS = {
        ".srt": "srt",
        ".vtt": "vtt",
        ".ass": "ass",
        ".ssa": "ssa",
    }

    TEXT_SUBTITLE_CODECS = {
        "subrip",
        "srt",
        "ass",
        "ssa",
        "webvtt",
        "mov_text",
        "text",
        "ttml",
    }

    def __init__(
        self,
        ffprobe: FFProbe | None = None,
    ) -> None:
        self.ffprobe = ffprobe or FFProbe()

    # ------------------------------------------------------------------
    # PUBLIC
    # ------------------------------------------------------------------

    def inspect(
        self,
        input_path: str | Path,
        *,
        include_subtitle_text: bool = False,
        include_raw: bool = False,
    ) -> dict[str, Any]:

        path = Path(input_path)
        data = self.ffprobe.probe(path)

        result = {
            "file": self._file(path),
            "format": self._format(data),
            "duration": self._duration(data),
            "video": [
                self._video(stream, i)
                for i, stream in enumerate(self._streams(data, "video"))
            ],
            "audio": [
                self._audio(stream, i)
                for i, stream in enumerate(self._streams(data, "audio"))
            ],
            "subtitles": self._subtitles(
                path,
                data,
                include_subtitle_text,
            ),
        }

        result["summary"] = self._summary(result)

        if include_raw:
            result["raw"] = data

        return result

    def inspect_json(
        self,
        input_path: str | Path,
        *,
        include_subtitle_text: bool = False,
        include_raw: bool = False,
        indent: int = 2,
    ) -> str:
        return json.dumps(
            self.inspect(
                input_path,
                include_subtitle_text=include_subtitle_text,
                include_raw=include_raw,
            ),
            indent=indent,
            ensure_ascii=False,
        )

    # ------------------------------------------------------------------
    # FILE / FORMAT
    # ------------------------------------------------------------------

    @staticmethod
    def _file(path: Path) -> dict[str, Any]:
        stat = path.stat()

        return {
            "name": path.name,
            "path": str(path),
            "directory": str(path.parent),
            "extension": path.suffix.lower(),
            "size_bytes": stat.st_size,
            "size_mb": round(stat.st_size / 1024 / 1024, 3),
        }

    def _format(self, data: dict[str, Any]) -> dict[str, Any]:
        fmt = data.get("format") or {}

        return {
            "name": fmt.get("format_name"),
            "long_name": fmt.get("format_long_name"),
            "filename": fmt.get("filename"),
            "duration": self._number(fmt.get("duration")),
            "size_bytes": self._integer(fmt.get("size")),
            "bitrate": self._integer(fmt.get("bit_rate")),
            "start_time": self._number(fmt.get("start_time")),
            "probe_score": self._integer(fmt.get("probe_score")),
            "tags": dict(fmt.get("tags") or {}),
        }

    # ------------------------------------------------------------------
    # VIDEO
    # ------------------------------------------------------------------

    def _video(
        self,
        stream: dict[str, Any],
        number: int,
    ) -> dict[str, Any]:

        width = self._integer(stream.get("width"))
        height = self._integer(stream.get("height"))

        return {
            "stream": number,
            "index": stream.get("index"),
            "codec": stream.get("codec_name"),
            "codec_long_name": stream.get("codec_long_name"),
            "profile": stream.get("profile"),
            "level": stream.get("level"),
            "width": width,
            "height": height,
            "resolution": self._resolution(width, height),
            "aspect_ratio": self._aspect_ratio(
                stream.get("display_aspect_ratio"),
                width,
                height,
            ),
            "pixel_format": stream.get("pix_fmt"),
            "fps": self._fraction(
                stream.get("avg_frame_rate")
                or stream.get("r_frame_rate")
            ),
            "frame_rate": self._fraction(
                stream.get("r_frame_rate")
            ),
            "frames": self._integer(stream.get("nb_frames")),
            "bitrate": self._integer(stream.get("bit_rate")),
            "duration": self._number(stream.get("duration")),
            "start_time": self._number(stream.get("start_time")),
            "color": {
                "space": stream.get("color_space"),
                "transfer": stream.get("color_transfer"),
                "primaries": stream.get("color_primaries"),
                "range": stream.get("color_range"),
            },
            "interlaced": self._interlaced(stream),
            "tags": dict(stream.get("tags") or {}),
        }

    # ------------------------------------------------------------------
    # AUDIO
    # ------------------------------------------------------------------

    def _audio(
        self,
        stream: dict[str, Any],
        number: int,
    ) -> dict[str, Any]:

        channels = self._integer(stream.get("channels"))
        layout = stream.get("channel_layout")

        return {
            "stream": number,
            "index": stream.get("index"),
            "codec": stream.get("codec_name"),
            "codec_long_name": stream.get("codec_long_name"),
            "profile": stream.get("profile"),
            "sample_rate": self._integer(stream.get("sample_rate")),
            "channels": channels,
            "channel_layout": layout,
            "channel_description": self._channel_description(
                channels,
                layout,
            ),
            "bitrate": self._integer(stream.get("bit_rate")),
            "bits_per_sample": self._integer(
                stream.get("bits_per_sample")
            ),
            "duration": self._number(stream.get("duration")),
            "start_time": self._number(stream.get("start_time")),
            "language": self._language(stream),
            "title": self._title(stream),
            "default": self._disposition(stream, "default"),
            "forced": self._disposition(stream, "forced"),
            "tags": dict(stream.get("tags") or {}),
        }

    # ------------------------------------------------------------------
    # SUBTITLES
    # ------------------------------------------------------------------

    def _subtitles(
        self,
        media_path: Path,
        data: dict[str, Any],
        include_text: bool,
    ) -> list[dict[str, Any]]:

        result = []

        streams = self._streams(data, "subtitle")

        for number, stream in enumerate(streams):
            result.append(self._embedded_subtitle(stream, number))

        start = len(result)

        for number, path in enumerate(
            self._sidecars(media_path),
            start=start,
        ):
            item = self._sidecar_subtitle(path, number)

            if include_text:
                item["text"] = self._read_text(path)

            result.append(item)

        return result

    def _embedded_subtitle(
        self,
        stream: dict[str, Any],
        number: int,
    ) -> dict[str, Any]:

        tags = stream.get("tags") or {}

        return {
            "stream": number,
            "index": stream.get("index"),
            "source": "embedded",
            "codec": stream.get("codec_name"),
            "codec_long_name": stream.get("codec_long_name"),
            "language": tags.get("language"),
            "title": tags.get("title"),
            "duration": self._number(stream.get("duration")),
            "start_time": self._number(stream.get("start_time")),
            "default": self._disposition(stream, "default"),
            "forced": self._disposition(stream, "forced"),
            "hearing_impaired": self._disposition(
                stream,
                "hearing_impaired",
            ),
            "text_based": (
                str(stream.get("codec_name") or "").lower()
                in self.TEXT_SUBTITLE_CODECS
            ),
            "tags": dict(tags),
        }

    def _sidecar_subtitle(
        self,
        path: Path,
        number: int,
    ) -> dict[str, Any]:

        return {
            "stream": number,
            "index": None,
            "source": "external",
            "path": str(path),
            "filename": path.name,
            "format": self.SUBTITLE_EXTENSIONS[path.suffix.lower()],
            "extension": path.suffix.lower(),
            "language": self._language_from_filename(path),
            "title": None,
            "size_bytes": path.stat().st_size,
        }

    def _sidecars(self, media_path: Path) -> list[Path]:
        return sorted(
            (
                path
                for path in media_path.parent.glob(
                    f"{media_path.stem}.*"
                )
                if path.is_file()
                and path.suffix.lower() in self.SUBTITLE_EXTENSIONS
            ),
            key=lambda p: p.name.lower(),
        )

    @staticmethod
    def _language_from_filename(
        path: Path,
    ) -> Optional[str]:

        for part in path.stem.split(".")[1:]:
            value = part.lower()

            if len(value) in (2, 3) and value.isalpha():
                return value

            if (
                len(value) == 5
                and value[2] == "-"
                and value[:2].isalpha()
                and value[3:].isalpha()
            ):
                return value

        return None

    @staticmethod
    def _read_text(path: Path) -> str:
        return path.read_text(
            encoding="utf-8-sig",
            errors="replace",
        )

    # ------------------------------------------------------------------
    # SUMMARY
    # ------------------------------------------------------------------

    @staticmethod
    def _summary(result: dict[str, Any]) -> dict[str, Any]:
        video = result["video"]
        audio = result["audio"]
        subtitles = result["subtitles"]

        primary = video[0] if video else {}
        primary_audio = audio[0] if audio else {}

        return {
            "has_video": bool(video),
            "has_audio": bool(audio),
            "has_subtitles": bool(subtitles),
            "video_streams": len(video),
            "audio_streams": len(audio),
            "subtitle_streams": len(subtitles),
            "duration": result["duration"],
            "resolution": primary.get("resolution"),
            "video_codec": primary.get("codec"),
            "fps": primary.get("fps"),
            "audio_codec": primary_audio.get("codec"),
            "languages": sorted({
                item["language"]
                for item in audio + subtitles
                if item.get("language")
            }),
        }

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    @staticmethod
    def _streams(
        data: dict[str, Any],
        codec_type: str,
    ) -> list[dict[str, Any]]:
        return [
            stream
            for stream in data.get("streams", [])
            if stream.get("codec_type") == codec_type
        ]

    @classmethod
    def _duration(
        cls,
        data: dict[str, Any],
    ) -> Optional[float]:

        duration = cls._number(
            (data.get("format") or {}).get("duration")
        )

        if duration is not None:
            return duration

        values = [
            cls._number(stream.get("duration"))
            for stream in data.get("streams", [])
        ]

        values = [value for value in values if value is not None]

        return max(values) if values else None

    @staticmethod
    def _number(value: Any) -> Optional[float]:
        try:
            value = float(value)
            return round(value, 6) if math.isfinite(value) else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _integer(value: Any) -> Optional[int]:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _fraction(cls, value: Any) -> Optional[float]:
        if not value or value == "0/0":
            return None

        try:
            numerator, denominator = str(value).split("/", 1)
            denominator = float(denominator)

            if denominator == 0:
                return None

            return cls._number(float(numerator) / denominator)
        except (TypeError, ValueError, ZeroDivisionError):
            return None

    @staticmethod
    def _resolution(
        width: Optional[int],
        height: Optional[int],
    ) -> Optional[str]:
        return (
            f"{width}x{height}"
            if width is not None and height is not None
            else None
        )

    @staticmethod
    def _aspect_ratio(
        value: Any,
        width: Optional[int],
        height: Optional[int],
    ) -> Optional[str]:

        if value and value != "0:1":
            return str(value)

        if not width or not height:
            return None

        divisor = math.gcd(width, height)
        return f"{width // divisor}:{height // divisor}"

    @staticmethod
    def _channel_description(
        channels: Optional[int],
        layout: Optional[str],
    ) -> Optional[str]:

        if layout:
            return layout

        return {
            1: "mono",
            2: "stereo",
            6: "5.1",
            8: "7.1",
        }.get(channels, f"{channels} channels" if channels else None)

    @staticmethod
    def _language(stream: dict[str, Any]) -> Optional[str]:
        return (stream.get("tags") or {}).get("language")

    @staticmethod
    def _title(stream: dict[str, Any]) -> Optional[str]:
        return (stream.get("tags") or {}).get("title")

    @staticmethod
    def _disposition(
        stream: dict[str, Any],
        name: str,
    ) -> bool:
        return bool((stream.get("disposition") or {}).get(name, 0))

    @staticmethod
    def _interlaced(stream: dict[str, Any]) -> bool:
        return str(stream.get("field_order") or "").lower() not in {
            "",
            "progressive",
            "unknown",
            "0",
        }
