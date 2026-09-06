from __future__ import annotations


class MediaError(Exception):
    """Base exception for all Veyra media errors."""


class MediaValidationError(MediaError):
    """Raised when media operation arguments are invalid."""


class MediaProbeError(MediaError):
    """Raised when ffprobe cannot inspect a media file."""


class MediaCommandError(MediaError):
    """Raised when ffmpeg/ffprobe exits unsuccessfully."""

    def __init__(
        self,
        message: str,
        *,
        command: list[str] | None = None,
        return_code: int | None = None,
        stdout: str = "",
        stderr: str = "",
    ) -> None:
        super().__init__(message)

        self.command = command or []
        self.return_code = return_code
        self.stdout = stdout
        self.stderr = stderr


class MediaCancelledError(MediaError):
    """Raised when an operation is cancelled."""


class MediaOutputError(MediaError):
    """Raised when an output file cannot be created safely."""


class SubtitleError(MediaError):
    """Base exception for subtitle operations."""


class SubtitleParseError(SubtitleError):
    """Raised when a subtitle cannot be parsed."""


class SubtitleJoinError(SubtitleError):
    """Raised when subtitle joining fails."""


class UnsupportedMediaError(MediaError):
    """Raised when a media format/codec is unsupported."""


class IncompatibleMediaError(MediaError):
    """Raised when media inputs cannot be concatenated directly."""