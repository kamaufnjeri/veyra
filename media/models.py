from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping


ProgressCallback = Callable[["Progress"], None]


@dataclass(frozen=True)
class Progress:
    """
    Represents operation progress.

    Attributes:
        fraction:
            Value from 0.0 to 1.0.
        percent:
            Percentage from 0 to 100.
        elapsed:
            Seconds elapsed.
        remaining:
            Estimated seconds remaining, if known.
        speed:
            ffmpeg processing speed, e.g. 1.5x.
        message:
            Human-readable status.
    """

    fraction: float
    percent: float
    elapsed: float | None = None
    remaining: float | None = None
    speed: float | None = None
    message: str = ""


@dataclass(frozen=True)
class MediaStream:
    """Description of an individual media stream."""

    index: int
    codec_type: str
    codec_name: str | None = None
    codec_long_name: str | None = None

    language: str | None = None
    title: str | None = None

    width: int | None = None
    height: int | None = None

    sample_rate: int | None = None
    channels: int | None = None
    channel_layout: str | None = None

    frame_rate: float | None = None
    bitrate: int | None = None
    duration: float | None = None

    disposition: Mapping[str, int] = field(default_factory=dict)
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class MediaInfo:
    """Complete media information returned by ffprobe."""

    path: Path
    format_name: str | None
    format_long_name: str | None

    duration: float
    size: int | None
    bitrate: int | None

    streams: tuple[MediaStream, ...]

    metadata: Mapping[str, str] = field(default_factory=dict)

    @property
    def video_streams(self) -> tuple[MediaStream, ...]:
        return tuple(
            stream
            for stream in self.streams
            if stream.codec_type == "video"
        )

    @property
    def audio_streams(self) -> tuple[MediaStream, ...]:
        return tuple(
            stream
            for stream in self.streams
            if stream.codec_type == "audio"
        )

    @property
    def subtitle_streams(self) -> tuple[MediaStream, ...]:
        return tuple(
            stream
            for stream in self.streams
            if stream.codec_type == "subtitle"
        )

    @property
    def has_video(self) -> bool:
        return bool(self.video_streams)

    @property
    def has_audio(self) -> bool:
        return bool(self.audio_streams)

    @property
    def has_subtitles(self) -> bool:
        return bool(self.subtitle_streams)


@dataclass(frozen=True)
class EncodeOptions:
    """
    Encoding configuration.

    If video_codec/audio_codec are None, sensible defaults are selected
    by the transcoder.
    """

    video_codec: str = "libx264"
    audio_codec: str = "aac"

    preset: str = "medium"
    crf: int = 23

    audio_bitrate: str = "192k"

    pixel_format: str = "yuv420p"

    width: int | None = None
    height: int | None = None

    fps: float | None = None

    video_bitrate: str | None = None

    threads: int | None = None

    faststart: bool = True

    tune: str | None = None

    profile: str | None = None

    level: str | None = None

    extra_video_args: tuple[str, ...] = ()
    extra_audio_args: tuple[str, ...] = ()


@dataclass(frozen=True)
class CutOptions:
    """
    Video cutting configuration.
    """

    start: float = 0.0
    end: float | None = None

    accurate: bool = True

    reencode: bool = False


@dataclass(frozen=True)
class MuxSubtitle:
    """External subtitle to add to a media container."""

    path: Path
    language: str | None = None
    title: str | None = None

    default: bool = False
    forced: bool = False


@dataclass(frozen=True)
class MediaPart:
    """
    A video segment and its corresponding external subtitles.

    Example:

        MediaPart(
            video=Path("episode1.mp4"),
            subtitles={
                "en": Path("episode1.en.srt"),
                "es": Path("episode1.es.srt"),
            },
        )
    """

    video: Path

    subtitles: Mapping[str, Path] = field(default_factory=dict)


@dataclass(frozen=True)
class ConversionResult:
    input_path: Path
    output_path: Path
    duration: float
    reencoded: bool


@dataclass(frozen=True)
class JoinResult:
    video: Path
    subtitles: Mapping[str, Path]

    durations: tuple[float, ...]
    total_duration: float

    reencoded: bool


@dataclass(frozen=True)
class MuxResult:
    output: Path


@dataclass(frozen=True)
class ExtractionResult:
    output: Path


@dataclass(frozen=True)
class CutResult:
    input_path: Path
    output_path: Path

    start: float
    end: float | None


@dataclass(frozen=True)
class BurnResult:
    input_path: Path
    subtitle_path: Path
    output_path: Path