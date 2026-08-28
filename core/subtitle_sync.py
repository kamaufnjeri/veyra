from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple, TypedDict

import re


# ============================================================
# SUBTITLE PART CONFIGURATION
# ============================================================


class SubtitlePart(TypedDict, total=False):
    """
    Configuration for one subtitle file used by JOIN.

    Part 1:
        {
            "name": "part1.srt",
            "offset": 0.0,
        }

    Part 2+:
        {
            "name": "part2.srt",
            "offset": 2.0,
            "gap": 5.0,
        }

    JOIN supports:
        - name
        - offset
        - gap (part 2+ only)
    """

    name: str | Path
    offset: float
    gap: float


# ============================================================
# MERGE FILE TYPE
# ============================================================

SubtitleMergeFile = str | Path


# ============================================================
# SUBTITLE ENTRY
# ============================================================


@dataclass
class SubtitleEntry:
    index: int
    start: float
    end: float
    text: str

    def copy(self) -> "SubtitleEntry":
        return SubtitleEntry(
            index=self.index,
            start=self.start,
            end=self.end,
            text=self.text,
        )

    @property
    def duration(self) -> float:
        return max(
            0.0,
            self.end - self.start,
        )


# ============================================================
# SUBTITLE FILE
# ============================================================


class SubtitleFile:
    """
    Subtitle container.

    Internally all timestamps are represented as seconds.

    Supported input:
        - SRT
        - VTT

    Output:
        - SRT
    """

    TIMESTAMP_RE = re.compile(
        r"(?P<hours>\d{1,3}):"
        r"(?P<minutes>\d{2}):"
        r"(?P<seconds>\d{2})"
        r"[,.]"
        r"(?P<milliseconds>\d{3})"
    )

    def __init__(
        self,
        entries: Optional[Iterable[SubtitleEntry]] = None,
        format_name: str = "srt",
    ):
        self.entries: List[SubtitleEntry] = list(
            entries or []
        )

        self.format_name = str(
            format_name or "srt"
        ).lower()

        self.sort()
        self.renumber()

    # ========================================================
    # LOADING
    # ========================================================

    @classmethod
    def load(
        cls,
        path: str | Path,
        encoding: str = "utf-8-sig",
    ) -> "SubtitleFile":

        path = Path(path).expanduser()

        if not path.is_file():
            raise FileNotFoundError(
                f"Subtitle file not found: {path}"
            )

        text = path.read_text(
            encoding=encoding,
            errors="replace",
        )

        suffix = path.suffix.lower()

        if suffix == ".vtt":
            return cls.from_vtt(text)

        if suffix == ".srt":
            return cls.from_srt(text)

        raise ValueError(
            f"Unsupported subtitle format: {suffix}"
        )

    # ========================================================
    # SRT PARSER
    # ========================================================

    @classmethod
    def from_srt(
        cls,
        text: str,
    ) -> "SubtitleFile":

        text = (
            text.replace("\r\n", "\n")
            .replace("\r", "\n")
        )

        # Split subtitle blocks on blank lines.
        blocks = re.split(
            r"\n\s*\n",
            text.strip(),
        )

        entries: List[SubtitleEntry] = []

        for block in blocks:

            lines = [
                line.rstrip()
                for line in block.splitlines()
            ]

            if not lines:
                continue

            index = 0

            # SRT normally starts with a numeric index.
            if lines[0].strip().isdigit():
                index = int(
                    lines[0].strip()
                )
                lines = lines[1:]

            if not lines:
                continue

            timing_index = None

            for i, line in enumerate(lines):
                if "-->" in line:
                    timing_index = i
                    break

            if timing_index is None:
                continue

            timing_line = lines[timing_index]

            start_text, end_text = timing_line.split(
                "-->",
                1,
            )

            start = cls.parse_timestamp(
                start_text.strip()
            )

            # Remove optional SRT/VTT timing settings.
            end = cls.parse_timestamp(
                end_text.strip().split()[0]
            )

            subtitle_lines = lines[
                timing_index + 1:
            ]

            subtitle_text = "\n".join(
                subtitle_lines
            ).strip()

            if not subtitle_text:
                continue

            if end < start:
                end = start

            entries.append(
                SubtitleEntry(
                    index=index,
                    start=start,
                    end=end,
                    text=subtitle_text,
                )
            )

        return cls(
            entries,
            "srt",
        )

    # ========================================================
    # VTT PARSER
    # ========================================================

    @classmethod
    def from_vtt(
        cls,
        text: str,
    ) -> "SubtitleFile":

        text = (
            text.replace("\r\n", "\n")
            .replace("\r", "\n")
        )

        lines = text.splitlines()

        # Remove WEBVTT header.
        if (
            lines
            and lines[0]
            .strip()
            .upper()
            .startswith("WEBVTT")
        ):
            lines = lines[1:]

        blocks = re.split(
            r"\n\s*\n",
            "\n".join(lines).strip(),
        )

        entries: List[SubtitleEntry] = []

        counter = 1

        for block in blocks:

            lines = block.splitlines()

            if not lines:
                continue

            timing_index = None

            for i, line in enumerate(lines):
                if "-->" in line:
                    timing_index = i
                    break

            if timing_index is None:
                continue

            timing_line = lines[timing_index]

            start_text, end_text = timing_line.split(
                "-->",
                1,
            )

            start = cls.parse_timestamp(
                start_text.strip()
            )

            end = cls.parse_timestamp(
                end_text.strip().split()[0]
            )

            subtitle_text = "\n".join(
                lines[
                    timing_index + 1:
                ]
            ).strip()

            if not subtitle_text:
                continue

            entries.append(
                SubtitleEntry(
                    index=counter,
                    start=start,
                    end=max(start, end),
                    text=subtitle_text,
                )
            )

            counter += 1

        return cls(
            entries,
            "vtt",
        )

    # ========================================================
    # TIMESTAMP PARSING
    # ========================================================

    @classmethod
    def parse_timestamp(
        cls,
        value: str,
    ) -> float:

        value = (
            value.strip()
            .replace(",", ".")
        )

        # HH:MM:SS.mmm
        match = re.match(
            r"^(\d+):(\d{2}):(\d{2})\.(\d{3})$",
            value,
        )

        if match:

            hours = int(
                match.group(1)
            )

            minutes = int(
                match.group(2)
            )

            seconds = int(
                match.group(3)
            )

            milliseconds = int(
                match.group(4)
            )

            return (
                hours * 3600
                + minutes * 60
                + seconds
                + milliseconds / 1000.0
            )

        # MM:SS.mmm
        match = re.match(
            r"^(\d{2}):(\d{2})\.(\d{3})$",
            value,
        )

        if match:

            minutes = int(
                match.group(1)
            )

            seconds = int(
                match.group(2)
            )

            milliseconds = int(
                match.group(3)
            )

            return (
                minutes * 60
                + seconds
                + milliseconds / 1000.0
            )

        raise ValueError(
            f"Invalid subtitle timestamp: {value}"
        )

    # ========================================================
    # TIMESTAMP FORMAT
    # ========================================================

    @staticmethod
    def format_timestamp(
        seconds: float,
        separator: str = ",",
    ) -> str:

        seconds = max(
            0.0,
            float(seconds),
        )

        total_ms = int(
            round(seconds * 1000)
        )

        hours, remainder = divmod(
            total_ms,
            3_600_000,
        )

        minutes, remainder = divmod(
            remainder,
            60_000,
        )

        seconds_part, milliseconds = divmod(
            remainder,
            1000,
        )

        return (
            f"{hours:02d}:"
            f"{minutes:02d}:"
            f"{seconds_part:02d}"
            f"{separator}"
            f"{milliseconds:03d}"
        )

    # ========================================================
    # SORT
    # ========================================================

    def sort(self) -> None:

        self.entries.sort(
            key=lambda e: (
                e.start,
                e.end,
                e.index,
            )
        )

    # ========================================================
    # RENUMBER
    # ========================================================

    def renumber(self) -> None:

        for number, entry in enumerate(
            self.entries,
            start=1,
        ):
            entry.index = number

    # ========================================================
    # COPY
    # ========================================================

    def copy(self) -> "SubtitleFile":

        return SubtitleFile(
            [
                entry.copy()
                for entry in self.entries
            ],
            self.format_name,
        )

    # ========================================================
    # SAVE
    # ========================================================

    def save(
        self,
        path: str | Path,
        encoding: str = "utf-8",
    ) -> None:

        path = Path(path).expanduser()

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        path.write_text(
            self.to_srt(),
            encoding=encoding,
        )

    # ========================================================
    # SRT OUTPUT
    # ========================================================

    def to_srt(self) -> str:

        self.sort()
        self.renumber()

        blocks = []

        for entry in self.entries:

            blocks.append(
                "\n".join(
                    [
                        str(entry.index),
                        (
                            f"{self.format_timestamp(entry.start)} "
                            f"--> "
                            f"{self.format_timestamp(entry.end)}"
                        ),
                        entry.text,
                    ]
                )
            )

        if not blocks:
            return ""

        return (
            "\n\n".join(blocks)
            + "\n"
        )

    # ========================================================
    # RANGE
    # ========================================================

    @property
    def start_time(self) -> float:

        if not self.entries:
            return 0.0

        return min(
            e.start
            for e in self.entries
        )

    @property
    def end_time(self) -> float:

        if not self.entries:
            return 0.0

        return max(
            e.end
            for e in self.entries
        )

    @property
    def duration(self) -> float:

        return max(
            0.0,
            self.end_time - self.start_time,
        )

    # ========================================================
    # SHIFT
    # ========================================================

    def shift(
        self,
        offset: float,
    ) -> "SubtitleFile":

        result = self.copy()

        offset = float(offset)

        for entry in result.entries:

            entry.start = max(
                0.0,
                entry.start + offset,
            )

            entry.end = max(
                entry.start,
                entry.end + offset,
            )

        result.sort()
        result.renumber()

        return result

    # ========================================================
    # SCALE TIMING
    # ========================================================

    def scale_timing(
        self,
        scale: float,
        anchor: float = 0.0,
    ) -> "SubtitleFile":

        if scale <= 0:
            raise ValueError(
                "Timing scale must be greater than zero."
            )

        result = self.copy()

        for entry in result.entries:

            entry.start = (
                anchor
                + (
                    entry.start - anchor
                ) * scale
            )

            entry.end = (
                anchor
                + (
                    entry.end - anchor
                ) * scale
            )

            entry.start = max(
                0.0,
                entry.start,
            )

            entry.end = max(
                entry.start,
                entry.end,
            )

        result.sort()
        result.renumber()

        return result

    # ========================================================
    # REMOVE DUPLICATES
    # ========================================================

    def remove_duplicates(
        self,
        time_tolerance: float = 0.05,
    ) -> "SubtitleFile":

        result = self.copy()

        unique: List[SubtitleEntry] = []

        for entry in result.entries:

            duplicate = False

            for existing in unique:

                same_text = (
                    entry.text.strip()
                    == existing.text.strip()
                )

                close_start = (
                    abs(
                        entry.start
                        - existing.start
                    )
                    <= time_tolerance
                )

                close_end = (
                    abs(
                        entry.end
                        - existing.end
                    )
                    <= time_tolerance
                )

                if (
                    same_text
                    and close_start
                    and close_end
                ):
                    duplicate = True
                    break

            if not duplicate:
                unique.append(entry)

        result.entries = unique

        result.sort()
        result.renumber()

        return result

    # ========================================================
    # CLAMP TO VIDEO
    # ========================================================

    def clamp_to_duration(
        self,
        video_duration: float,
    ) -> "SubtitleFile":

        video_duration = float(
            video_duration
        )

        if video_duration <= 0:
            raise ValueError(
                "Video duration must be greater than zero."
            )

        result = self.copy()

        valid: List[SubtitleEntry] = []

        for entry in result.entries:

            if entry.start >= video_duration:
                continue

            entry.start = max(
                0.0,
                entry.start,
            )

            entry.end = min(
                video_duration,
                entry.end,
            )

            if entry.end <= entry.start:
                continue

            valid.append(entry)

        result.entries = valid

        result.sort()
        result.renumber()

        return result

    # ========================================================
    # VALIDATE
    # ========================================================

    def validate(self) -> List[str]:

        errors: List[str] = []

        previous_start = -1.0

        for number, entry in enumerate(
            self.entries,
            start=1,
        ):

            if entry.start < 0:
                errors.append(
                    f"Entry {number}: negative start time."
                )

            if entry.end < entry.start:
                errors.append(
                    f"Entry {number}: end before start."
                )

            if entry.start < previous_start:
                errors.append(
                    f"Entry {number}: subtitle order problem."
                )

            if not entry.text.strip():
                errors.append(
                    f"Entry {number}: empty text."
                )

            previous_start = entry.start

        return errors


# ============================================================
# SUBTITLE JOINER
# ============================================================


class SubtitleJoiner:

    # ========================================================
    # VALIDATE JOIN PART
    # ========================================================

    @staticmethod
    def _validate_part(
        part: SubtitlePart,
        is_first: bool = False,
    ) -> Tuple[str | Path, float, float]:

        if not isinstance(part, dict):
            raise TypeError(
                "Each JOIN subtitle file must be a dictionary "
                "containing 'name' and 'offset'."
            )

        if "name" not in part:
            raise ValueError(
                "Each JOIN subtitle file must contain "
                "a 'name' key."
            )

        if "offset" not in part:
            raise ValueError(
                "Each JOIN subtitle file must contain "
                "an 'offset' key."
            )

        name = part["name"]

        if not isinstance(name, (str, Path)):
            raise TypeError(
                "Subtitle 'name' must be a string or Path."
            )

        try:
            offset = float(part["offset"])
        except (TypeError, ValueError) as exc:
            raise TypeError(
                f"Invalid offset for subtitle file "
                f"'{name}': {part['offset']!r}"
            ) from exc

        # Part 1 cannot have gap.
        if is_first:
            if "gap" in part:
                raise ValueError(
                    "Part 1 cannot have a 'gap'. "
                    "Gap is only allowed from part 2 onward."
                )

            gap = 0.0

        # Part 2+ may have gap.
        else:
            if "gap" not in part:
                gap = 0.0
            else:
                try:
                    gap = float(part["gap"])
                except (TypeError, ValueError) as exc:
                    raise TypeError(
                        f"Invalid gap for subtitle file "
                        f"'{name}': {part['gap']!r}"
                    ) from exc

                if gap < 0:
                    raise ValueError(
                        f"Gap for subtitle file "
                        f"'{name}' cannot be negative."
                    )

        return name, offset, gap

    # ========================================================
    # SEQUENTIAL JOIN
    # ========================================================

    @staticmethod
    def join_sequential(
        subtitles: Sequence[SubtitleFile],
        offsets: Sequence[float],
        gaps: Sequence[float],
    ) -> SubtitleFile:
        """
        JOIN subtitle files sequentially.

        Part 1:
            original timestamps + offset

        Part 2+:
            previous final end + gap,
            then apply current part's offset.

        Offset belongs to the current part.
        Gap belongs between the previous part and
        the current part.
        """

        if not subtitles:
            return SubtitleFile([], "srt")

        if len(subtitles) != len(offsets):
            raise ValueError(
                "The number of subtitle files must match "
                "the number of offsets."
            )

        if len(subtitles) != len(gaps):
            raise ValueError(
                "The number of subtitle files must match "
                "the number of gaps."
            )

        result = SubtitleFile([], "srt")

        previous_end = 0.0
        has_previous_part = False

        for subtitle, offset, gap in zip(
            subtitles,
            offsets,
            gaps,
        ):
            if not subtitle.entries:
                continue

            offset = float(offset)
            gap = float(gap)

            # ------------------------------------------------
            # PART 1
            # ------------------------------------------------

            if not has_previous_part:
                shifted = subtitle.shift(offset)

            # ------------------------------------------------
            # PART 2+
            # ------------------------------------------------

            else:
                # Previous part has already received its offset.
                # Gap is measured from that final timestamp.
                target_start = previous_end + gap

                # Position the current part so its original
                # first subtitle lands at target_start.
                placement_shift = (
                    target_start
                    - subtitle.start_time
                )

                # Apply this part's own offset.
                total_shift = (
                    placement_shift
                    + offset
                )

                shifted = subtitle.shift(total_shift)

            result.entries.extend(
                entry.copy()
                for entry in shifted.entries
            )

            # IMPORTANT:
            # Store the end AFTER the current part's offset.
            # The next gap is calculated from this value.
            previous_end = shifted.end_time

            has_previous_part = True

        result.sort()
        result.renumber()

        return result

    # ========================================================
    # JOIN CONFIGURED FILES
    # ========================================================

    @staticmethod
    def join_configured_files(
        subtitle_files: Sequence[SubtitlePart],
        output_path: str | Path,
    ) -> SubtitleFile:
        """
        Load and JOIN configured subtitle files.

        Example:

            [
                {
                    "name": "part1.srt",
                    "offset": 2.0,
                },
                {
                    "name": "part2.srt",
                    "offset": -1.0,
                    "gap": 5.0,
                },
                {
                    "name": "part3.srt",
                    "offset": 3.0,
                    "gap": 2.0,
                },
            ]

        Each part's offset is applied.
        Each part after Part 1 also receives its gap.
        """

        if not subtitle_files:
            raise ValueError(
                "At least one subtitle file is required."
            )

        subtitles: List[SubtitleFile] = []
        offsets: List[float] = []
        gaps: List[float] = []

        for index, part in enumerate(
            subtitle_files
        ):
            name, offset, gap = (
                SubtitleJoiner._validate_part(
                    part,
                    is_first=(index == 0),
                )
            )

            subtitles.append(
                SubtitleFile.load(name)
            )

            offsets.append(offset)
            gaps.append(gap)

        result = SubtitleJoiner.join_sequential(
            subtitles=subtitles,
            offsets=offsets,
            gaps=gaps,
        )

        result.save(output_path)

        return result

# ============================================================
# SYNC POINT
# ============================================================


@dataclass
class SyncPoint:
    subtitle_time: float
    video_time: float


# ============================================================
# SUBTITLE SYNCHRONIZER
# ============================================================


class SubtitleSynchronizer:

    # ========================================================
    # FIXED OFFSET
    # ========================================================

    @staticmethod
    def apply_offset(
        subtitles: SubtitleFile,
        offset: float,
    ) -> SubtitleFile:

        return subtitles.shift(
            offset
        )

    # ========================================================
    # TWO POINT SYNC
    # ========================================================

    @staticmethod
    def synchronize_two_points(
        subtitles: SubtitleFile,
        subtitle_point_1: float,
        video_point_1: float,
        subtitle_point_2: float,
        video_point_2: float,
    ) -> SubtitleFile:

        return SubtitleSynchronizer.synchronize(
            subtitles,
            [
                SyncPoint(
                    subtitle_point_1,
                    video_point_1,
                ),
                SyncPoint(
                    subtitle_point_2,
                    video_point_2,
                ),
            ],
        )

    # ========================================================
    # MULTI POINT SYNC
    # ========================================================

    @staticmethod
    def synchronize(
        subtitles: SubtitleFile,
        points: Sequence[SyncPoint],
    ) -> SubtitleFile:

        if len(points) < 2:
            raise ValueError(
                "At least two synchronization points "
                "are required."
            )

        points = sorted(
            points,
            key=lambda p: p.subtitle_time,
        )

        result = subtitles.copy()

        # ----------------------------------------------------
        # VALIDATE POINTS
        # ----------------------------------------------------

        for i in range(1, len(points)):

            if (
                points[i].subtitle_time
                <= points[i - 1].subtitle_time
            ):
                raise ValueError(
                    "Synchronization subtitle times "
                    "must be strictly increasing."
                )

            if (
                points[i].video_time
                <= points[i - 1].video_time
            ):
                raise ValueError(
                    "Synchronization video times "
                    "must be strictly increasing."
                )

        # ----------------------------------------------------
        # TRANSFORM
        # ----------------------------------------------------

        def transform(
            timestamp: float,
        ) -> float:

            # Before first point.
            if timestamp <= points[0].subtitle_time:

                p1 = points[0]
                p2 = points[1]

            # After last point.
            elif timestamp >= points[-1].subtitle_time:

                p1 = points[-2]
                p2 = points[-1]

            # Between points.
            else:

                p1 = points[0]
                p2 = points[1]

                for i in range(
                    1,
                    len(points),
                ):

                    if (
                        timestamp
                        <= points[i].subtitle_time
                    ):

                        p1 = points[i - 1]
                        p2 = points[i]

                        break

            subtitle_delta = (
                p2.subtitle_time
                - p1.subtitle_time
            )

            video_delta = (
                p2.video_time
                - p1.video_time
            )

            if abs(subtitle_delta) < 0.000001:
                return p1.video_time

            scale = (
                video_delta
                / subtitle_delta
            )

            return (
                p1.video_time
                + (
                    timestamp
                    - p1.subtitle_time
                )
                * scale
            )

        # ----------------------------------------------------
        # TRANSFORM EVERY ENTRY
        # ----------------------------------------------------

        for entry in result.entries:

            entry.start = transform(
                entry.start
            )

            entry.end = transform(
                entry.end
            )

            entry.start = max(
                0.0,
                entry.start,
            )

            entry.end = max(
                entry.start,
                entry.end,
            )

        result.sort()
        result.renumber()

        return result

    # ========================================================
    # FIT TO VIDEO
    # ========================================================

    @staticmethod
    def fit_to_video(
        subtitles: SubtitleFile,
        video_duration: float,
    ) -> SubtitleFile:

        if not subtitles.entries:
            return subtitles.copy()

        video_duration = float(
            video_duration
        )

        if video_duration <= 0:
            raise ValueError(
                "Video duration must be greater than zero."
            )

        subtitle_start = subtitles.start_time
        subtitle_end = subtitles.end_time

        subtitle_duration = (
            subtitle_end
            - subtitle_start
        )

        if subtitle_duration <= 0:
            return subtitles.copy()

        scale = (
            video_duration
            / subtitle_duration
        )

        result = subtitles.copy()

        for entry in result.entries:

            entry.start = (
                (
                    entry.start
                    - subtitle_start
                )
                * scale
            )

            entry.end = (
                (
                    entry.end
                    - subtitle_start
                )
                * scale
            )

            entry.start = max(
                0.0,
                entry.start,
            )

            entry.end = max(
                entry.start,
                entry.end,
            )

        result.sort()
        result.renumber()

        return result

    # ========================================================
    # ALIGN START
    # ========================================================

    @staticmethod
    def align_start(
        subtitles: SubtitleFile,
        video_start: float = 0.0,
    ) -> SubtitleFile:

        if not subtitles.entries:
            return subtitles.copy()

        offset = (
            float(video_start)
            - subtitles.start_time
        )

        return subtitles.shift(
            offset
        )

    # ========================================================
    # ALIGN END
    # ========================================================

    @staticmethod
    def align_end(
        subtitles: SubtitleFile,
        video_duration: float,
    ) -> SubtitleFile:

        if not subtitles.entries:
            return subtitles.copy()

        offset = (
            float(video_duration)
            - subtitles.end_time
        )

        return subtitles.shift(
            offset
        )

    # ========================================================
    # CLAMP
    # ========================================================

    @staticmethod
    def clamp(
        subtitles: SubtitleFile,
        video_duration: float,
    ) -> SubtitleFile:

        return subtitles.clamp_to_duration(
            video_duration
        )

    # ========================================================
    # START + END SYNC
    # ========================================================

    @staticmethod
    def synchronize_start_end(
        subtitles: SubtitleFile,
        video_duration: float,
    ) -> SubtitleFile:

        if not subtitles.entries:
            return subtitles.copy()

        return SubtitleSynchronizer.synchronize(
            subtitles,
            [
                SyncPoint(
                    subtitles.start_time,
                    0.0,
                ),
                SyncPoint(
                    subtitles.end_time,
                    float(video_duration),
                ),
            ],
        )

    # ========================================================
    # CALCULATE OFFSET
    # ========================================================

    @staticmethod
    def calculate_offset(
        subtitle_time: float,
        video_time: float,
    ) -> float:

        return (
            float(video_time)
            - float(subtitle_time)
        )

    # ========================================================
    # CALCULATE DRIFT
    # ========================================================

    @staticmethod
    def calculate_drift(
        point_1: SyncPoint,
        point_2: SyncPoint,
    ) -> Tuple[float, float]:

        subtitle_delta = (
            point_2.subtitle_time
            - point_1.subtitle_time
        )

        video_delta = (
            point_2.video_time
            - point_1.video_time
        )

        if abs(subtitle_delta) < 0.000001:
            raise ValueError(
                "Cannot calculate drift from "
                "identical subtitle timestamps."
            )

        scale = (
            video_delta
            / subtitle_delta
        )

        offset = (
            point_1.video_time
            - point_1.subtitle_time * scale
        )

        return scale, offset


# ============================================================
# HIGH LEVEL PROCESSOR
# ============================================================


class SubtitleProcessor:

    # ========================================================
    # LOAD
    # ========================================================

    @staticmethod
    def load(
        path: str | Path,
    ) -> SubtitleFile:

        return SubtitleFile.load(
            path
        )

    # ========================================================
    # VALIDATE JOIN SUBTITLE CONFIGURATION
    # ========================================================

    @staticmethod
    def _validate_subtitle_files(
        subtitle_files: Sequence[SubtitlePart],
    ) -> List[SubtitlePart]:
        """
        Validate JOIN subtitle configuration.

        This method is JOIN-specific.

        JOIN requires dictionaries:

            {
                "name": "...",
                "offset": 0.0,
                "gap": 5.0,
            }

        Part 1 must not contain gap.
        """

        if not subtitle_files:
            raise ValueError(
                "At least one subtitle file is required."
            )

        normalized: List[SubtitlePart] = []

        for index, part in enumerate(
            subtitle_files,
            start=1,
        ):

            if not isinstance(
                part,
                dict,
            ):
                raise TypeError(
                    f"JOIN subtitle file #{index} must be "
                    "a dictionary with 'name' and 'offset'."
                )

            if "name" not in part:
                raise ValueError(
                    f"JOIN subtitle file #{index} "
                    "is missing 'name'."
                )

            if "offset" not in part:
                raise ValueError(
                    f"JOIN subtitle file #{index} "
                    "is missing 'offset'."
                )

            name = part["name"]

            if not isinstance(
                name,
                (str, Path),
            ):
                raise TypeError(
                    f"JOIN subtitle file #{index} "
                    "'name' must be a string or Path."
                )

            try:
                offset = float(
                    part["offset"]
                )
            except (
                TypeError,
                ValueError,
            ) as exc:
                raise TypeError(
                    f"JOIN subtitle file #{index} "
                    f"has invalid offset: "
                    f"{part['offset']!r}"
                ) from exc

            # ------------------------------------------------
            # PART 1
            # ------------------------------------------------

            if index == 1:

                if "gap" in part:
                    raise ValueError(
                        "Part 1 cannot have a 'gap'. "
                        "Gap is only allowed from part 2 onward."
                    )

                normalized.append(
                    {
                        "name": name,
                        "offset": offset,
                    }
                )

                continue

            # ------------------------------------------------
            # PART 2+
            # ------------------------------------------------

            if "gap" not in part:

                gap = 0.0

            else:

                try:
                    gap = float(
                        part["gap"]
                    )
                except (
                    TypeError,
                    ValueError,
                ) as exc:
                    raise TypeError(
                        f"JOIN subtitle file #{index} "
                        f"has invalid gap: "
                        f"{part['gap']!r}"
                    ) from exc

                if gap < 0:
                    raise ValueError(
                        f"JOIN subtitle file #{index} "
                        "gap cannot be negative."
                    )

            normalized.append(
                {
                    "name": name,
                    "offset": offset,
                    "gap": gap,
                }
            )

        return normalized

    # ========================================================
    # VALIDATE MERGE FILES
    # ========================================================

    @staticmethod
    def _validate_merge_files(
        subtitle_files: Sequence[SubtitleMergeFile],
    ) -> List[Path]:
        """
        Validate MERGE subtitle files.

        MERGE intentionally accepts ONLY file paths.

        Example:

            [
                "english.srt",
                "english_extra.srt",
                "signs.srt",
            ]

        MERGE has no:
            - name
            - offset
            - gap

        Files retain their original timestamps.
        """

        if not subtitle_files:
            raise ValueError(
                "At least one subtitle file is required."
            )

        normalized: List[Path] = []
        seen: set[Path] = set()

        for index, filepath in enumerate(
            subtitle_files,
            start=1,
        ):

            if not isinstance(
                filepath,
                (str, Path),
            ):
                raise TypeError(
                    f"MERGE subtitle file #{index} must be "
                    "a string path or Path."
                )

            path = Path(
                filepath
            ).expanduser()

            if not str(path).strip():
                continue

            path = path.absolute()

            if path in seen:
                continue

            seen.add(path)
            normalized.append(path)

        if not normalized:
            raise ValueError(
                "At least one subtitle file is required."
            )

        return normalized

    # ========================================================
    # JOIN PARTS
    # ========================================================

    @staticmethod
    def join_parts(
        subtitle_files: Sequence[SubtitlePart],
        output_path: str | Path,
    ) -> SubtitleFile:
        """
        Join multiple subtitle files sequentially.

        Part 1:
            name
            offset

        Part 2+:
            name
            offset
            gap
        """

        if output_path is None:
            raise ValueError(
                "output_path is required."
            )

        files = (
            SubtitleProcessor
            ._validate_subtitle_files(
                subtitle_files
            )
        )

        return SubtitleJoiner.join_configured_files(
            subtitle_files=files,
            output_path=output_path,
        )

    # ========================================================
    # MERGE TRACKS
    # ========================================================

    @staticmethod
    def merge_tracks(
        subtitle_files: Sequence[SubtitleMergeFile],
        output_path: str | Path,
        remove_duplicates: bool = True,
    ) -> SubtitleFile:
        """
        Merge multiple subtitle files on their existing
        timelines.

        MERGE accepts a plain list of file paths.

        Example:

            [
                "english.srt",
                "english_extra.srt",
                "signs.srt",
            ]

        No offset is applied.
        No gap is applied.
        No sequential positioning is performed.
        """

        if output_path is None:
            raise ValueError(
                "output_path is required."
            )

        files = (
            SubtitleProcessor
            ._validate_merge_files(
                subtitle_files
            )
        )

        subtitles: List[SubtitleFile] = []

        for path in files:
            subtitles.append(
                SubtitleFile.load(path)
            )

        result = SubtitleJoiner.merge_tracks(
            subtitles=subtitles,
            remove_duplicates=remove_duplicates,
        )

        result.save(output_path)

        return result

    # ========================================================
    # FIXED OFFSET
    # ========================================================

    @staticmethod
    def sync_offset(
        subtitle_path: str | Path,
        output_path: str | Path,
        offset: float,
        video_duration: Optional[float] = None,
    ) -> SubtitleFile:

        subtitles = SubtitleFile.load(
            subtitle_path
        )

        result = (
            SubtitleSynchronizer
            .apply_offset(
                subtitles,
                offset,
            )
        )

        if video_duration is not None:

            result = (
                SubtitleSynchronizer
                .clamp(
                    result,
                    video_duration,
                )
            )

        result.save(
            output_path
        )

        return result

    # ========================================================
    # TWO POINT SYNC
    # ========================================================

    @staticmethod
    def sync_two_points(
        subtitle_path: str | Path,
        output_path: str | Path,
        subtitle_point_1: float,
        video_point_1: float,
        subtitle_point_2: float,
        video_point_2: float,
        video_duration: Optional[float] = None,
    ) -> SubtitleFile:

        subtitles = SubtitleFile.load(
            subtitle_path
        )

        result = (
            SubtitleSynchronizer
            .synchronize_two_points(
                subtitles,
                subtitle_point_1,
                video_point_1,
                subtitle_point_2,
                video_point_2,
            )
        )

        if video_duration is not None:

            result = (
                SubtitleSynchronizer
                .clamp(
                    result,
                    video_duration,
                )
            )

        result.save(
            output_path
        )

        return result

    # ========================================================
    # MULTI POINT SYNC
    # ========================================================

    @staticmethod
    def sync_points(
        subtitle_path: str | Path,
        output_path: str | Path,
        points: Sequence[SyncPoint],
        video_duration: Optional[float] = None,
    ) -> SubtitleFile:

        subtitles = SubtitleFile.load(
            subtitle_path
        )

        result = (
            SubtitleSynchronizer
            .synchronize(
                subtitles,
                points,
            )
        )

        if video_duration is not None:

            result = (
                SubtitleSynchronizer
                .clamp(
                    result,
                    video_duration,
                )
            )

        result.save(
            output_path
        )

        return result

    # ========================================================
    # START + END SYNC
    # ========================================================

    @staticmethod
    def sync_start_end(
        subtitle_path: str | Path,
        output_path: str | Path,
        video_duration: float,
    ) -> SubtitleFile:

        subtitles = SubtitleFile.load(
            subtitle_path
        )

        result = (
            SubtitleSynchronizer
            .synchronize_start_end(
                subtitles,
                video_duration,
            )
        )

        result = (
            SubtitleSynchronizer
            .clamp(
                result,
                video_duration,
            )
        )

        result.save(
            output_path
        )

        return result

    # ========================================================
    # VALIDATE
    # ========================================================

    @staticmethod
    def validate(
        subtitle_path: str | Path,
    ) -> List[str]:

        subtitles = SubtitleFile.load(
            subtitle_path
        )

        return subtitles.validate()

