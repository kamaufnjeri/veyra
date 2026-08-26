from PySide6.QtWidgets import (
    QMainWindow,
    QTabWidget,
)

from ui.subtitle_page import SubtitlePage
from cli.ui.media_download_page import DownloadPage
from cli.ui.subtitle_sync_page import SyncPage


class VeyraWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Veyra")
        self.resize(1050, 750)

        self.tabs = QTabWidget()

        self.subtitle_page = SubtitlePage()
        self.download_page = DownloadPage()
        self.sync_page = SyncPage()

        self.tabs.addTab(
            self.subtitle_page,
            "Subtitle Generation",
        )

        self.tabs.addTab(
            self.download_page,
            "Video Download",
        )

        self.tabs.addTab(
            self.sync_page,
            "Video / Subtitle Synchronization",
        )

        self.setCentralWidget(self.tabs)