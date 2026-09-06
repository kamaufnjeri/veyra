from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence

from .concatenator import MediaConcatenator
from .exceptions import MediaValidationError
from .models import (
    EncodeOptions,
    JoinResult,
    MediaPart,
    ProgressCallback,
)
from .probe import MediaProbe
from subtitles import SubtitleJoiner


class MediaJoiner:
    """
    Join video segments and their corresponding external subtitles.
    """

    def __init__(
        self,
        probe: MediaProbe | None = None,
        concatenator: MediaConcatenator | None = None,
        subtitle_joiner: SubtitleJoiner | None = None,
    ) -> None:
        self.probe = probe or MediaProbe()

        self.concatenator = (
            concatenator
            or MediaConcatenator(
                probe=self.probe,
            )
        )

        self.subtitle_joiner = (
            subtitle_joiner
            or SubtitleJoiner()
        )

    def join(
        self,
        parts: Sequence[MediaPart],
        output_video: str | Path,
        *,
        subtitle_outputs: Mapping[str, str | Path] | None = None,
        reencode: bool = False,
        encode_options: EncodeOptions | None = None,
        overwrite: bool = True,
        progress_callback: ProgressCallback | None = None,
    ) -> JoinResult:
        if len(parts) < 2:
            raise MediaValidationError(
                "At least two media parts are required."
            )

        output_video = (
            Path(output_video)
            .expanduser()
            .resolve()
        )

        durations = tuple(
            self.probe.duration(part.video)
            for part in parts
        )

        videos = [
            Path(part.video)
            for part in parts
        ]

        output_video_result = self.concatenator.concatenate(
            videos,
            output_video,
            reencode=reencode,
            encode_options=encode_options,
            overwrite=overwrite,
            progress_callback=progress_callback,
        )

        languages = self._languages(parts)

        requested_outputs = (
            dict(subtitle_outputs or {})
        )

        subtitle_results: dict[str, Path] = {}

        for language in languages:
            paths = [
                part.subtitles.get(language)
                for part in parts
            ]

            output = requested_outputs.get(language)

            if output is None:
                output = self._default_subtitle_output(
                    output_video,
                    language,
                )

            output = Path(output).expanduser().resolve()

            subtitle_result = self.subtitle_joiner.join(
                paths,
                durations,
                output,
                overwrite=overwrite,
            )

            subtitle_results[language] = subtitle_result

        return JoinResult(
            video=output_video_result,
            subtitles=subtitle_results,
            durations=durations,
            total_duration=sum(durations),
            reencoded=(
                reencode
                or not self.concatenator.can_stream_copy(
                    [
                        self.probe.inspect(part.video)
                        for part in parts
                    ]
                )
            ),
        )

    @staticmethod
    def _languages(
        parts: Sequence[MediaPart],
    ) -> set[str]:
        languages: set[str] = set()

        for part in parts:
            languages.update(part.subtitles.keys())

        return languages

    @staticmethod
    def _default_subtitle_output(
        video: Path,
        language: str,
    ) -> Path:
        return video.with_name(
            f"{video.stem}.{language}.srt"
        )