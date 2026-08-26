from __future__ import annotations

import os

from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Sequence,
)

from core.subtitle_sync import (
    SubtitleFile,
    SubtitleJoiner,
    SubtitleSynchronizer,
    SubtitleProcessor,
    SyncPoint,
)


class SubtitleSyncService:
    """
    Subtitle orchestration service.

    This service sits above subtitle_processor.py and uses the
    existing subtitle classes without modifying them.

    Responsibilities:

        - settings normalization
        - validation
        - progress reporting
        - cancellation
        - callback handling
        - orchestration
        - result formatting

    Core subtitle operations remain delegated to:

        SubtitleFile
        SubtitleJoiner
        SubtitleSynchronizer
        SubtitleProcessor
        SyncPoint
    """

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
        progress_callback: Optional[
            Callable[..., None]
        ] = None,
        error_callback: Optional[
            Callable[[Any], None]
        ] = None,
        finished_callback: Optional[
            Callable[..., None]
        ] = None,
        cancelled_callback: Optional[
            Callable[..., None]
        ] = None,
    ) -> None:

        self.progress_callback = progress_callback
        self.error_callback = error_callback
        self.finished_callback = finished_callback
        self.cancelled_callback = cancelled_callback

        self.cancelled = False
        self._progress_stage = "idle"

    # ==========================================================
    # PUBLIC
    # ==========================================================

    def process(
        self,
        settings: Dict[str, Any],
    ) -> Dict[str, Any]:

        return self.create_subtitles(settings)

    def start(
        self,
        settings: Dict[str, Any],
    ) -> Dict[str, Any]:

        return self.create_subtitles(settings)

    # ==========================================================
    # CANCEL
    # ==========================================================

    def cancel(self) -> None:

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
        self.cancelled = False

    # ==========================================================
    # MAIN
    # ==========================================================

    def create_subtitles(
        self,
        settings: Dict[str, Any],
    ) -> Dict[str, Any]:

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

        first_path = settings["first_file"]
        second_path = settings["second_file"]
        output_path = settings["output"]

        self._progress(
            "Joining subtitle files",
            self._display_name(settings),
            30,
        )

        # Use SubtitleProcessor as the high-level file operation.
        result = SubtitleProcessor.join_parts(
            first_path,
            second_path,
            output_path,
            gap=settings["gap"],
            second_offset=settings.get("second_offset"),
        )

        if self.cancelled:
            return self._cancelled_result(settings)

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

        self._progress(
            "Merging subtitle tracks",
            self._display_name(settings),
            30,
        )

        # SubtitleProcessor orchestrates loading, merging,
        # and saving through SubtitleJoiner.
        result = SubtitleProcessor.merge_tracks(
            settings["first_file"],
            settings["second_file"],
            settings["output"],
        )

        if self.cancelled:
            return self._cancelled_result(settings)

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

        # Use SubtitleProcessor for the complete file operation.
        result = SubtitleProcessor.sync_offset(
            settings["subtitle_file"],
            settings["output"],
            settings["offset"],
            video_duration=settings.get("video_duration"),
        )

        if self.cancelled:
            return self._cancelled_result(settings)

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

        # SubtitleProcessor delegates the actual mathematics to
        # SubtitleSynchronizer.
        result = SubtitleProcessor.sync_two_points(
            settings["subtitle_file"],
            settings["output"],
            settings["subtitle_point_1"],
            settings["video_point_1"],
            settings["subtitle_point_2"],
            settings["video_point_2"],
            video_duration=settings.get("video_duration"),
        )

        if self.cancelled:
            return self._cancelled_result(settings)

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

        points = self._parse_sync_points(
            settings["sync_points"]
        )

        if len(points) < 2:
            raise ValueError(
                "At least two synchronization points "
                "are required."
            )

        self._progress(
            "Applying multi-point timing correction",
            self._display_name(settings),
            50,
        )

        result = SubtitleProcessor.sync_points(
            settings["subtitle_file"],
            settings["output"],
            points,
            video_duration=settings.get("video_duration"),
        )

        if self.cancelled:
            return self._cancelled_result(settings)

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

        result = SubtitleProcessor.sync_start_end(
            settings["subtitle_file"],
            settings["output"],
            video_duration,
        )

        if self.cancelled:
            return self._cancelled_result(settings)

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

        # SubtitleProcessor does not currently expose a fit()
        # file-level operation, so use SubtitleFile +
        # SubtitleSynchronizer directly.
        subtitles = SubtitleFile.load(
            settings["subtitle_file"]
        )

        if self.cancelled:
            return self._cancelled_result(settings)

        self._progress(
            "Fitting subtitles to video duration",
            self._display_name(settings),
            50,
        )

        result = SubtitleSynchronizer.fit_to_video(
            subtitles,
            video_duration,
        )

        if self.cancelled:
            return self._cancelled_result(settings)

        result = self._finalize_timing(
            result,
            settings,
        )

        self._progress(
            "Saving fitted subtitles",
            self._display_name(settings),
            90,
        )

        result.save(settings["output"])

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

        subtitles = SubtitleFile.load(
            settings["subtitle_file"]
        )

        if self.cancelled:
            return self._cancelled_result(settings)

        self._progress(
            "Clamping subtitles to video duration",
            self._display_name(settings),
            60,
        )

        result = SubtitleSynchronizer.clamp(
            subtitles,
            video_duration,
        )

        if self.cancelled:
            return self._cancelled_result(settings)

        self._progress(
            "Saving clamped subtitles",
            self._display_name(settings),
            90,
        )

        result.save(settings["output"])

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

        # Use SubtitleProcessor for the high-level validation API.
        result = SubtitleProcessor.validate(
            settings["subtitle_file"]
        )

        self._progress(
            "Subtitle validation complete",
            self._display_name(settings),
            100,
        )

        return {
            **result,
            "operation": "validate",
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

        if self.cancelled:
            return result

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

        if self.cancelled:
            return result

        errors = result.validate()

        if errors:

            raise ValueError(
                "Subtitle timing validation failed:\n"
                + "\n".join(errors)
            )

        return result

    # ==========================================================
    # SYNC POINT PARSER
    # ==========================================================

    @staticmethod
    def _parse_sync_points(
        points: Any,
    ) -> List[SyncPoint]:

        if not isinstance(
            points,
            (list, tuple),
        ):
            raise ValueError(
                "sync_points must be a list."
            )

        result: List[SyncPoint] = []

        for point in points:

            if isinstance(
                point,
                SyncPoint,
            ):
                result.append(point)
                continue

            if isinstance(
                point,
                dict,
            ):

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
                        "Invalid synchronization point."
                    ) from exc

                result.append(
                    SyncPoint(
                        subtitle_time=subtitle_time,
                        video_time=video_time,
                    )
                )

                continue

            if (
                isinstance(
                    point,
                    (list, tuple),
                )
                and len(point) >= 2
            ):

                try:

                    result.append(
                        SyncPoint(
                            subtitle_time=float(point[0]),
                            video_time=float(point[1]),
                        )
                    )

                except (
                    TypeError,
                    ValueError,
                ) as exc:

                    raise ValueError(
                        f"Invalid synchronization point: "
                        f"{point!r}"
                    ) from exc

                continue

            raise ValueError(
                "Invalid synchronization point: "
                f"{point!r}"
            )

        return result

    # ==========================================================
    # SETTINGS
    # ==========================================================

    def _normalize_settings(
        self,
        settings: Dict[str, Any],
    ) -> Dict[str, Any]:

        settings = dict(settings or {})

        operation = str(
            settings.get("operation", "offset")
            or "offset"
        ).strip().lower()

        aliases = {
            "join": "join_parts",
            "join_two": "join_parts",
            "join_files": "join_parts",
            "merge": "merge_tracks",
            "sync": "offset",
            "fixed": "offset",
            "fixed_offset": "offset",
            "drift": "two_point",
            "two_points": "two_point",
            "multi_points": "multi_point",
            "start_end_sync": "start_end",
        }

        operation = aliases.get(
            operation,
            operation,
        )

        settings["operation"] = operation

        # ------------------------------------------------------
        # Output
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
        # Files
        # ------------------------------------------------------

        for key in (
            "subtitle_file",
            "first_file",
            "second_file",
        ):

            value = str(
                settings.get(key, "")
                or ""
            ).strip()

            settings[key] = (
                os.path.abspath(
                    os.path.expanduser(value)
                )
                if value
                else ""
            )

        # ------------------------------------------------------
        # Offset
        # ------------------------------------------------------

        try:

            settings["offset"] = float(
                settings.get("offset", 0.0)
            )

        except (
            TypeError,
            ValueError,
        ):

            settings["offset"] = 0.0

        # ------------------------------------------------------
        # Join gap
        # ------------------------------------------------------

        try:

            settings["gap"] = float(
                settings.get("gap", 0.0)
            )

        except (
            TypeError,
            ValueError,
        ):

            settings["gap"] = 0.0

        # ------------------------------------------------------
        # Optional second offset
        # ------------------------------------------------------

        second_offset = settings.get(
            "second_offset"
        )

        if second_offset in (None, ""):

            settings["second_offset"] = None

        else:

            try:

                settings["second_offset"] = float(
                    second_offset
                )

            except (
                TypeError,
                ValueError,
            ) as exc:

                raise ValueError(
                    "second_offset must be numeric."
                ) from exc

        # ------------------------------------------------------
        # Video duration
        # ------------------------------------------------------

        duration = settings.get(
            "video_duration"
        )

        if duration in (None, ""):

            settings["video_duration"] = None

        else:

            try:

                duration = float(duration)

            except (
                TypeError,
                ValueError,
            ) as exc:

                raise ValueError(
                    "video_duration must be greater than zero."
                ) from exc

            if duration <= 0:

                raise ValueError(
                    "video_duration must be greater than zero."
                )

            settings["video_duration"] = duration

        # ------------------------------------------------------
        # Two-point synchronization
        # ------------------------------------------------------

        for key in (
            "subtitle_point_1",
            "video_point_1",
            "subtitle_point_2",
            "video_point_2",
        ):

            value = settings.get(key)

            if value is None and operation != "two_point":
                continue

            try:

                settings[key] = float(value)

            except (
                TypeError,
                ValueError,
            ) as exc:

                if operation == "two_point":

                    raise ValueError(
                        f"{key} is required and must be numeric."
                    ) from exc

        # ------------------------------------------------------
        # Multi-point synchronization
        # ------------------------------------------------------

        settings["sync_points"] = settings.get(
            "sync_points",
            [],
        )

        # ------------------------------------------------------
        # Processing options
        # ------------------------------------------------------

        settings["remove_duplicates"] = bool(
            settings.get(
                "remove_duplicates",
                True,
            )
        )

        settings["clamp_to_video"] = bool(
            settings.get(
                "clamp_to_video",
                True,
            )
        )

        settings["subtitle_format"] = str(
            settings.get(
                "subtitle_format",
                "srt",
            )
            or "srt"
        ).strip().lower().lstrip(".")

        return settings

    # ==========================================================
    # VALIDATION
    # ==========================================================

    def _validate_settings(
        self,
        settings: Dict[str, Any],
    ) -> None:

        operation = settings["operation"]

        if operation not in self.OPERATIONS:

            raise ValueError(
                f"Unsupported subtitle operation: "
                f"{operation}. "
                f"Valid operations: "
                f"{', '.join(sorted(self.OPERATIONS))}"
            )

        if settings.get("subtitle_format") not in self.FORMATS:

            raise ValueError(
                "Unsupported subtitle format: "
                f"{settings.get('subtitle_format')}. "
                f"Valid formats: "
                f"{', '.join(sorted(self.FORMATS))}"
            )

        # ------------------------------------------------------
        # Output
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
        # Required files
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

        if operation in {
            "join_parts",
            "merge_tracks",
        }:

            self._require_file(
                settings["first_file"],
                "first_file",
            )

            self._require_file(
                settings["second_file"],
                "second_file",
            )

        # ------------------------------------------------------
        # Video duration
        # ------------------------------------------------------

        if operation in {
            "start_end",
            "fit",
            "clamp",
        }:

            if settings.get("video_duration") is None:

                raise ValueError(
                    "video_duration is required "
                    f"for {operation}."
                )

        # ------------------------------------------------------
        # Multi-point
        # ------------------------------------------------------

        if operation == "multi_point":

            points = self._parse_sync_points(
                settings["sync_points"]
            )

            if len(points) < 2:

                raise ValueError(
                    "At least two synchronization "
                    "points are required."
                )

    # ==========================================================
    # FILE VALIDATION
    # ==========================================================

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
            "operation": settings.get("operation"),

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
            "first_file",
        ):

            value = settings.get(key)

            if value:

                return os.path.basename(
                    str(value)
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

            percentage = float(percentage)

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

        try:

            self.progress_callback(
                info,
                filename,
                (
                    int(percentage)
                    if percentage.is_integer()
                    else round(
                        percentage,
                        1,
                    )
                ),
                "--",
                "--",
                "--:--",
            )

        except TypeError:

            try:

                self.progress_callback(
                    info,
                    filename,
                    percentage,
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

            self.finished_callback(result)

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

                self.error_callback(error)

                return

            except Exception:
                pass

        print(error)
