from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple
import re


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

        self.format_name = (
            format_name.lower()
        )

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

        path = Path(path)

        text = path.read_text(
            encoding=encoding,
            errors="replace",
        )

        suffix = path.suffix.lower()

        if suffix == ".vtt":
            return cls.from_vtt(text)

        return cls.from_srt(text)

    # ========================================================
    # SRT PARSER
    # ========================================================

    @classmethod
    def from_srt(
        cls,
        text: str,
    ) -> "SubtitleFile":

        text = text.replace(
            "\r\n",
            "\n",
        ).replace(
            "\r",
            "\n",
        )

        blocks = re.split(
            r"\n\s*\n",
            text.strip(),
        )

        entries = []

        for block in blocks:

            lines = block.splitlines()

            if not lines:
                continue

            lines = [
                line.rstrip()
                for line in lines
            ]

            index = 0

            # --------------------------------------------
            # NUMBER
            # --------------------------------------------

            if lines[0].strip().isdigit():
                index = int(
                    lines[0].strip()
                )
                lines = lines[1:]

            if not lines:
                continue

            # --------------------------------------------
            # TIMING
            # --------------------------------------------

            timing_line = None
            timing_index = None

            for i, line in enumerate(lines):
                if "-->" in line:
                    timing_line = line
                    timing_index = i
                    break

            if timing_line is None:
                continue

            start_text, end_text = (
                timing_line.split(
                    "-->",
                    1,
                )
            )

            start = cls.parse_timestamp(
                start_text.strip()
            )

            end = cls.parse_timestamp(
                end_text.strip().split()[0]
            )

            # --------------------------------------------
            # TEXT
            # --------------------------------------------

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

        text = text.replace(
            "\r\n",
            "\n",
        ).replace(
            "\r",
            "\n",
        )

        lines = text.splitlines()

        # Remove WEBVTT header.
        if lines and lines[0].strip().upper().startswith(
            "WEBVTT"
        ):
            lines = lines[1:]

        blocks = re.split(
            r"\n\s*\n",
            "\n".join(lines).strip(),
        )

        entries = []
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

            timing_line = lines[
                timing_index
            ]

            start_text, end_text = (
                timing_line.split(
                    "-->",
                    1,
                )
            )

            start = cls.parse_timestamp(
                start_text.strip()
            )

            end = cls.parse_timestamp(
                end_text.strip().split()[0]
            )

            subtitle_text = "\n".join(
                lines[timing_index + 1:]
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

        match = re.match(
            r"^(\d+):(\d{2}):(\d{2})\.(\d{3})$",
            value,
        )

        if not match:

            # VTT may allow MM:SS.mmm.
            match = re.match(
                r"^(\d{2}):(\d{2})\.(\d{3})$",
                value,
            )

            if not match:
                raise ValueError(
                    f"Invalid subtitle timestamp: {value}"
                )

            minutes = int(match.group(1))
            seconds = int(match.group(2))
            milliseconds = int(match.group(3))

            return (
                minutes * 60
                + seconds
                + milliseconds / 1000.0
            )

        hours = int(match.group(1))
        minutes = int(match.group(2))
        seconds = int(match.group(3))
        milliseconds = int(match.group(4))

        return (
            hours * 3600
            + minutes * 60
            + seconds
            + milliseconds / 1000.0
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

    def sort(self):

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

    def renumber(self):

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
    ):

        path = Path(path)

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
                + (entry.start - anchor)
                * scale
            )

            entry.end = (
                anchor
                + (entry.end - anchor)
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

        return result

    # ========================================================
    # REMOVE DUPLICATES
    # ========================================================

    def remove_duplicates(
        self,
        time_tolerance: float = 0.05,
    ) -> "SubtitleFile":

        result = self.copy()

        unique = []

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

        result = self.copy()
        valid = []

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
        result.renumber()

        return result

    # ========================================================
    # VALIDATE
    # ========================================================

    def validate(self) -> List[str]:

        errors = []

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
    # SEQUENTIAL JOIN
    # ========================================================

    @staticmethod
    def join_sequential(
        first: SubtitleFile,
        second: SubtitleFile,
        gap: float = 0.0,
        second_offset: Optional[float] = None,
    ) -> SubtitleFile:

        first_result = first.copy()
        second_result = second.copy()

        if second_offset is None:

            if first_result.entries:
                first_end = (
                    first_result.end_time
                )
            else:
                first_end = 0.0

            second_start = (
                second_result.start_time
                if second_result.entries
                else 0.0
            )

            second_offset = (
                first_end
                + float(gap)
                - second_start
            )

        second_result = second_result.shift(
            second_offset
        )

        first_result.entries.extend(
            second_result.entries
        )

        first_result.sort()
        first_result.renumber()

        return first_result.remove_duplicates()

    # ========================================================
    # TIMELINE MERGE
    # ========================================================

    @staticmethod
    def merge_tracks(
        first: SubtitleFile,
        second: SubtitleFile,
        remove_duplicates: bool = True,
    ) -> SubtitleFile:

        result = first.copy()

        result.entries.extend(
            entry.copy()
            for entry in second.entries
        )

        result.sort()

        if remove_duplicates:
            result = result.remove_duplicates()

        result.renumber()

        return result

    # ========================================================
    # JOIN FILES
    # ========================================================

    @staticmethod
    def join_files(
        first_path: str | Path,
        second_path: str | Path,
        output_path: str | Path,
        gap: float = 0.0,
        second_offset: Optional[float] = None,
    ) -> SubtitleFile:

        first = SubtitleFile.load(
            first_path
        )

        second = SubtitleFile.load(
            second_path
        )

        result = SubtitleJoiner.join_sequential(
            first,
            second,
            gap=gap,
            second_offset=second_offset,
        )

        result.save(
            output_path
        )

        return result


# ============================================================
# SYNCHRONIZATION ANCHOR
# ============================================================

@dataclass
class SyncPoint:
    """
    A known matching point.

    subtitle_time:
        Timestamp in subtitle file.

    video_time:
        Corresponding timestamp in video.
    """

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
    # TWO POINT DRIFT CORRECTION
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
    # MULTI-POINT SYNCHRONIZATION
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
        # Check duplicate subtitle points.
        # ----------------------------------------------------

        for i in range(
            1,
            len(points),
        ):

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
        # Piecewise linear correction.
        #
        # This is important because a subtitle track can
        # drift differently over different sections.
        # ----------------------------------------------------

        def transform(
            timestamp: float,
        ) -> float:

            # Before first anchor.
            if timestamp <= points[0].subtitle_time:

                p1 = points[0]
                p2 = points[1]

            # After last anchor.
            elif timestamp >= points[-1].subtitle_time:

                p1 = points[-2]
                p2 = points[-1]

            else:

                p1 = points[0]
                p2 = points[1]

                for i in range(
                    1,
                    len(points),
                ):

                    if timestamp <= points[i].subtitle_time:
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
        # Transform every subtitle.
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
    # AUTOMATIC TWO-POINT DURATION CORRECTION
    # ========================================================

    @staticmethod
    def fit_to_video(
        subtitles: SubtitleFile,
        video_duration: float,
    ) -> SubtitleFile:

        if not subtitles.entries:
            return subtitles.copy()

        subtitle_start = (
            subtitles.start_time
        )

        subtitle_end = (
            subtitles.end_time
        )

        subtitle_duration = (
            subtitle_end
            - subtitle_start
        )

        if subtitle_duration <= 0:
            return subtitles.copy()

        video_duration = float(
            video_duration
        )

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
    # START ALIGNMENT
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
    # END ALIGNMENT
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
    # AUTO CORRECT USING START + END
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
    # JOIN TWO PARTS
    # ========================================================

    @staticmethod
    def join_parts(
        first_path: str | Path,
        second_path: str | Path,
        output_path: str | Path,
        gap: float = 0.0,
        second_offset: Optional[float] = None,
    ) -> SubtitleFile:

        result = SubtitleJoiner.join_files(
            first_path,
            second_path,
            output_path,
            gap=gap,
            second_offset=second_offset,
        )

        return result

    # ========================================================
    # MERGE TWO TRACKS
    # ========================================================

    @staticmethod
    def merge_tracks(
        first_path: str | Path,
        second_path: str | Path,
        output_path: str | Path,
    ) -> SubtitleFile:

        first = SubtitleFile.load(
            first_path
        )

        second = SubtitleFile.load(
            second_path
        )

        result = SubtitleJoiner.merge_tracks(
            first,
            second,
        )

        result.save(
            output_path
        )

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

        result = SubtitleSynchronizer.apply_offset(
            subtitles,
            offset,
        )

        if video_duration is not None:
            result = SubtitleSynchronizer.clamp(
                result,
                video_duration,
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
            SubtitleSynchronizer.synchronize_two_points(
                subtitles,
                subtitle_point_1,
                video_point_1,
                subtitle_point_2,
                video_point_2,
            )
        )

        if video_duration is not None:
            result = SubtitleSynchronizer.clamp(
                result,
                video_duration,
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

        result = SubtitleSynchronizer.synchronize(
            subtitles,
            points,
        )

        if video_duration is not None:
            result = SubtitleSynchronizer.clamp(
                result,
                video_duration,
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
            SubtitleSynchronizer.synchronize_start_end(
                subtitles,
                video_duration,
            )
        )

        result = SubtitleSynchronizer.clamp(
            result,
            video_duration,
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