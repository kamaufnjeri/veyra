from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
)

from media.models import CompressorSettings
from jobs.media_engine_processor import MediaEngineJob

from .base import Workspace


class CompressWorkspace(Workspace):
    def __init__(self, parent=None) -> None:
        super().__init__(
            "Compress Settings",
            parent,
        )

        form = QFormLayout()

        self.output_format = QComboBox()

        self.output_format.addItems(
            [
                "Auto",
                "mp4",
                "mkv",
                "mov",
                "webm",
                "avi",
                "ts",
                "mp3",
                "m4a",
                "aac",
                "flac",
                "wav",
                "ogg",
                "opus",
            ]
        )

        self.compress_video = QCheckBox(
            "Compress video"
        )
        self.compress_video.setChecked(True)

        self.compress_audio = QCheckBox(
            "Compress audio"
        )
        self.compress_audio.setChecked(True)

        self.resolution = QComboBox()
        self.resolution.addItem(
            "Keep original",
            None,
        )
        self.resolution.addItem(
            "1920x1080",
            "1920:1080",
        )
        self.resolution.addItem(
            "1280x720",
            "1280:720",
        )
        self.resolution.addItem(
            "854x480",
            "854:480",
        )
        self.resolution.addItem(
            "640x360",
            "640:360",
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
            self.compress_video,
        )
        form.addRow(
            "",
            self.compress_audio,
        )
        form.addRow(
            "Resolution:",
            self.resolution,
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
        settings = CompressorSettings(
            video_codec=shared["video_codec"],
            audio_codec=shared["audio_codec"],
            video_crf=shared["crf"],
            video_preset=shared["preset"],
            audio_bitrate=shared["audio_bitrate"],
            pixel_format=shared["pixel_format"],
            resolution=self.resolution.currentData(),
            compress_video=self.compress_video.isChecked(),
            compress_audio=self.compress_audio.isChecked(),
            keep_subtitles=self.keep_subtitles.isChecked(),
            keep_metadata=self.keep_metadata.isChecked(),
            faststart=shared["faststart"],
            overwrite=shared["overwrite"],
        )

        settings.validate()

        jobs = []

        for source in media:
            directory = (
                output_directory
                or source.parent
            )

            fmt = self._format_for_source(
                source
            )

            name = output_name.strip()

            if name:
                base = (
                    f"{source.stem}_{name}"
                    if len(media) > 1
                    else name
                )
            else:
                base = f"{source.stem}_compressed"

            output = self.output_path(
                directory,
                base,
                fmt,
            )

            jobs.append(
                MediaEngineJob(
                    operation="compress",
                    inputs=(source,),
                    output=output,
                    settings=settings,
                )
            )

        return jobs

    def _format_for_source(
        self,
        source,
    ) -> str:
        selected = self.output_format.currentText()

        if selected != "Auto":
            return selected

        audio_extensions = {
            ".mp3",
            ".wav",
            ".flac",
            ".aac",
            ".m4a",
            ".ogg",
            ".opus",
        }

        if source.suffix.lower() in audio_extensions:
            return source.suffix.lstrip(".") or "mp3"

        return "mp4"

    def reset(self):
        self.output_format.setCurrentText("Auto")
        self.compress_video.setChecked(True)
        self.compress_audio.setChecked(True)
        self.resolution.setCurrentIndex(0)
        self.keep_subtitles.setChecked(True)
        self.keep_metadata.setChecked(True)