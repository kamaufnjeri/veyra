from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
QDialog,
QDialogButtonBox,
QHBoxLayout,
QLabel,
QLineEdit,
QListWidget,
QListWidgetItem,
QPushButton,
QVBoxLayout,
QWidget,
)

class MediaSelectionDialog(QDialog):
    """
    Reusable dialog for selecting media/subtitle files.


    The dialog only manages temporary selection state.

    It does not modify:
    - MediaLibrary
    - working media
    - group state

    The caller decides what to do with the returned paths.
    """

    def __init__(
        self,
        title: str,
        files: list[Path],
        allowed_extensions: set[str],
        allow_multiple: bool,
        existing_files: list[Path] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.setWindowTitle(title)
        self.setMinimumSize(620, 480)

        self._allow_multiple = allow_multiple
        self._allowed_extensions = {
            extension.lower()
            for extension in allowed_extensions
        }

        self._existing_files = {
            Path(path).resolve()
            for path in (existing_files or [])
        }

        self._all_files: list[Path] = []
        self._filtered_files: list[Path] = []

        self._build_ui()
        self._set_files(files)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        instruction = QLabel(
            "Select the media you want to add to this group."
        )
        instruction.setWordWrap(True)
        layout.addWidget(instruction)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "Search by filename or path..."
        )
        self.search_input.textChanged.connect(self._filter_files)
        layout.addWidget(self.search_input)

        self.list_widget = QListWidget()

        if self._allow_multiple:
            self.list_widget.setSelectionMode(
                QListWidget.SelectionMode.ExtendedSelection
            )
        else:
            self.list_widget.setSelectionMode(
                QListWidget.SelectionMode.SingleSelection
            )

        self.list_widget.itemSelectionChanged.connect(
            self._update_select_button
        )

        layout.addWidget(self.list_widget)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        if self._allow_multiple:
            selection_layout = QHBoxLayout()

            select_all_button = QPushButton("Select All")
            clear_button = QPushButton("Clear")

            select_all_button.clicked.connect(
                self.list_widget.selectAll
            )
            clear_button.clicked.connect(
                self.list_widget.clearSelection
            )

            selection_layout.addWidget(select_all_button)
            selection_layout.addWidget(clear_button)
            selection_layout.addStretch()

            layout.addLayout(selection_layout)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Ok
        )

        self.select_button = buttons.button(
            QDialogButtonBox.StandardButton.Ok
        )

        if self.select_button is not None:
            self.select_button.setText("Select")

        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self._accept)

        layout.addWidget(buttons)

    # ------------------------------------------------------------------
    # Files
    # ------------------------------------------------------------------

    def _set_files(self, files: list[Path]) -> None:
        seen: set[Path] = set()

        compatible: list[Path] = []

        for raw_path in files:
            path = Path(raw_path)

            try:
                resolved = path.resolve()
            except OSError:
                resolved = path.absolute()

            if resolved in seen:
                continue

            seen.add(resolved)

            if path.suffix.lower() not in self._allowed_extensions:
                continue

            compatible.append(path)

        self._all_files = compatible

        self._filter_files()

    def _filter_files(self) -> None:
        query = self.search_input.text().strip().lower()

        if not query:
            filtered = list(self._all_files)
        else:
            filtered = [
                path
                for path in self._all_files
                if query in path.name.lower()
                or query in str(path).lower()
            ]

        self._filtered_files = filtered

        self.list_widget.blockSignals(True)
        self.list_widget.clear()

        for path in filtered:
            item = QListWidgetItem(path.name)
            item.setToolTip(str(path))
            item.setData(
                Qt.ItemDataRole.UserRole,
                path,
            )

            self.list_widget.addItem(item)

            try:
                resolved = path.resolve()
            except OSError:
                resolved = path.absolute()

            if resolved in self._existing_files:
                item.setSelected(True)

        self.list_widget.blockSignals(False)

        self._update_status()
        self._update_select_button()

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def _selected_items(self) -> list[QListWidgetItem]:
        return self.list_widget.selectedItems()

    def selected_files(self) -> list[Path]:
        """
        Return selected files in the same order they appear in the dialog.
        """

        selected_items = set(self._selected_items())

        selected: list[Path] = []

        for index in range(self.list_widget.count()):
            item = self.list_widget.item(index)

            if item not in selected_items:
                continue

            path = item.data(Qt.ItemDataRole.UserRole)

            if path is not None:
                selected.append(Path(path))

        return selected

    def _update_status(self) -> None:
        total = len(self._filtered_files)
        selected = len(self._selected_items())

        if total == 0:
            self.status_label.setText(
                "No compatible files available."
            )
            return

        if self._allow_multiple:
            self.status_label.setText(
                f"{total} compatible file(s) available · "
                f"{selected} selected"
            )
        else:
            self.status_label.setText(
                f"{total} compatible file(s) available · "
                f"{selected} selected"
            )

    def _update_select_button(self) -> None:
        selected = bool(self._selected_items())

        if self.select_button is not None:
            self.select_button.setEnabled(selected)

        self._update_status()

    # ------------------------------------------------------------------
    # Dialog actions
    # ------------------------------------------------------------------

    def _accept(self) -> None:
        if not self.selected_files():
            return

        self.accept()

