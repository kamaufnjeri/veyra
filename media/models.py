from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional


# ============================================================
# ERRORS
# ============================================================


class MediaError(Exception):
    """Base exception for media operations."""


class MediaCancelled(MediaError):
    """Raised when an operation is cancelled."""


# ============================================================
# COMMON SETTINGS
# ============================================================


@dataclass(frozen=True, slots=True)
class MediaSettings:
    """
    Settings shared by media operations.

    Copying is the default because it is considerably faster than
    re-encoding. Operations that technically require encoding,
    such as subtitle burning, override the necessary stream mode.
    """

    video_mode: str = "fast_copy"
    audio_mode: str = "fast_copy"

    video_codec: str = "libx264"
    audio_codec: str = "aac"

    preset: str = "veryfast"
    crf: int = 20
    audio_bitrate: str = "192k"

    pixel_format: str = "yuv420p"

    faststart: bool = True
    overwrite: bool = False

    output_format: Optional[str] = None

    def validate(self) -> None:
        if self.video_mode not in {"fast_copy", "reencode"}:
            raise ValueError(
                "video_mode must be 'fast_copy' or 'reencode'."
            )

        if self.audio_mode not in {"fast_copy", "reencode"}:
            raise ValueError(
                "audio_mode must be 'fast_copy' or 'reencode'."
            )

        if not 0 <= self.crf <= 51:
            raise ValueError("crf must be between 0 and 51.")

        if not self.video_codec:
            raise ValueError("video_codec cannot be empty.")

        if not self.audio_codec:
            raise ValueError("audio_codec cannot be empty.")

        if not self.preset:
            raise ValueError("preset cannot be empty.")

        if not self.audio_bitrate:
            raise ValueError("audio_bitrate cannot be empty.")


# ============================================================
# SUBTITLE SETTINGS
# ============================================================


@dataclass(frozen=True, slots=True)
class SubtitleSettings:
    output_format: str = "same"
    language: Optional[str] = None
    encoding: str = "utf-8"
    overwrite: bool = False

    def validate(self) -> None:
        if self.output_format.lower() not in {
            "same",
            "srt",
            "vtt",
            "ass",
            "ssa",
        }:
            raise ValueError(
                "output_format must be "
                "'same', 'srt', 'vtt', 'ass', or 'ssa'."
            )


# ============================================================
# CUTTER
# ============================================================


@dataclass(frozen=True, slots=True)
class CutterSettings(MediaSettings):
    mode: str = "duration"

    parts: Optional[int] = None
    duration: Optional[float] = None
    durations: tuple[float, ...] = ()
    timestamps: tuple[float, ...] = ()

    start: float = 0.0
    end: Optional[float] = None

    cut_subtitles: bool = True
    subtitle: SubtitleSettings = field(
        default_factory=SubtitleSettings
    )

    numbered_suffix: str = "-of-"


# ============================================================
# JOINER
# ============================================================


@dataclass(frozen=True, slots=True)
class JoinerSettings(MediaSettings):
    """
    Files should normally have compatible streams when using
    fast_copy.
    """

    join_subtitles: bool = True
    subtitle: SubtitleSettings = field(
        default_factory=SubtitleSettings
    )


# ============================================================
# CONVERTER
# ============================================================


@dataclass(frozen=True, slots=True)
class ConverterSettings(MediaSettings):
    """
    Settings controlling media conversion.
    """

    output_format: str = "mp4"

    keep_subtitles: bool = True
    keep_metadata: bool = True

    def validate(self) -> None:
        super().validate()

        allowed_formats = {
            "mp4",
            "mkv",
            "mov",
            "avi",
            "webm",
            "ts",
        }

        fmt = self.output_format.lower().lstrip(".")

        if fmt not in allowed_formats:
            raise ValueError(
                f"Unsupported output format: {self.output_format}"
            )



# ============================================================
# BURNER
# ============================================================


@dataclass(frozen=True, slots=True)
class BurnerSettings:
    """
    Burning subtitles requires video re-encoding.

    Audio remains copy by default.
    """

    video_codec: str = "libx264"
    audio_mode: str = "fast_copy"
    audio_codec: str = "aac"

    preset: str = "veryfast"
    crf: int = 20
    audio_bitrate: str = "192k"

    pixel_format: str = "yuv420p"

    subtitle_font: Optional[str] = None
    subtitle_font_size: Optional[int] = None
    subtitle_color: Optional[str] = None

    overwrite: bool = False
    faststart: bool = True

    def validate(self) -> None:
        if self.audio_mode not in {
            "fast_copy",
            "reencode",
        }:
            raise ValueError(
                "audio_mode must be 'fast_copy' or 'reencode'."
            )

        if not 0 <= self.crf <= 51:
            raise ValueError(
                "crf must be between 0 and 51."
            )

        if self.subtitle_font_size is not None:
            if self.subtitle_font_size <= 0:
                raise ValueError(
                    "subtitle_font_size must be greater than zero."
                )


# ============================================================
# SUBTITLE MODEL
# ============================================================


@dataclass(frozen=True, slots=True)
class SubtitleTrack:
    source: Path

    language: Optional[str] = None
    title: Optional[str] = None

    embedded: bool = False
    stream_index: Optional[int] = None
    codec: Optional[str] = None


# ============================================================
# MEDIA MODEL
# ============================================================


@dataclass(frozen=True, slots=True)
class MediaInput:
    path: Path
    duration: float
    subtitles: tuple[SubtitleTrack, ...] = ()


@dataclass(frozen=True, slots=True)
class MediaPart:
    index: int
    total: int

    source: Path
    output: Path

    start: float
    end: float
    duration: float

    subtitle_outputs: tuple[Path, ...] = ()


@dataclass(frozen=True, slots=True)
class CutResult:
    source: Path
    outputs: tuple[Path, ...]
    parts: tuple[MediaPart, ...]
    duration: float


@dataclass(frozen=True, slots=True)
class JoinResult:
    inputs: tuple[Path, ...]
    output: Path
    duration: float


@dataclass(frozen=True, slots=True)
class ConvertResult:
    source: Path
    output: Path
    duration: float


@dataclass(frozen=True, slots=True)
class BurnResult:
    source: Path
    subtitle: Path
    output: Path
    duration: float


# ============================================================
# CALLBACK
# ============================================================


ProgressCallback = Callable[..., None]
