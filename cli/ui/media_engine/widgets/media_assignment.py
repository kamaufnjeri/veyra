from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


@dataclass(frozen=True)
class MediaSubtitleAssignment:
    media: Path
    subtitle: Path


class MediaAssignmentWidget(QGroupBox):
    def __init__(
        self,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            "Subtitle Assignments",
            parent,
        )

        self.media: list[Path] = []
        self.subtitles: list[Path] = []

        layout = QVBoxLayout(self)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(
            [
                "Video",
                "Subtitle",
            ]
        )

        self.table.horizontalHeader().setStretchLastSection(
            True
        )

        layout.addWidget(self.table)

        buttons = QHBoxLayout()

        self.auto_match_button = QPushButton(
            "Auto Match"
        )
        self.apply_button = QPushButton(
            "Apply Selected to All"
        )
        self.clear_button = QPushButton(
            "Clear Assignments"
        )

        self.auto_match_button.clicked.connect(
            self.auto_match
        )
        self.apply_button.clicked.connect(
            self.apply_selected_to_all
        )
        self.clear_button.clicked.connect(
            self.clear_assignments
        )

        buttons.addWidget(
            self.auto_match_button
        )
        buttons.addWidget(
            self.apply_button
        )
        buttons.addWidget(
            self.clear_button
        )

        layout.addLayout(buttons)

    def set_data(
        self,
        media: list[Path],
        subtitles: list[Path],
    ) -> None:
        self.media = list(media)
        self.subtitles = list(subtitles)

        self.table.setRowCount(0)

        for path in self.media:
            row = self.table.rowCount()
            self.table.insertRow(row)

            video_item = QTableWidgetItem(
                path.name
            )
            video_item.setToolTip(str(path))
            video_item.setData(
                32,
                str(path),
            )

            self.table.setItem(
                row,
                0,
                video_item,
            )

            combo = QComboBox()
            combo.addItem(
                "No subtitle",
                None,
            )

            for subtitle in self.subtitles:
                combo.addItem(
                    subtitle.name,
                    str(subtitle),
                )

            self.table.setCellWidget(
                row,
                1,
                combo,
            )

    def assignments(
        self,
    ) -> list[MediaSubtitleAssignment]:
        result: list[MediaSubtitleAssignment] = []

        for row in range(self.table.rowCount()):
            video_item = self.table.item(row, 0)

            if video_item is None:
                continue

            video = Path(
                str(
                    video_item.data(32)
                )
            )

            combo = self.table.cellWidget(
                row,
                1,
            )

            if not isinstance(combo, QComboBox):
                continue

            subtitle = combo.currentData()

            if not subtitle:
                continue

            result.append(
                MediaSubtitleAssignment(
                    media=video,
                    subtitle=Path(
                        str(subtitle)
                    ),
                )
            )

        return result

    def auto_match(self) -> None:
        for row in range(self.table.rowCount()):
            video_item = self.table.item(row, 0)

            if video_item is None:
                continue

            video = Path(
                str(video_item.data(32))
            )

            combo = self.table.cellWidget(
                row,
                1,
            )

            if not isinstance(combo, QComboBox):
                continue

            best_index = 0

            for index in range(
                1,
                combo.count(),
            ):
                subtitle_value = combo.itemData(index)

                if not subtitle_value:
                    continue

                subtitle = Path(
                    str(subtitle_value)
                )

                if subtitle.stem.lower() == video.stem.lower():
                    best_index = index
                    break

            combo.setCurrentIndex(best_index)

    def apply_selected_to_all(self) -> None:
        if self.table.rowCount() == 0:
            return

        selected_row = self.table.currentRow()

        if selected_row < 0:
            selected_row = 0

        source_combo = self.table.cellWidget(
            selected_row,
            1,
        )

        if not isinstance(source_combo, QComboBox):
            return

        value = source_combo.currentData()

        for row in range(self.table.rowCount()):
            combo = self.table.cellWidget(
                row,
                1,
            )

            if not isinstance(combo, QComboBox):
                continue

            index = combo.findData(value)

            if index >= 0:
                combo.setCurrentIndex(index)

    def clear_assignments(self) -> None:
        for row in range(self.table.rowCount()):
            combo = self.table.cellWidget(
                row,
                1,
            )

            if isinstance(combo, QComboBox):
                combo.setCurrentIndex(0)