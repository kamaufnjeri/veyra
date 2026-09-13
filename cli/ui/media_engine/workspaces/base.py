from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QGroupBox, QVBoxLayout, QWidget

from media.models import (
    BurnerSettings,
    CompressorSettings,
    ConverterSettings,
    CutterSettings,
    ExtractorSettings,
    JoinerSettings,
    MuxerSettings,
)

from jobs.media_engine_processor import MediaEngineJob


class Workspace(QGroupBox):
    def __init__(
        self,
        title: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(title, parent)

        self.layout = QVBoxLayout(self)
        self.layout.setSpacing(8)

    def set_media(
        self,
        media: list[Path],
    ) -> None:
        pass

    def set_subtitles(
        self,
        subtitles: list[Path],
    ) -> None:
        pass

    def build_jobs(
        self,
        media: list[Path],
        output_directory: Path | None,
        output_name: str,
        shared: dict[str, Any],
    ) -> list[MediaEngineJob]:
        raise NotImplementedError

    def reset(self) -> None:
        pass

    @staticmethod
    def output_path(
        directory: Path,
        name: str,
        extension: str,
    ) -> Path:
        extension = extension.lstrip(".")

        if not name.lower().endswith(
            f".{extension.lower()}"
        ):
            name = f"{name}.{extension}"

        return directory / name

    @staticmethod
    def unique_output_path(
        path: Path,
    ) -> Path:
        if not path.exists():
            return path

        counter = 2

        while True:
            candidate = (
                path.parent
                / f"{path.stem}_{counter}"
                f"{path.suffix}"
            )

            if not candidate.exists():
                return candidate

            counter += 1