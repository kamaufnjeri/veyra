from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Iterable

from .exceptions import (
    MediaOutputError,
    MediaValidationError,
    UnsupportedMediaError,
)
from .models import MuxResult, MuxSubtitle
from .probe import MediaProbe
from .runner import CommandRunner
from .toolchain import FFmpegToolchain


class MediaMuxer:
    """Mux video, audio and external subtitle streams."""

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

    def mux(
        self,
        video: str | Path,
        *,
        audio: str | Path | None = None,
        subtitles: Iterable[MuxSubtitle] | None = None,
        output: str | Path,
        overwrite: bool = True,
        video_codec: str = "copy",
        audio_codec: str = "copy",
    ) -> MuxResult:
        video_path = self._validate_file(video)

        audio_path = (
            self._validate_file(audio)
            if audio is not None
            else None
        )

        subtitle_list = list(subtitles or [])

        for subtitle in subtitle_list:
            self._validate_file(subtitle.path)

        output_path = Path(output).expanduser().resolve()

        if output_path == video_path:
            raise MediaValidationError(
                "Mux output cannot overwrite the input video."
            )

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        container = output_path.suffix.lower()

        if container not in {".mkv", ".mp4", ".mov"}:
            raise UnsupportedMediaError(
                f"Unsupported mux container: {container}"
            )

        command = [
            self.toolchain.ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y" if overwrite else "-n",
            "-i",
            str(video_path),
        ]

        input_index = 1

        if audio_path:
            command.extend(
                [
                    "-i",
                    str(audio_path),
                ]
            )

        for subtitle in subtitle_list:
            command.extend(
                [
                    "-i",
                    str(subtitle.path),
                ]
            )

        command.extend(
            [
                "-map",
                "0:v:0",
            ]
        )

        if audio_path:
            command.extend(
                [
                    "-map",
                    "1:a:0",
                ]
            )
        else:
            command.extend(
                [
                    "-map",
                    "0:a:0?",
                ]
            )

        for index in range(len(subtitle_list)):
            subtitle_input_index = (
                input_index
                + (1 if audio_path else 0)
                + index
            )

            command.extend(
                [
                    "-map",
                    f"{subtitle_input_index}:s:0",
                ]
            )

        command.extend(
            [
                "-c:v",
                video_codec,
            ]
        )

        if audio_path:
            command.extend(
                [
                    "-c:a",
                    audio_codec,
                ]
            )
        else:
            command.extend(
                [
                    "-c:a",
                    "copy",
                ]
            )

        subtitle_codec = self._subtitle_codec(
            container
        )

        if subtitle_list:
            command.extend(
                [
                    "-c:s",
                    subtitle_codec,
                ]
            )

        for index, subtitle in enumerate(subtitle_list):
            stream_index = index

            if subtitle.language:
                command.extend(
                    [
                        f"-metadata:s:s:{stream_index}",
                        f"language={subtitle.language}",
                    ]
                )

            if subtitle.title:
                command.extend(
                    [
                        f"-metadata:s:s:{stream_index}",
                        f"title={subtitle.title}",
                    ]
                )

            disposition: list[str] = []

            if subtitle.default:
                disposition.append("default")

            if subtitle.forced:
                disposition.append("forced")

            if disposition:
                command.extend(
                    [
                        f"-disposition:s:{stream_index}",
                        "+".join(disposition),
                    ]
                )

        temporary = self._temporary_output(output_path)

        command.append(str(temporary))

        try:
            self.runner.run(command)

            if not temporary.exists():
                raise MediaOutputError(
                    f"Mux output was not created: {temporary}"
                )

            temporary.replace(output_path)

        finally:
            temporary.unlink(missing_ok=True)

        return MuxResult(
            output=output_path
        )

    @staticmethod
    def _subtitle_codec(
        container: str,
    ) -> str:
        if container in {".mp4", ".mov"}:
            return "mov_text"

        return "copy"

    @staticmethod
    def _validate_file(
        path: str | Path,
    ) -> Path:
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