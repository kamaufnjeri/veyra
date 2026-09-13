from __future__ import annotations

from PySide6.QtWidgets import (
    QGroupBox,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)


class ProgressPanel(QGroupBox):
    def __init__(
        self,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("Processing", parent)

        layout = QVBoxLayout(self)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

        self.progress_label = QLabel("Ready")
        self.progress_label.setWordWrap(True)

        layout.addWidget(
            self.progress_bar
        )
        layout.addWidget(
            self.progress_label
        )

    def reset(self) -> None:
        self.progress_bar.setValue(0)
        self.progress_label.setText("Ready")

    def set_progress(
        self,
        value: int,
        message: str = "",
    ) -> None:
        self.progress_bar.setValue(
            max(0, min(100, int(value)))
        )

        if message:
            self.progress_label.setText(message)

    def set_message(
        self,
        message: str,
    ) -> None:
        self.progress_label.setText(message)