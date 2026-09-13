from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QCheckBox, QFormLayout

from media.models import JoinerSettings
from jobs.media_engine_processor import MediaEngineJob

from ..widgets.media_group import MediaGroupWidget
from .base import Workspace


class JoinWorkspace(Workspace):

    def __init__(
        self,
        parent=None,
    ) -> None:

        super().__init__(
            "Join Groups",
            parent,
        )

        self.groups = MediaGroupWidget(
            "join",
            self,
        )

        self.layout.addWidget(
            self.groups
        )

        form = QFormLayout()

        self.join_subtitles = QCheckBox(
            "Join matching video sidecar subtitles"
        )

        self.join_subtitles.setChecked(
            True
        )

        form.addRow(
            "",
            self.join_subtitles,
        )

        self.layout.addLayout(
            form
        )

    # ========================================================
    # WORKING MEDIA
    # ========================================================

    def set_media(
        self,
        media: list[Path],
    ) -> None:
        """
        Keep compatibility with MediaEnginePage.

        Working media is separate from the group's available
        selection source.
        """
        self.groups.set_media(
            media
        )

    def set_available_media(
        self,
        media: list[Path],
    ) -> None:
        self.groups.set_available_media(
            media
        )

    # ========================================================
    # SUBTITLES
    # ========================================================

    def set_subtitles(
        self,
        subtitles: list[Path],
    ) -> None:
        self.groups.set_subtitles(
            subtitles
        )

    def set_available_subtitles(
        self,
        subtitles: list[Path],
    ) -> None:
        self.groups.set_available_subtitles(
            subtitles
        )

    # ========================================================
    # BUILD JOBS
    # ========================================================

    def build_jobs(
        self,
        media,
        output_directory,
        output_name,
        shared,
    ):
        groups = self.groups.join_data()

        if not groups:
            raise ValueError(
                "Create at least one join group "
                "with video, audio, or subtitle files."
            )

        settings = JoinerSettings(
            **shared,
            join_subtitles=self.join_subtitles.isChecked(),
        )

        settings.validate()

        jobs: list[MediaEngineJob] = []

        total_groups = len(
            groups
        )

        output_directory_path = (
            Path(output_directory).expanduser()
            if output_directory
            else None
        )

        requested_name = (
            output_name.strip()
            if output_name
            else ""
        )

        for group_index, group in enumerate(
            groups,
            start=1,
        ):

            group_outputs = self._build_group_jobs(
                group=group,
                group_index=group_index,
                total_groups=total_groups,
                output_directory=output_directory_path,
                output_name=requested_name,
                settings=settings,
            )

            jobs.extend(
                group_outputs
            )

        if not jobs:
            raise ValueError(
                "No valid media was added to the join groups."
            )

        return jobs

    # ========================================================
    # GROUP JOBS
    # ========================================================

    def _build_group_jobs(
        self,
        *,
        group,
        group_index: int,
        total_groups: int,
        output_directory: Path | None,
        output_name: str,
        settings: JoinerSettings,
    ) -> list[MediaEngineJob]:

        jobs: list[MediaEngineJob] = []

        # ----------------------------------------------------
        # VIDEO
        # ----------------------------------------------------

        if group.video:

            if len(group.video) < 2:
                raise ValueError(
                    f"Join Group {group_index}: "
                    "at least two video files are required."
                )

            directory = (
                output_directory
                or group.video[0].parent
            )

            base = self._build_base_name(
                first_path=group.video[0],
                requested_name=output_name,
                group_index=group_index,
                total_groups=total_groups,
                media_type="video",
            )

            extension = (
                group.video[0].suffix.lstrip(".")
                or "mp4"
            )

            output = self.output_path(
                directory,
                base,
                extension,
            )

            jobs.append(
                MediaEngineJob(
                    operation="join",
                    inputs=tuple(
                        group.video
                    ),
                    output=output,
                    settings=settings,
                )
            )

        # ----------------------------------------------------
        # AUDIO
        # ----------------------------------------------------

        if group.audio:

            if len(group.audio) < 2:
                raise ValueError(
                    f"Join Group {group_index}: "
                    "at least two audio files are required."
                )

            directory = (
                output_directory
                or group.audio[0].parent
            )

            base = self._build_base_name(
                first_path=group.audio[0],
                requested_name=output_name,
                group_index=group_index,
                total_groups=total_groups,
                media_type="audio",
            )

            jobs.append(
                MediaEngineJob(
                    operation="join",
                    inputs=tuple(
                        group.audio
                    ),
                    output=self.output_path(
                        directory,
                        base,
                        "m4a",
                    ),
                    settings=settings,
                )
            )

        # ----------------------------------------------------
        # SUBTITLES
        # ----------------------------------------------------

        if group.subtitles:

            if len(group.subtitles) < 2:
                raise ValueError(
                    f"Join Group {group_index}: "
                    "at least two subtitle files are required."
                )

            directory = (
                output_directory
                or group.subtitles[0].parent
            )

            base = self._build_base_name(
                first_path=group.subtitles[0],
                requested_name=output_name,
                group_index=group_index,
                total_groups=total_groups,
                media_type="subtitles",
            )

            jobs.append(
                MediaEngineJob(
                    operation="join",
                    inputs=tuple(
                        group.subtitles
                    ),
                    output=self.output_path(
                        directory,
                        base,
                        "srt",
                    ),
                    settings=settings,
                )
            )

        return jobs

    # ========================================================
    # OUTPUT NAME
    # ========================================================

    @staticmethod
    def _build_base_name(
        *,
        first_path: Path,
        requested_name: str,
        group_index: int,
        total_groups: int,
        media_type: str,
    ) -> str:

        if requested_name:

            base = requested_name

            if total_groups > 1:
                return (
                    f"{base}_{media_type}_"
                    f"{group_index}"
                )

            return (
                f"{base}_{media_type}"
            )

        stem = first_path.stem

        if total_groups > 1:
            return (
                f"{stem}_joined_"
                f"{media_type}_"
                f"{group_index}"
            )

        return (
            f"{stem}_joined_"
            f"{media_type}"
        )

    # ========================================================
    # RESET
    # ========================================================

    def reset(self) -> None:

        self.groups.clear_groups()

        self.join_subtitles.setChecked(
            True
        )