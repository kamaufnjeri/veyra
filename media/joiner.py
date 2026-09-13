from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .ffmpeg import FFmpeg
from .ffprobe import FFProbe
from .models import JoinResult, JoinerSettings
from .subtitles import SubtitleManager


@dataclass(frozen=True)
class _SRTCue:
    index: int
    start: float
    end: float
    text: str


class MediaJoiner:
    """
    Join videos, audio files, and SRT subtitle files independently.

    Supported operations:

        join_videos(...)
        join_audio(...)
        join_subtitles(...)

    The generic join(...) method remains available and automatically
    determines whether the supplied inputs are:

        - videos
        - audio
        - SRT subtitles

    Video behavior:

        video1 + video2 + video3
            -> joined video

    Audio behavior:

        audio1 + audio2 + audio3
            -> joined audio

    Subtitle behavior:

        subtitle1 + subtitle2 + subtitle3
            -> joined SRT

    If videos have matching sidecar SRT files, those subtitle files
    are also joined automatically using the actual duration of each
    corresponding video as the timestamp offset.

    Embedded subtitle streams inside video containers are preserved
    when possible by the FFmpeg concat demuxer.
    """

    VIDEO_EXTENSIONS = {
        ".mp4",
        ".mkv",
        ".mov",
        ".avi",
        ".webm",
        ".m4v",
        ".ts",
        ".mpeg",
        ".mpg",
        ".3gp",
    }

    AUDIO_EXTENSIONS = {
        ".mp3",
        ".wav",
        ".flac",
        ".aac",
        ".m4a",
        ".ogg",
        ".opus",
        ".wma",
    }

    SUBTITLE_EXTENSIONS = {
        ".srt",
    }

    def __init__(
        self,
        *,
        ffmpeg: str = "ffmpeg",
        ffprobe: str = "ffprobe",
        progress_callback=None,
        cancellation_callback=None,
    ):
        self.ff = FFmpeg(
            ffmpeg=ffmpeg,
            progress_callback=progress_callback,
            cancellation_callback=cancellation_callback,
        )

        self.ffprobe = FFProbe(
            executable=ffprobe
        )

        self.subtitles = SubtitleManager(
            ffmpeg=self.ff,
            ffprobe=self.ffprobe,
        )

    # ========================================================
    # GENERIC JOIN
    # ========================================================

    def join(
        self,
        inputs: Sequence[str | Path],
        output: str | Path,
        settings: JoinerSettings | None = None,
    ) -> JoinResult:
        """
        Automatically join videos, audio, or SRT files.

        This method is intentionally kept as the public generic
        entry point because the job system already dispatches the
        "join" operation with an input sequence.
        """

        paths = self._normalize_paths(inputs)

        if not paths:
            raise ValueError(
                "At least one input is required."
            )

        media_type = self._detect_join_type(paths)

        if media_type == "video":
            return self.join_videos(
                paths,
                output,
                settings,
            )

        if media_type == "audio":
            return self.join_audio(
                paths,
                output,
                settings,
            )

        if media_type == "subtitle":
            return self.join_subtitles(
                paths,
                output,
                settings,
            )

        raise ValueError(
            f"Unsupported join media type: {media_type}"
        )

    # ========================================================
    # JOIN VIDEOS
    # ========================================================

    def join_videos(
        self,
        inputs: Sequence[str | Path],
        output: str | Path,
        settings: JoinerSettings | None = None,
    ) -> JoinResult:
        """
        Join video files.

        Existing audio streams inside the videos are retained.

        Matching sidecar SRT files are automatically joined after
        the video has been created.

        Example:

            episode01.mp4
            episode02.mp4
            episode03.mp4

        produces:

            joined.mp4

        And if these exist:

            episode01.srt
            episode02.srt
            episode03.srt

        Veyra also produces:

            joined.en.srt

        with subtitle timestamps offset according to the duration
        of each corresponding video.
        """

        settings = (
            settings
            or JoinerSettings()
        )

        settings.validate()

        paths = self._normalize_paths(inputs)

        if not paths:
            raise ValueError(
                "At least one video input is required."
            )

        for path in paths:
            self.ff.validate_input(path)

        self._validate_video_inputs(paths)

        output = Path(
            output
        ).expanduser()

        self.ff.validate_output(
            paths[0],
            output,
            settings.overwrite,
        )

        durations = [
            self.ffprobe.duration(path)
            for path in paths
        ]

        duration = sum(durations)

        concat_file = self.ff.temporary_path(
            ".txt"
        )

        temp = self.ff.temporary_path(
            output.suffix or ".mp4"
        )

        try:
            concat_file.write_text(
                "\n".join(
                    self._concat_line(path)
                    for path in paths
                ),
                encoding="utf-8",
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

                # ----------------------------------------
                # VIDEO
                # ----------------------------------------

                "-map",
                "0:v:0",
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

            # ----------------------------------------
            # AUDIO
            # ----------------------------------------

            command += [
                "-map",
                "0:a?",
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

            # ----------------------------------------
            # EMBEDDED SUBTITLES
            # ----------------------------------------
            #
            # Preserve embedded subtitle streams when
            # the concat demuxer exposes them.
            #
            # We use optional mapping so videos without
            # subtitles continue to work.
            # ----------------------------------------

            command += [
                "-map",
                "0:s?",
                "-c:s",
                "copy",
            ]

            # ----------------------------------------
            # DATA / ATTACHMENTS
            # ----------------------------------------

            command += [
                "-dn",
            ]

            # ----------------------------------------
            # FASTSTART
            # ----------------------------------------

            if (
                settings.faststart
                and output.suffix.lower()
                in {
                    ".mp4",
                    ".m4v",
                    ".mov",
                }
            ):
                command += [
                    "-movflags",
                    "+faststart",
                ]

            command.append(
                str(temp)
            )

            self.ff.run(
                command,
                message="Joining videos",
                duration=duration,
            )

            self.ff.atomic_replace(
                temp,
                output,
            )

            # ----------------------------------------
            # SIDE-CAR SUBTITLES
            # ----------------------------------------

            if settings.join_subtitles:

                self._join_matching_sidecar_subtitles(
                    videos=paths,
                    durations=durations,
                    output=output,
                    settings=settings,
                )

            return JoinResult(
                inputs=paths,
                output=output,
                duration=duration,
            )

        finally:

            self.ff.cleanup()

    # ========================================================
    # JOIN AUDIO
    # ========================================================

    def join_audio(
        self,
        inputs: Sequence[str | Path],
        output: str | Path,
        settings: JoinerSettings | None = None,
    ) -> JoinResult:
        """
        Join audio files independently.
        """

        settings = (
            settings
            or JoinerSettings()
        )

        settings.validate()

        paths = self._normalize_paths(inputs)

        if not paths:
            raise ValueError(
                "At least one audio input is required."
            )

        for path in paths:
            self.ff.validate_input(path)

        self._validate_audio_inputs(paths)

        output = Path(
            output
        ).expanduser()

        self.ff.validate_output(
            paths[0],
            output,
            settings.overwrite,
        )

        durations = [
            self.ffprobe.duration(path)
            for path in paths
        ]

        duration = sum(durations)

        concat_file = self.ff.temporary_path(
            ".txt"
        )

        temp = self.ff.temporary_path(
            output.suffix or ".m4a"
        )

        try:

            concat_file.write_text(
                "\n".join(
                    self._concat_line(path)
                    for path in paths
                ),
                encoding="utf-8",
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
                "0:a:0",
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

            command += [
                "-vn",
                "-sn",
                "-dn",
            ]

            if (
                settings.faststart
                and output.suffix.lower()
                in {
                    ".mp4",
                    ".m4a",
                    ".mov",
                }
            ):
                command += [
                    "-movflags",
                    "+faststart",
                ]

            command.append(
                str(temp)
            )

            self.ff.run(
                command,
                message="Joining audio",
                duration=duration,
            )

            self.ff.atomic_replace(
                temp,
                output,
            )

            return JoinResult(
                inputs=paths,
                output=output,
                duration=duration,
            )

        finally:

            self.ff.cleanup()

    # ========================================================
    # JOIN SUBTITLES
    # ========================================================

    def join_subtitles(
        self,
        inputs: Sequence[str | Path],
        output: str | Path,
        settings: JoinerSettings | None = None,
    ) -> JoinResult:
        """
        Join SRT files independently.

        Timestamps are automatically offset according to the
        duration of every preceding subtitle segment.

        Example:

            01.srt
            02.srt
            03.srt

        becomes:

            joined.srt
        """

        settings = (
            settings
            or JoinerSettings()
        )

        settings.validate()

        paths = self._normalize_paths(inputs)

        if not paths:
            raise ValueError(
                "At least one subtitle input is required."
            )

        self._validate_srt_inputs(paths)

        output = Path(
            output
        ).expanduser()

        output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        # Subtitle files do not have media duration in
        # the same sense as video/audio. The offset for
        # each SRT segment is therefore the end timestamp
        # of the preceding SRT.
        #
        # This gives deterministic subtitle concatenation
        # even when the SRT files came from independently
        # downloaded media.

        cues: list[_SRTCue] = []

        offset = 0.0
        cue_index = 1

        for path in paths:

            file_cues = self._read_srt(
                path
            )

            if not file_cues:
                continue

            segment_end = max(
                cue.end
                for cue in file_cues
            )

            for cue in file_cues:

                cues.append(
                    _SRTCue(
                        index=cue_index,
                        start=cue.start + offset,
                        end=cue.end + offset,
                        text=cue.text,
                    )
                )

                cue_index += 1

            offset += segment_end

        if not cues:
            raise ValueError(
                "None of the supplied SRT files "
                "contains subtitle cues."
            )

        temp = self.ff.temporary_path(
            output.suffix or ".srt"
        )

        try:

            self._write_srt(
                temp,
                cues,
            )

            self._replace_file(
                temp,
                output,
                settings.overwrite,
            )

            return JoinResult(
                inputs=paths,
                output=output,
                duration=offset,
            )

        finally:

            self.ff.cleanup()

    # ========================================================
    # TYPE DETECTION
    # ========================================================

    def _detect_join_type(
        self,
        paths: tuple[Path, ...],
    ) -> str:

        suffixes = {
            path.suffix.lower()
            for path in paths
        }

        if suffixes and suffixes.issubset(
            self.SUBTITLE_EXTENSIONS
        ):
            return "subtitle"

        if suffixes and suffixes.issubset(
            self.AUDIO_EXTENSIONS
        ):
            return "audio"

        if suffixes and suffixes.issubset(
            self.VIDEO_EXTENSIONS
        ):
            return "video"

        # Some containers may have uncommon extensions.
        # Probe them instead.
        detected: set[str] = set()

        for path in paths:

            data = self.ffprobe.probe(
                path
            )

            streams = data.get(
                "streams",
                [],
            )

            has_video = any(
                isinstance(stream, dict)
                and stream.get("codec_type")
                == "video"
                for stream in streams
            )

            has_audio = any(
                isinstance(stream, dict)
                and stream.get("codec_type")
                == "audio"
                for stream in streams
            )

            if has_video:
                detected.add("video")

            elif has_audio:
                detected.add("audio")

            else:
                raise ValueError(
                    f"Unable to determine media type: {path}"
                )

        if len(detected) != 1:
            raise ValueError(
                "Join inputs must contain only one media type."
            )

        return detected.pop()

    # ========================================================
    # VIDEO VALIDATION
    # ========================================================

    def _validate_video_inputs(
        self,
        paths: tuple[Path, ...],
    ) -> None:

        for path in paths:

            data = self.ffprobe.probe(
                path
            )

            streams = data.get(
                "streams",
                [],
            )

            has_video = any(
                isinstance(stream, dict)
                and stream.get("codec_type")
                == "video"
                for stream in streams
            )

            if not has_video:
                raise ValueError(
                    f"Input is not a video file: {path}"
                )

    # ========================================================
    # AUDIO VALIDATION
    # ========================================================

    def _validate_audio_inputs(
        self,
        paths: tuple[Path, ...],
    ) -> None:

        for path in paths:

            data = self.ffprobe.probe(
                path
            )

            streams = data.get(
                "streams",
                [],
            )

            has_audio = any(
                isinstance(stream, dict)
                and stream.get("codec_type")
                == "audio"
                for stream in streams
            )

            if not has_audio:
                raise ValueError(
                    f"Input is not an audio file: {path}"
                )

    # ========================================================
    # SRT VALIDATION
    # ========================================================

    def _validate_srt_inputs(
        self,
        paths: tuple[Path, ...],
    ) -> None:

        for path in paths:

            if path.suffix.lower() != ".srt":
                raise ValueError(
                    "Join subtitles currently supports "
                    f"SRT files only: {path}"
                )

            if not path.is_file():
                raise FileNotFoundError(
                    f"Subtitle file does not exist: {path}"
                )

    # ========================================================
    # SIDE-CAR SUBTITLES
    # ========================================================

    def _join_matching_sidecar_subtitles(
        self,
        *,
        videos: tuple[Path, ...],
        durations: list[float],
        output: Path,
        settings: JoinerSettings,
    ) -> None:
        """
        Automatically join matching sidecar SRT files.

        We first look for the common naming convention:

            video01.mp4
            video01.srt

        We also use SubtitleManager discovery when available,
        allowing existing Veyra subtitle discovery behavior to
        continue working.
        """

        subtitle_sets: dict[str, list[Path | None]] = {}

        for video in videos:

            candidates = self._sidecar_srt_candidates(
                video
            )

            discovered: list[Path] = []

            try:

                tracks = self.subtitles.discover(
                    video
                )

                tracks = self.subtitles.filter(
                    tracks,
                    settings.subtitle,
                )

                for track in tracks:

                    if track.embedded:
                        continue

                    source = Path(
                        track.source
                    )

                    if source.suffix.lower() == ".srt":
                        discovered.append(
                            source
                        )

            except Exception:
                # Sidecar discovery is supplementary. The
                # direct filename check below remains usable
                # even when SubtitleManager has no result.
                pass

            all_candidates = [
                *candidates,
                *discovered,
            ]

            unique_candidates: list[Path] = []
            seen: set[Path] = set()

            for candidate in all_candidates:

                resolved = candidate.expanduser().resolve()

                if resolved in seen:
                    continue

                if not resolved.is_file():
                    continue

                seen.add(resolved)
                unique_candidates.append(
                    resolved
                )

            for subtitle in unique_candidates:

                language = self._subtitle_language(
                    subtitle
                )

                key = language or "und"

                subtitle_sets.setdefault(
                    key,
                    [None] * len(videos),
                )

                index = videos.index(
                    video
                )

                subtitle_sets[key][index] = subtitle

        for language, tracks in subtitle_sets.items():

            if not all(tracks):
                continue

            concrete_tracks = tuple(
                track
                for track in tracks
                if track is not None
            )

            if len(concrete_tracks) != len(videos):
                continue

            subtitle_output = output.with_name(
                f"{output.stem}.{language}.srt"
            )

            self._join_srt_with_offsets(
                subtitles=concrete_tracks,
                offsets=self._cumulative_offsets(
                    durations
                ),
                output=subtitle_output,
                overwrite=settings.overwrite,
            )

    # ========================================================
    # SIDE-CAR CANDIDATES
    # ========================================================

    @staticmethod
    def _sidecar_srt_candidates(
        video: Path,
    ) -> list[Path]:
        """
        Find common sidecar subtitle naming conventions.

        Examples:

            episode.mp4
            episode.srt

            episode.mp4
            episode.en.srt

        The exact-language files are later grouped.
        """

        parent = video.parent
        stem = video.stem

        candidates = [
            parent / f"{stem}.srt",
        ]

        candidates.extend(
            sorted(
                parent.glob(
                    f"{stem}.*.srt"
                )
            )
        )

        return candidates

    # ========================================================
    # SIDE-CAR LANGUAGE
    # ========================================================

    @staticmethod
    def _subtitle_language(
        path: Path,
    ) -> str:
        """
        Infer a simple language identifier from an SRT filename.

        Examples:

            episode.en.srt -> en
            episode.sw.srt -> sw
            episode.srt    -> und
        """

        stem = path.stem

        parts = stem.split(".")

        if len(parts) < 2:
            return "und"

        language = parts[-1].strip().lower()

        if not language:
            return "und"

        if not re.fullmatch(
            r"[a-z]{2,3}(?:[-_][a-z]{2,4})?",
            language,
        ):
            return "und"

        return language.replace(
            "_",
            "-",
        )

    # ========================================================
    # CUMULATIVE OFFSETS
    # ========================================================

    @staticmethod
    def _cumulative_offsets(
        durations: Sequence[float],
    ) -> list[float]:

        offsets: list[float] = []

        current = 0.0

        for duration in durations:

            offsets.append(
                current
            )

            current += duration

        return offsets

    # ========================================================
    # JOIN SRT WITH OFFSETS
    # ========================================================

    def _join_srt_with_offsets(
        self,
        *,
        subtitles: Sequence[Path],
        offsets: Sequence[float],
        output: Path,
        overwrite: bool,
    ) -> None:

        if len(subtitles) != len(offsets):
            raise ValueError(
                "Subtitle and video counts must match "
                "when joining corresponding sidecar subtitles."
            )

        all_cues: list[_SRTCue] = []

        index = 1

        for subtitle, offset in zip(
            subtitles,
            offsets,
        ):

            cues = self._read_srt(
                subtitle
            )

            for cue in cues:

                all_cues.append(
                    _SRTCue(
                        index=index,
                        start=cue.start + offset,
                        end=cue.end + offset,
                        text=cue.text,
                    )
                )

                index += 1

        if not all_cues:
            return

        temp = self.ff.temporary_path(
            ".srt"
        )

        try:

            self._write_srt(
                temp,
                all_cues,
            )

            self._replace_file(
                temp,
                output,
                overwrite,
            )

        finally:

            self.ff.cleanup()

    # ========================================================
    # READ SRT
    # ========================================================

    @classmethod
    def _read_srt(
        cls,
        path: Path,
    ) -> list[_SRTCue]:

        text = path.read_text(
            encoding="utf-8-sig",
            errors="replace",
        )

        blocks = re.split(
            r"\n\s*\n",
            text.replace(
                "\r\n",
                "\n",
            ).replace(
                "\r",
                "\n",
            ).strip(),
        )

        cues: list[_SRTCue] = []

        for fallback_index, block in enumerate(
            blocks,
            start=1,
        ):

            lines = block.splitlines()

            if len(lines) < 2:
                continue

            timing_index = None

            for index, line in enumerate(lines):

                if "-->" in line:
                    timing_index = index
                    break

            if timing_index is None:
                continue

            timing = lines[timing_index]

            match = re.match(
                r"\s*(\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})"
                r"\s*-->\s*"
                r"(\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})",
                timing,
            )

            if not match:
                continue

            start = cls._parse_srt_time(
                match.group(1)
            )

            end = cls._parse_srt_time(
                match.group(2)
            )

            if end < start:
                continue

            text_lines = lines[
                timing_index + 1:
            ]

            cue_text = "\n".join(
                text_lines
            ).strip()

            cues.append(
                _SRTCue(
                    index=fallback_index,
                    start=start,
                    end=end,
                    text=cue_text,
                )
            )

        return cues

    # ========================================================
    # WRITE SRT
    # ========================================================

    @classmethod
    def _write_srt(
        cls,
        path: Path,
        cues: Sequence[_SRTCue],
    ) -> None:

        lines: list[str] = []

        for index, cue in enumerate(
            cues,
            start=1,
        ):

            lines.append(
                str(index)
            )

            lines.append(
                f"{cls._format_srt_time(cue.start)} "
                f"--> "
                f"{cls._format_srt_time(cue.end)}"
            )

            lines.extend(
                cue.text.splitlines()
                if cue.text
                else [""]
            )

            lines.append("")

        path.write_text(
            "\n".join(lines),
            encoding="utf-8",
        )

    # ========================================================
    # SRT TIME
    # ========================================================

    @staticmethod
    def _parse_srt_time(
        value: str,
    ) -> float:

        value = value.replace(
            ",",
            ".",
        )

        hours, minutes, seconds = value.split(
            ":"
        )

        return (
            float(hours) * 3600.0
            + float(minutes) * 60.0
            + float(seconds)
        )

    @staticmethod
    def _format_srt_time(
        seconds: float,
    ) -> str:

        seconds = max(
            0.0,
            seconds,
        )

        total_milliseconds = int(
            round(
                seconds * 1000
            )
        )

        hours = total_milliseconds // 3_600_000

        remainder = (
            total_milliseconds
            % 3_600_000
        )

        minutes = remainder // 60_000

        remainder %= 60_000

        secs = remainder // 1000

        milliseconds = remainder % 1000

        return (
            f"{hours:02d}:"
            f"{minutes:02d}:"
            f"{secs:02d},"
            f"{milliseconds:03d}"
        )

    # ========================================================
    # FILE REPLACEMENT
    # ========================================================

    @staticmethod
    def _replace_file(
        source: Path,
        destination: Path,
        overwrite: bool,
    ) -> None:

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        if destination.exists():

            if not overwrite:
                raise FileExistsError(
                    f"Output already exists: {destination}"
                )

            destination.unlink()

        source.replace(
            destination
        )

    # ========================================================
    # PATH NORMALIZATION
    # ========================================================

    @staticmethod
    def _normalize_paths(
        inputs: Sequence[str | Path],
    ) -> tuple[Path, ...]:

        return tuple(
            Path(path).expanduser()
            for path in inputs
        )

    # ========================================================
    # CONCAT FILE
    # ========================================================

    @staticmethod
    def _concat_line(
        path: Path,
    ) -> str:

        value = str(
            path.resolve()
        ).replace(
            "'",
            "'\\''",
        )

        return f"file '{value}'"

