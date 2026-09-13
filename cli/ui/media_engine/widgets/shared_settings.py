from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QWidget,
)


class SharedSettings(QGroupBox):
    def __init__(
        self,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("Shared Media Settings", parent)

        form = QFormLayout(self)
        form.setSpacing(8)

        self.video_mode = QComboBox()
        self.video_mode.addItems(
            [
                "Fast Copy",
                "Re-encode",
            ]
        )

        self.audio_mode = QComboBox()
        self.audio_mode.addItems(
            [
                "Fast Copy",
                "Re-encode",
            ]
        )

        self.video_codec = QComboBox()
        self.video_codec.addItems(
            [
                "libx264",
                "libx265",
                "libvpx-vp9",
                "copy",
            ]
        )

        self.audio_codec = QComboBox()
        self.audio_codec.addItems(
            [
                "aac",
                "libmp3lame",
                "libopus",
                "flac",
                "copy",
            ]
        )

        self.preset = QComboBox()
        self.preset.addItems(
            [
                "ultrafast",
                "superfast",
                "veryfast",
                "faster",
                "fast",
                "medium",
                "slow",
                "slower",
            ]
        )

        self.crf = QComboBox()
        self.crf.addItems(
            [
                "18",
                "20",
                "22",
                "23",
                "24",
                "26",
                "28",
                "30",
                "32",
                "35",
            ]
        )

        self.audio_bitrate = QComboBox()
        self.audio_bitrate.addItems(
            [
                "96k",
                "128k",
                "160k",
                "192k",
                "256k",
                "320k",
            ]
        )

        self.pixel_format = QComboBox()
        self.pixel_format.addItems(
            [
                "yuv420p",
                "yuv422p",
                "yuv444p",
            ]
        )

        self.faststart = QCheckBox(
            "Enable Faststart"
        )
        self.faststart.setChecked(True)

        self.overwrite = QCheckBox(
            "Allow Overwrite"
        )

        form.addRow(
            "Video Mode:",
            self.video_mode,
        )
        form.addRow(
            "Audio Mode:",
            self.audio_mode,
        )
        form.addRow(
            "Video Codec:",
            self.video_codec,
        )
        form.addRow(
            "Audio Codec:",
            self.audio_codec,
        )
        form.addRow(
            "Preset:",
            self.preset,
        )
        form.addRow(
            "CRF:",
            self.crf,
        )
        form.addRow(
            "Audio Bitrate:",
            self.audio_bitrate,
        )
        form.addRow(
            "Pixel Format:",
            self.pixel_format,
        )
        form.addRow(
            "",
            self.faststart,
        )
        form.addRow(
            "",
            self.overwrite,
        )

    def values(self) -> dict[str, Any]:
        video_mode = (
            "fast_copy"
            if self.video_mode.currentIndex() == 0
            else "reencode"
        )

        audio_mode = (
            "fast_copy"
            if self.audio_mode.currentIndex() == 0
            else "reencode"
        )

        video_codec = self.video_codec.currentText()

        audio_codec = self.audio_codec.currentText()

        if video_mode == "fast_copy":
            video_codec = "copy"

        if audio_mode == "fast_copy":
            audio_codec = "copy"

        return {
            "video_mode": video_mode,
            "audio_mode": audio_mode,
            "video_codec": video_codec,
            "audio_codec": audio_codec,
            "preset": self.preset.currentText(),
            "crf": int(self.crf.currentText()),
            "audio_bitrate": self.audio_bitrate.currentText(),
            "pixel_format": self.pixel_format.currentText(),
            "faststart": self.faststart.isChecked(),
            "overwrite": self.overwrite.isChecked(),
        }

    def reset(self) -> None:
        self.video_mode.setCurrentIndex(0)
        self.audio_mode.setCurrentIndex(0)

        self.video_codec.setCurrentText(
            "libx264"
        )
        self.audio_codec.setCurrentText(
            "aac"
        )
        self.preset.setCurrentText(
            "veryfast"
        )
        self.crf.setCurrentText("20")
        self.audio_bitrate.setCurrentText(
            "192k"
        )
        self.pixel_format.setCurrentText(
            "yuv420p"
        )

        self.faststart.setChecked(True)
        self.overwrite.setChecked(False)