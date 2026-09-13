from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)


class OutputSettings(QGroupBox):
    changed = Signal()

    def __init__(
        self,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("Output", parent)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        directory_row = QHBoxLayout()

        self.directory_label = QLabel(
            "No output directory selected."
        )
        self.directory_label.setWordWrap(True)

        self.choose_directory_button = QPushButton(
            "Browse..."
        )

        self.choose_directory_button.clicked.connect(
            self.choose_directory
        )

        directory_row.addWidget(
            self.directory_label,
            1,
        )
        directory_row.addWidget(
            self.choose_directory_button
        )

        form.addRow(
            "Directory:",
            directory_row,
        )

        self.output_name = QLineEdit()
        self.output_name.setPlaceholderText(
            "Output filename / base name"
        )

        self.output_name.textChanged.connect(
            lambda _: self.changed.emit()
        )

        form.addRow(
            "Name:",
            self.output_name,
        )

        layout.addLayout(form)

        self.preview_label = QLabel(
            "Output: not configured."
        )
        self.preview_label.setWordWrap(True)

        layout.addWidget(
            self.preview_label
        )

        self.directory: Path | None = None
        self.user_modified_directory = False
        self.user_modified_name = False

    def choose_directory(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self,
            "Choose Output Directory",
            str(
                self.directory
                or Path.home()
            ),
        )

        if not directory:
            return

        self.directory = Path(directory)
        self.user_modified_directory = True

        self.directory_label.setText(
            str(self.directory)
        )

        self.changed.emit()

    def set_default_directory(
        self,
        directory: Path,
    ) -> None:
        if self.user_modified_directory:
            return

        self.directory = Path(directory)

        self.directory_label.setText(
            str(self.directory)
        )

    def set_name(
        self,
        name: str,
        *,
        force: bool = False,
    ) -> None:
        if self.user_modified_name and not force:
            return

        self.output_name.setText(name)
        self.user_modified_name = False

    def set_preview(
        self,
        text: str,
    ) -> None:
        self.preview_label.setText(text)

    def reset(self) -> None:
        self.directory = None
        self.user_modified_directory = False
        self.user_modified_name = False

        self.directory_label.setText(
            "No output directory selected."
        )

        self.output_name.clear()
        self.preview_label.setText(
            "Output: not configured."
        )