from __future__ import annotations

import os
from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class SubtitleControllerWidget(QWidget):
    """
    Master subtitle-file controller.

    This widget owns the complete list of loaded subtitle files.

    It does NOT contain operation-specific selection.

    Operation-specific selection is handled by
    SubtitleOperationWidget.

    files()
        Return all loaded subtitle files.

    set_files()
        Replace the complete list.

    add_files()
        Add files without duplicates.

    remove_selected()
        Remove files from the master list.
    """

    files_changed = Signal(object)

    def __init__(
        self,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)

        self._files: List[str] = []

        self._build_ui()
        self._connect_signals()

    # ==========================================================
    # UI
    # ==========================================================

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        header = QHBoxLayout()

        self.title_label = QLabel(
            "Loaded Subtitle Files"
        )

        header.addWidget(
            self.title_label
        )

        header.addStretch()

        self.count_label = QLabel(
            "0 files"
        )

        header.addWidget(
            self.count_label
        )

        layout.addLayout(header)

        self.subtitle_list = QListWidget()

        self.subtitle_list.setMinimumHeight(
            150
        )

        self.subtitle_list.setSelectionMode(
            QListWidget.ExtendedSelection
        )

        layout.addWidget(
            self.subtitle_list,
            1,
        )

        buttons = QHBoxLayout()

        self.remove_button = QPushButton(
            "Remove"
        )

        self.clear_button = QPushButton(
            "Clear List"
        )

        buttons.addWidget(
            self.remove_button
        )

        buttons.addWidget(
            self.clear_button
        )

        layout.addLayout(buttons)

        self.info_label = QLabel(
            "These are all subtitle files available "
            "to the operation selector."
        )

        self.info_label.setObjectName(
            "SubtitleControllerInfo"
        )

        self.info_label.setWordWrap(True)

        layout.addWidget(
            self.info_label
        )

    # ==========================================================
    # SIGNALS
    # ==========================================================

    def _connect_signals(self) -> None:
        self.remove_button.clicked.connect(
            self.remove_selected
        )

        self.clear_button.clicked.connect(
            self.clear_files
        )

    # ==========================================================
    # FILES
    # ==========================================================

    def set_files(
        self,
        files: List[str],
    ) -> None:
        self._files = list(
            dict.fromkeys(files)
        )

        self._refresh()

    def add_files(
        self,
        files: List[str],
    ) -> None:
        self._files = list(
            dict.fromkeys(
                self._files + list(files)
            )
        )

        self._refresh()

    def files(self) -> List[str]:
        return list(
            self._files
        )

    def count(self) -> int:
        return len(
            self._files
        )

    # ==========================================================
    # REFRESH
    # ==========================================================

    def _refresh(self) -> None:
        self.subtitle_list.blockSignals(
            True
        )

        try:
            self.subtitle_list.clear()

            for index, filepath in enumerate(
                self._files,
                start=1,
            ):
                item = QListWidgetItem(
                    f"{index}. "
                    f"{os.path.basename(filepath)}"
                )

                item.setData(
                    Qt.UserRole,
                    filepath,
                )

                item.setToolTip(
                    filepath
                )

                self.subtitle_list.addItem(
                    item
                )

        finally:
            self.subtitle_list.blockSignals(
                False
            )

        count = len(
            self._files
        )

        self.count_label.setText(
            f"{count} file"
            f"{'s' if count != 1 else ''}"
        )

        if count:
            self.info_label.setText(
                "All loaded subtitles are available "
                "to the operation selector below."
            )
        else:
            self.info_label.setText(
                "No subtitle files loaded."
            )

        self.files_changed.emit(
            list(self._files)
        )

    # ==========================================================
    # REMOVE
    # ==========================================================

    def remove_selected(self) -> None:
        selected = {
            item.data(Qt.UserRole)
            for item in self.subtitle_list.selectedItems()
        }

        if not selected:
            return

        self._files = [
            filepath
            for filepath in self._files
            if filepath not in selected
        ]

        self._refresh()

    def clear_files(self) -> None:
        if not self._files:
            return

        self._files.clear()

        self._refresh()

    # ==========================================================
    # STYLE
    # ==========================================================

    def apply_style(self) -> None:
        self.setStyleSheet(
            """
            QListWidget {
                background: #0f172a;
                color: #e5e7eb;
                border: 1px solid #334155;
                border-radius: 7px;
                padding: 4px;
            }

            QListWidget::item {
                padding: 8px;
                border-radius: 5px;
            }

            QListWidget::item:selected {
                background: #2563eb;
                color: white;
            }

            QPushButton {
                background: #1f2937;
                color: #e5e7eb;
                border: 1px solid #374151;
                border-radius: 7px;
                padding: 7px 10px;
            }

            QPushButton:hover {
                background: #374151;
            }

            #SubtitleControllerInfo {
                color: #94a3b8;
            }
            """
        )

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.apply_style()