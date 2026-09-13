from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QSpinBox,
)

from media.models import ExtractorSettings
from jobs.media_engine_processor import MediaEngineJob

from .base import Workspace


class ExtractWorkspace(Workspace):
    def __init__(self, parent=None) -> None:
        super().__init__(
            "Extract Settings",
            parent,
        )

        form = QFormLayout()

        self.stream_type = QComboBox()
        self.stream_type.addItem(
            "Audio",
            "audio",
        )
        self.stream_type.addItem(
            "Video",
            "video",
        )
        self.stream_type.addItem(
            "Subtitle",
            "subtitle",
        )

        self.stream_index = QSpinBox()
        self.stream_index.setRange(
            0,
            999,
        )

        self.output_format = QComboBox()

        form.addRow(
            "Stream Type:",
            self.stream_type,
        )
        form.addRow(
            "Stream Index:",
            self.stream_index,
        )
        form.addRow(
            "Output Format:",
            self.output_format,
        )

        self.layout.addLayout(form)

        self.stream_type.currentIndexChanged.connect(
            self._update_formats
        )

        self._update_formats()

    def _update_formats(self):
        stream_type = self.stream_type.currentData()

        self.output_format.blockSignals(True)
        self.output_format.clear()

        if stream_type == "audio":
            formats = [
                "m4a",
                "mp3",
                "aac",
                "wav",
                "flac",
                "ogg",
                "opus",
            ]

        elif stream_type == "video":
            formats = [
                "mp4",
                "mkv",
                "mov",
                "webm",
                "avi",
                "ts",
            ]

        else:
            formats = [
                "srt",
                "vtt",
                "ass",
                "ssa",
            ]

        self.output_format.addItems(formats)
        self.output_format.blockSignals(False)

    def build_jobs(
        self,
        media,
        output_directory,
        output_name,
        shared,
    ):
        stream_type = self.stream_type.currentData()

        audio_codec = None
        video_codec = None

        if stream_type == "audio":
            audio_codec = (
                None
                if shared["audio_codec"] == "copy"
                else shared["audio_codec"]
            )

        if stream_type == "video":
            video_codec = (
                None
                if shared["video_codec"] == "copy"
                else shared["video_codec"]
            )

        subtitle_format = (
            self.output_format.currentText()
            if stream_type == "subtitle"
            else None
        )

        settings = ExtractorSettings(
            stream_type=stream_type,
            stream_index=self.stream_index.value(),
            output_format=self.output_format.currentText(),
            audio_codec=audio_codec,
            audio_bitrate=shared["audio_bitrate"],
            video_codec=video_codec,
            video_pixel_format=shared["pixel_format"],
            subtitle_format=subtitle_format,
            overwrite=shared["overwrite"],
        )

        settings.validate()

        jobs = []

        suffix = {
            "audio": "_audio",
            "video": "_video",
            "subtitle": "_subtitle",
        }[stream_type]

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
                base = source.stem + suffix

            output = self.output_path(
                directory,
                base,
                self.output_format.currentText(),
            )

            jobs.append(
                MediaEngineJob(
                    operation="extract",
                    inputs=(source,),
                    output=output,
                    settings=settings,
                )
            )

        return jobs

    def reset(self):
        self.stream_type.setCurrentIndex(0)
        self.stream_index.setValue(0)
        self._update_formats()