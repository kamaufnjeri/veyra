from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFontDatabase
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QToolButton,
    QWidget,
)

from media.models import BurnerSettings
from jobs.media_engine_processor import MediaEngineJob

from ..widgets.media_group import MediaGroupWidget
from .base import Workspace


class BurnSubtitlesWorkspace(Workspace):
    """
    Workspace for permanently burning subtitles into video.

    Subtitle colors are represented in the UI and settings as
    standard HTML-style hex colors:

        #FFFFFF
        #FFFF00
        #00FFFF
        #00FF00
        #FFA500
        #FF69B4
    """

    # ==================================================================
    # COMMON COLORS
    # ==================================================================

    COMMON_COLORS: tuple[tuple[str, str], ...] = (
        ("White", "#FFFFFF"),
        ("Yellow", "#FFFF00"),
        ("Cyan", "#00FFFF"),
        ("Green", "#00FF00"),
        ("Orange", "#FFA500"),
        ("Pink", "#FF69B4"),
    )

    # ==================================================================
    # INIT
    # ==================================================================

    def __init__(self, parent=None) -> None:
        super().__init__(
            "Burn Subtitles",
            parent,
        )

        # ==================================================================
        # MEDIA GROUPS
        # ==================================================================

        self.groups = MediaGroupWidget(
            "burn",
            self,
        )

        self.layout.addWidget(
            self.groups
        )

        # ==================================================================
        # BURN SETTINGS
        # ==================================================================

        form = QFormLayout()

        # ==================================================================
        # FONT
        # ==================================================================

        self.font = self._create_font_combo()

        # ==================================================================
        # FONT SIZE
        # ==================================================================

        self.font_size = QComboBox()

        self.font_size.setEditable(
            True
        )

        self.font_size.addItems(
            [
                "Default",
                "16",
                "18",
                "20",
                "22",
                "24",
                "28",
                "32",
                "36",
                "40",
                "48",
                "56",
                "64",
            ]
        )

        self.font_size.setCurrentText(
            "20"
        )

        # ==================================================================
        # COLOR HEX
        # ==================================================================

        self.color_hex = QLineEdit()

        self.color_hex.setText(
            "#FFFFFF"
        )

        self.color_hex.setPlaceholderText(
            "#RRGGBB"
        )

        self.color_hex.setMaxLength(
            7
        )

        self.color_hex.setFixedWidth(
            100
        )

        self.color_hex.textChanged.connect(
            self._on_hex_changed
        )

        # ==================================================================
        # COLOR SWATCH
        # ==================================================================

        self.color_swatch = QToolButton()

        self.color_swatch.setFixedSize(
            42,
            28,
        )

        self.color_swatch.setCursor(
            Qt.PointingHandCursor
        )

        self.color_swatch.setToolTip(
            "Click to choose a color"
        )

        self.color_swatch.clicked.connect(
            self._choose_color
        )

        # ==================================================================
        # COLOR BUTTON
        # ==================================================================

        self.color_button = QPushButton(
            "Choose Color"
        )

        self.color_button.clicked.connect(
            self._choose_color
        )

        # ==================================================================
        # QUICK COLORS
        # ==================================================================

        self.color_presets = QComboBox()

        self.color_presets.addItem(
            "Quick colors"
        )

        for name, value in self.COMMON_COLORS:
            self.color_presets.addItem(
                name,
                value,
            )

        self.color_presets.currentIndexChanged.connect(
            self._on_preset_changed
        )

        # ==================================================================
        # COLOR LAYOUT
        # ==================================================================

        color_layout = QHBoxLayout()

        color_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        color_layout.setSpacing(
            6
        )

        color_layout.addWidget(
            self.color_swatch
        )

        color_layout.addWidget(
            self.color_hex
        )

        color_layout.addWidget(
            self.color_button
        )

        color_layout.addWidget(
            self.color_presets
        )

        color_layout.addStretch()

        color_widget = QWidget()

        color_widget.setLayout(
            color_layout
        )

        # ==================================================================
        # FORM
        # ==================================================================

        form.addRow(
            "Font:",
            self.font,
        )

        form.addRow(
            "Size:",
            self.font_size,
        )

        form.addRow(
            "Color:",
            color_widget,
        )

        self.layout.addLayout(
            form
        )

        # ==================================================================
        # INITIAL COLOR
        # ==================================================================

        self._current_color = "#FFFFFF"

        self._update_color(
            "#FFFFFF"
        )

    # ==================================================================
    # FONT
    # ==================================================================

    def _create_font_combo(self) -> QComboBox:
        """
        Create an editable font combo containing installed fonts.

        The user can:
            - select an installed font
            - type a font name manually
        """

        combo = QComboBox()

        combo.setEditable(
            True
        )

        combo.setInsertPolicy(
            QComboBox.NoInsert
        )

        fonts = list(
            QFontDatabase.families()
        )

        preferred_fonts = [
            "Arial",
            "DejaVu Sans",
            "Liberation Sans",
            "Noto Sans",
            "Roboto",
            "Open Sans",
        ]

        ordered_fonts: list[str] = []

        # --------------------------------------------------------------
        # Preferred fonts first
        # --------------------------------------------------------------

        for font_name in preferred_fonts:
            if font_name in fonts:
                ordered_fonts.append(
                    font_name
                )

        # --------------------------------------------------------------
        # Remaining installed fonts
        # --------------------------------------------------------------

        for font_name in sorted(
            fonts,
            key=str.casefold,
        ):
            if font_name not in ordered_fonts:
                ordered_fonts.append(
                    font_name
                )

        combo.addItems(
            ordered_fonts
        )

        # --------------------------------------------------------------
        # Default font
        # --------------------------------------------------------------

        if "Arial" in fonts:
            combo.setCurrentText(
                "Arial"
            )

        elif "DejaVu Sans" in fonts:
            combo.setCurrentText(
                "DejaVu Sans"
            )

        elif ordered_fonts:
            combo.setCurrentText(
                ordered_fonts[0]
            )

        return combo

    # ==================================================================
    # COLOR
    # ==================================================================

    @staticmethod
    def _normalize_hex(
        value: str,
    ) -> str | None:
        """
        Normalize a color into #RRGGBB.

        Accepts:

            FFFFFF
            #FFFFFF
            ffffff
            #ffffff
        """

        value = value.strip()

        if value.startswith("#"):
            value = value[1:]

        if len(value) != 6:
            return None

        try:
            int(
                value,
                16,
            )
        except ValueError:
            return None

        return f"#{value.upper()}"

    def _update_color(
        self,
        value: str,
    ) -> bool:
        """
        Update the selected color and synchronize all controls.
        """

        normalized = self._normalize_hex(
            value
        )

        if normalized is None:
            return False

        self._current_color = normalized

        # --------------------------------------------------------------
        # Update hex field without recursion.
        # --------------------------------------------------------------

        self.color_hex.blockSignals(
            True
        )

        self.color_hex.setText(
            normalized
        )

        self.color_hex.blockSignals(
            False
        )

        self.color_hex.setStyleSheet(
            ""
        )

        # --------------------------------------------------------------
        # Update swatch.
        # --------------------------------------------------------------

        self._update_color_swatch(
            normalized
        )

        # --------------------------------------------------------------
        # Select matching preset.
        # --------------------------------------------------------------

        matching_index = 0

        for index in range(
            1,
            self.color_presets.count(),
        ):
            preset = self.color_presets.itemData(
                index
            )

            if preset == normalized:
                matching_index = index
                break

        self.color_presets.blockSignals(
            True
        )

        self.color_presets.setCurrentIndex(
            matching_index
        )

        self.color_presets.blockSignals(
            False
        )

        return True

    def _update_color_swatch(
        self,
        value: str,
    ) -> None:
        color = QColor(
            value
        )

        if not color.isValid():
            return

        luminance = (
            0.299 * color.red()
            + 0.587 * color.green()
            + 0.114 * color.blue()
        )

        border_color = (
            "#000000"
            if luminance > 160
            else "#FFFFFF"
        )

        self.color_swatch.setStyleSheet(
            f"""
            QToolButton {{
                background-color: {value};
                border: 2px solid {border_color};
                border-radius: 4px;
            }}

            QToolButton:hover {{
                border: 2px solid #666666;
            }}
            """
        )

        self.color_swatch.setToolTip(
            value
        )

    def _on_hex_changed(
        self,
        value: str,
    ) -> None:
        """
        Handle manually entered hex colors.
        """

        normalized = self._normalize_hex(
            value
        )

        if normalized is None:
            self.color_hex.setStyleSheet(
                """
                QLineEdit {
                    border: 1px solid #d9534f;
                }
                """
            )

            return

        self.color_hex.setStyleSheet(
            ""

        )

        self._current_color = normalized

        self._update_color_swatch(
            normalized
        )

        # --------------------------------------------------------------
        # Match quick-color preset when possible.
        # --------------------------------------------------------------

        matching_index = 0

        for index in range(
            1,
            self.color_presets.count(),
        ):
            preset = self.color_presets.itemData(
                index
            )

            if preset == normalized:
                matching_index = index
                break

        self.color_presets.blockSignals(
            True
        )

        self.color_presets.setCurrentIndex(
            matching_index
        )

        self.color_presets.blockSignals(
            False
        )

    def _on_preset_changed(
        self,
        index: int,
    ) -> None:
        if index <= 0:
            return

        value = self.color_presets.itemData(
            index
        )

        if not isinstance(
            value,
            str,
        ):
            return

        self._update_color(
            value
        )

    def _choose_color(self) -> None:
        """
        Open the native Qt color picker.
        """

        current = QColor(
            self._current_color
        )

        color = QColorDialog.getColor(
            current,
            self,
            "Choose Subtitle Color",
        )

        if not color.isValid():
            return

        self._update_color(
            color.name(
                QColor.HexRgb
            )
        )

    # ==================================================================
    # MEDIA
    # ==================================================================
    
    def set_media(
        self,
        media: list[Path],
    ) -> None:
        """
        Synchronize working media.

        This is retained for compatibility with MediaEnginePage.
        Group Select... uses available media separately.
        """
        self.groups.set_media(
            media
        )

    def set_available_media(
        self,
        media: list[Path],
    ) -> None:
        """
        Files available to the group selection dialog.
        """
        self.groups.set_available_media(
            media
        )

    def set_subtitles(
        self,
        subtitles: list[Path],
    ) -> None:
        """
        Synchronize available subtitle files.
        """
        self.groups.set_subtitles(
            subtitles
        )

    def set_available_subtitles(
        self,
        subtitles: list[Path],
    ) -> None:
        """
        Files available to the subtitle selection dialog.
        """
        self.groups.set_available_subtitles(
            subtitles
        )

    def set_subtitles(
        self,
        subtitles: list[Path],
    ) -> None:
        self.groups.set_subtitles(
            subtitles
        )

    def set_selected_media(
        self,
        media: list[Path],
    ) -> None:
        self.groups.set_selected_media(
            media
        )

    def set_selected_subtitles(
        self,
        subtitles: list[Path],
    ) -> None:
        self.groups.set_selected_subtitles(
            subtitles
        )

    # ==================================================================
    # BUILD JOBS
    # ==================================================================

    def build_jobs(
        self,
        media,
        output_directory,
        output_name,
        shared,
    ):
        groups = self.groups.burn_data()

        if not groups:
            raise ValueError(
                "Create at least one burn group "
                "with a video and subtitle."
            )

        # --------------------------------------------------------------
        # FONT
        # --------------------------------------------------------------

        font_name = (
            self.font.currentText().strip()
        )

        if not font_name:
            raise ValueError(
                "Please choose or enter a subtitle font."
            )

        # --------------------------------------------------------------
        # FONT SIZE
        # --------------------------------------------------------------

        font_size_text = (
            self.font_size.currentText().strip()
        )

        if font_size_text == "Default":
            font_size = None

        else:
            try:
                font_size = int(
                    font_size_text
                )
            except ValueError as exc:
                raise ValueError(
                    "Subtitle font size must be "
                    "a valid number."
                ) from exc

            if font_size <= 0:
                raise ValueError(
                    "Subtitle font size must be "
                    "greater than zero."
                )

        # --------------------------------------------------------------
        # COLOR
        # --------------------------------------------------------------

        subtitle_color = self._normalize_hex(
            self.color_hex.text()
        )

        if subtitle_color is None:
            raise ValueError(
                "Subtitle color must be a valid "
                "hex color, for example #FFFFFF."
            )

        # --------------------------------------------------------------
        # VIDEO CODEC
        # --------------------------------------------------------------

        video_codec = shared["video_codec"]

        # Burning subtitles requires video encoding.
        if video_codec == "copy":
            video_codec = "libx264"

        # --------------------------------------------------------------
        # SETTINGS
        # --------------------------------------------------------------

        settings = BurnerSettings(
            video_codec=video_codec,
            audio_mode=shared["audio_mode"],
            audio_codec=shared["audio_codec"],
            preset=shared["preset"],
            crf=shared["crf"],
            audio_bitrate=shared["audio_bitrate"],
            pixel_format=shared["pixel_format"],
            subtitle_font=font_name,
            subtitle_font_size=font_size,
            subtitle_color=subtitle_color,
            overwrite=shared["overwrite"],
            faststart=shared["faststart"],
        )

        settings.validate()

        # --------------------------------------------------------------
        # BUILD JOBS
        # --------------------------------------------------------------

        jobs = []

        for index, group in enumerate(
            groups,
            start=1,
        ):
            # ----------------------------------------------------------
            # VIDEO
            # ----------------------------------------------------------

            if group.video is None:
                raise ValueError(
                    f"Burn Group {index} requires "
                    "a video."
                )

            # ----------------------------------------------------------
            # SUBTITLE
            # ----------------------------------------------------------

            if group.subtitle is None:
                raise ValueError(
                    f"Burn Group {index} requires "
                    "a subtitle."
                )

            # ----------------------------------------------------------
            # OUTPUT DIRECTORY
            # ----------------------------------------------------------

            directory = (
                output_directory
                or group.video.parent
            )

            # ----------------------------------------------------------
            # OUTPUT NAME
            # ----------------------------------------------------------

            name = output_name.strip()

            if name:
                if len(groups) > 1:
                    base = (
                        f"{group.video.stem}"
                        f"_{name}_{index}"
                    )
                else:
                    base = name

            else:
                if len(groups) == 1:
                    base = (
                        f"{group.video.stem}"
                        "_burned"
                    )
                else:
                    base = (
                        f"{group.video.stem}"
                        f"_burned_{index}"
                    )

            # ----------------------------------------------------------
            # EXTENSION
            # ----------------------------------------------------------

            extension = (
                group.video
                .suffix
                .lstrip(".")
                or "mp4"
            )

            # ----------------------------------------------------------
            # OUTPUT PATH
            # ----------------------------------------------------------

            output = self.output_path(
                directory,
                base,
                extension,
            )

            # ----------------------------------------------------------
            # JOB
            # ----------------------------------------------------------

            jobs.append(
                MediaEngineJob(
                    operation="burn_subtitles",
                    inputs=(
                        group.video,
                        group.subtitle,
                    ),
                    output=output,
                    settings=settings,
                )
            )

        return jobs

    # ==================================================================
    # RESET
    # ==================================================================

    def reset(self) -> None:
        self.groups.clear_groups()

        # --------------------------------------------------------------
        # FONT
        # --------------------------------------------------------------

        fonts = list(
            QFontDatabase.families()
        )

        if "Arial" in fonts:
            self.font.setCurrentText(
                "Arial"
            )

        elif "DejaVu Sans" in fonts:
            self.font.setCurrentText(
                "DejaVu Sans"
            )

        elif fonts:
            self.font.setCurrentText(
                sorted(
                    fonts,
                    key=str.casefold,
                )[0]
            )

        else:
            self.font.setCurrentText(
                ""
            )

        # --------------------------------------------------------------
        # FONT SIZE
        # --------------------------------------------------------------

        self.font_size.setCurrentText(
            "20"
        )

        # --------------------------------------------------------------
        # COLOR
        # --------------------------------------------------------------

        self._update_color(
            "#FFFFFF"
        )