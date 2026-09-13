from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


MEDIA_EXTENSIONS = {
    ".mp4",
    ".mkv",
    ".mov",
    ".avi",
    ".webm",
    ".m4v",
    ".ts",
    ".mpeg",
    ".mpg",
    ".3gp",
    ".mp3",
    ".wav",
    ".flac",
    ".aac",
    ".m4a",
    ".ogg",
    ".opus",
}


class MediaLibrary(QGroupBox):
    mediaSelectionChanged = Signal(object)
    mediaFilesChanged = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("Media Library", parent)

        self.media_files: list[Path] = []

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        self.media_list = QListWidget()
        self.media_list.setSelectionMode(
            QListWidget.SelectionMode.ExtendedSelection
        )
        self.media_list.setMinimumHeight(180)

        self.media_list.itemSelectionChanged.connect(
            self._selection_changed
        )

        layout.addWidget(self.media_list)

        self.count_label = QLabel("0 media files loaded.")
        layout.addWidget(self.count_label)

        buttons = QHBoxLayout()

        self.add_button = QPushButton("Add Media")
        self.remove_button = QPushButton("Remove Selected")
        self.clear_button = QPushButton("Clear Loaded")

        self.add_button.clicked.connect(self.browse)
        self.remove_button.clicked.connect(
            self.remove_selected
        )
        self.clear_button.clicked.connect(
            self.clear
        )

        buttons.addWidget(self.add_button)
        buttons.addWidget(self.remove_button)
        buttons.addWidget(self.clear_button)

        layout.addLayout(buttons)

    # =========================================================
    # PUBLIC API
    # =========================================================

    def files(self) -> list[Path]:
        return list(self.media_files)

    def selected_files(self) -> list[Path]:
        paths: list[Path] = []

        for row in range(self.media_list.count()):
            item = self.media_list.item(row)

            if not item.isSelected():
                continue

            value = item.data(Qt.ItemDataRole.UserRole)

            if value:
                paths.append(Path(str(value)))

        return paths

    def set_files(
        self,
        files: list[Path],
    ) -> None:
        self.media_files.clear()
        self.media_list.clear()

        for path in files:
            self._add_path(path)

        self._update_count()
        self.mediaFilesChanged.emit()

    def add_files(
        self,
        files: list[Path],
        *,
        select: bool = True,
    ) -> list[Path]:
        added: list[Path] = []

        for path in files:
            path = Path(path)

            if not path.is_file():
                continue

            if path.suffix.lower() not in MEDIA_EXTENSIONS:
                continue

            if path in self.media_files:
                continue

            self._add_path(path)
            added.append(path)

        if added and select:
            self.media_list.clearSelection()

            for path in added:
                for row in range(self.media_list.count()):
                    item = self.media_list.item(row)

                    if item.data(
                        Qt.ItemDataRole.UserRole
                    ) == str(path):
                        item.setSelected(True)
                        break

        self._update_count()

        if added:
            self.mediaFilesChanged.emit()

        return added

    def set_enabled(
        self,
        enabled: bool,
    ) -> None:
        self.add_button.setEnabled(enabled)
        self.remove_button.setEnabled(enabled)
        self.clear_button.setEnabled(enabled)
        self.media_list.setEnabled(enabled)

    # =========================================================
    # BROWSE
    # =========================================================

    def browse(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Media Files",
            "",
            (
                "Media Files "
                "(*.mp4 *.mkv *.mov *.avi *.webm *.m4v "
                "*.ts *.mpeg *.mpg *.3gp "
                "*.mp3 *.wav *.flac *.aac *.m4a *.ogg *.opus);;"
                "All Files (*)"
            ),
        )

        if not files:
            return

        self.add_files(
            [Path(filename) for filename in files]
        )

    # =========================================================
    # REMOVE
    # =========================================================

    def remove_selected(self) -> None:
        rows = sorted(
            {
                index.row()
                for index in self.media_list.selectedIndexes()
            },
            reverse=True,
        )

        if not rows:
            return

        for row in rows:
            if 0 <= row < len(self.media_files):
                self.media_files.pop(row)
                self.media_list.takeItem(row)

        self._update_count()
        self.mediaFilesChanged.emit()

    # =========================================================
    # CLEAR
    # =========================================================

    def clear(self) -> None:
        if not self.media_files:
            return

        self.media_files.clear()
        self.media_list.clear()

        self._update_count()
        self.mediaFilesChanged.emit()

    # =========================================================
    # INTERNAL
    # =========================================================

    def _add_path(
        self,
        path: Path,
    ) -> None:
        path = Path(path)

        self.media_files.append(path)

        item = QListWidgetItem(path.name)

        item.setToolTip(str(path))

        item.setData(
            Qt.ItemDataRole.UserRole,
            str(path),
        )

        self.media_list.addItem(item)

    def _selection_changed(self) -> None:
        selected = self.selected_files()

        self.mediaSelectionChanged.emit(selected)

    def _update_count(self) -> None:
        count = len(self.media_files)

        if count == 1:
            self.count_label.setText(
                "1 media file loaded."
            )
        else:
            self.count_label.setText(
                f"{count} media files loaded."
            )