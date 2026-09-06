from __future__ import annotations

import copy
from pathlib import Path
from typing import Iterable

import pysubs2

from media import (
    MediaValidationError,
    SubtitleJoinError,
)


class SubtitleJoiner:
    """
    Join external subtitle files according to video durations.

    Example:

        Video 1 = 1800 sec
        Video 2 = 2100 sec
        Video 3 = 1900 sec

        Subtitle 1 -> offset 0
        Subtitle 2 -> offset 1800
        Subtitle 3 -> offset 3900
    """

    def join(
        self,
        subtitle_paths: Iterable[str | Path | None],
        video_durations: Iterable[float],
        output_path: str | Path,
        *,
        overwrite: bool = True,
    ) -> Path:
        subtitles = list(subtitle_paths)
        durations = list(video_durations)

        if len(subtitles) != len(durations):
            raise MediaValidationError(
                "Subtitle and video duration lists must have "
                "the same number of items."
            )

        if not durations:
            raise MediaValidationError(
                "At least one subtitle/video pair is required."
            )

        if any(duration < 0 for duration in durations):
            raise MediaValidationError(
                "Video durations cannot be negative."
            )

        output = Path(output_path).expanduser().resolve()

        if output.exists() and not overwrite:
            raise SubtitleJoinError(
                f"Output already exists: {output}"
            )

        output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        combined = pysubs2.SSAFile()

        cumulative_offset = 0

        for subtitle_path, duration in zip(
            subtitles,
            durations,
            strict=True,
        ):
            if subtitle_path is not None:
                subtitle = self._load(
                    Path(subtitle_path)
                )

                for event in subtitle:
                    cloned = copy.deepcopy(event)

                    cloned.start += cumulative_offset
                    cloned.end += cumulative_offset

                    combined.events.append(cloned)

            cumulative_offset += duration

        combined.events.sort(
            key=lambda event: (
                event.start,
                event.end,
            )
        )

        self._renumber(combined)

        combined.save(
            str(output),
            format=self._format_from_extension(output),
        )

        return output

    def join_language(
        self,
        subtitle_paths: Iterable[str | Path | None],
        video_durations: Iterable[float],
        output_path: str | Path,
        *,
        overwrite: bool = True,
    ) -> Path:
        return self.join(
            subtitle_paths,
            video_durations,
            output_path,
            overwrite=overwrite,
        )

    @staticmethod
    def _load(path: Path) -> pysubs2.SSAFile:
        if not path.exists():
            raise SubtitleJoinError(
                f"Subtitle file does not exist: {path}"
            )

        if not path.is_file():
            raise SubtitleJoinError(
                f"Subtitle path is not a file: {path}"
            )

        try:
            return pysubs2.load(
                str(path),
                encoding="utf-8",
            )
        except Exception as exc:
            raise SubtitleJoinError(
                f"Unable to parse subtitle file: {path}"
            ) from exc

    @staticmethod
    def _renumber(
        subtitles: pysubs2.SSAFile,
    ) -> None:
        """
        SRT uses sequential cue numbers.

        pysubs2 manages these when writing, but explicitly keeping events
        ordered gives deterministic output.
        """

        subtitles.events.sort(
            key=lambda event: (
                event.start,
                event.end,
            )
        )

    @staticmethod
    def _format_from_extension(
        path: Path,
    ) -> str:
        extension = path.suffix.lower()

        mapping = {
            ".srt": "srt",
            ".ass": "ass",
            ".ssa": "ssa",
            ".vtt": "vtt",
        }

        try:
            return mapping[extension]
        except KeyError as exc:
            raise SubtitleJoinError(
                f"Unsupported subtitle output format: {extension}"
            ) from exc