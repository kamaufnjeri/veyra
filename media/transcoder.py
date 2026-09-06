from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Sequence

from .exceptions import MediaOutputError, MediaValidationError
from .models import EncodeOptions, Progress, ProgressCallback
from .runner import CommandRunner
from .toolchain import FFmpegToolchain


class MediaTranscoder:
    """Low-level ffmpeg video transcoding engine."""

    def __init__(
        self,
        toolchain: FFmpegToolchain | None = None,
        runner: CommandRunner | None = None,
    ) -> None:
        self.toolchain = toolchain or FFmpegToolchain()
        self.runner = runner or CommandRunner()

    def transcode(
        self,
        input_path: str | Path,
        output_path: str | Path,
        *,
        options: EncodeOptions | None = None,
        duration: float | None = None,
        overwrite: bool = True,
        progress_callback: ProgressCallback | None = None,
    ) -> Path:
        input_path = self._validate_input(input_path)
        output_path = Path(output_path).expanduser().resolve()

        options = options or EncodeOptions()

        self._validate_output(
            input_path,
            output_path,
        )

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary = self._temporary_output(output_path)

        try:
            command = self._build_command(
                input_path,
                temporary,
                options=options,
                overwrite=overwrite,
            )

            self.runner.run(
                command,
                stdout_callback=self._stdout_progress(
                    duration,
                    progress_callback,
                ),
            )

            if not temporary.exists():
                raise MediaOutputError(
                    f"ffmpeg completed but output was not created: "
                    f"{temporary}"
                )

            temporary.replace(output_path)

            return output_path

        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    def _build_command(
        self,
        input_path: Path,
        output_path: Path,
        *,
        options: EncodeOptions,
        overwrite: bool,
    ) -> list[str]:
        command = [
            self.toolchain.ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
        ]

        command.append("-y" if overwrite else "-n")

        command.extend(
            [
                "-i",
                str(input_path),
            ]
        )

        command.extend(
            [
                "-map",
                "0:v:0",
            ]
        )

        command.extend(
            [
                "-map",
                "0:a:0?",
            ]
        )

        command.extend(
            [
                "-c:v",
                options.video_codec,
            ]
        )

        command.extend(
            [
                "-preset",
                options.preset,
            ]
        )

        command.extend(
            [
                "-crf",
                str(options.crf),
            ]
        )

        if options.video_bitrate:
            command.extend(
                [
                    "-b:v",
                    options.video_bitrate,
                ]
            )

        if options.width or options.height:
            width = options.width or -2
            height = options.height or -2

            command.extend(
                [
                    "-vf",
                    f"scale={width}:{height}",
                ]
            )

        if options.fps:
            command.extend(
                [
                    "-r",
                    str(options.fps),
                ]
            )

        command.extend(
            [
                "-pix_fmt",
                options.pixel_format,
            ]
        )

        if options.profile:
            command.extend(
                [
                    "-profile:v",
                    options.profile,
                ]
            )

        if options.level:
            command.extend(
                [
                    "-level:v",
                    options.level,
                ]
            )

        if options.tune:
            command.extend(
                [
                    "-tune",
                    options.tune,
                ]
            )

        command.extend(options.extra_video_args)

        command.extend(
            [
                "-c:a",
                options.audio_codec,
                "-b:a",
                options.audio_bitrate,
            ]
        )

        command.extend(options.extra_audio_args)

        if options.faststart:
            command.extend(
                [
                    "-movflags",
                    "+faststart",
                ]
            )

        if options.threads:
            command.extend(
                [
                    "-threads",
                    str(options.threads),
                ]
            )

        command.extend(
            [
                "-progress",
                "pipe:1",
                str(output_path),
            ]
        )

        return command

    def _stdout_progress(
        self,
        duration: float | None,
        callback: ProgressCallback | None,
    ):
        if callback is None:
            return None

        state: dict[str, str] = {}

        def handle(line: str) -> None:
            if "=" not in line:
                return

            key, value = line.split("=", 1)

            state[key] = value

            if key != "progress":
                return

            if duration and duration > 0:
                out_time_ms = self._float(
                    state.get("out_time_ms")
                )

                elapsed = out_time_ms / 1_000_000

                fraction = max(
                    0.0,
                    min(
                        1.0,
                        elapsed / duration,
                    ),
                )

                callback(
                    Progress(
                        fraction=fraction,
                        percent=fraction * 100,
                        elapsed=elapsed,
                        remaining=max(
                            0.0,
                            duration - elapsed,
                        ),
                        speed=self._parse_speed(
                            state.get("speed")
                        ),
                        message="Transcoding",
                    )
                )

        return handle

    @staticmethod
    def _parse_speed(
        value: str | None,
    ) -> float | None:
        if not value:
            return None

        value = value.strip().lower().replace("x", "")

        try:
            return float(value)
        except ValueError:
            return None

    @staticmethod
    def _float(value: str | None) -> float:
        try:
            return float(value or 0)
        except ValueError:
            return 0.0

    @staticmethod
    def _validate_input(path: str | Path) -> Path:
        path = Path(path).expanduser().resolve()

        if not path.exists():
            raise MediaValidationError(
                f"Input does not exist: {path}"
            )

        if not path.is_file():
            raise MediaValidationError(
                f"Input is not a file: {path}"
            )

        return path

    @staticmethod
    def _validate_output(
        input_path: Path,
        output_path: Path,
    ) -> None:
        if input_path == output_path:
            raise MediaValidationError(
                "Input and output cannot be the same file."
            )

    @staticmethod
    def _temporary_output(
        output_path: Path,
    ) -> Path:
        suffix = output_path.suffix or ".tmp"

        with tempfile.NamedTemporaryFile(
            prefix=f".{output_path.stem}.",
            suffix=suffix,
            dir=output_path.parent,
            delete=False,
        ) as file:
            return Path(file.name)