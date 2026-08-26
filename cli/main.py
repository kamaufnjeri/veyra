from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from cli.ui.subtitle_page import SubtitlePage
from cli.ui.media_download_page import VideoDownloadPage
from cli.ui.subtitle_sync_page import SubtitleSyncPage


class VeyraWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Veyra")
        self.resize(1200, 800)

        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ======================================================
        # SIDEBAR
        # ======================================================

        self.sidebar = QFrame()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(230)

        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(15, 20, 15, 20)
        sidebar_layout.setSpacing(10)

        # Logo / application name
        logo = QLabel("VEYRA")
        logo.setObjectName("Logo")

        sidebar_layout.addWidget(logo)

        subtitle = QLabel("Media Subtitle Tools")
        subtitle.setObjectName("SidebarSubtitle")

        sidebar_layout.addWidget(subtitle)

        sidebar_layout.addSpacing(25)

        # Navigation
        self.navigation = QListWidget()
        self.navigation.setObjectName("Navigation")

        self._add_navigation_item(
            "Subtitle Generation",
            "subtitle",
        )

        self._add_navigation_item(
            "Video Download",
            "download",
        )

        self._add_navigation_item(
            "Subtitle Sync",
            "sync",
        )

        sidebar_layout.addWidget(
            self.navigation,
            1,
        )

        version = QLabel("Veyra")
        version.setObjectName("Version")

        sidebar_layout.addWidget(version)

        main_layout.addWidget(self.sidebar)

        # ======================================================
        # PAGE AREA
        # ======================================================

        self.pages = QStackedWidget()
        self.pages.setObjectName("Pages")

        main_layout.addWidget(
            self.pages,
            1,
        )

        # ======================================================
        # PAGES
        # ======================================================

        self.subtitle_page = SubtitlePage()

        self.video_download_page = VideoDownloadPage()

        self.subtitle_sync_page = SubtitleSyncPage()

        self.pages.addWidget(
            self.subtitle_page
        )

        self.pages.addWidget(
            self.video_download_page
        )

        self.pages.addWidget(
            self.subtitle_sync_page
        )

        # ======================================================
        # NAVIGATION
        # ======================================================

        self.navigation.currentRowChanged.connect(
            self.change_page
        )

        # Open first page
        self.navigation.setCurrentRow(0)

        # ======================================================
        # STYLE
        # ======================================================

        self._apply_style()

    # ==========================================================
    # NAVIGATION ITEM
    # ==========================================================

    def _add_navigation_item(
        self,
        text: str,
        page_id: str,
    ):
        item = QListWidgetItem(text)

        item.setData(
            Qt.UserRole,
            page_id,
        )

        self.navigation.addItem(item)

    # ==========================================================
    # CHANGE PAGE
    # ==========================================================

    def change_page(
        self,
        index: int,
    ):
        if index < 0:
            return

        self.pages.setCurrentIndex(index)

    # ==========================================================
    # STYLE
    # ==========================================================

    def _apply_style(self):
        self.setStyleSheet(
            """
            QMainWindow {
                background: #111827;
            }

            #Sidebar {
                background: #0b1220;
                border-right: 1px solid #1f2937;
            }

            #Logo {
                color: #ffffff;
                font-size: 26px;
                font-weight: 800;
                padding-left: 8px;
            }

            #SidebarSubtitle {
                color: #6b7280;
                font-size: 12px;
                padding-left: 8px;
            }

            #Navigation {
                background: transparent;
                border: none;
                outline: none;
            }

            #Navigation::item {
                color: #9ca3af;
                padding: 14px 12px;
                margin: 2px 0;
                border-radius: 8px;
            }

            #Navigation::item:hover {
                background: #172033;
                color: #ffffff;
            }

            #Navigation::item:selected {
                background: #2563eb;
                color: #ffffff;
                font-weight: 600;
            }

            #Version {
                color: #4b5563;
                padding-left: 8px;
            }

            #Pages {
                background: #111827;
            }
            """
        )


# ==============================================================
# MAIN
# ==============================================================

def main() -> int:
    app = QApplication(sys.argv)

    app.setApplicationName("Veyra")
    app.setOrganizationName("Veyra")

    window = VeyraWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())