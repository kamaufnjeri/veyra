from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from .ffmpeg import FFmpeg
from .models import (
    MediaError,
    MediaInput,
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
    # DISCOVERY
    # ========================================================

    def __init__(self, ff: FFmpeg):
        self.ff = ff

    def discover(
        self,
        media_path: Path,
    ) -> list[SubtitleTrack]:

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

        data = self.ff.probe(path)

        result = []

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

        result = []

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

        output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        source = track.source

        if track.embedded:
            input_spec = [
                "-i",
                str(source),
            ]

            map_spec = [
                "-map",
                f"0:{track.stream_index}",
            ]
        else:
            input_spec = [
                "-i",
                str(source),
            ]

            map_spec = [
                "-map",
                "0:0",
            ]

        extension = (
            self._output_extension(
                track,
                settings,
            )
        )

        if output.suffix.lower() != extension:
            output = output.with_suffix(extension)

        temp = self.ff.temporary_path(
            extension
        )

        codec = EXTENSION_TO_CODEC[extension]

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
            command += ["-f", "webvtt"]

        command.append(str(temp))

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

        extension = self._requested_extension(
            tracks[0],
            settings,
        )

        output = output.with_suffix(
            extension
        )

        cues: list[SubtitleCue] = []
        offset = 0.0

        for path in tracks:
            current = self.read(
                path
            )

            if current:
                for cue in current:
                    cues.append(
                        SubtitleCue(
                            start=cue.start + offset,
                            end=cue.end + offset,
                            text=cue.text,
                        )
                    )

                offset = max(
                    offset,
                    max(c.end for c in current)
                    + offset,
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

        extension = self._requested_extension(
            source,
            settings,
        )

        output = output.with_suffix(
            extension
        )

        if source.resolve() == output.resolve():
            return output

        temp = self.ff.temporary_path(
            extension
        )

        codec = EXTENSION_TO_CODEC[extension]

        command = [
            self.ff.ffmpeg,
            "-hide_banner",
            "-y",
            "-nostdin",

            "-i",
            str(source),

            "-c:s",
            codec,

            str(temp),
        ]

        self.ff.run(
            command,
            message="Converting subtitles",
        )

        self.ff.atomic_replace(
            temp,
            output,
        )

        return output

    # ========================================================
    # SRT / VTT
    # ========================================================

    @staticmethod
    def read(
        path: Path,
    ) -> list[SubtitleCue]:

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

        cues = []

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

            timing = lines[timing_index]

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

            text_lines = lines[
                timing_index + 1:
            ]

            if text_lines:
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

    @staticmethod
    def write(
        cues: Sequence[SubtitleCue],
        output: Path,
        extension: str,
    ) -> None:

        output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        if extension == ".vtt":
            chunks = ["WEBVTT", ""]

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

        chunks = []

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
    def parse_time(value: str) -> float:

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
            hours = 0
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

        seconds = max(0.0, seconds)

        hours = int(seconds // 3600)

        seconds %= 3600

        minutes = int(seconds // 60)

        seconds %= 60

        whole = int(seconds)

        milliseconds = int(
            round(
                (seconds - whole) * 1000
            )
        )

        if milliseconds >= 1000:
            whole += 1
            milliseconds = 0

        separator = "." if dot else ","

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
    def _seconds(value: float) -> str:
        return f"{max(0.0, value):.6f}"

    @staticmethod
    def _output_extension(
        track: SubtitleTrack,
        settings: SubtitleSettings,
    ) -> str:

        if settings.output_format != "same":
            return "." + settings.output_format.lower()

        if track.codec in CODEC_TO_EXTENSION:
            return CODEC_TO_EXTENSION[
                track.codec
            ]

        if track.source.suffix:
            return track.source.suffix.lower()

        return ".srt"

    @staticmethod
    def _requested_extension(
        source: Path,
        settings: SubtitleSettings,
    ) -> str:

        if settings.output_format != "same":
            return "." + settings.output_format.lower()

        return source.suffix.lower() or ".srt"
