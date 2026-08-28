from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
QComboBox,
QHBoxLayout,
QLabel,
QTableWidget,
QTableWidgetItem,
QVBoxLayout,
QWidget,
QHeaderView,
)

@dataclass
class SubtitleCue:
    number: int
    start_ms: int
    end_ms: int
    text: str

class SubtitlePreviewWidget(QWidget):
    """
    Subtitle preview widget.


    Displays subtitle files as:

        # | Start | End | Words

    Supports:
        - SRT
        - VTT
        - Multiple subtitle files
        - Subtitle track switching
        - Current subtitle highlighting
        - Automatic scrolling to the active subtitle
        - HTML/VTT tag cleanup
    """

    subtitle_loaded = Signal(str)
    cue_changed = Signal(int)

    def __init__(
        self,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)

        self.subtitle_files: List[str] = []
        self.cues_by_file: dict[str, List[SubtitleCue]] = {}

        self.current_file: Optional[str] = None
        self.current_cue_index = -1

        self._build_ui()

    # ==========================================================
    # UI
    # ==========================================================

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        root.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        root.setSpacing(8)

        # ------------------------------------------------------
        # TRACK SELECTOR
        # ------------------------------------------------------

        track_row = QHBoxLayout()

        track_row.addWidget(
            QLabel("Subtitle File:")
        )

        self.track_combo = QComboBox()

        self.track_combo.setPlaceholderText(
            "No subtitle selected"
        )

        track_row.addWidget(
            self.track_combo,
            1,
        )

        root.addLayout(
            track_row
        )

        # ------------------------------------------------------
        # INFORMATION
        # ------------------------------------------------------

        self.info_label = QLabel(
            "No subtitle loaded."
        )

        self.info_label.setObjectName(
            "SubtitlePreviewInfo"
        )

        root.addWidget(
            self.info_label
        )

        # ------------------------------------------------------
        # SUBTITLE TABLE
        # ------------------------------------------------------

        self.cue_table = QTableWidget()

        self.cue_table.setColumnCount(4)

        self.cue_table.setHorizontalHeaderLabels(
            [
                "#",
                "Start",
                "End",
                "Words",
            ]
        )

        self.cue_table.setSelectionBehavior(
            QTableWidget.SelectRows
        )

        self.cue_table.setSelectionMode(
            QTableWidget.SingleSelection
        )

        self.cue_table.setEditTriggers(
            QTableWidget.NoEditTriggers
        )

        self.cue_table.setWordWrap(
            True
        )

        self.cue_table.setAlternatingRowColors(
            True
        )

        self.cue_table.verticalHeader().setVisible(
            False
        )

        # Column sizing
        header = self.cue_table.horizontalHeader()

        header.setSectionResizeMode(
            0,
            QHeaderView.ResizeToContents
        )

        header.setSectionResizeMode(
            1,
            QHeaderView.ResizeToContents
        )

        header.setSectionResizeMode(
            2,
            QHeaderView.ResizeToContents
        )

        header.setSectionResizeMode(
            3,
            QHeaderView.Stretch
        )

        self.cue_table.setMinimumHeight(
            350
        )

        root.addWidget(
            self.cue_table,
            1,
        )

        # Combo changes are handled here.
        self.track_combo.currentIndexChanged.connect(
            self._track_changed
        )

    # ==========================================================
    # FILE MANAGEMENT
    # ==========================================================

    def set_files(
        self,
        files: List[str],
    ) -> None:
        """
        Replace the available subtitle files.
        """

        previous = self.current_file

        self.subtitle_files = [
            filepath
            for filepath in files
            if filepath
            and os.path.isfile(filepath)
        ]

        self.track_combo.blockSignals(
            True
        )

        self.track_combo.clear()

        for filepath in self.subtitle_files:
            self.track_combo.addItem(
                os.path.basename(filepath),
                filepath,
            )

        self.track_combo.blockSignals(
            False
        )

        if not self.subtitle_files:
            self.current_file = None
            self.current_cue_index = -1

            self.cue_table.setRowCount(
                0
            )

            self.info_label.setText(
                "No subtitle loaded."
            )

            return

        if previous in self.subtitle_files:
            index = self.subtitle_files.index(
                previous
            )
        else:
            index = 0

        self.track_combo.setCurrentIndex(
            index
        )

        self.load_file(
            self.subtitle_files[index]
        )

    def add_file(
        self,
        filepath: str,
    ) -> None:

        if not filepath:
            return

        if filepath in self.subtitle_files:
            return

        if not os.path.isfile(filepath):
            return

        self.subtitle_files.append(
            filepath
        )

        self.track_combo.addItem(
            os.path.basename(filepath),
            filepath,
        )

        if self.current_file is None:
            self.track_combo.setCurrentIndex(
                0
            )

            self.load_file(
                filepath
            )

    def remove_file(
        self,
        filepath: str,
    ) -> None:

        if filepath not in self.subtitle_files:
            return

        index = self.subtitle_files.index(
            filepath
        )

        self.subtitle_files.pop(
            index
        )

        self.cues_by_file.pop(
            filepath,
            None,
        )

        self.track_combo.removeItem(
            index
        )

        if not self.subtitle_files:
            self.current_file = None
            self.current_cue_index = -1

            self.cue_table.setRowCount(
                0
            )

            self.info_label.setText(
                "No subtitle loaded."
            )

            return

        new_index = min(
            index,
            len(self.subtitle_files) - 1,
        )

        self.track_combo.setCurrentIndex(
            new_index
        )

    # ==========================================================
    # TRACK CHANGED
    # ==========================================================

    def _track_changed(
        self,
        index: int,
    ) -> None:

        if index < 0:
            return

        filepath = self.track_combo.itemData(
            index
        )

        if not filepath:
            return

        self.load_file(
            filepath
        )

    # ==========================================================
    # LOADING
    # ==========================================================

    def load_file(
        self,
        filepath: str,
    ) -> bool:

        if not filepath:
            return False

        if not os.path.isfile(filepath):
            self.info_label.setText(
                "Subtitle file does not exist."
            )

            return False

        try:

            if filepath not in self.cues_by_file:

                cues = self._parse_file(
                    filepath
                )

                self.cues_by_file[
                    filepath
                ] = cues

            else:

                cues = self.cues_by_file[
                    filepath
                ]

        except Exception as exc:

            self.info_label.setText(
                f"Subtitle error: {exc}"
            )

            return False

        self.current_file = filepath
        self.current_cue_index = -1

        self._display_cues(
            cues
        )

        self.subtitle_loaded.emit(
            filepath
        )

        return True

    # ==========================================================
    # PARSING
    # ==========================================================

    def _parse_file(
        self,
        filepath: str,
    ) -> List[SubtitleCue]:

        extension = os.path.splitext(
            filepath
        )[1].lower()

        with open(
            filepath,
            "r",
            encoding="utf-8-sig",
        ) as file:

            content = file.read()

        if extension == ".vtt":
            return self._parse_vtt(
                content
            )

        return self._parse_srt(
            content
        )

    # ==========================================================
    # SRT
    # ==========================================================

    def _parse_srt(
        self,
        content: str,
    ) -> List[SubtitleCue]:

        # IMPORTANT:
        # SRT cues are separated by blank lines.
        blocks = re.split(
            r"\r?\n\s*\r?\n",
            content.strip(),
        )

        cues: List[SubtitleCue] = []

        for block in blocks:

            lines = [
                line.strip("\ufeff")
                for line in block.splitlines()
            ]

            if not lines:
                continue

            timing_index = -1

            for index, line in enumerate(lines):

                if "-->" in line:
                    timing_index = index
                    break

            if timing_index < 0:
                continue

            timing = lines[
                timing_index
            ]

            parts = timing.split(
                "-->",
                1,
            )

            if len(parts) != 2:
                continue

            start_text = parts[0].strip()

            end_text = parts[1].strip()

            # SRT normally has no cue settings,
            # but removing anything after whitespace
            # makes this parser more tolerant.
            end_text = end_text.split(
                None,
                1,
            )[0]

            try:

                start_ms = self._parse_timestamp(
                    start_text
                )

                end_ms = self._parse_timestamp(
                    end_text
                )

            except ValueError:
                continue

            text_lines = lines[
                timing_index + 1:
            ]

            text = "\n".join(
                text_lines
            ).strip()

            text = self._clean_subtitle_text(
                text
            )

            if not text:
                continue

            cues.append(
                SubtitleCue(
                    number=len(cues) + 1,
                    start_ms=start_ms,
                    end_ms=end_ms,
                    text=text,
                )
            )

        return cues

    # ==========================================================
    # VTT
    # ==========================================================

    def _parse_vtt(
        self,
        content: str,
    ) -> List[SubtitleCue]:

        blocks = re.split(
            r"\r?\n\s*\r?\n",
            content.strip(),
        )

        cues: List[SubtitleCue] = []

        for block in blocks:

            lines = [
                line.strip("\ufeff")
                for line in block.splitlines()
            ]

            if not lines:
                continue

            # Ignore WEBVTT header.
            if lines[0].strip().upper().startswith(
                "WEBVTT"
            ):
                continue

            # Ignore NOTE blocks.
            if lines[0].strip().upper().startswith(
                "NOTE"
            ):
                continue

            timing_index = -1

            for index, line in enumerate(lines):

                if "-->" in line:
                    timing_index = index
                    break

            if timing_index < 0:
                continue

            parts = lines[
                timing_index
            ].split(
                "-->",
                1,
            )

            if len(parts) != 2:
                continue

            start_text = parts[0].strip()

            end_text = parts[1].strip()

            # VTT may have settings after the end time:
            #
            # 00:00:02.000 position:10%
            #
            end_text = end_text.split(
                None,
                1,
            )[0]

            try:

                start_ms = self._parse_timestamp(
                    start_text
                )

                end_ms = self._parse_timestamp(
                    end_text
                )

            except ValueError:
                continue

            text_lines = lines[
                timing_index + 1:
            ]

            text = "\n".join(
                text_lines
            ).strip()

            text = self._clean_subtitle_text(
                text
            )

            if not text:
                continue

            cues.append(
                SubtitleCue(
                    number=len(cues) + 1,
                    start_ms=start_ms,
                    end_ms=end_ms,
                    text=text,
                )
            )

        return cues

    # ==========================================================
    # TEXT CLEANING
    # ==========================================================

    @staticmethod
    def _clean_subtitle_text(
        text: str,
    ) -> str:

        # Remove common HTML/VTT tags.
        text = re.sub(
            r"<[^>]+>",
            "",
            text,
        )

        # Remove ASS-style formatting.
        text = re.sub(
            r"\{\\[^}]*\}",
            "",
            text,
        )

        # Decode common entities.
        text = (
            text.replace(
                "&nbsp;",
                " ",
            )
            .replace(
                "&amp;",
                "&",
            )
            .replace(
                "&lt;",
                "<",
            )
            .replace(
                "&gt;",
                ">",
            )
            .replace(
                "&quot;",
                '"',
            )
            .replace(
                "&#39;",
                "'",
            )
        )

        # Keep subtitle line breaks readable.
        text = re.sub(
            r"\s*\n\s*",
            "\n",
            text,
        )

        return text.strip()

    # ==========================================================
    # TIMESTAMP
    # ==========================================================

    @staticmethod
    def _parse_timestamp(
        value: str,
    ) -> int:

        value = value.strip()

        value = value.replace(
            ",",
            ".",
        )

        parts = value.split(
            ":"
        )

        try:

            if len(parts) == 3:

                hours = int(
                    parts[0]
                )

                minutes = int(
                    parts[1]
                )

                seconds = float(
                    parts[2]
                )

            elif len(parts) == 2:

                hours = 0

                minutes = int(
                    parts[0]
                )

                seconds = float(
                    parts[1]
                )

            else:

                raise ValueError

            if hours < 0:
                raise ValueError

            if minutes < 0:
                raise ValueError

            if seconds < 0:
                raise ValueError

            if minutes >= 60:
                raise ValueError

            if seconds >= 60:
                raise ValueError

            total_seconds = (
                hours * 3600
                + minutes * 60
                + seconds
            )

            return int(
                round(
                    total_seconds * 1000
                )
            )

        except (
            ValueError,
            TypeError,
        ):

            raise ValueError(
                f"Invalid timestamp: {value}"
            )

    # ==========================================================
    # DISPLAY
    # ==========================================================

    def _display_cues(
        self,
        cues: List[SubtitleCue],
    ) -> None:

        self.cue_table.setRowCount(
            0
        )

        self.cue_table.setRowCount(
            len(cues)
        )

        for row, cue in enumerate(cues):

            number_item = QTableWidgetItem(
                str(cue.number)
            )

            number_item.setTextAlignment(
                Qt.AlignCenter
            )

            start_item = QTableWidgetItem(
                self._format_ms(
                    cue.start_ms
                )
            )

            start_item.setTextAlignment(
                Qt.AlignCenter
            )

            end_item = QTableWidgetItem(
                self._format_ms(
                    cue.end_ms
                )
            )

            end_item.setTextAlignment(
                Qt.AlignCenter
            )

            text_item = QTableWidgetItem(
                cue.text
            )

            text_item.setTextAlignment(
                Qt.AlignLeft
                | Qt.AlignVCenter
            )

            self.cue_table.setItem(
                row,
                0,
                number_item,
            )

            self.cue_table.setItem(
                row,
                1,
                start_item,
            )

            self.cue_table.setItem(
                row,
                2,
                end_item,
            )

            self.cue_table.setItem(
                row,
                3,
                text_item,
            )

        self.info_label.setText(
            f"{len(cues)} subtitle cue(s)"
        )

        self.cue_table.resizeRowsToContents()

    # ==========================================================
    # VIDEO SYNCHRONIZATION
    # ==========================================================

    def set_current_time(
        self,
        milliseconds: int,
    ) -> None:

        if not self.current_file:
            return

        cues = self.cues_by_file.get(
            self.current_file,
            [],
        )

        if not cues:
            return

        cue_index = self._find_cue(
            cues,
            milliseconds,
        )

        if cue_index == self.current_cue_index:
            return

        self.current_cue_index = cue_index

        if cue_index < 0:

            self.cue_table.clearSelection()

            return

        self.cue_table.setCurrentCell(
            cue_index,
            3,
        )

        self.cue_table.selectRow(
            cue_index
        )

        self.cue_table.scrollToItem(
            self.cue_table.item(
                cue_index,
                3,
            ),
            QTableWidget.PositionAtCenter,
        )

        self.cue_changed.emit(
            cue_index
        )

    @staticmethod
    def _find_cue(
        cues: List[SubtitleCue],
        milliseconds: int,
    ) -> int:

        for index, cue in enumerate(cues):

            if (
                cue.start_ms
                <= milliseconds
                < cue.end_ms
            ):
                return index

        return -1

    # ==========================================================
    # ACCESSORS
    # ==========================================================

    def current_cues(
        self,
    ) -> List[SubtitleCue]:

        if not self.current_file:
            return []

        return list(
            self.cues_by_file.get(
                self.current_file,
                [],
            )
        )

    def current_file_path(
        self,
    ) -> Optional[str]:

        return self.current_file

    # ==========================================================
    # TIME FORMAT
    # ==========================================================

    @staticmethod
    def _format_ms(
        milliseconds: int,
    ) -> str:

        milliseconds = max(
            0,
            int(milliseconds),
        )

        hours, remainder = divmod(
            milliseconds,
            3_600_000,
        )

        minutes, remainder = divmod(
            remainder,
            60_000,
        )

        seconds, ms = divmod(
            remainder,
            1000,
        )

        return (
            f"{hours:02d}:"
            f"{minutes:02d}:"
            f"{seconds:02d}."
            f"{ms:03d}"
        )

