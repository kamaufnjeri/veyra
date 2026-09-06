from __future__ import annotations

import tempfile
from pathlib import Path

from .exceptions import (
    MediaOutputError,
    MediaValidationError,
)
from .models import BurnResult
from .runner import CommandRunner
from .toolchain import FFmpegToolchain


class SubtitleBurner:
    """Burn subtitles permanently into video frames."""

    def __init__(
        self,
        toolchain: FFmpegToolchain | None = None,
        runner: CommandRunner | None = None,
    ) -> None:
        self.toolchain = toolchain or FFmpegToolchain()
        self.runner = runner or CommandRunner()

    def burn(
        self,
        video: str | Path,
        subtitle: str | Path,
        output: str | Path,
        *,
        overwrite: bool = True,
        video_codec: str = "libx264",
        preset: str = "medium",
        crf: int = 20,
        audio_codec: str = "copy",
    ) -> BurnResult:
        video_path = self._validate(video)
        subtitle_path = self._validate(subtitle)

        output_path = Path(output).expanduser().resolve()

        if video_path == output_path:
            raise MediaValidationError(
                "Input and output cannot be the same file."
            )

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        subtitle_filter_path = self._escape_filter_path(
            subtitle_path
        )

        subtitle_filter = (
            f"subtitles='{subtitle_filter_path}'"
        )

        command = [
            self.toolchain.ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y" if overwrite else "-n",
            "-i",
            str(video_path),
            "-vf",
            subtitle_filter,
            "-c:v",
            video_codec,
            "-preset",
            preset,
            "-crf",
            str(crf),
            "-c:a",
            audio_codec,
            "-movflags",
            "+faststart",
        ]

        temporary = self._temporary_output(output_path)

        command.append(str(temporary))

        try:
            self.runner.run(command)

            if not temporary.exists():
                raise MediaOutputError(
                    f"Burned subtitle output was not created: "
                    f"{temporary}"
                )

            temporary.replace(output_path)

        finally:
            temporary.unlink(missing_ok=True)

        return BurnResult(
            input_path=video_path,
            subtitle_path=subtitle_path,
            output_path=output_path,
        )

    @staticmethod
    def _escape_filter_path(
        path: Path,
    ) -> str:
        """
        Escape a Linux path for ffmpeg's subtitles filter.
        """

        value = str(path)

        return (
            value
            .replace("\\", "\\\\")
            .replace(":", "\\:")
            .replace("'", "\\'")
        )

    @staticmethod
    def _validate(path: str | Path) -> Path:
        path = Path(path).expanduser().resolve()

        if not path.exists():
            raise MediaValidationError(
                f"File does not exist: {path}"
            )

        if not path.is_file():
            raise MediaValidationError(
                f"Path is not a file: {path}"
            )

        return path

    @staticmethod
    def _temporary_output(
        output: Path,
    ) -> Path:
        with tempfile.NamedTemporaryFile(
            prefix=f".{output.stem}.",
            suffix=output.suffix,
            dir=output.parent,
            delete=False,
        ) as file:
            return Path(file.name)