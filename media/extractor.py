from __future__ import annotations

import tempfile
from pathlib import Path

from .exceptions import (
    MediaOutputError,
    MediaValidationError,
)
from .models import ExtractionResult
from .probe import MediaProbe
from .runner import CommandRunner
from .toolchain import FFmpegToolchain


class MediaExtractor:
    """Extract audio and subtitle streams from media."""

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

    def audio(
        self,
        video: str | Path,
        output: str | Path,
        *,
        stream_index: int = 0,
        codec: str = "copy",
        overwrite: bool = True,
    ) -> ExtractionResult:
        video = self._validate(video)
        output = Path(output).expanduser().resolve()

        streams = self.probe.audio_streams(video)

        if stream_index >= len(streams):
            raise MediaValidationError(
                f"Audio stream {stream_index} does not exist."
            )

        command = [
            self.toolchain.ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y" if overwrite else "-n",
            "-i",
            str(video),
            "-map",
            f"0:a:{stream_index}",
            "-vn",
            "-c:a",
            codec,
            str(output),
        ]

        self._run_atomic(
            command,
            output,
        )

        return ExtractionResult(output=output)

    def subtitle(
        self,
        video: str | Path,
        output: str | Path,
        *,
        stream_index: int = 0,
        overwrite: bool = True,
    ) -> ExtractionResult:
        video = self._validate(video)
        output = Path(output).expanduser().resolve()

        streams = self.probe.subtitle_streams(video)

        if stream_index >= len(streams):
            raise MediaValidationError(
                f"Subtitle stream {stream_index} does not exist."
            )

        command = [
            self.toolchain.ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y" if overwrite else "-n",
            "-i",
            str(video),
            "-map",
            f"0:s:{stream_index}",
            "-c:s",
            "copy",
            str(output),
        ]

        self._run_atomic(
            command,
            output,
        )

        return ExtractionResult(output=output)

    def _run_atomic(
        self,
        command: list[str],
        output: Path,
    ) -> None:
        output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary = self._temporary_output(output)

        try:
            self.runner.run(command[:-1] + [str(temporary)])

            if not temporary.exists():
                raise MediaOutputError(
                    f"Output was not created: {temporary}"
                )

            temporary.replace(output)

        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _validate(path: str | Path) -> Path:
        path = Path(path).expanduser().resolve()

        if not path.exists():
            raise MediaValidationError(
                f"File does not exist: {path}"
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