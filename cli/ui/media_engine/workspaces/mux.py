from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
)

from media.models import MuxerSettings
from jobs.media_engine_processor import MediaEngineJob

from ..widgets.media_group import MediaGroupWidget
from .base import Workspace


class MuxWorkspace(Workspace):

    def __init__(
        self,
        parent=None,
    ) -> None:

        super().__init__(
            "Mux Groups",
            parent,
        )

        self.groups = MediaGroupWidget(
            "mux",
            self,
        )

        self.layout.addWidget(
            self.groups
        )

        form = QFormLayout()

        # ----------------------------------------------------------
        # SUBTITLE CODEC
        # ----------------------------------------------------------

        self.subtitle_codec = QComboBox()

        self.subtitle_codec.addItem(
            "Automatic",
            None,
        )

        self.subtitle_codec.addItem(
            "SubRip",
            "srt",
        )

        self.subtitle_codec.addItem(
            "ASS",
            "ass",
        )

        self.subtitle_codec.addItem(
            "WebVTT",
            "webvtt",
        )

        # ----------------------------------------------------------
        # METADATA
        # ----------------------------------------------------------

        self.keep_metadata = QCheckBox(
            "Keep metadata"
        )

        self.keep_metadata.setChecked(
            True
        )

        form.addRow(
            "Subtitle Codec:",
            self.subtitle_codec,
        )

        form.addRow(
            "",
            self.keep_metadata,
        )

        self.layout.addLayout(
            form
        )

    # ==========================================================
    # WORKING MEDIA
    # ==========================================================

    def set_media(
        self,
        media: list[Path],
    ) -> None:
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

    # ==========================================================
    # SUBTITLES
    # ==========================================================

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

    # ==========================================================
    # BUILD JOBS
    # ==========================================================

    def build_jobs(
        self,
        media,
        output_directory,
        output_name,
        shared,
    ):
        groups = self.groups.mux_data()

        if not groups:
            raise ValueError(
                "Create at least one mux group "
                "with a video."
            )

        settings = MuxerSettings(
            video_mode=shared["video_mode"],
            audio_mode=shared["audio_mode"],
            video_codec=shared["video_codec"],
            audio_codec=shared["audio_codec"],
            preset=shared["preset"],
            crf=shared["crf"],
            audio_bitrate=shared["audio_bitrate"],
            pixel_format=shared["pixel_format"],
            subtitle_codec=self.subtitle_codec.currentData(),
            subtitle_encoding="utf-8",
            keep_metadata=self.keep_metadata.isChecked(),
            faststart=shared["faststart"],
            overwrite=shared["overwrite"],
        )

        settings.validate()

        jobs: list[MediaEngineJob] = []

        for index, group in enumerate(
            groups,
            start=1,
        ):
            if group.video is None:
                raise ValueError(
                    f"Mux Group {index} requires "
                    "a video."
                )

            if (
                not group.audio
                and not group.subtitles
            ):
                raise ValueError(
                    f"Mux Group {index} requires "
                    "at least one audio or subtitle "
                    "input."
                )

            inputs = [
                group.video
            ]

            inputs.extend(
                group.audio
            )

            inputs.extend(
                group.subtitles
            )

            directory = (
                Path(output_directory).expanduser()
                if output_directory
                else group.video.parent
            )

            name = (
                output_name.strip()
                if output_name
                else ""
            )

            if name:
                if len(groups) > 1:
                    base = (
                        f"{group.video.stem}"
                        f"_{name}_{index}"
                    )
                else:
                    base = name

            else:
                if len(groups) == 1:
                    base = (
                        f"{group.video.stem}"
                        "_muxed"
                    )
                else:
                    base = (
                        f"{group.video.stem}"
                        f"_muxed_{index}"
                    )

            extension = (
                group.video.suffix.lstrip(".")
                or "mkv"
            )

            output = self.output_path(
                directory,
                base,
                extension,
            )

            jobs.append(
                MediaEngineJob(
                    operation="mux",
                    inputs=tuple(inputs),
                    output=output,
                    settings=settings,
                )
            )

        return jobs

    # ==========================================================
    # RESET
    # ==========================================================

    def reset(self) -> None:
        self.groups.clear_groups()

        self.subtitle_codec.setCurrentIndex(
            0
        )

        self.keep_metadata.setChecked(
            True
        )