from __future__ import annotations

import os
from pathlib import Path
from typing import Sequence

from .ffmpeg import FFmpeg
from .models import JoinResult, JoinerSettings
from .subtitles import SubtitleManager


class MediaJoiner:

    def __init__(
        self,
        *,
        ffmpeg="ffmpeg",
        ffprobe="ffprobe",
        progress_callback=None,
        cancellation_callback=None,
    ):
        self.ff = FFmpeg(
            ffmpeg=ffmpeg,
            ffprobe=ffprobe,
            progress_callback=progress_callback,
            cancellation_callback=cancellation_callback,
        )

        self.subtitles = SubtitleManager(
            self.ff
        )

    def join(
        self,
        inputs: Sequence[str | Path],
        output: str | Path,
        settings: JoinerSettings | None = None,
    ) -> JoinResult:

        settings = settings or JoinerSettings()

        settings.validate()

        paths = tuple(
            Path(path)
            for path in inputs
        )

        if not paths:
            raise ValueError(
                "At least one input is required."
            )

        for path in paths:
            self.ff.validate_input(path)

        output = Path(output)

        self.ff.validate_output(
            paths[0],
            output,
            settings.overwrite,
        )

        duration = sum(
            self.ff.duration(path)
            for path in paths
        )

        concat_file = self.ff.temporary_path(
            ".txt"
        )

        try:
            concat_file.write_text(
                "\n".join(
                    self._concat_line(path)
                    for path in paths
                ),
                encoding="utf-8",
            )

            temp = self.ff.temporary_path(
                output.suffix or ".mp4"
            )

            command = [
                self.ff.ffmpeg,
                "-hide_banner",
                "-y",
                "-nostdin",

                "-f",
                "concat",
                "-safe",
                "0",

                "-i",
                str(concat_file),

                "-map",
                "0:v:0?",
                "-map",
                "0:a?",
                "-sn",
                "-dn",
            ]

            if settings.video_mode == "fast_copy":
                command += [
                    "-c:v",
                    "copy",
                ]
            else:
                command += [
                    "-c:v",
                    settings.video_codec,
                    "-preset",
                    settings.preset,
                    "-crf",
                    str(settings.crf),
                    "-pix_fmt",
                    settings.pixel_format,
                ]

            if settings.audio_mode == "fast_copy":
                command += [
                    "-c:a",
                    "copy",
                ]
            else:
                command += [
                    "-c:a",
                    settings.audio_codec,
                    "-b:a",
                    settings.audio_bitrate,
                ]

            if (
                settings.faststart
                and output.suffix.lower()
                in {".mp4", ".m4v", ".mov"}
            ):
                command += [
                    "-movflags",
                    "+faststart",
                ]

            command.append(str(temp))

            self.ff.run(
                command,
                message="Joining media",
                duration=duration,
            )

            self.ff.atomic_replace(
                temp,
                output,
            )

            if settings.join_subtitles:
                self._join_sidecar_subtitles(
                    paths,
                    output,
                    settings,
                )

            return JoinResult(
                inputs=paths,
                output=output,
                duration=duration,
            )

        finally:
            self.ff.cleanup()

    @staticmethod
    def _concat_line(path: Path) -> str:
        value = str(
            path.resolve()
        ).replace(
            "'",
            "'\\''",
        )

        return f"file '{value}'"

    def _join_sidecar_subtitles(
        self,
        inputs,
        output,
        settings,
    ):
        groups = {}

        for path in inputs:
            tracks = self.subtitles.discover(
                path
            )

            tracks = self.subtitles.filter(
                tracks,
                settings.subtitle,
            )

            for track in tracks:
                if track.embedded:
                    continue

                key = (
                    track.language
                    or "und"
                )

                groups.setdefault(
                    key,
                    [],
                ).append(
                    track.source
                )

        for language, tracks in groups.items():
            if len(tracks) != len(inputs):
                continue

            subtitle_output = output.with_name(
                f"{output.stem}."
                f"{language}"
                f"{tracks[0].suffix}"
            )

            self.subtitles.join(
                tracks,
                subtitle_output,
                settings.subtitle,
            )
