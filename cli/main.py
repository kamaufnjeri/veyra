from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
)

from cli.ui.subtitle_page import SubtitlePage
from cli.ui.media_download_page import MediaDownloadPage
from cli.ui.media_engine_page import MediaEnginePage

from core.temp_manager import (
    initialize_veyra_temp,
    cleanup_veyra_temp,
)


class VeyraWindow(QMainWindow):
    SIDEBAR_EXPANDED_WIDTH = 230
    SIDEBAR_COLLAPSED_WIDTH = 70

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Veyra")
        self.resize(1200, 800)

        self.sidebar_collapsed = False

        self.navigation_buttons = []

        self._build_ui()

    # ==========================================================
    # BUILD UI
    # ==========================================================

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
        self.sidebar.setFixedWidth(
            self.SIDEBAR_EXPANDED_WIDTH
        )

        sidebar_layout = QVBoxLayout(
            self.sidebar
        )

        sidebar_layout.setContentsMargins(
            10,
            15,
            10,
            15,
        )

        sidebar_layout.setSpacing(8)

        # ======================================================
        # HEADER
        # ======================================================

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(
            5,
            0,
            5,
            0,
        )

        header_layout.setSpacing(5)

        self.logo = QLabel("VEYRA")
        self.logo.setObjectName("Logo")

        header_layout.addWidget(
            self.logo,
            1,
        )

        self.toggle_button = QPushButton("☰")
        self.toggle_button.setObjectName(
            "SidebarToggle"
        )

        self.toggle_button.setFixedSize(
            38,
            38,
        )

        self.toggle_button.setCursor(
            Qt.PointingHandCursor
        )

        self.toggle_button.clicked.connect(
            self.toggle_sidebar
        )

        header_layout.addWidget(
            self.toggle_button
        )

        sidebar_layout.addLayout(
            header_layout
        )

        # ======================================================
        # SIDEBAR SUBTITLE
        # ======================================================

        self.sidebar_subtitle = QLabel(
            "Media Tools"
        )

        self.sidebar_subtitle.setObjectName(
            "SidebarSubtitle"
        )

        sidebar_layout.addWidget(
            self.sidebar_subtitle
        )

        sidebar_layout.addSpacing(18)

        # ======================================================
        # NAVIGATION CONTAINER
        # ======================================================

        self.navigation_container = QWidget()

        self.navigation_container.setObjectName(
            "NavigationContainer"
        )

        navigation_layout = QVBoxLayout(
            self.navigation_container
        )

        navigation_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        navigation_layout.setSpacing(4)

        # ======================================================
        # NAVIGATION BUTTONS
        # ======================================================

        self.subtitle_button = self._create_navigation_button(
            "Subtitle Generation",
            "SG",
            0,
        )

        self.download_button = self._create_navigation_button(
            "Media Download",
            "VD",
            1,
        )

        self.media_processing_button = (
            self._create_navigation_button(
                "Media Processing",
                "MP",
                2,
            )
        )

        navigation_layout.addWidget(
            self.subtitle_button
        )

        navigation_layout.addWidget(
            self.download_button
        )

        navigation_layout.addWidget(
            self.media_processing_button
        )

        navigation_layout.addStretch()

        sidebar_layout.addWidget(
            self.navigation_container,
            1,
        )

        # ======================================================
        # VERSION
        # ======================================================

        self.version = QLabel("Veyra")
        self.version.setObjectName(
            "Version"
        )

        sidebar_layout.addWidget(
            self.version
        )

        main_layout.addWidget(
            self.sidebar
        )

        # ======================================================
        # PAGE AREA
        # ======================================================

        self.pages = QStackedWidget()
        self.pages.setObjectName(
            "Pages"
        )

        main_layout.addWidget(
            self.pages,
            1,
        )

        # ======================================================
        # PAGES
        # ======================================================

        self.subtitle_page = SubtitlePage()

        self.media_download_page = (
            MediaDownloadPage()
        )

        self.media_processing_page = (
            MediaEnginePage()
        )

        # ======================================================
        # ADD PAGES
        # ======================================================

        self.pages.addWidget(
            self.subtitle_page
        )

        self.pages.addWidget(
            self.media_download_page
        )

        self.pages.addWidget(
            self.media_processing_page
        )

        # ======================================================
        # INITIAL PAGE
        # ======================================================

        self.pages.setCurrentIndex(0)

        self._set_active_button(
            self.subtitle_button
        )

    # ==========================================================
    # CREATE NAVIGATION BUTTON
    # ==========================================================

    def _create_navigation_button(
        self,
        full_text: str,
        short_text: str,
        page_index: int,
    ) -> QPushButton:

        button = QPushButton(
            full_text
        )

        button.setObjectName(
            "NavigationButton"
        )

        button.setProperty(
            "fullText",
            full_text,
        )

        button.setProperty(
            "shortText",
            short_text,
        )

        button.setProperty(
            "pageIndex",
            page_index,
        )

        button.setToolTip(
            full_text
        )

        button.setCursor(
            Qt.PointingHandCursor
        )

        button.setFixedHeight(
            48
        )

        button.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Fixed,
        )

        button.clicked.connect(
            lambda checked=False,
            index=page_index,
            btn=button:
                self._navigation_clicked(
                    index,
                    btn,
                )
        )

        self.navigation_buttons.append(
            button
        )

        return button

    # ==========================================================
    # NAVIGATION CLICK
    # ==========================================================

    def _navigation_clicked(
        self,
        page_index: int,
        button: QPushButton,
    ):
        self.pages.setCurrentIndex(
            page_index
        )

        self._set_active_button(
            button
        )

    # ==========================================================
    # ACTIVE BUTTON
    # ==========================================================

    def _set_active_button(
        self,
        active_button: QPushButton,
    ):
        for button in self.navigation_buttons:
            button.setProperty(
                "active",
                button is active_button,
            )

            button.style().unpolish(
                button
            )

            button.style().polish(
                button
            )

            button.update()

    # ==========================================================
    # TOGGLE SIDEBAR
    # ==========================================================

    def toggle_sidebar(self):
        self.sidebar_collapsed = (
            not self.sidebar_collapsed
        )

        if self.sidebar_collapsed:
            self._collapse_sidebar()
        else:
            self._expand_sidebar()

    # ==========================================================
    # COLLAPSE
    # ==========================================================

    def _collapse_sidebar(self):
        self.sidebar.setFixedWidth(
            self.SIDEBAR_COLLAPSED_WIDTH
        )

        self.logo.hide()
        self.sidebar_subtitle.hide()
        self.version.hide()

        for button in self.navigation_buttons:
            button.setText(
                button.property(
                    "shortText"
                )
            )

            button.setToolTip(
                button.property(
                    "fullText"
                )
            )

            button.setStyleSheet(
                """
                QPushButton {
                    text-align: center;
                    padding: 0px;
                }
                """
            )

        self.toggle_button.setText("☰")

    # ==========================================================
    # EXPAND
    # ==========================================================

    def _expand_sidebar(self):
        self.sidebar.setFixedWidth(
            self.SIDEBAR_EXPANDED_WIDTH
        )

        self.logo.show()
        self.sidebar_subtitle.show()
        self.version.show()

        for button in self.navigation_buttons:
            button.setText(
                button.property(
                    "fullText"
                )
            )

            button.setToolTip("")

            button.setStyleSheet("")

    # ==========================================================
    # STYLE
    # ==========================================================

    def _apply_style(self):
        self.setStyleSheet(
            """
            /* ==================================================
               MAIN WINDOW
               ================================================== */

            QMainWindow {
                background: #111827;
            }

            /* ==================================================
               SIDEBAR
               ================================================== */

            #Sidebar {
                background: #0b1220;
                border-right: 1px solid #1f2937;
            }

            /* ==================================================
               LOGO
               ================================================== */

            #Logo {
                color: #ffffff;
                font-size: 26px;
                font-weight: 800;
                padding-left: 6px;
            }

            #SidebarSubtitle {
                color: #6b7280;
                font-size: 12px;
                padding-left: 6px;
            }

            /* ==================================================
               TOGGLE
               ================================================== */

            #SidebarToggle {
                background: transparent;
                color: #9ca3af;
                border: none;
                border-radius: 8px;
                font-size: 19px;
            }

            #SidebarToggle:hover {
                background: #172033;
                color: #ffffff;
            }

            #SidebarToggle:pressed {
                background: #1e293b;
            }

            /* ==================================================
               NAVIGATION
               ================================================== */

            #NavigationButton {
                background: transparent;
                color: #9ca3af;

                border: none;
                border-radius: 9px;

                text-align: left;

                padding-left: 14px;
                padding-right: 10px;

                font-size: 14px;
                font-weight: 500;
            }

            /* ==================================================
               NAVIGATION HOVER
               ================================================== */

            #NavigationButton:hover {
                background: #172033;
                color: #ffffff;
            }

            /* ==================================================
               ACTIVE PAGE
               ================================================== */

            #NavigationButton[active="true"] {
                background: #2563eb;
                color: #ffffff;
                font-weight: 600;
            }

            #NavigationButton[active="true"]:hover {
                background: #3b82f6;
            }

            /* ==================================================
               VERSION
               ================================================== */

            #Version {
                color: #4b5563;
                padding-left: 6px;
            }

            /* ==================================================
               PAGE AREA
               ================================================== */

            #Pages {
                background: #111827;
            }
            """
        )


# ==============================================================
# MAIN
# ==============================================================

def main() -> int:

    # ==========================================================
    # VEYRA TEMP DIRECTORY — STARTUP
    # ==========================================================

    initialize_veyra_temp()

    # ==========================================================
    # QT APPLICATION
    # ==========================================================

    app = QApplication(sys.argv)

    app.setApplicationName("Veyra")
    app.setOrganizationName("Veyra")

    # ==========================================================
    # VEYRA TEMP DIRECTORY — SHUTDOWN
    # ==========================================================

    app.aboutToQuit.connect(
        cleanup_veyra_temp
    )

    # ==========================================================
    # MAIN WINDOW
    # ==========================================================

    window = VeyraWindow()

    # Apply stylesheet after all widgets exist.
    window._apply_style()

    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())