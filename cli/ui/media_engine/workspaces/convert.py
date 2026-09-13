from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
)

from media.models import ConverterSettings
from jobs.media_engine_processor import MediaEngineJob

from .base import Workspace


class ConvertWorkspace(Workspace):
    def __init__(self, parent=None) -> None:
        super().__init__(
            "Convert Settings",
            parent,
        )

        form = QFormLayout()

        self.output_format = QComboBox()
        self.output_format.addItems(
            [
                "mp4",
                "mkv",
                "mov",
                "avi",
                "webm",
                "ts",
            ]
        )

        self.keep_subtitles = QCheckBox(
            "Keep subtitles"
        )
        self.keep_subtitles.setChecked(True)

        self.keep_metadata = QCheckBox(
            "Keep metadata"
        )
        self.keep_metadata.setChecked(True)

        form.addRow(
            "Output Format:",
            self.output_format,
        )
        form.addRow(
            "",
            self.keep_subtitles,
        )
        form.addRow(
            "",
            self.keep_metadata,
        )

        self.layout.addLayout(form)

    def build_jobs(
        self,
        media,
        output_directory,
        output_name,
        shared,
    ):
        settings = ConverterSettings(
            **shared,
            output_format=self.output_format.currentText(),
            keep_subtitles=self.keep_subtitles.isChecked(),
            keep_metadata=self.keep_metadata.isChecked(),
        )

        settings.validate()

        jobs = []

        for source in media:
            directory = (
                output_directory
                or source.parent
            )

            name = output_name.strip()

            if name:
                base = (
                    f"{source.stem}_{name}"
                    if len(media) > 1
                    else name
                )
            else:
                base = f"{source.stem}_converted"

            output = self.output_path(
                directory,
                base,
                self.output_format.currentText(),
            )

            jobs.append(
                MediaEngineJob(
                    operation="convert",
                    inputs=(source,),
                    output=output,
                    settings=settings,
                )
            )

        return jobs

    def reset(self):
        self.output_format.setCurrentText("mp4")
        self.keep_subtitles.setChecked(True)
        self.keep_metadata.setChecked(True)