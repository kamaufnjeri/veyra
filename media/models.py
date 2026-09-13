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
        if self.video_mode not in {
            "fast_copy",
            "reencode",
        }:
            raise ValueError(
                "video_mode must be "
                "'fast_copy' or 'reencode'."
            )

        if self.audio_mode not in {
            "fast_copy",
            "reencode",
        }:
            raise ValueError(
                "audio_mode must be "
                "'fast_copy' or 'reencode'."
            )

        if not 0 <= self.crf <= 51:
            raise ValueError(
                "crf must be between 0 and 51."
            )

        if not self.video_codec:
            raise ValueError(
                "video_codec cannot be empty."
            )

        if not self.audio_codec:
            raise ValueError(
                "audio_codec cannot be empty."
            )

        if not self.preset:
            raise ValueError(
                "preset cannot be empty."
            )

        if not self.audio_bitrate:
            raise ValueError(
                "audio_bitrate cannot be empty."
            )


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
    Settings for sequential media joining.

    MediaJoiner joins compatible files of the same media type:

        video + video + video
        audio + audio + audio

    It does not mux independent streams such as:

        video + audio

    Use MediaMuxer for that operation.
    """

    join_subtitles: bool = True

    subtitle: SubtitleSettings = field(
        default_factory=SubtitleSettings
    )

    def validate(self) -> None:
        MediaSettings.validate(self)

        self.subtitle.validate()

# ============================================================
# MUXER
# ============================================================


@dataclass(frozen=True, slots=True)
class MuxerSettings:
    """
    Settings for muxing independent media streams into one
    container.

    Typical use:

        video + audio
        video + audio + subtitles
        video + multiple audio tracks
        video + multiple subtitle tracks

    Unlike MediaJoiner, muxing does not concatenate media
    sequentially. It places independent streams into the same
    output container.

    Stream modes:

        fast_copy
            Copy the existing stream without re-encoding.

        reencode
            Re-encode the stream using the selected codec/settings.
    """

    video_mode: str = "fast_copy"
    audio_mode: str = "fast_copy"

    video_codec: str = "libx264"
    audio_codec: str = "aac"

    preset: str = "veryfast"
    crf: int = 20
    audio_bitrate: str = "192k"

    pixel_format: str = "yuv420p"

    subtitle_codec: Optional[str] = None
    subtitle_encoding: str = "utf-8"

    keep_metadata: bool = True
    faststart: bool = True

    overwrite: bool = False

    def validate(self) -> None:
        # ----------------------------------------------------
        # Video
        # ----------------------------------------------------

        if self.video_mode not in {
            "fast_copy",
            "reencode",
        }:
            raise ValueError(
                "video_mode must be "
                "'fast_copy' or 'reencode'."
            )

        # ----------------------------------------------------
        # Audio
        # ----------------------------------------------------

        if self.audio_mode not in {
            "fast_copy",
            "reencode",
        }:
            raise ValueError(
                "audio_mode must be "
                "'fast_copy' or 'reencode'."
            )

        # ----------------------------------------------------
        # Video codec
        # ----------------------------------------------------

        if not self.video_codec:
            raise ValueError(
                "video_codec cannot be empty."
            )

        # ----------------------------------------------------
        # Audio codec
        # ----------------------------------------------------

        if not self.audio_codec:
            raise ValueError(
                "audio_codec cannot be empty."
            )

        # ----------------------------------------------------
        # Encoding
        # ----------------------------------------------------

        if not self.preset:
            raise ValueError(
                "preset cannot be empty."
            )

        if not 0 <= self.crf <= 51:
            raise ValueError(
                "crf must be between 0 and 51."
            )

        if not self.audio_bitrate:
            raise ValueError(
                "audio_bitrate cannot be empty."
            )

        # ----------------------------------------------------
        # Pixel format
        # ----------------------------------------------------

        if not self.pixel_format:
            raise ValueError(
                "pixel_format cannot be empty."
            )

        # ----------------------------------------------------
        # Subtitle encoding
        # ----------------------------------------------------

        if not self.subtitle_encoding:
            raise ValueError(
                "subtitle_encoding cannot be empty."
            )

        # ----------------------------------------------------
        # Subtitle codec
        # ----------------------------------------------------

        if self.subtitle_codec is not None:
            if not self.subtitle_codec.strip():
                raise ValueError(
                    "subtitle_codec cannot be empty when provided."
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
        MediaSettings.validate(self)

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
                f"Unsupported output format: "
                f"{self.output_format}"
            )


# ============================================================
# COMPRESSOR
# ============================================================


@dataclass(frozen=True, slots=True)
class CompressorSettings:
    """
    Settings specifically for reducing media size.

    Compression always re-encodes the streams that are selected
    for compression. Copying a stream does not reduce its size.

    The compressor can process:

        video
        audio
        video + audio
    """

    video_codec: str = "libx264"
    audio_codec: str = "aac"

    video_crf: int = 28
    video_preset: str = "veryfast"

    audio_bitrate: str = "128k"

    pixel_format: str = "yuv420p"

    resolution: Optional[str] = None

    compress_video: bool = True
    compress_audio: bool = True

    keep_subtitles: bool = True
    keep_metadata: bool = True

    faststart: bool = True
    overwrite: bool = False

    def validate(self) -> None:
        if not self.compress_video and not self.compress_audio:
            raise ValueError(
                "At least one of compress_video or "
                "compress_audio must be enabled."
            )

        if not self.video_codec:
            raise ValueError(
                "video_codec cannot be empty."
            )

        if not self.audio_codec:
            raise ValueError(
                "audio_codec cannot be empty."
            )

        if not 0 <= self.video_crf <= 51:
            raise ValueError(
                "video_crf must be between 0 and 51."
            )

        if not self.video_preset:
            raise ValueError(
                "video_preset cannot be empty."
            )

        if not self.audio_bitrate:
            raise ValueError(
                "audio_bitrate cannot be empty."
            )

        if self.pixel_format == "":
            raise ValueError(
                "pixel_format cannot be empty."
            )

        if self.resolution is not None:
            if not self.resolution.strip():
                raise ValueError(
                    "resolution cannot be empty."
                )


# ============================================================
# EXTRACTOR
# ============================================================


@dataclass(frozen=True, slots=True)
class ExtractorSettings:
    """
    Settings for extracting media streams.

    Supported stream types:

        audio
        video
        subtitle
    """

    stream_type: str = "audio"

    stream_index: Optional[int] = None

    output_format: Optional[str] = None

    audio_codec: Optional[str] = None
    audio_bitrate: str = "192k"

    video_codec: Optional[str] = None
    video_pixel_format: Optional[str] = None

    subtitle_format: Optional[str] = None

    overwrite: bool = False

    def validate(self) -> None:
        allowed_stream_types = {
            "audio",
            "video",
            "subtitle",
        }

        stream_type = self.stream_type.lower()

        if stream_type not in allowed_stream_types:
            raise ValueError(
                "stream_type must be "
                "'audio', 'video', or 'subtitle'."
            )

        if self.stream_index is not None:
            if self.stream_index < 0:
                raise ValueError(
                    "stream_index cannot be negative."
                )

        if not self.audio_bitrate:
            raise ValueError(
                "audio_bitrate cannot be empty."
            )

        if self.output_format is not None:
            if not self.output_format.strip():
                raise ValueError(
                    "output_format cannot be empty."
                )

        if self.subtitle_format is not None:
            allowed_subtitle_formats = {
                "srt",
                "vtt",
                "ass",
                "ssa",
            }

            fmt = (
                self.subtitle_format
                .lower()
                .lstrip(".")
            )

            if fmt not in allowed_subtitle_formats:
                raise ValueError(
                    "subtitle_format must be "
                    "'srt', 'vtt', 'ass', or 'ssa'."
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
                "audio_mode must be "
                "'fast_copy' or 'reencode'."
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

# ============================================================
# MUX RESULT
# ============================================================

@dataclass(frozen=True, slots=True)
class MuxResult:
    """
    Result returned after muxing independent media streams
    into a single output container.

    The inputs are the source media files supplied to the
    mux operation. The output is the final container.

    video_streams:
        Number of video streams written to the output.

    audio_streams:
        Number of audio streams written to the output.

    subtitle_streams:
        Number of subtitle streams written to the output.
    """

    inputs: tuple[Path, ...]
    output: Path
    duration: float
    video_streams: int
    audio_streams: int
    subtitle_streams: int

@dataclass(frozen=True, slots=True)
class ConvertResult:
    source: Path
    output: Path
    duration: float


@dataclass(frozen=True, slots=True)
class CompressResult:
    source: Path
    output: Path

    duration: float

    original_size: int
    output_size: int

    @property
    def bytes_saved(self) -> int:
        return max(
            0,
            self.original_size - self.output_size,
        )

    @property
    def compression_ratio(self) -> float:
        if self.original_size <= 0:
            return 0.0

        return (
            self.output_size
            / self.original_size
        )

    @property
    def size_reduction(self) -> float:
        if self.original_size <= 0:
            return 0.0

        return (
            1.0
            - (
                self.output_size
                / self.original_size
            )
        )


@dataclass(frozen=True, slots=True)
class ExtractResult:
    source: Path
    output: Path

    stream_type: str
    stream_index: int

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