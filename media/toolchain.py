from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass

from .exceptions import MediaCommandError, MediaValidationError


@dataclass(frozen=True)
class FFmpegToolchain:
    """
    Configuration for ffmpeg and ffprobe.

    By default the executables are discovered from PATH.
    """

    ffmpeg: str = "ffmpeg"
    ffprobe: str = "ffprobe"

    def validate(self) -> None:
        """Ensure ffmpeg and ffprobe are available."""

        if shutil.which(self.ffmpeg) is None:
            raise MediaValidationError(
                f"ffmpeg executable not found: {self.ffmpeg}"
            )

        if shutil.which(self.ffprobe) is None:
            raise MediaValidationError(
                f"ffprobe executable not found: {self.ffprobe}"
            )

    def ffmpeg_version(self) -> str:
        """Return the installed ffmpeg version."""

        self.validate()

        process = subprocess.run(
            [self.ffmpeg, "-version"],
            capture_output=True,
            text=True,
            check=False,
        )

        if process.returncode != 0:
            raise MediaCommandError(
                "Unable to determine ffmpeg version.",
                command=[self.ffmpeg, "-version"],
                return_code=process.returncode,
                stdout=process.stdout,
                stderr=process.stderr,
            )

        return process.stdout.splitlines()[0].strip()

    def ffprobe_version(self) -> str:
        """Return the installed ffprobe version."""

        self.validate()

        process = subprocess.run(
            [self.ffprobe, "-version"],
            capture_output=True,
            text=True,
            check=False,
        )

        if process.returncode != 0:
            raise MediaCommandError(
                "Unable to determine ffprobe version.",
                command=[self.ffprobe, "-version"],
                return_code=process.returncode,
                stdout=process.stdout,
                stderr=process.stderr,
            )

        return process.stdout.splitlines()[0].strip()