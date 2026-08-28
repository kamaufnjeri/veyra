from __future__ import annotations

import os

from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
)

from core.subtitle_sync import (
    SubtitleFile,
    SubtitleSynchronizer,
    SubtitleProcessor,
    SyncPoint,
)


class SubtitleSyncService:
    """
    Subtitle orchestration service.

    Supported operations:

        join_parts
        merge_tracks
        offset
        two_point
        multi_point
        start_end
        fit
        clamp
        validate

    JOIN / MERGE support one to four subtitle files.

    JOIN:
        Files are placed sequentially on the timeline.

    MERGE:
        Files are combined while preserving their timestamps.

    Preferred JOIN / MERGE settings:

        {
            "operation": "join_parts",
            "subtitle_files": [
                "/path/one.srt",
                "/path/two.srt",
                "/path/three.srt",
                "/path/four.srt",
            ],
            "output": "/path/output.srt",
        }

    Backwards compatibility:

        first_file
        second_file

    are still accepted.
    """

    MAX_SUBTITLE_FILES = 4

    OPERATIONS = {
        "join_parts",
        "merge_tracks",
        "offset",
        "two_point",
        "multi_point",
        "start_end",
        "fit",
        "clamp",
        "validate",
    }

    FORMATS = {
        "srt",
        "vtt",
    }

    def __init__(
        self,
        progress_callback: Optional[Callable[..., None]] = None,
        error_callback: Optional[Callable[[Any], None]] = None,
        finished_callback: Optional[Callable[..., None]] = None,
        cancelled_callback: Optional[Callable[..., None]] = None,
    ) -> None:

        self.progress_callback = progress_callback
        self.error_callback = error_callback
        self.finished_callback = finished_callback
        self.cancelled_callback = cancelled_callback

        self.cancelled = False
        self._progress_stage = "idle"

        # FIX:
        # The old code referenced self.subtitle_format without
        # ever creating the attribute.
        self.subtitle_format = "srt"

    # ==========================================================
    # PUBLIC
    # ==========================================================

    def process(
        self,
        settings: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Process a subtitle operation."""
        return self.create_subtitles(settings)

    def start(
        self,
        settings: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Start a subtitle operation."""
        return self.create_subtitles(settings)

    def process_subtitle_operation(
        self,
        settings: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Compatibility wrapper.

        Some callers use process_subtitle_operation()
        directly. Keep it as an alias to the main processing
        entry point.
        """
        return self.create_subtitles(settings)

    # ==========================================================
    # CONVENIENCE JOIN API
    # ==========================================================

    def join_subtitles(
        self,
        subtitle_files: Optional[List[str]] = None,
        output_path: str = "",
        first_path: Optional[str] = None,
        second_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Sequentially join one to four subtitle files.

        Preferred API:

            subtitle_files=[...]

        Backwards-compatible API:

            first_path=...
            second_path=...
        """

        files = self._build_compatibility_file_list(
            subtitle_files=subtitle_files,
            first_path=first_path,
            second_path=second_path,
        )

        return self.create_subtitles(
            {
                "operation": "join_parts",
                "subtitle_files": files,
                "output": output_path,
            }
        )

    # ==========================================================
    # CONVENIENCE MERGE API
    # ==========================================================

    def merge_subtitles(
        self,
        subtitle_files: Optional[List[Any]] = None,
        output: str = "",
        remove_duplicates: bool = True,
        first_file: Optional[str] = None,
        second_file: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Merge one to four subtitle tracks.

        MERGE uses a plain list of subtitle file paths.

        Example:

            [
                "/absolute/file1.srt",
                "/absolute/file2.srt",
            ]

        MERGE does not use:
            - name
            - offset
            - gap
        """

        self.check_cancelled()

        if subtitle_files is not None:

            if isinstance(
                subtitle_files,
                (str, os.PathLike),
            ):
                files: List[Any] = [subtitle_files]
            else:
                files = list(subtitle_files)

        else:

            files = []

            if first_file:
                files.append(first_file)

            if second_file:
                files.append(second_file)

        files = self._normalize_subtitle_files(
            {
                "subtitle_files": files,
            },
            operation="merge_tracks",
        )

        if not output:
            raise ValueError(
                "Output filepath cannot be empty."
            )

        settings: Dict[str, Any] = {
            "operation": "merge_tracks",
            "subtitle_files": files,
            "output": output,
            "remove_duplicates": bool(
                remove_duplicates
            ),
            "subtitle_format": self._detect_format(
                output
            ),
        }

        return self.process_subtitle_operation(
            settings
        )

    # ==========================================================
    # CANCEL
    # ==========================================================

    def cancel(self) -> None:
        """Request cancellation."""

        if self.cancelled:
            return

        self.cancelled = True

        self._progress(
            "Cancelling subtitle operation",
            "",
            0,
        )

        if self.cancelled_callback:
            try:
                self.cancelled_callback()
            except Exception as exc:
                self._error(exc)

    def reset_cancel(self) -> None:
        """Reset cancellation state before a new operation."""
        self.cancelled = False

    def check_cancelled(self) -> None:
        """Public cancellation check."""
        self._check_cancelled()

    # ==========================================================
    # MAIN
    # ==========================================================

    def create_subtitles(
        self,
        settings: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Main subtitle-processing entry point."""

        self.reset_cancel()

        settings = self._normalize_settings(settings)
        self._validate_settings(settings)

        operation = settings["operation"]

        self._progress_stage = "preparing"

        self._progress(
            "Preparing subtitle processing",
            self._display_name(settings),
            0,
        )

        if self.cancelled:
            return self._cancelled_result(settings)

        try:

            if operation == "join_parts":
                result = self._join_parts(settings)

            elif operation == "merge_tracks":
                result = self._merge_tracks(settings)

            elif operation == "offset":
                result = self._apply_offset(settings)

            elif operation == "two_point":
                result = self._two_point_sync(settings)

            elif operation == "multi_point":
                result = self._multi_point_sync(settings)

            elif operation == "start_end":
                result = self._start_end_sync(settings)

            elif operation == "fit":
                result = self._fit_to_video(settings)

            elif operation == "clamp":
                result = self._clamp_to_video(settings)

            elif operation == "validate":
                result = self._validate_file(settings)

            else:
                raise ValueError(
                    f"Unsupported subtitle operation: {operation}"
                )

            if self.cancelled:
                return self._cancelled_result(settings)

            self._progress_stage = "complete"

            self._progress(
                "Subtitle processing complete",
                self._display_name(settings),
                100,
            )

            self._finished(result)

            return result

        except KeyboardInterrupt:

            self.cancel()

            return self._cancelled_result(settings)

        except Exception as exc:

            if self.cancelled:
                return self._cancelled_result(settings)

            self._error(exc)
            raise

    # ==========================================================
    # JOIN PARTS
    # ==========================================================

    def _join_parts(
        self,
        settings: Dict[str, Any],
    ) -> Dict[str, Any]:

        self._progress_stage = "joining"

        files = settings["subtitle_files"]

        self._progress(
            "Joining subtitle files",
            self._display_name(settings),
            30,
        )

        self._check_cancelled()

        result = SubtitleProcessor.join_parts(
            subtitle_files=files,
            output_path=settings["output"],
        )

        self._check_cancelled()

        self._progress(
            "Joined subtitle files",
            self._display_name(settings),
            90,
        )

        return self._result(
            settings=settings,
            subtitle=result,
            operation="join_parts",
        )

    # ==========================================================
    # MERGE TRACKS
    # ==========================================================

    def _merge_tracks(
        self,
        settings: Dict[str, Any],
    ) -> Dict[str, Any]:

        self._progress_stage = "merging"

        files = settings["subtitle_files"]

        self._progress(
            "Merging subtitle tracks",
            self._display_name(settings),
            30,
        )

        self._check_cancelled()

        result = SubtitleProcessor.merge_tracks(
            subtitle_files=files,
            output_path=settings["output"],
            remove_duplicates=settings.get(
                "remove_duplicates",
                True,
            ),
        )

        self._check_cancelled()

        self._progress(
            "Merged subtitle tracks",
            self._display_name(settings),
            90,
        )

        return self._result(
            settings=settings,
            subtitle=result,
            operation="merge_tracks",
        )

    # ==========================================================
    # FIXED OFFSET
    # ==========================================================

    def _apply_offset(
        self,
        settings: Dict[str, Any],
    ) -> Dict[str, Any]:

        self._progress_stage = "synchronizing"

        self._progress(
            "Applying subtitle timing offset",
            self._display_name(settings),
            40,
        )

        self._check_cancelled()

        result = SubtitleProcessor.sync_offset(
            settings["subtitle_file"],
            settings["output"],
            settings["offset"],
            video_duration=settings.get(
                "video_duration"
            ),
        )

        self._check_cancelled()

        self._progress(
            "Subtitle offset applied",
            self._display_name(settings),
            90,
        )

        return self._result(
            settings=settings,
            subtitle=result,
            operation="offset",
        )

    # ==========================================================
    # TWO POINT SYNC
    # ==========================================================

    def _two_point_sync(
        self,
        settings: Dict[str, Any],
    ) -> Dict[str, Any]:

        self._progress_stage = "synchronizing"

        self._progress(
            "Calculating subtitle drift",
            self._display_name(settings),
            30,
        )

        self._check_cancelled()

        result = SubtitleProcessor.sync_two_points(
            settings["subtitle_file"],
            settings["output"],
            settings["subtitle_point_1"],
            settings["video_point_1"],
            settings["subtitle_point_2"],
            settings["video_point_2"],
            video_duration=settings.get(
                "video_duration"
            ),
        )

        self._check_cancelled()

        self._progress(
            "Progressive subtitle timing correction applied",
            self._display_name(settings),
            90,
        )

        return self._result(
            settings=settings,
            subtitle=result,
            operation="two_point",
        )

    # ==========================================================
    # MULTI POINT SYNC
    # ==========================================================

    def _multi_point_sync(
        self,
        settings: Dict[str, Any],
    ) -> Dict[str, Any]:

        self._progress_stage = "synchronizing"

        self._progress(
            "Preparing synchronization points",
            self._display_name(settings),
            20,
        )

        self._check_cancelled()

        points = self._parse_sync_points(
            settings["sync_points"]
        )

        if len(points) < 2:
            raise ValueError(
                "At least two synchronization points are required."
            )

        self._progress(
            "Applying multi-point timing correction",
            self._display_name(settings),
            50,
        )

        self._check_cancelled()

        result = SubtitleProcessor.sync_points(
            settings["subtitle_file"],
            settings["output"],
            points,
            video_duration=settings.get(
                "video_duration"
            ),
        )

        self._check_cancelled()

        self._progress(
            "Multi-point synchronization complete",
            self._display_name(settings),
            90,
        )

        return self._result(
            settings=settings,
            subtitle=result,
            operation="multi_point",
        )

    # ==========================================================
    # START + END
    # ==========================================================

    def _start_end_sync(
        self,
        settings: Dict[str, Any],
    ) -> Dict[str, Any]:

        self._progress_stage = "synchronizing"

        video_duration = settings["video_duration"]

        self._progress(
            "Synchronizing subtitle start and end",
            self._display_name(settings),
            50,
        )

        self._check_cancelled()

        result = SubtitleProcessor.sync_start_end(
            settings["subtitle_file"],
            settings["output"],
            video_duration,
        )

        self._check_cancelled()

        self._progress(
            "Start and end synchronization complete",
            self._display_name(settings),
            90,
        )

        return self._result(
            settings=settings,
            subtitle=result,
            operation="start_end",
        )

    # ==========================================================
    # FIT
    # ==========================================================

    def _fit_to_video(
        self,
        settings: Dict[str, Any],
    ) -> Dict[str, Any]:

        self._progress_stage = "synchronizing"

        video_duration = settings["video_duration"]

        self._progress(
            "Loading subtitles",
            self._display_name(settings),
            10,
        )

        self._check_cancelled()

        subtitles = SubtitleFile.load(
            settings["subtitle_file"]
        )

        self._check_cancelled()

        self._progress(
            "Fitting subtitles to video duration",
            self._display_name(settings),
            50,
        )

        result = SubtitleSynchronizer.fit_to_video(
            subtitles,
            video_duration,
        )

        self._check_cancelled()

        result = self._finalize_timing(
            result,
            settings,
        )

        self._check_cancelled()

        self._progress(
            "Saving fitted subtitles",
            self._display_name(settings),
            90,
        )

        result.save(settings["output"])

        self._check_cancelled()

        return self._result(
            settings=settings,
            subtitle=result,
            operation="fit",
        )

    # ==========================================================
    # CLAMP
    # ==========================================================

    def _clamp_to_video(
        self,
        settings: Dict[str, Any],
    ) -> Dict[str, Any]:

        self._progress_stage = "processing"

        video_duration = settings["video_duration"]

        self._progress(
            "Loading subtitles",
            self._display_name(settings),
            10,
        )

        self._check_cancelled()

        subtitles = SubtitleFile.load(
            settings["subtitle_file"]
        )

        self._check_cancelled()

        self._progress(
            "Clamping subtitles to video duration",
            self._display_name(settings),
            60,
        )

        result = SubtitleSynchronizer.clamp(
            subtitles,
            video_duration,
        )

        self._check_cancelled()

        self._progress(
            "Saving clamped subtitles",
            self._display_name(settings),
            90,
        )

        result.save(settings["output"])

        self._check_cancelled()

        return self._result(
            settings=settings,
            subtitle=result,
            operation="clamp",
        )

    # ==========================================================
    # VALIDATION
    # ==========================================================

    def _validate_file(
        self,
        settings: Dict[str, Any],
    ) -> Dict[str, Any]:

        self._progress_stage = "validating"

        self._progress(
            "Validating subtitle file",
            self._display_name(settings),
            50,
        )

        self._check_cancelled()

        result = SubtitleProcessor.validate(
            settings["subtitle_file"]
        )

        self._check_cancelled()

        self._progress(
            "Subtitle validation complete",
            self._display_name(settings),
            100,
        )

        if isinstance(result, dict):
            output = dict(result)
        else:
            output = {
                "errors": result
            }

        errors = output.get("errors", [])

        return {
            **output,
            "operation": "validate",
            "success": not bool(errors),
            "completed": True,
            "cancelled": False,
        }

    # ==========================================================
    # FINAL TIMING
    # ==========================================================

    def _finalize_timing(
        self,
        subtitles: SubtitleFile,
        settings: Dict[str, Any],
    ) -> SubtitleFile:

        result = subtitles

        if settings["remove_duplicates"]:
            result = result.remove_duplicates()

        self._check_cancelled()

        video_duration = settings.get(
            "video_duration"
        )

        if (
            settings["clamp_to_video"]
            and video_duration is not None
        ):
            result = SubtitleSynchronizer.clamp(
                result,
                video_duration,
            )

        self._check_cancelled()

        errors = result.validate()

        if errors:
            raise ValueError(
                "Subtitle timing validation failed:\n"
                + "\n".join(map(str, errors))
            )

        return result

    # ==========================================================
    # SYNC POINT PARSER
    # ==========================================================

    @staticmethod
    def _parse_sync_points(
        points: Any,
    ) -> List[SyncPoint]:

        if not isinstance(points, (list, tuple)):
            raise ValueError(
                "sync_points must be a list."
            )

        result: List[SyncPoint] = []

        for point in points:

            if isinstance(point, SyncPoint):
                result.append(point)
                continue

            if isinstance(point, dict):

                try:
                    subtitle_time = float(
                        point["subtitle_time"]
                    )
                    video_time = float(
                        point["video_time"]
                    )

                except (
                    KeyError,
                    TypeError,
                    ValueError,
                ) as exc:

                    raise ValueError(
                        "Invalid synchronization point. "
                        "Expected subtitle_time and video_time."
                    ) from exc

                if subtitle_time < 0 or video_time < 0:
                    raise ValueError(
                        "Synchronization times cannot be negative."
                    )

                result.append(
                    SyncPoint(
                        subtitle_time=subtitle_time,
                        video_time=video_time,
                    )
                )

                continue

            if (
                isinstance(point, (list, tuple))
                and len(point) >= 2
            ):

                try:
                    subtitle_time = float(point[0])
                    video_time = float(point[1])

                except (
                    TypeError,
                    ValueError,
                ) as exc:

                    raise ValueError(
                        f"Invalid synchronization point: "
                        f"{point!r}"
                    ) from exc

                if subtitle_time < 0 or video_time < 0:
                    raise ValueError(
                        "Synchronization times cannot be negative."
                    )

                result.append(
                    SyncPoint(
                        subtitle_time=subtitle_time,
                        video_time=video_time,
                    )
                )

                continue

            raise ValueError(
                f"Invalid synchronization point: {point!r}"
            )

        return result

    # ==========================================================
    # SETTINGS NORMALIZATION
    # ==========================================================

    def _normalize_settings(
        self,
        settings: Dict[str, Any],
    ) -> Dict[str, Any]:

        if settings is None:
            settings = {}

        if not isinstance(settings, dict):
            raise TypeError(
                "Subtitle settings must be a dictionary."
            )

        settings = dict(settings)

        operation = str(
            settings.get("operation", "offset")
            or "offset"
        ).strip().lower()

        aliases = {
            "join": "join_parts",
            "join_two": "join_parts",
            "join_files": "join_parts",
            "merge": "merge_tracks",
            "merge_files": "merge_tracks",
            "sync": "offset",
            "fixed": "offset",
            "fixed_offset": "offset",
            "drift": "two_point",
            "two_points": "two_point",
            "multi_points": "multi_point",
            "points": "multi_point",
            "start_end_sync": "start_end",
        }

        operation = aliases.get(
            operation,
            operation,
        )

        settings["operation"] = operation

        # ------------------------------------------------------
        # OUTPUT
        # ------------------------------------------------------

        output = str(
            settings.get("output", "")
            or ""
        ).strip()

        settings["output"] = (
            os.path.abspath(
                os.path.expanduser(output)
            )
            if output
            else ""
        )

        # ------------------------------------------------------
        # SINGLE SUBTITLE FILE
        # ------------------------------------------------------

        subtitle_file = (
            settings.get("subtitle_file")
            or settings.get("subtitle_path")
            or settings.get("subtitle_filepath")
            or ""
        )

        subtitle_file = str(
            subtitle_file
            or ""
        ).strip()

        settings["subtitle_file"] = (
            os.path.abspath(
                os.path.expanduser(subtitle_file)
            )
            if subtitle_file
            else ""
        )

        # ------------------------------------------------------
        # FILE LIST
        #
        # IMPORTANT FIX:
        # operation must be passed here.
        #
        # The old code always used the default "join_parts",
        # which caused MERGE to return JOIN dictionaries.
        # ------------------------------------------------------

        settings["subtitle_files"] = (
            self._normalize_subtitle_files(
                settings,
                operation=operation,
            )
        )

        # ------------------------------------------------------
        # VIDEO DURATION
        # ------------------------------------------------------

        duration = settings.get(
            "video_duration"
        )

        if duration in (None, ""):

            settings["video_duration"] = None

        else:

            duration = self._to_float(
                duration,
                "video_duration",
            )

            if duration <= 0:
                raise ValueError(
                    "video_duration must be greater than zero."
                )

            settings["video_duration"] = duration

        # ------------------------------------------------------
        # OFFSET
        # ------------------------------------------------------

        offset = settings.get(
            "offset",
            0.0,
        )

        settings["offset"] = self._to_float(
            offset,
            "offset",
            default=0.0,
        )

        # ------------------------------------------------------
        # TWO POINT VALUES
        # ------------------------------------------------------

        for key in (
            "subtitle_point_1",
            "video_point_1",
            "subtitle_point_2",
            "video_point_2",
        ):

            value = settings.get(key)

            if value in (None, ""):

                if operation == "two_point":
                    raise ValueError(
                        f"{key} is required and must be numeric."
                    )

                settings[key] = None
                continue

            settings[key] = self._to_float(
                value,
                key,
            )

            if settings[key] < 0:
                raise ValueError(
                    f"{key} cannot be negative."
                )

        # ------------------------------------------------------
        # SYNC POINTS
        # ------------------------------------------------------

        settings["sync_points"] = settings.get(
            "sync_points",
            [],
        )

        # ------------------------------------------------------
        # OPTIONS
        # ------------------------------------------------------

        settings["remove_duplicates"] = (
            self._to_bool(
                settings.get(
                    "remove_duplicates",
                    True,
                )
            )
        )

        settings["clamp_to_video"] = (
            self._to_bool(
                settings.get(
                    "clamp_to_video",
                    True,
                )
            )
        )

        # ------------------------------------------------------
        # FORMAT
        # ------------------------------------------------------

        subtitle_format = str(
            settings.get(
                "subtitle_format",
                "",
            )
            or ""
        ).strip().lower().lstrip(".")

        if not subtitle_format and output:
            subtitle_format = self._detect_format(
                output
            )

        if not subtitle_format:
            subtitle_format = "srt"

        settings["subtitle_format"] = subtitle_format

        # Keep service-level compatibility.
        self.subtitle_format = subtitle_format

        return settings

    # ==========================================================
    # FILE LIST NORMALIZATION
    # ==========================================================

    @classmethod
    def _normalize_subtitle_files(
        cls,
        settings: Dict[str, Any],
        operation: str = "join_parts",
    ) -> List[Any]:
        """
        Normalize subtitle files.

        JOIN returns dictionaries:

            [
                {
                    "name": "/absolute/part1.srt",
                    "offset": 0.0,
                },
                {
                    "name": "/absolute/part2.srt",
                    "offset": 0.0,
                    "gap": 0.0,
                },
            ]

        MERGE returns plain paths:

            [
                "/absolute/file1.srt",
                "/absolute/file2.srt",
            ]
        """

        files_value = settings.get("subtitle_files")

        if files_value is None:
            files_value = settings.get("files")

        raw_files: List[Any] = []

        # ------------------------------------------------------
        # NEW API
        # ------------------------------------------------------

        if files_value is not None:

            if isinstance(
                files_value,
                (str, os.PathLike),
            ):
                raw_files.append(files_value)

            elif isinstance(
                files_value,
                (list, tuple),
            ):
                raw_files.extend(files_value)

            else:
                raise ValueError(
                    "subtitle_files must be a list "
                    "of subtitle file paths or dictionaries."
                )

        # ------------------------------------------------------
        # OLD API
        # ------------------------------------------------------

        else:

            first = settings.get("first_file")
            second = settings.get("second_file")

            if first:
                raw_files.append(first)

            if second:
                raw_files.append(second)

        normalized: List[Any] = []

        for index, item in enumerate(raw_files):

            if not item:
                continue

            # ==================================================
            # MERGE
            # ==================================================

            if operation == "merge_tracks":

                if isinstance(
                    item,
                    dict,
                ):

                    name = (
                        item.get("name")
                        or item.get("file")
                        or item.get("path")
                        or item.get("filepath")
                        or item.get("subtitle_file")
                    )

                    if not name:
                        raise ValueError(
                            f"Subtitle file #{index + 1} "
                            "is missing a file path."
                        )

                elif isinstance(
                    item,
                    (str, os.PathLike),
                ):

                    name = item

                else:

                    raise ValueError(
                        f"Subtitle file #{index + 1} must be "
                        "a string path or dictionary."
                    )

                name = str(name).strip()

                if not name:
                    continue

                normalized.append(
                    os.path.abspath(
                        os.path.expanduser(name)
                    )
                )

                continue

            # ==================================================
            # JOIN
            # ==================================================

            if operation == "join_parts":

                # ----------------------------------------------
                # STRING PATH
                # ----------------------------------------------

                if isinstance(
                    item,
                    (str, os.PathLike),
                ):

                    name = str(item).strip()

                    if not name:
                        continue

                    config: Dict[str, Any] = {
                        "name": os.path.abspath(
                            os.path.expanduser(name)
                        ),
                        "offset": 0.0,
                    }

                    if index > 0:
                        config["gap"] = 0.0

                    normalized.append(config)

                    continue

                # ----------------------------------------------
                # DICTIONARY
                # ----------------------------------------------

                if isinstance(
                    item,
                    dict,
                ):

                    name = (
                        item.get("name")
                        or item.get("file")
                        or item.get("path")
                        or item.get("filepath")
                        or item.get("subtitle_file")
                    )

                    if not name:
                        raise ValueError(
                            f"Subtitle file #{index + 1} "
                            "is missing a file path."
                        )

                    name = str(name).strip()

                    if not name:
                        continue

                    raw_offset = item.get(
                        "offset",
                        0.0,
                    )

                    try:
                        offset = float(raw_offset)
                    except (
                        TypeError,
                        ValueError,
                    ) as exc:

                        raise ValueError(
                            f"Invalid offset for subtitle "
                            f"file #{index + 1}: "
                            f"{raw_offset!r}"
                        ) from exc

                    config = {
                        "name": os.path.abspath(
                            os.path.expanduser(name)
                        ),
                        "offset": offset,
                    }

                    if index > 0:

                        raw_gap = item.get(
                            "gap",
                            0.0,
                        )

                        try:
                            gap = float(raw_gap)
                        except (
                            TypeError,
                            ValueError,
                        ) as exc:

                            raise ValueError(
                                f"Invalid gap for subtitle "
                                f"file #{index + 1}: "
                                f"{raw_gap!r}"
                            ) from exc

                        if gap < 0:
                            raise ValueError(
                                f"Gap for subtitle file "
                                f"#{index + 1} cannot be negative."
                            )

                        config["gap"] = gap

                    normalized.append(config)

                    continue

                raise ValueError(
                    f"Subtitle file #{index + 1} must be "
                    "a string path or dictionary."
                )

        # ------------------------------------------------------
        # REMOVE DUPLICATES
        # ------------------------------------------------------

        if operation == "merge_tracks":

            cleaned: List[str] = []
            seen: set[str] = set()

            for filepath in normalized:

                filepath = os.path.normcase(
                    os.path.abspath(filepath)
                )

                if filepath in seen:
                    continue

                seen.add(filepath)
                cleaned.append(filepath)

        else:

            cleaned = []
            seen = set()

            for config in normalized:

                name = os.path.normcase(
                    os.path.abspath(
                        config["name"]
                    )
                )

                if name in seen:
                    continue

                seen.add(name)
                cleaned.append(config)

        # ------------------------------------------------------
        # VALIDATE COUNT
        # ------------------------------------------------------

        if not cleaned:
            raise ValueError(
                "Select at least one subtitle file."
            )

        if len(cleaned) > cls.MAX_SUBTITLE_FILES:
            raise ValueError(
                "A maximum of four subtitle files can be used."
            )

        # ------------------------------------------------------
        # PART 1 MUST NOT HAVE GAP
        # ------------------------------------------------------

        if operation == "join_parts":
            cleaned[0].pop("gap", None)

        return cleaned

    # ==========================================================
    # COMPATIBILITY FILE LIST
    # ==========================================================

    @classmethod
    def _build_compatibility_file_list(
        cls,
        subtitle_files: Optional[List[str]] = None,
        first_path: Optional[str] = None,
        second_path: Optional[str] = None,
    ) -> List[str]:

        files: List[Any] = []

        if subtitle_files is not None:

            if isinstance(
                subtitle_files,
                (str, os.PathLike),
            ):

                files = [subtitle_files]

            else:

                try:
                    files = list(subtitle_files)

                except TypeError as exc:

                    raise ValueError(
                        "subtitle_files must be a list "
                        "of subtitle file paths."
                    ) from exc

        else:

            if first_path:
                files.append(first_path)

            if second_path:
                files.append(second_path)

        cleaned: List[str] = []

        for filepath in files:

            if not filepath:
                continue

            filepath = str(
                filepath
            ).strip()

            if not filepath:
                continue

            filepath = os.path.abspath(
                os.path.expanduser(filepath)
            )

            if filepath not in cleaned:
                cleaned.append(filepath)

        if not cleaned:
            raise ValueError(
                "At least one subtitle file is required."
            )

        if len(cleaned) > cls.MAX_SUBTITLE_FILES:
            raise ValueError(
                "A maximum of four subtitle files can be used."
            )

        return cleaned

    # ==========================================================
    # VALIDATION
    # ==========================================================

    def _validate_settings(
        self,
        settings: Dict[str, Any],
    ) -> None:

        operation = settings["operation"]

        # ------------------------------------------------------
        # OPERATION
        # ------------------------------------------------------

        if operation not in self.OPERATIONS:
            raise ValueError(
                f"Unsupported subtitle operation: {operation}. "
                f"Valid operations: "
                f"{', '.join(sorted(self.OPERATIONS))}"
            )

        # ------------------------------------------------------
        # FORMAT
        # ------------------------------------------------------

        subtitle_format = settings.get(
            "subtitle_format"
        )

        if subtitle_format not in self.FORMATS:
            raise ValueError(
                f"Unsupported subtitle format: "
                f"{subtitle_format}. "
                f"Valid formats: "
                f"{', '.join(sorted(self.FORMATS))}"
            )

        # ------------------------------------------------------
        # OUTPUT
        # ------------------------------------------------------

        if operation != "validate":

            if not settings["output"]:
                raise ValueError(
                    "Output subtitle file is required."
                )

            output_directory = os.path.dirname(
                settings["output"]
            )

            if output_directory:

                try:
                    os.makedirs(
                        output_directory,
                        exist_ok=True,
                    )

                except OSError as exc:

                    raise RuntimeError(
                        "Cannot create subtitle output directory."
                    ) from exc

        # ------------------------------------------------------
        # NORMAL OPERATIONS
        # ------------------------------------------------------

        if operation in {
            "offset",
            "two_point",
            "multi_point",
            "start_end",
            "fit",
            "clamp",
            "validate",
        }:

            self._require_file(
                settings["subtitle_file"],
                "subtitle_file",
            )

        # ------------------------------------------------------
        # JOIN / MERGE
        # ------------------------------------------------------

        if operation in {
            "join_parts",
            "merge_tracks",
        }:

            files = settings.get(
                "subtitle_files",
                [],
            )

            if not files:
                raise ValueError(
                    "At least one subtitle file is required."
                )

            if len(files) > self.MAX_SUBTITLE_FILES:
                raise ValueError(
                    "A maximum of four subtitle files can be used."
                )

            for index, item in enumerate(
                files,
                start=1,
            ):

                # FIX:
                # JOIN uses dictionaries, MERGE uses strings.
                filepath = self._extract_file_path(
                    item
                )

                self._require_file(
                    filepath,
                    f"subtitle_file_{index}",
                )

        # ------------------------------------------------------
        # VIDEO DURATION
        # ------------------------------------------------------

        if operation in {
            "start_end",
            "fit",
            "clamp",
        }:

            if settings.get("video_duration") is None:
                raise ValueError(
                    f"video_duration is required for {operation}."
                )

        # ------------------------------------------------------
        # TWO POINT
        # ------------------------------------------------------

        if operation == "two_point":

            required = (
                "subtitle_point_1",
                "video_point_1",
                "subtitle_point_2",
                "video_point_2",
            )

            for key in required:

                if settings.get(key) is None:
                    raise ValueError(
                        f"{key} is required."
                    )

            if (
                settings["subtitle_point_2"]
                <= settings["subtitle_point_1"]
            ):
                raise ValueError(
                    "subtitle_point_2 must be greater than "
                    "subtitle_point_1."
                )

            if (
                settings["video_point_2"]
                <= settings["video_point_1"]
            ):
                raise ValueError(
                    "video_point_2 must be greater than "
                    "video_point_1."
                )

        # ------------------------------------------------------
        # MULTI POINT
        # ------------------------------------------------------

        if operation == "multi_point":

            points = self._parse_sync_points(
                settings["sync_points"]
            )

            if len(points) < 2:
                raise ValueError(
                    "At least two synchronization points "
                    "are required."
                )

            previous_subtitle = None
            previous_video = None

            for point in points:

                if (
                    previous_subtitle is not None
                    and point.subtitle_time
                    <= previous_subtitle
                ):

                    raise ValueError(
                        "Synchronization subtitle times "
                        "must be strictly increasing."
                    )

                if (
                    previous_video is not None
                    and point.video_time
                    <= previous_video
                ):

                    raise ValueError(
                        "Synchronization video times "
                        "must be strictly increasing."
                    )

                previous_subtitle = (
                    point.subtitle_time
                )

                previous_video = (
                    point.video_time
                )

    # ==========================================================
    # FILE VALIDATION
    # ==========================================================

    @staticmethod
    def _extract_file_path(
        item: Any,
    ) -> str:
        """
        Extract an actual filesystem path from either:

            "/path/file.srt"

        or:

            {
                "name": "/path/file.srt",
                "offset": 0,
                "gap": 0,
            }
        """

        if isinstance(
            item,
            (str, os.PathLike),
        ):
            return str(item)

        if isinstance(item, dict):

            filepath = (
                item.get("name")
                or item.get("file")
                or item.get("path")
                or item.get("filepath")
                or item.get("subtitle_file")
            )

            if filepath:
                return str(filepath)

        raise ValueError(
            f"Invalid subtitle file configuration: {item!r}"
        )

    @staticmethod
    def _require_file(
        filepath: str,
        name: str,
    ) -> None:

        if not filepath:
            raise ValueError(
                f"{name} is required."
            )

        if not os.path.isfile(filepath):
            raise FileNotFoundError(
                f"{name} was not found: {filepath}"
            )

    # ==========================================================
    # FORMAT
    # ==========================================================

    @staticmethod
    def _detect_format(
        filepath: str,
    ) -> str:

        extension = os.path.splitext(
            str(filepath)
        )[1].lower().lstrip(".")

        if extension in {
            "srt",
            "vtt",
        }:
            return extension

        return "srt"

    # ==========================================================
    # NUMERIC HELPERS
    # ==========================================================

    @staticmethod
    def _to_float(
        value: Any,
        name: str,
        default: Optional[float] = None,
    ) -> float:

        if value in (None, ""):

            if default is not None:
                return float(default)

            raise ValueError(
                f"{name} must be numeric."
            )

        try:
            return float(value)

        except (
            TypeError,
            ValueError,
        ) as exc:

            raise ValueError(
                f"{name} must be numeric."
            ) from exc

    @staticmethod
    def _to_bool(
        value: Any,
    ) -> bool:
        """
        Safely normalize booleans.

        This fixes:

            bool("false") == True
        """

        if isinstance(value, bool):
            return value

        if value is None:
            return False

        if isinstance(
            value,
            (int, float),
        ):
            return bool(value)

        value = str(
            value
        ).strip().lower()

        if value in {
            "true",
            "1",
            "yes",
            "y",
            "on",
            "enabled",
        }:
            return True

        if value in {
            "false",
            "0",
            "no",
            "n",
            "off",
            "disabled",
            "",
            "none",
            "null",
        }:
            return False

        return bool(value)

    # ==========================================================
    # CANCELLATION CHECK
    # ==========================================================

    def _check_cancelled(self) -> None:

        if self.cancelled:
            raise KeyboardInterrupt(
                "Subtitle processing cancelled."
            )

    # ==========================================================
    # RESULT
    # ==========================================================

    @staticmethod
    def _result(
        settings: Dict[str, Any],
        subtitle: SubtitleFile,
        operation: str,
    ) -> Dict[str, Any]:

        output = settings.get("output")

        errors = subtitle.validate()

        filepath = (
            os.path.abspath(output)
            if output
            else None
        )

        return {
            "operation": operation,
            "success": not bool(errors),
            "completed": True,
            "cancelled": False,
            "filepath": filepath,
            "path": filepath,
            "subtitle_filepath": filepath,
            "subtitle_count": len(
                subtitle.entries
            ),
            "start_time": subtitle.start_time,
            "end_time": subtitle.end_time,
            "duration": subtitle.duration,
            "errors": errors,
        }

    # ==========================================================
    # CANCELLED RESULT
    # ==========================================================

    @staticmethod
    def _cancelled_result(
        settings: Dict[str, Any],
    ) -> Dict[str, Any]:

        return {
            "operation": settings.get(
                "operation"
            ),
            "success": False,
            "completed": False,
            "cancelled": True,
            "filepath": None,
            "path": None,
            "subtitle_filepath": None,
            "subtitle_count": 0,
            "start_time": 0.0,
            "end_time": 0.0,
            "duration": 0.0,
            "errors": [],
        }

    # ==========================================================
    # DISPLAY NAME
    # ==========================================================

    @staticmethod
    def _display_name(
        settings: Dict[str, Any],
    ) -> str:

        for key in (
            "output",
            "subtitle_file",
        ):

            value = settings.get(key)

            if value:
                return os.path.basename(
                    str(value)
                )

        files = settings.get(
            "subtitle_files"
        )

        if files:

            first = files[0]

            if isinstance(first, dict):
                first = (
                    first.get("name")
                    or first.get("file")
                    or first.get("path")
                    or ""
                )

            return os.path.basename(
                str(first)
            )

        return "Subtitle"

    # ==========================================================
    # PROGRESS
    # ==========================================================

    def _progress(
        self,
        info: str,
        filename: str,
        percentage: Any = 0,
    ) -> None:

        if not self.progress_callback:
            return

        try:
            percentage = float(
                percentage
            )

        except (
            TypeError,
            ValueError,
        ):
            percentage = 0.0

        percentage = max(
            0.0,
            min(
                100.0,
                percentage,
            ),
        )

        if percentage.is_integer():

            callback_percentage: Any = int(
                percentage
            )

        else:

            callback_percentage = round(
                percentage,
                1,
            )

        try:

            self.progress_callback(
                info,
                filename,
                callback_percentage,
                "--",
                "--",
                "--:--",
            )

        except TypeError:

            try:

                self.progress_callback(
                    info,
                    filename,
                    callback_percentage,
                )

            except Exception:
                pass

        except Exception:
            pass

    # ==========================================================
    # FINISHED
    # ==========================================================

    def _finished(
        self,
        result: Dict[str, Any],
    ) -> None:

        if not self.finished_callback:
            return

        try:
            self.finished_callback(
                result
            )

        except Exception as exc:
            self._error(exc)

    # ==========================================================
    # ERROR
    # ==========================================================

    def _error(
        self,
        error: Any,
    ) -> None:

        if self.error_callback:

            try:
                self.error_callback(
                    error
                )
                return

            except Exception:
                pass

        print(error)

