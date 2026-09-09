from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from .ffmpeg import FFmpeg
from .ffprobe import FFProbe
from .models import (
    SubtitleSettings,
    SubtitleTrack,
)


SUBTITLE_EXTENSIONS = {
    ".srt",
    ".vtt",
    ".ass",
    ".ssa",
}

CODEC_TO_EXTENSION = {
    "subrip": ".srt",
    "srt": ".srt",
    "webvtt": ".vtt",
    "ass": ".ass",
    "ssa": ".ssa",
}

EXTENSION_TO_CODEC = {
    ".srt": "srt",
    ".vtt": "webvtt",
    ".ass": "ass",
    ".ssa": "ass",
}


@dataclass(frozen=True, slots=True)
class SubtitleCue:
    start: float
    end: float
    text: str


class SubtitleManager:

    # ========================================================
    # INITIALIZATION
    # ========================================================

    def __init__(
        self,
        ffmpeg: FFmpeg,
        ffprobe: FFProbe,
    ) -> None:
        self.ff = ffmpeg
        self.ffprobe = ffprobe

    # ========================================================
    # DISCOVERY
    # ========================================================

    def discover(
        self,
        media_path: Path,
    ) -> list[SubtitleTrack]:

        media_path = Path(media_path)

        result = self._discover_embedded(
            media_path
        )

        result.extend(
            self._discover_external(
                media_path
            )
        )

        return result

    def _discover_embedded(
        self,
        path: Path,
    ) -> list[SubtitleTrack]:

        # FFprobe owns inspection/probing.
        data = self.ffprobe.probe(
            path
        )

        result: list[SubtitleTrack] = []

        for stream in data.get("streams", []):

            if stream.get("codec_type") != "subtitle":
                continue

            codec = str(
                stream.get("codec_name", "")
            ).lower()

            if codec not in CODEC_TO_EXTENSION:
                continue

            tags = stream.get("tags") or {}

            result.append(
                SubtitleTrack(
                    source=path,
                    language=tags.get("language"),
                    title=tags.get("title"),
                    embedded=True,
                    stream_index=stream.get("index"),
                    codec=codec,
                )
            )

        return result

    def _discover_external(
        self,
        media_path: Path,
    ) -> list[SubtitleTrack]:

        result: list[SubtitleTrack] = []

        for path in sorted(
            media_path.parent.glob(
                media_path.stem + ".*"
            )
        ):

            if not path.is_file():
                continue

            if path.suffix.lower() not in SUBTITLE_EXTENSIONS:
                continue

            result.append(
                SubtitleTrack(
                    source=path,
                    language=self.language_from_name(
                        path,
                        media_path,
                    ),
                    embedded=False,
                    codec=EXTENSION_TO_CODEC.get(
                        path.suffix.lower()
                    ),
                )
            )

        return result

    @staticmethod
    def language_from_name(
        subtitle: Path,
        media: Path,
    ) -> Optional[str]:

        prefix = media.stem + "."
        name = subtitle.name

        if not name.startswith(prefix):
            return None

        value = name[
            len(prefix):
            -len(subtitle.suffix)
        ]

        for item in value.split("."):

            item = item.strip().lower()

            if re.fullmatch(
                r"[a-z]{2,3}(?:-[a-z]{2,4})?",
                item,
            ):
                return item

        return None

    # ========================================================
    # FILTER
    # ========================================================

    @staticmethod
    def filter(
        tracks: Sequence[SubtitleTrack],
        settings: SubtitleSettings,
    ) -> list[SubtitleTrack]:

        if not settings.language:
            return list(tracks)

        wanted = settings.language.lower()

        return [
            track
            for track in tracks
            if (
                track.language
                and track.language.lower() == wanted
            )
        ]

    # ========================================================
    # CUT
    # ========================================================

    def cut(
        self,
        track: SubtitleTrack,
        start: float,
        end: float,
        output: Path,
        settings: SubtitleSettings,
    ) -> Path:

        settings.validate()

        output = Path(output)

        output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        source = Path(
            track.source
        )

        # ----------------------------------------------------
        # OUTPUT FORMAT
        # ----------------------------------------------------

        extension = self._output_extension(
            track,
            settings,
        )

        if output.suffix.lower() != extension:
            output = output.with_suffix(
                extension
            )

        codec = EXTENSION_TO_CODEC.get(
            extension
        )

        if codec is None:
            raise ValueError(
                f"Unsupported subtitle extension: {extension}"
            )

        # ----------------------------------------------------
        # INPUT / MAP
        # ----------------------------------------------------

        input_spec = [
            "-i",
            str(source),
        ]

        if track.embedded:

            if track.stream_index is None:
                raise ValueError(
                    "Embedded subtitle has no stream index."
                )

            map_spec = [
                "-map",
                f"0:{track.stream_index}",
            ]

        else:

            map_spec = [
                "-map",
                "0:0",
            ]

        # ----------------------------------------------------
        # TEMP OUTPUT
        # ----------------------------------------------------

        temp = self.ff.temporary_path(
            extension
        )

        command = [
            self.ff.ffmpeg,
            "-hide_banner",
            "-y",
            "-nostdin",

            "-ss",
            self._seconds(start),

            *input_spec,

            "-t",
            self._seconds(end - start),

            *map_spec,

            "-c:s",
            codec,
        ]

        if codec == "webvtt":
            command += [
                "-f",
                "webvtt",
            ]

        command.append(
            str(temp)
        )

        try:

            self.ff.run(
                command,
                message="Cutting subtitles",
                duration=end - start,
            )

            self.ff.atomic_replace(
                temp,
                output,
            )

            return output

        finally:

            self.ff.cleanup()

    # ========================================================
    # JOIN
    # ========================================================

    def join(
        self,
        tracks: Sequence[Path],
        output: Path,
        settings: SubtitleSettings,
    ) -> Path:

        settings.validate()

        if not tracks:
            raise ValueError(
                "At least one subtitle is required."
            )

        tracks = tuple(
            Path(path)
            for path in tracks
        )

        extension = self._requested_extension(
            tracks[0],
            settings,
        )

        output = Path(output).with_suffix(
            extension
        )

        cues: list[SubtitleCue] = []

        offset = 0.0

        for path in tracks:

            current = self.read(
                path
            )

            if not current:
                continue

            for cue in current:

                cues.append(
                    SubtitleCue(
                        start=cue.start + offset,
                        end=cue.end + offset,
                        text=cue.text,
                    )
                )

            # Preserve the original behavior:
            # the next subtitle starts after the
            # duration represented by this subtitle.
            offset = max(
                offset,
                max(
                    cue.end
                    for cue in current
                ) + offset,
            )

        self.write(
            cues,
            output,
            extension,
        )

        return output

    # ========================================================
    # CONVERT
    # ========================================================

    def convert(
        self,
        source: Path,
        output: Path,
        settings: SubtitleSettings,
    ) -> Path:

        settings.validate()

        source = Path(source)
        output = Path(output)

        extension = self._requested_extension(
            source,
            settings,
        )

        output = output.with_suffix(
            extension
        )

        if source.resolve() == output.resolve():
            return output

        codec = EXTENSION_TO_CODEC.get(
            extension
        )

        if codec is None:
            raise ValueError(
                f"Unsupported subtitle extension: {extension}"
            )

        # ----------------------------------------------------
        # TEMP OUTPUT
        # ----------------------------------------------------

        temp = self.ff.temporary_path(
            extension
        )

        command = [
            self.ff.ffmpeg,
            "-hide_banner",
            "-y",
            "-nostdin",

            "-i",
            str(source),

            "-c:s",
            codec,
        ]

        if codec == "webvtt":
            command += [
                "-f",
                "webvtt",
            ]

        command.append(
            str(temp)
        )

        try:

            self.ff.run(
                command,
                message="Converting subtitles",
            )

            self.ff.atomic_replace(
                temp,
                output,
            )

            return output

        finally:

            self.ff.cleanup()

    # ========================================================
    # READ
    # ========================================================

    @staticmethod
    def read(
        path: Path,
    ) -> list[SubtitleCue]:

        path = Path(path)

        text = path.read_text(
            encoding="utf-8-sig"
        )

        if path.suffix.lower() == ".vtt":

            text = re.sub(
                r"^WEBVTT.*?\n\n",
                "",
                text,
                count=1,
                flags=re.DOTALL,
            )

        blocks = re.split(
            r"\n\s*\n",
            text.strip(),
        )

        cues: list[SubtitleCue] = []

        for block in blocks:

            lines = block.splitlines()

            if not lines:
                continue

            timing_index = next(
                (
                    i
                    for i, line in enumerate(lines)
                    if "-->" in line
                ),
                None,
            )

            if timing_index is None:
                continue

            timing = lines[
                timing_index
            ]

            left, right = timing.split(
                "-->",
                1,
            )

            start = SubtitleManager.parse_time(
                left.strip()
            )

            end = SubtitleManager.parse_time(
                right.strip().split()[0]
            )

            if end <= start:
                continue

            text_lines = lines[
                timing_index + 1:
            ]

            if not text_lines:
                continue

            cues.append(
                SubtitleCue(
                    start=start,
                    end=end,
                    text="\n".join(
                        text_lines
                    ),
                )
            )

        return cues

    # ========================================================
    # WRITE
    # ========================================================

    @staticmethod
    def write(
        cues: Sequence[SubtitleCue],
        output: Path,
        extension: str,
    ) -> None:

        output = Path(output)

        output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        extension = extension.lower()

        if extension == ".vtt":

            chunks = [
                "WEBVTT",
                "",
            ]

            for cue in cues:

                chunks.extend([
                    (
                        f"{SubtitleManager.format_time(cue.start, True)}"
                        " --> "
                        f"{SubtitleManager.format_time(cue.end, True)}"
                    ),
                    cue.text,
                    "",
                ])

            output.write_text(
                "\n".join(chunks),
                encoding="utf-8",
            )

            return

        chunks: list[str] = []

        for index, cue in enumerate(
            cues,
            1,
        ):

            chunks.extend([
                str(index),
                (
                    f"{SubtitleManager.format_time(cue.start)}"
                    " --> "
                    f"{SubtitleManager.format_time(cue.end)}"
                ),
                cue.text,
                "",
            ])

        output.write_text(
            "\n".join(chunks),
            encoding="utf-8",
        )

    # ========================================================
    # TIME
    # ========================================================

    @staticmethod
    def parse_time(
        value: str,
    ) -> float:

        value = value.strip()

        value = value.replace(
            ",",
            ".",
        )

        parts = value.split(":")

        if len(parts) == 3:

            hours = float(parts[0])
            minutes = float(parts[1])
            seconds = float(parts[2])

        elif len(parts) == 2:

            hours = 0.0
            minutes = float(parts[0])
            seconds = float(parts[1])

        else:

            return float(value)

        return (
            hours * 3600
            + minutes * 60
            + seconds
        )

    @staticmethod
    def format_time(
        seconds: float,
        dot: bool = False,
    ) -> str:

        seconds = max(
            0.0,
            seconds,
        )

        hours = int(
            seconds // 3600
        )

        seconds %= 3600

        minutes = int(
            seconds // 60
        )

        seconds %= 60

        whole = int(
            seconds
        )

        milliseconds = int(
            round(
                (seconds - whole) * 1000
            )
        )

        if milliseconds >= 1000:

            whole += 1
            milliseconds = 0

        separator = (
            "."
            if dot
            else ","
        )

        return (
            f"{hours:02d}:"
            f"{minutes:02d}:"
            f"{whole:02d}"
            f"{separator}"
            f"{milliseconds:03d}"
        )

    # ========================================================
    # HELPERS
    # ========================================================

    @staticmethod
    def _seconds(
        value: float,
    ) -> str:

        return f"{max(0.0, value):.6f}"

    @staticmethod
    def _output_extension(
        track: SubtitleTrack,
        settings: SubtitleSettings,
    ) -> str:

        if settings.output_format != "same":

            extension = (
                "."
                + settings.output_format.lower()
            )

            if extension not in SUBTITLE_EXTENSIONS:
                raise ValueError(
                    f"Unsupported subtitle format: "
                    f"{settings.output_format}"
                )

            return extension

        if track.codec in CODEC_TO_EXTENSION:

            return CODEC_TO_EXTENSION[
                track.codec
            ]

        if track.source.suffix:

            extension = (
                track.source.suffix.lower()
            )

            if extension in SUBTITLE_EXTENSIONS:
                return extension

        return ".srt"

    @staticmethod
    def _requested_extension(
        source: Path,
        settings: SubtitleSettings,
    ) -> str:

        if settings.output_format != "same":

            extension = (
                "."
                + settings.output_format.lower()
            )

            if extension not in SUBTITLE_EXTENSIONS:
                raise ValueError(
                    f"Unsupported subtitle format: "
                    f"{settings.output_format}"
                )

            return extension

        extension = source.suffix.lower()

        if extension in SUBTITLE_EXTENSIONS:
            return extension

        return ".srt"
