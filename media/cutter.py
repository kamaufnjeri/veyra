from __future__ import annotations

import tempfile
from pathlib import Path

from .exceptions import (
    MediaOutputError,
    MediaValidationError,
)
from .models import CutOptions, CutResult
from .probe import MediaProbe
from .runner import CommandRunner
from .toolchain import FFmpegToolchain


class MediaCutter:
    """Trim media files."""

    def __init__(
        self,
        probe: MediaProbe | None = None,
        toolchain: FFmpegToolchain | None = None,
        runner: CommandRunner | None = None,
    ) -> None:
        self.toolchain = toolchain or FFmpegToolchain()
        self.runner = runner or CommandRunner()

        self.probe = probe or MediaProbe(
            toolchain=self.toolchain,
            runner=self.runner,
        )

    def trim(
        self,
        input_path: str | Path,
        output_path: str | Path,
        *,
        options: CutOptions | None = None,
        overwrite: bool = True,
    ) -> CutResult:
        input_path = Path(input_path).expanduser().resolve()
        output_path = Path(output_path).expanduser().resolve()

        options = options or CutOptions()

        if options.start < 0:
            raise MediaValidationError(
                "Start time cannot be negative."
            )

        if options.end is not None:
            if options.end <= options.start:
                raise MediaValidationError(
                    "End time must be greater than start time."
                )

        if input_path == output_path:
            raise MediaValidationError(
                "Input and output cannot be the same file."
            )

        duration = self.probe.duration(input_path)

        if options.start >= duration:
            raise MediaValidationError(
                "Start time is beyond the media duration."
            )

        if options.end is not None:
            end = min(options.end, duration)
        else:
            end = None

        if options.reencode:
            self._trim_reencode(
                input_path,
                output_path,
                start=options.start,
                end=end,
                overwrite=overwrite,
            )

        elif options.accurate:
            self._trim_copy_accurate(
                input_path,
                output_path,
                start=options.start,
                end=end,
                overwrite=overwrite,
            )

        else:
            self._trim_copy_fast(
                input_path,
                output_path,
                start=options.start,
                end=end,
                overwrite=overwrite,
            )

        return CutResult(
            input_path=input_path,
            output_path=output_path,
            start=options.start,
            end=end,
        )

    def _trim_copy_fast(
        self,
        input_path: Path,
        output_path: Path,
        *,
        start: float,
        end: float | None,
        overwrite: bool,
    ) -> None:
        command = [
            self.toolchain.ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y" if overwrite else "-n",
            "-ss",
            str(start),
            "-i",
            str(input_path),
        ]

        if end is not None:
            command.extend(
                [
                    "-t",
                    str(end - start),
                ]
            )

        command.extend(
            [
                "-c",
                "copy",
                str(output_path),
            ]
        )

        self.runner.run(command)

    def _trim_copy_accurate(
        self,
        input_path: Path,
        output_path: Path,
        *,
        start: float,
        end: float | None,
        overwrite: bool,
    ) -> None:
        command = [
            self.toolchain.ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y" if overwrite else "-n",
            "-i",
            str(input_path),
            "-ss",
            str(start),
        ]

        if end is not None:
            command.extend(
                [
                    "-t",
                    str(end - start),
                ]
            )

        command.extend(
            [
                "-c",
                "copy",
                str(output_path),
            ]
        )

        self.runner.run(command)

    def _trim_reencode(
        self,
        input_path: Path,
        output_path: Path,
        *,
        start: float,
        end: float | None,
        overwrite: bool,
    ) -> None:
        command = [
            self.toolchain.ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y" if overwrite else "-n",
            "-i",
            str(input_path),
            "-ss",
            str(start),
        ]

        if end is not None:
            command.extend(
                [
                    "-t",
                    str(end - start),
                ]
            )

        command.extend(
            [
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "23",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
                str(output_path),
            ]
        )

        self.runner.run(command)