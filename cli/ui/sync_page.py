from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
)


class SubtitleSyncPage(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)

        layout.setContentsMargins(
            30,
            25,
            30,
            25,
        )

        title = QLabel(
            "Subtitle Sync"
        )

        title.setStyleSheet(
            """
            font-size: 28px;
            font-weight: 700;
            color: white;
            """
        )

        layout.addWidget(title)

        description = QLabel(
            "Synchronize subtitle timing with your video."
        )

        description.setStyleSheet(
            "color: #9ca3af;"
        )

        layout.addWidget(description)

        self.select_video_button = QPushButton(
            "Select Video"
        )

        layout.addWidget(
            self.select_video_button
        )

        self.select_subtitle_button = QPushButton(
            "Select Subtitle"
        )

        layout.addWidget(
            self.select_subtitle_button
        )

        self.sync_button = QPushButton(
            "Synchronize Subtitle"
        )

        self.sync_button.setMinimumHeight(
            42
        )

        layout.addWidget(
            self.sync_button
        )

        layout.addStretch()