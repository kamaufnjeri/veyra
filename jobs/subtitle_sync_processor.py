from __future__ import annotations

import os

from typing import Any, Callable, Dict, List, Optional

from services.subtitle_sync_service import (
    SubtitleSyncService,
)


class JobCancelled(Exception):
    """Raised when a subtitle synchronization job is cancelled."""


class SubtitleSyncJobProcessor:
    """
    High-level processor for subtitle synchronization.

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

    JOIN:

        Each subtitle file may contain:

            {
                "name": "...",
                "offset": 0.0,
                "gap": 5.0,
            }

        Part 1:
            gap is NOT allowed.

        Part 2+:
            gap is optional.

    MERGE:

        Each subtitle file may contain:

            {
                "name": "...",
                "offset": 0.0,
            }

        Any gap value is ignored for MERGE.

    Compatibility aliases are accepted.

    The processor supports up to four subtitle files.
    """

    MAX_SUBTITLE_FILES = 4

    VALID_OPERATIONS = {
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

    OPERATION_ALIASES = {
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
        "points": "multi_point",
        "multi_points": "multi_point",
        "start_end_sync": "start_end",
    }

    def __init__(
        self,
        operation: str = "offset",
        subtitle_format: str = "srt",
        progress_callback: Optional[
            Callable[..., None]
        ] = None,
        error_callback: Optional[
            Callable[[Any], None]
        ] = None,
    ) -> None:

        self.operation = self._normalize_operation(
            operation
        )

        self.subtitle_format = (
            str(
                subtitle_format
                or "srt"
            )
            .strip()
            .lower()
            .lstrip(".")
        )

        self.progress_callback = progress_callback
        self.error_callback = error_callback

        self.cancelled = False

        if self.subtitle_format not in {
            "srt",
            "vtt",
        }:
            raise ValueError(
                "Invalid subtitle format: "
                f"{self.subtitle_format}"
            )

    # ==========================================================
    # OPERATION NORMALIZATION
    # ==========================================================

    @classmethod
    def _normalize_operation(
        cls,
        operation: Any,
    ) -> str:

        operation = str(
            operation
            or ""
        ).strip().lower()

        operation = cls.OPERATION_ALIASES.get(
            operation,
            operation,
        )

        if operation not in cls.VALID_OPERATIONS:
            raise ValueError(
                "Invalid synchronization operation: "
                f"{operation}. Valid operations: "
                f"{', '.join(sorted(cls.VALID_OPERATIONS))}"
            )

        return operation

    # ==========================================================
    # CANCELLATION
    # ==========================================================

    def cancel(self) -> None:

        self.cancelled = True

        service = getattr(
            self,
            "_active_service",
            None,
        )

        if service is not None:
            try:
                service.cancel()
            except Exception:
                pass

    def check_cancelled(self) -> None:

        if self.cancelled:
            raise JobCancelled(
                "Subtitle synchronization cancelled."
            )

    # ==========================================================
    # SET OPERATION
    # ==========================================================

    def set_operation(
        self,
        operation: str,
    ) -> None:

        self.operation = self._normalize_operation(
            operation
        )

    # ==========================================================
    # SERVICE
    # ==========================================================

    def _create_service(
        self,
    ) -> SubtitleSyncService:

        def progress_wrapper(
            *args: Any,
            **kwargs: Any,
        ) -> None:

            if self.cancelled:
                raise KeyboardInterrupt(
                    "Subtitle synchronization cancelled."
                )

            if self.progress_callback:
                try:
                    self.progress_callback(
                        *args,
                        **kwargs,
                    )
                except Exception:
                    pass

        service = SubtitleSyncService(
            progress_callback=progress_wrapper,
            error_callback=self.error_callback,
            finished_callback=None,
            cancelled_callback=None,
        )

        self._active_service = service

        if self.cancelled:
            service.cancel()

        return service

    def _release_service(self) -> None:

        self._active_service = None

    # ==========================================================
    # PROCESS ONE SYNCHRONIZATION OPERATION
    # ==========================================================

    def process(
        self,
        subtitle_filepath: Optional[str] = None,
        output_filepath: Optional[str] = None,
        operation: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:

        self.check_cancelled()

        selected_operation = self._normalize_operation(
            operation
            if operation is not None
            else self.operation
        )

        valid_operations = {
            "offset",
            "two_point",
            "multi_point",
            "start_end",
        }

        if selected_operation not in valid_operations:
            raise ValueError(
                "Invalid synchronization operation for process(): "
                f"{selected_operation}"
            )

        if not subtitle_filepath:
            raise ValueError(
                "Subtitle filepath cannot be empty."
            )

        if not output_filepath:
            raise ValueError(
                "Output filepath cannot be empty."
            )

        settings: Dict[str, Any] = {
            "operation": selected_operation,
            "subtitle_file": subtitle_filepath,
            "output": output_filepath,
            "subtitle_format": self.subtitle_format,
        }

        # ======================================================
        # FIXED OFFSET
        # ======================================================

        if selected_operation == "offset":

            if "offset" not in kwargs:
                raise ValueError(
                    "Offset is required for "
                    "offset synchronization."
                )

            settings["offset"] = kwargs["offset"]

            if "video_duration" in kwargs:
                settings["video_duration"] = kwargs[
                    "video_duration"
                ]

        # ======================================================
        # TWO POINT
        # ======================================================

        elif selected_operation == "two_point":

            required = (
                "subtitle_point_1",
                "video_point_1",
                "subtitle_point_2",
                "video_point_2",
            )

            self._require_arguments(
                kwargs,
                required,
            )

            for key in required:
                settings[key] = kwargs[key]

            if "video_duration" in kwargs:
                settings["video_duration"] = kwargs[
                    "video_duration"
                ]

        # ======================================================
        # MULTI POINT
        # ======================================================

        elif selected_operation == "multi_point":

            points = kwargs.get(
                "sync_points"
            )

            if points is None:
                points = kwargs.get(
                    "points"
                )

            if points is None:
                raise ValueError(
                    "Synchronization points are required "
                    "for multi-point synchronization."
                )

            settings["sync_points"] = points

            if "video_duration" in kwargs:
                settings["video_duration"] = kwargs[
                    "video_duration"
                ]

        # ======================================================
        # START + END
        # ======================================================

        elif selected_operation == "start_end":

            if (
                "video_duration" not in kwargs
                or kwargs["video_duration"] is None
            ):
                raise ValueError(
                    "Video duration is required for "
                    "start_end synchronization."
                )

            settings["video_duration"] = kwargs[
                "video_duration"
            ]

        try:
            return self.process_subtitle_operation(
                settings
            )

        except JobCancelled:
            raise

        except KeyboardInterrupt as exc:

            self.cancel()

            raise JobCancelled(
                "Subtitle processing cancelled by user."
            ) from exc

        except Exception as exc:

            if self.cancelled:
                raise JobCancelled(
                    "Subtitle processing cancelled."
                ) from exc

            raise

    # ==========================================================
    # GENERIC SUBTITLE OPERATION
    # ==========================================================

    def process_subtitle_operation(
        self,
        settings: Dict[str, Any],
    ) -> Dict[str, Any]:

        self.check_cancelled()

        if not isinstance(
            settings,
            dict,
        ):
            raise ValueError(
                "Subtitle operation settings must be a dictionary."
            )

        operation_settings = dict(
            settings
        )

        raw_operation = operation_settings.get(
            "operation",
            self.operation,
        )

        operation = self._normalize_operation(
            raw_operation
        )

        operation_settings["operation"] = operation

        # ======================================================
        # JOIN / MERGE
        # ======================================================

        if operation in {
            "join_parts",
            "merge_tracks",
        }:

            operation_settings[
                "subtitle_files"
            ] = self._normalize_subtitle_files(
                operation_settings,
                operation=operation,
            )

        # ======================================================
        # NORMAL OPERATIONS
        # ======================================================

        else:

            self._normalize_single_subtitle_settings(
                operation_settings
            )

        # ======================================================
        # FORMAT
        # ======================================================

        subtitle_format = (
            operation_settings.get(
                "subtitle_format"
            )
            or self.subtitle_format
        )

        operation_settings[
            "subtitle_format"
        ] = (
            str(
                subtitle_format
            )
            .strip()
            .lower()
            .lstrip(".")
        )

        # ======================================================
        # PROCESS
        # ======================================================

        try:

            self.check_cancelled()

            service = self._create_service()

            self.check_cancelled()

            result = service.process(
                operation_settings
            )

            self.check_cancelled()

            if isinstance(
                result,
                dict,
            ):
                return result

            return {
                "operation": operation,
                "success": True,
                "completed": True,
                "cancelled": False,
                "result": result,
            }

        except KeyboardInterrupt as exc:

            self.cancel()

            raise JobCancelled(
                "Subtitle processing cancelled by user."
            ) from exc

        except JobCancelled:
            raise

        except Exception as exc:

            if self.cancelled:
                raise JobCancelled(
                    "Subtitle processing cancelled."
                ) from exc

            self._emit_error(
                exc
            )

            raise

        finally:

            self._release_service()

    # ==========================================================
    # NORMALIZE SINGLE SUBTITLE SETTINGS
    # ==========================================================

    @staticmethod
    def _normalize_single_subtitle_settings(
        settings: Dict[str, Any],
    ) -> None:

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

        if subtitle_file:
            settings["subtitle_file"] = os.path.abspath(
                os.path.expanduser(
                    subtitle_file
                )
            )

        output = (
            settings.get("output")
            or settings.get("output_path")
            or settings.get("output_filepath")
            or ""
        )

        output = str(
            output
            or ""
        ).strip()

        if output:
            settings["output"] = os.path.abspath(
                os.path.expanduser(
                    output
                )
            )

    # ==========================================================
    # NORMALIZE SUBTITLE FILES
    # ==========================================================

    @classmethod
    def _normalize_subtitle_files(
        cls,
        settings: Dict[str, Any],
        operation: str = "join_parts",
    ) -> List[Dict[str, Any]]:
        """
        Normalize subtitle files while PRESERVING offset/gap.

        Output format:

            JOIN:

            [
                {
                    "name": "/absolute/part1.srt",
                    "offset": 0.0,
                },
                {
                    "name": "/absolute/part2.srt",
                    "offset": 2.0,
                    "gap": 5.0,
                },
            ]

            MERGE:

            [
                {
                    "name": "/absolute/file1.srt",
                    "offset": 0.0,
                },
                {
                    "name": "/absolute/file2.srt",
                    "offset": 10.0,
                },
            ]

        MERGE deliberately does not send gap.
        """

        files_value = settings.get(
            "subtitle_files"
        )

        if files_value is None:
            files_value = settings.get(
                "files"
            )

        raw_files: List[Any] = []

        # ------------------------------------------------------
        # NEW API
        # ------------------------------------------------------

        if files_value is not None:

            if isinstance(
                files_value,
                (str, os.PathLike),
            ):

                raw_files.append(
                    files_value
                )

            elif isinstance(
                files_value,
                (list, tuple),
            ):

                raw_files.extend(
                    files_value
                )

            else:

                raise ValueError(
                    "subtitle_files must be a list "
                    "of subtitle file paths or dictionaries."
                )

        # ------------------------------------------------------
        # OLD API
        # ------------------------------------------------------

        else:

            first = settings.get(
                "first_file"
            )

            second = settings.get(
                "second_file"
            )

            if first:
                raw_files.append(first)

            if second:
                raw_files.append(second)

        # ------------------------------------------------------
        # BUILD CONFIGURATION
        # ------------------------------------------------------

        normalized: List[Dict[str, Any]] = []

        for index, item in enumerate(
            raw_files
        ):

            if not item:
                continue

            # ==================================================
            # STRING FILE
            # ==================================================

            if isinstance(
                item,
                (str, os.PathLike),
            ):

                name = str(
                    item
                ).strip()

                if not name:
                    continue

                config: Dict[str, Any] = {
                    "name": os.path.abspath(
                        os.path.expanduser(
                            name
                        )
                    ),
                    "offset": 0.0,
                }

                # MERGE never receives gap.
                if (
                    operation == "join_parts"
                    and index > 0
                ):
                    config["gap"] = 0.0

                normalized.append(
                    config
                )

                continue

            # ==================================================
            # DICTIONARY FILE
            # ==================================================

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
                        "is missing 'name'."
                    )

                name = str(
                    name
                ).strip()

                if not name:
                    continue

                # ----------------------------------------------
                # OFFSET
                # ----------------------------------------------

                raw_offset = item.get(
                    "offset",
                    0.0,
                )

                try:
                    offset = float(
                        raw_offset
                    )
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
                        os.path.expanduser(
                            name
                        )
                    ),
                    "offset": offset,
                }

                # ----------------------------------------------
                # GAP
                #
                # ONLY JOIN PARTS USES GAP.
                # ----------------------------------------------

                if (
                    operation == "join_parts"
                    and index > 0
                ):

                    raw_gap = item.get(
                        "gap",
                        0.0,
                    )

                    try:
                        gap = float(
                            raw_gap
                        )
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

                normalized.append(
                    config
                )

                continue

            raise ValueError(
                f"Subtitle file #{index + 1} must be "
                "a string path or dictionary."
            )

        # ------------------------------------------------------
        # CLEAN DUPLICATES
        #
        # Do NOT use _clean_file_list() here because that
        # would destroy offset/gap metadata.
        # ------------------------------------------------------

        cleaned: List[Dict[str, Any]] = []
        seen: set[str] = set()

        for config in normalized:

            name = config["name"]

            if name in seen:
                continue

            seen.add(name)

            cleaned.append(
                config
            )

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

            cleaned[0].pop(
                "gap",
                None,
            )

        return cleaned

    # ==========================================================
    # JOIN SUBTITLES
    # ==========================================================

    def join_subtitles(
        self,
        subtitle_files: Optional[List[Any]] = None,
        output: str = "",
        offsets: Optional[List[float]] = None,
        gaps: Optional[List[float]] = None,
    ) -> Dict[str, Any]:
        """
        Join one to four subtitle files sequentially.

        subtitle_files may contain either:

            ["part1.srt", "part2.srt"]

        or:

            [
                {
                    "name": "part1.srt",
                    "offset": 0.0,
                },
                {
                    "name": "part2.srt",
                    "offset": 2.0,
                    "gap": 5.0,
                },
            ]

        offsets/gaps can also be supplied separately for GUI
        compatibility.
        """

        self.check_cancelled()

        if subtitle_files is None:
            files: List[Any] = []
        elif isinstance(
            subtitle_files,
            str,
        ):
            files = [
                subtitle_files
            ]
        else:
            files = list(
                subtitle_files
            )

        # ------------------------------------------------------
        # APPLY SEPARATE OFFSETS/GAPS
        # ------------------------------------------------------

        if offsets is not None:
            for index, offset in enumerate(
                offsets
            ):

                if index >= len(files):
                    break

                if isinstance(
                    files[index],
                    dict,
                ):

                    files[index] = dict(
                        files[index]
                    )

                    files[index]["offset"] = offset

                else:

                    files[index] = {
                        "name": files[index],
                        "offset": offset,
                    }

        if gaps is not None:

            for index, gap in enumerate(
                gaps
            ):

                if index >= len(files):
                    break

                if index == 0:
                    continue

                if isinstance(
                    files[index],
                    dict,
                ):

                    files[index] = dict(
                        files[index]
                    )

                    files[index]["gap"] = gap

                else:

                    files[index] = {
                        "name": files[index],
                        "offset": 0.0,
                        "gap": gap,
                    }

        files = self._normalize_subtitle_files(
            {
                "subtitle_files": files,
            },
            operation="join_parts",
        )

        if not output:
            raise ValueError(
                "Output filepath cannot be empty."
            )

        settings: Dict[str, Any] = {
            "operation": "join_parts",
            "subtitle_files": files,
            "output": output,
            "subtitle_format": self.subtitle_format,
        }

        return self.process_subtitle_operation(
            settings
        )

    # ==========================================================
    # MERGE SUBTITLES
    # ==========================================================

    def merge_subtitles(
        self,
        subtitle_files: Optional[List[Any]] = None,
        output: str = "",
        remove_duplicates: bool = True,
        first_file: Optional[str] = None,
        second_file: Optional[str] = None,
        offsets: Optional[List[float]] = None,
    ) -> Dict[str, Any]:
        """
        Merge one to four subtitle tracks.

        MERGE uses offset.

        MERGE DOES NOT USE GAP.
        """

        self.check_cancelled()

        if subtitle_files is not None:

            if isinstance(
                subtitle_files,
                str,
            ):
                files: List[Any] = [
                    subtitle_files
                ]
            else:
                files = list(
                    subtitle_files
                )

        else:

            files = []

            if first_file:
                files.append(
                    first_file
                )

            if second_file:
                files.append(
                    second_file
                )

        # ------------------------------------------------------
        # APPLY OFFSETS
        # ------------------------------------------------------

        if offsets is not None:

            for index, offset in enumerate(
                offsets
            ):

                if index >= len(files):
                    break

                if isinstance(
                    files[index],
                    dict,
                ):

                    files[index] = dict(
                        files[index]
                    )

                    files[index]["offset"] = offset

                else:

                    files[index] = {
                        "name": files[index],
                        "offset": offset,
                    }

        # ------------------------------------------------------
        # NORMALIZE
        # ------------------------------------------------------

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
            "subtitle_format": self.subtitle_format,
        }

        return self.process_subtitle_operation(
            settings
        )

    # ==========================================================
    # FILE LIST HELPER
    # ==========================================================

    @staticmethod
    def _clean_file_list(
        files: List[str],
    ) -> List[str]:
        """
        Clean a plain subtitle file list.

        Kept for compatibility with older callers.
        """

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
                os.path.expanduser(
                    filepath
                )
            )

            if filepath not in cleaned:
                cleaned.append(
                    filepath
                )

        return cleaned

    # ==========================================================
    # GENERIC SUBTITLE JOB
    # ==========================================================

    def process_subtitle(
        self,
        settings: Dict[str, Any],
    ) -> Dict[str, Any]:

        return self.process_subtitle_operation(
            settings
        )

    # ==========================================================
    # CONVENIENCE: VALIDATE
    # ==========================================================

    def validate_subtitles(
        self,
        subtitle_file: str,
    ) -> Dict[str, Any]:

        self.check_cancelled()

        if not subtitle_file:
            raise ValueError(
                "Subtitle filepath cannot be empty."
            )

        return self.process_subtitle_operation(
            {
                "operation": "validate",
                "subtitle_file": subtitle_file,
                "subtitle_format": self.subtitle_format,
            }
        )

    # ==========================================================
    # CONVENIENCE: OFFSET
    # ==========================================================

    def offset_subtitles(
        self,
        subtitle_file: str,
        output: str,
        offset: float,
        video_duration: Optional[float] = None,
    ) -> Dict[str, Any]:

        self.check_cancelled()

        return self.process_subtitle_operation(
            {
                "operation": "offset",
                "subtitle_file": subtitle_file,
                "output": output,
                "offset": offset,
                "video_duration": video_duration,
                "subtitle_format": self.subtitle_format,
            }
        )

    # ==========================================================
    # CONVENIENCE: TWO POINT
    # ==========================================================

    def sync_two_points(
        self,
        subtitle_file: str,
        output: str,
        subtitle_point_1: float,
        video_point_1: float,
        subtitle_point_2: float,
        video_point_2: float,
        video_duration: Optional[float] = None,
    ) -> Dict[str, Any]:

        self.check_cancelled()

        return self.process_subtitle_operation(
            {
                "operation": "two_point",
                "subtitle_file": subtitle_file,
                "output": output,
                "subtitle_point_1": subtitle_point_1,
                "video_point_1": video_point_1,
                "subtitle_point_2": subtitle_point_2,
                "video_point_2": video_point_2,
                "video_duration": video_duration,
                "subtitle_format": self.subtitle_format,
            }
        )

    # ==========================================================
    # CONVENIENCE: MULTI POINT
    # ==========================================================

    def sync_points(
        self,
        subtitle_file: str,
        output: str,
        sync_points: Any,
        video_duration: Optional[float] = None,
    ) -> Dict[str, Any]:

        self.check_cancelled()

        return self.process_subtitle_operation(
            {
                "operation": "multi_point",
                "subtitle_file": subtitle_file,
                "output": output,
                "sync_points": sync_points,
                "video_duration": video_duration,
                "subtitle_format": self.subtitle_format,
            }
        )

    # ==========================================================
    # CONVENIENCE: START + END
    # ==========================================================

    def sync_start_end(
        self,
        subtitle_file: str,
        output: str,
        video_duration: float,
    ) -> Dict[str, Any]:

        self.check_cancelled()

        return self.process_subtitle_operation(
            {
                "operation": "start_end",
                "subtitle_file": subtitle_file,
                "output": output,
                "video_duration": video_duration,
                "subtitle_format": self.subtitle_format,
            }
        )

    # ==========================================================
    # CONVENIENCE: FIT
    # ==========================================================

    def fit_subtitles(
        self,
        subtitle_file: str,
        output: str,
        video_duration: float,
        remove_duplicates: bool = True,
        clamp_to_video: bool = True,
    ) -> Dict[str, Any]:

        self.check_cancelled()

        return self.process_subtitle_operation(
            {
                "operation": "fit",
                "subtitle_file": subtitle_file,
                "output": output,
                "video_duration": video_duration,
                "remove_duplicates": remove_duplicates,
                "clamp_to_video": clamp_to_video,
                "subtitle_format": self.subtitle_format,
            }
        )

    # ==========================================================
    # CONVENIENCE: CLAMP
    # ==========================================================

    def clamp_subtitles(
        self,
        subtitle_file: str,
        output: str,
        video_duration: float,
    ) -> Dict[str, Any]:

        self.check_cancelled()

        return self.process_subtitle_operation(
            {
                "operation": "clamp",
                "subtitle_file": subtitle_file,
                "output": output,
                "video_duration": video_duration,
                "subtitle_format": self.subtitle_format,
            }
        )

    # ==========================================================
    # ERROR CALLBACK
    # ==========================================================

    def _emit_error(
        self,
        error: Any,
    ) -> None:

        if not self.error_callback:
            return

        try:
            self.error_callback(
                error
            )
        except Exception:
            pass

    # ==========================================================
    # VALIDATION HELPER
    # ==========================================================

    @staticmethod
    def _require_arguments(
        arguments: Dict[str, Any],
        required: tuple[str, ...],
    ) -> None:

        missing = [
            name
            for name in required
            if name not in arguments
            or arguments[name] is None
        ]

        if missing:
            raise ValueError(
                "Missing required synchronization "
                "arguments: "
                + ", ".join(missing)
            )

