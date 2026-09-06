from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Iterable

from .exceptions import (
    IncompatibleMediaError,
    MediaOutputError,
    MediaValidationError,
)
from .models import EncodeOptions, ProgressCallback
from .probe import MediaProbe
from .runner import CommandRunner
from .toolchain import FFmpegToolchain
from .transcoder import MediaTranscoder


class MediaConcatenator:
    """Concatenate multiple video files."""

    def __init__(
        self,
        probe: MediaProbe | None = None,
        toolchain: FFmpegToolchain | None = None,
        runner: CommandRunner | None = None,
        transcoder: MediaTranscoder | None = None,
    ) -> None:
        self.toolchain = toolchain or FFmpegToolchain()
        self.runner = runner or CommandRunner()
        self.probe = probe or MediaProbe(
            toolchain=self.toolchain,
            runner=self.runner,
        )
        self.transcoder = transcoder or MediaTranscoder(
            toolchain=self.toolchain,
            runner=self.runner,
        )

    def concatenate(
        self,
        inputs: Iterable[str | Path],
        output_path: str | Path,
        *,
        reencode: bool = False,
        encode_options: EncodeOptions | None = None,
        overwrite: bool = True,
        progress_callback: ProgressCallback | None = None,
    ) -> Path:
        paths = [
            Path(path).expanduser().resolve()
            for path in inputs
        ]

        if len(paths) < 2:
            raise MediaValidationError(
                "At least two videos are required for concatenation."
            )

        output = Path(output_path).expanduser().resolve()

        if output in paths:
            raise MediaValidationError(
                "Output cannot be one of the input files."
            )

        infos = [
            self.probe.inspect(path)
            for path in paths
        ]

        if not reencode and self.can_stream_copy(infos):
            return self._concat_stream_copy(
                paths,
                output,
                overwrite=overwrite,
            )

        return self._concat_reencode(
            paths,
            output,
            infos=infos,
            encode_options=encode_options,
            overwrite=overwrite,
            progress_callback=progress_callback,
        )

    def can_stream_copy(
        self,
        infos,
    ) -> bool:
        """
        Determine whether the concat demuxer can safely stream-copy
        the supplied files.

        The video/audio codec parameters must match.
        """

        first = infos[0]

        if not first.has_video:
            return False

        first_video = first.video_streams[0]

        first_audio = (
            first.audio_streams[0]
            if first.audio_streams
            else None
        )

        for info in infos[1:]:
            if not info.has_video:
                return False

            video = info.video_streams[0]

            if video.codec_name != first_video.codec_name:
                return False

            if video.width != first_video.width:
                return False

            if video.height != first_video.height:
                return False

            if video.pixel_format if hasattr(video, "pixel_format") else False:
                pass

            audio = (
                info.audio_streams[0]
                if info.audio_streams
                else None
            )

            if bool(audio) != bool(first_audio):
                return False

            if audio and first_audio:
                if audio.codec_name != first_audio.codec_name:
                    return False

                if audio.sample_rate != first_audio.sample_rate:
                    return False

                if audio.channels != first_audio.channels:
                    return False

        return True

    def _concat_stream_copy(
        self,
        inputs: list[Path],
        output: Path,
        *,
        overwrite: bool,
    ) -> Path:
        output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        concat_file = self._create_concat_file(inputs)

        temporary = self._temporary_output(output)

        try:
            command = [
                self.toolchain.ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y" if overwrite else "-n",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_file),
                "-c",
                "copy",
                "-avoid_negative_ts",
                "make_zero",
                str(temporary),
            ]

            self.runner.run(command)

            if not temporary.exists():
                raise MediaOutputError(
                    f"Concat output was not created: {temporary}"
                )

            temporary.replace(output)

            return output

        finally:
            concat_file.unlink(missing_ok=True)
            temporary.unlink(missing_ok=True)

    def _concat_reencode(
        self,
        inputs: list[Path],
        output: Path,
        *,
        infos,
        encode_options: EncodeOptions | None,
        overwrite: bool,
        progress_callback: ProgressCallback | None,
    ) -> Path:
        """
        Re-encode concatenation.

        This implementation normalizes video and audio through an ffmpeg
        filter graph.
        """

        if any(not info.has_video for info in infos):
            raise IncompatibleMediaError(
                "Every input must contain a video stream."
            )

        output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        options = encode_options or EncodeOptions()

        temporary = self._temporary_output(output)

        command = [
            self.toolchain.ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y" if overwrite else "-n",
        ]

        for path in inputs:
            command.extend(
                [
                    "-i",
                    str(path),
                ]
            )

        filters: list[str] = []

        for index, info in enumerate(infos):
            filters.append(
                f"[{index}:v:0]"
                f"setpts=PTS-STARTPTS,"
                f"format={options.pixel_format}"
                f"[v{index}]"
            )

            if info.has_audio:
                filters.append(
                    f"[{index}:a:0]"
                    f"aresample=async=1:first_pts=0,"
                    f"asetpts=PTS-STARTPTS"
                    f"[a{index}]"
                )

        # Re-encoding concat requires consistent streams.
        has_audio = all(info.has_audio for info in infos)

        if not has_audio:
            video_inputs = "".join(
                f"[v{i}]"
                for i in range(len(inputs))
            )

            filters.append(
                f"{video_inputs}"
                f"concat=n={len(inputs)}:v=1:a=0"
                f"[vout]"
            )

        else:
            concat_inputs = "".join(
                f"[v{i}][a{i}]"
                for i in range(len(inputs))
            )

            filters.append(
                f"{concat_inputs}"
                f"concat=n={len(inputs)}:v=1:a=1"
                f"[vout][aout]"
            )

        command.extend(
            [
                "-filter_complex",
                ";".join(filters),
                "-map",
                "[vout]",
            ]
        )

        if has_audio:
            command.extend(
                [
                    "-map",
                    "[aout]",
                ]
            )

        command.extend(
            [
                "-c:v",
                options.video_codec,
                "-preset",
                options.preset,
                "-crf",
                str(options.crf),
                "-pix_fmt",
                options.pixel_format,
            ]
        )

        if has_audio:
            command.extend(
                [
                    "-c:a",
                    options.audio_codec,
                    "-b:a",
                    options.audio_bitrate,
                ]
            )

        if options.faststart:
            command.extend(
                [
                    "-movflags",
                    "+faststart",
                ]
            )

        command.append(str(temporary))

        try:
            self.runner.run(command)

            if not temporary.exists():
                raise MediaOutputError(
                    f"Concatenation output was not created: {temporary}"
                )

            temporary.replace(output)

            return output

        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _create_concat_file(
        inputs: list[Path],
    ) -> Path:
        file = tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".txt",
            prefix="veyra-concat-",
            delete=False,
            encoding="utf-8",
        )

        path = Path(file.name)

        try:
            for input_path in inputs:
                escaped = (
                    str(input_path)
                    .replace("'", "'\\''")
                )

                file.write(
                    f"file '{escaped}'\n"
                )

            file.flush()

        finally:
            file.close()

        return path

    @staticmethod
    def _temporary_output(
        output: Path,
    ) -> Path:
        with tempfile.NamedTemporaryFile(
            prefix=f".{output.stem}.",
            suffix=output.suffix or ".tmp",
            dir=output.parent,
            delete=False,
        ) as file:
            return Path(file.name)