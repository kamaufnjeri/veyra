from __future__ import annotations

import os
from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
    QPushButton,
    QDoubleSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)


class SubtitleOperationWidget(QWidget):
    """
    Operation-specific subtitle selector and controls.

    NORMAL OPERATIONS
        Exactly one subtitle is selected through a combo box.

    JOIN / MERGE
        Subtitles are selected using the Available subtitles list.

        Selected subtitles are shown separately in the
        "Selected subtitles" list.

        Selected order can be changed using Move Up / Move Down.

    JOIN
        Every selected subtitle has its own Offset.

        Every selected subtitle except the FIRST has its own Gap.

        Example:

            1. episode1.srt   Offset 0.000
            2. episode3.srt   Offset 1.200
                                  Gap 0.500
            3. episode2.srt   Offset -0.300
                                  Gap 1.000

    MERGE
        Selected subtitles have no offset or gap controls.

    The widget does NOT own the master subtitle list.

    The parent/controller should call:

        set_files([...])

    Optional video providers:

        set_video_time_provider(...)
        set_video_duration_provider(...)
    """

    selection_changed = Signal(object)

    MAX_MULTI_SUBTITLES = 4

    MULTI_OPERATIONS = {
        "join_parts",
        "merge_tracks",
    }

    def __init__(
        self,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)

        self._files: List[str] = []

        self._operation = "offset"

        self._sync_points: List[
            Dict[str, float]
        ] = []

        self._video_time_provider: Optional[
            Callable[[], float]
        ] = None

        self._video_duration_provider: Optional[
            Callable[[], Optional[float]]
        ] = None

        self._building_multi_ui = False

        # Per-file JOIN settings.
        #
        # {
        #     "/path/one.srt": {
        #         "offset": 0.0,
        #         "gap": 0.0,
        #     },
        # }
        self._join_settings: Dict[
            str,
            Dict[str, float],
        ] = {}

        self._build_ui()
        self._connect_signals()

        self._update_operation_ui()

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

        self.stack = QStackedWidget()

        self._build_normal_page()
        self._build_two_point_page()
        self._build_points_page()
        self._build_start_end_page()
        self._build_join_merge_page()
        self._build_simple_page()
        self._build_validate_page()

        root.addWidget(self.stack)

    # ==========================================================
    # NORMAL OPERATION
    # ==========================================================

    def _build_normal_page(self) -> None:
        page = QWidget()

        layout = QFormLayout(page)

        self.normal_subtitle_combo = QComboBox()

        self.normal_subtitle_combo.setMinimumWidth(
            250
        )

        layout.addRow(
            "Subtitle:",
            self.normal_subtitle_combo,
        )

        self.offset_spin = QDoubleSpinBox()

        self.offset_spin.setRange(
            -86400,
            86400,
        )

        self.offset_spin.setDecimals(3)
        self.offset_spin.setSingleStep(0.1)
        self.offset_spin.setSuffix(
            " sec"
        )

        layout.addRow(
            "Offset:",
            self.offset_spin,
        )

        self.stack.addWidget(page)

    # ==========================================================
    # TWO POINTS
    # ==========================================================

    def _build_two_point_page(self) -> None:
        page = QWidget()

        layout = QFormLayout(page)

        self.two_point_subtitle_combo = QComboBox()

        layout.addRow(
            "Subtitle:",
            self.two_point_subtitle_combo,
        )

        self.subtitle_point_1 = self._time_spin()
        self.video_point_1 = self._time_spin()

        self.subtitle_point_2 = self._time_spin()
        self.video_point_2 = self._time_spin()

        layout.addRow(
            "Subtitle point 1:",
            self.subtitle_point_1,
        )

        row1 = QHBoxLayout()

        row1.addWidget(
            self.video_point_1,
            1,
        )

        self.capture_video_1_button = QPushButton(
            "Use Current Video Time"
        )

        row1.addWidget(
            self.capture_video_1_button
        )

        layout.addRow(
            "Video point 1:",
            row1,
        )

        layout.addRow(
            "Subtitle point 2:",
            self.subtitle_point_2,
        )

        row2 = QHBoxLayout()

        row2.addWidget(
            self.video_point_2,
            1,
        )

        self.capture_video_2_button = QPushButton(
            "Use Current Video Time"
        )

        row2.addWidget(
            self.capture_video_2_button
        )

        layout.addRow(
            "Video point 2:",
            row2,
        )

        self.stack.addWidget(page)

    # ==========================================================
    # MULTI POINTS
    # ==========================================================

    def _build_points_page(self) -> None:
        page = QWidget()

        layout = QVBoxLayout(page)

        self.points_subtitle_combo = QComboBox()

        layout.addWidget(
            QLabel("Subtitle:")
        )

        layout.addWidget(
            self.points_subtitle_combo
        )

        description = QLabel(
            "Enter a subtitle timestamp, position the "
            "video, then add the synchronization point."
        )

        description.setWordWrap(True)

        layout.addWidget(description)

        row = QHBoxLayout()

        self.multi_subtitle_time = self._time_spin()

        self.add_point_button = QPushButton(
            "Add Current Video Time"
        )

        row.addWidget(
            QLabel("Subtitle:")
        )

        row.addWidget(
            self.multi_subtitle_time
        )

        row.addWidget(
            self.add_point_button
        )

        layout.addLayout(row)

        self.points_list = QListWidget()

        self.points_list.setMinimumHeight(
            140
        )

        layout.addWidget(
            self.points_list,
            1,
        )

        point_buttons = QHBoxLayout()

        self.remove_point_button = QPushButton(
            "Remove"
        )

        self.clear_points_button = QPushButton(
            "Clear"
        )

        point_buttons.addWidget(
            self.remove_point_button
        )

        point_buttons.addWidget(
            self.clear_points_button
        )

        point_buttons.addStretch()

        layout.addLayout(point_buttons)

        self.stack.addWidget(page)

    # ==========================================================
    # START / END
    # ==========================================================

    def _build_start_end_page(self) -> None:
        page = QWidget()

        layout = QFormLayout(page)

        self.start_end_subtitle_combo = QComboBox()

        layout.addRow(
            "Subtitle:",
            self.start_end_subtitle_combo,
        )

        self.start_end_duration = self._time_spin()

        layout.addRow(
            "Video duration:",
            self.start_end_duration,
        )

        self.use_video_duration_button = QPushButton(
            "Use Video Duration"
        )

        layout.addRow(
            "",
            self.use_video_duration_button,
        )

        self.stack.addWidget(page)

    # ==========================================================
    # JOIN / MERGE
    # ==========================================================

    def _build_join_merge_page(self) -> None:
        page = QWidget()

        layout = QVBoxLayout(page)

        self.multi_description = QLabel()

        self.multi_description.setWordWrap(
            True
        )

        layout.addWidget(
            self.multi_description
        )

        # ------------------------------------------------------
        # SELECTED
        # ------------------------------------------------------

        self.selected_title = QLabel(
            "Selected subtitles (2–4)"
        )

        layout.addWidget(
            self.selected_title
        )

        self.selected_subtitle_list = QListWidget()

        self.selected_subtitle_list.setMinimumHeight(
            170
        )

        self.selected_subtitle_list.setSpacing(
            4
        )

        layout.addWidget(
            self.selected_subtitle_list,
            1,
        )

        self.multi_selection_info = QLabel()

        self.multi_selection_info.setWordWrap(
            True
        )

        layout.addWidget(
            self.multi_selection_info
        )

        # ------------------------------------------------------
        # ORDER BUTTONS
        # ------------------------------------------------------

        order_row = QHBoxLayout()

        self.move_up_button = QPushButton(
            "↑"
        )

        self.move_up_button.setToolTip(
            "Move selected subtitle up"
        )

        self.move_down_button = QPushButton(
            "↓"
        )

        self.move_down_button.setToolTip(
            "Move selected subtitle down"
        )

        self.remove_selected_button = QPushButton(
            "Remove"
        )

        order_row.addStretch()

        order_row.addWidget(
            self.move_up_button
        )

        order_row.addWidget(
            self.move_down_button
        )

        order_row.addWidget(
            self.remove_selected_button
        )

        layout.addLayout(
            order_row
        )

        # ------------------------------------------------------
        # AVAILABLE
        # ------------------------------------------------------

        layout.addWidget(
            QLabel("Available subtitles")
        )

        self.available_subtitle_list = QListWidget()

        self.available_subtitle_list.setMinimumHeight(
            100
        )

        layout.addWidget(
            self.available_subtitle_list
        )

        # ------------------------------------------------------
        # OUTPUT
        # ------------------------------------------------------

        output_row = QHBoxLayout()

        output_row.addWidget(
            QLabel("Output:")
        )

        self.multi_operation_output_edit = QLineEdit()

        self.multi_operation_output_edit.setPlaceholderText(
            "Output subtitle file"
        )

        output_row.addWidget(
            self.multi_operation_output_edit,
            1,
        )

        self.multi_operation_output_button = QPushButton(
            "Browse"
        )

        output_row.addWidget(
            self.multi_operation_output_button
        )

        layout.addLayout(
            output_row
        )

        self.stack.addWidget(page)

    # ==========================================================
    # SIMPLE
    # ==========================================================

    def _build_simple_page(self) -> None:
        page = QWidget()

        layout = QVBoxLayout(page)

        self.simple_subtitle_combo = QComboBox()

        layout.addWidget(
            QLabel("Subtitle:")
        )

        layout.addWidget(
            self.simple_subtitle_combo
        )

        layout.addWidget(
            QLabel(
                "The loaded video's duration will be used."
            )
        )

        layout.addStretch()

        self.stack.addWidget(page)

    # ==========================================================
    # VALIDATE
    # ==========================================================

    def _build_validate_page(self) -> None:
        page = QWidget()

        layout = QVBoxLayout(page)

        self.validate_subtitle_combo = QComboBox()

        layout.addWidget(
            QLabel("Subtitle:")
        )

        layout.addWidget(
            self.validate_subtitle_combo
        )

        layout.addWidget(
            QLabel(
                "Validate the selected subtitle."
            )
        )

        layout.addStretch()

        self.stack.addWidget(page)

    # ==========================================================
    # SIGNALS
    # ==========================================================

    def _connect_signals(self) -> None:
        combos = (
            self.normal_subtitle_combo,
            self.two_point_subtitle_combo,
            self.points_subtitle_combo,
            self.start_end_subtitle_combo,
            self.simple_subtitle_combo,
            self.validate_subtitle_combo,
        )

        for combo in combos:
            combo.currentIndexChanged.connect(
                self._selection_changed
            )

        self.available_subtitle_list.itemChanged.connect(
            self._available_item_changed
        )

        self.selected_subtitle_list.currentItemChanged.connect(
            self._selected_current_item_changed
        )

        self.move_up_button.clicked.connect(
            self.move_selected_up
        )

        self.move_down_button.clicked.connect(
            self.move_selected_down
        )

        self.remove_selected_button.clicked.connect(
            self.remove_selected_item
        )

        self.capture_video_1_button.clicked.connect(
            self.capture_video_point_1
        )

        self.capture_video_2_button.clicked.connect(
            self.capture_video_point_2
        )

        self.add_point_button.clicked.connect(
            self.add_current_point
        )

        self.remove_point_button.clicked.connect(
            self.remove_selected_point
        )

        self.clear_points_button.clicked.connect(
            self.clear_points
        )

        self.use_video_duration_button.clicked.connect(
            self.use_video_duration
        )

        self.multi_operation_output_button.clicked.connect(
            self.select_output
        )

    # ==========================================================
    # VIDEO PROVIDERS
    # ==========================================================

    def set_video_time_provider(
        self,
        provider: Optional[Callable[[], float]],
    ) -> None:
        self._video_time_provider = provider

    def set_video_duration_provider(
        self,
        provider: Optional[
            Callable[[], Optional[float]]
        ],
    ) -> None:
        self._video_duration_provider = provider

    def _current_video_seconds(self) -> float:
        if self._video_time_provider is None:
            return 0.0

        try:
            value = self._video_time_provider()

            if value is None:
                return 0.0

            return max(
                0.0,
                float(value),
            )

        except Exception:
            return 0.0

    def _get_video_duration(
        self,
    ) -> Optional[float]:
        if self._video_duration_provider is None:
            return None

        try:
            value = self._video_duration_provider()

            if value is None:
                return None

            value = float(value)

            if value <= 0:
                return None

            return value

        except Exception:
            return None

    # ==========================================================
    # FILES
    # ==========================================================

    def set_files(
        self,
        files: List[str],
    ) -> None:
        cleaned: List[str] = []

        for filepath in files:
            if not filepath:
                continue

            filepath = str(filepath).strip()

            if not filepath:
                continue

            if filepath not in cleaned:
                cleaned.append(filepath)

        self._files = cleaned

        # Remove settings for files that no longer exist.
        self._join_settings = {
            filepath: settings
            for filepath, settings
            in self._join_settings.items()
            if filepath in self._files
        }

        self._populate_file_controls()

    def files(self) -> List[str]:
        return list(self._files)

    # ==========================================================
    # OPERATION
    # ==========================================================

    def set_operation(
        self,
        operation: str,
    ) -> None:
        valid_operations = {
            "offset",
            "two_points",
            "points",
            "start_end",
            "join_parts",
            "merge_tracks",
            "fit",
            "clamp",
            "validate",
        }

        if operation not in valid_operations:
            raise ValueError(
                f"Unsupported operation: {operation}"
            )

        self._operation = operation

        self._update_operation_ui()

    def operation(self) -> str:
        return self._operation

    def is_multi_operation(self) -> bool:
        return (
            self._operation
            in self.MULTI_OPERATIONS
        )

    # ==========================================================
    # POPULATE NORMAL CONTROLS
    # ==========================================================

    def _populate_file_controls(self) -> None:
        combos = [
            self.normal_subtitle_combo,
            self.two_point_subtitle_combo,
            self.points_subtitle_combo,
            self.start_end_subtitle_combo,
            self.simple_subtitle_combo,
            self.validate_subtitle_combo,
        ]

        for combo in combos:
            current = combo.currentData()

            combo.blockSignals(True)

            try:
                combo.clear()

                for filepath in self._files:
                    combo.addItem(
                        os.path.basename(filepath),
                        filepath,
                    )

                if current in self._files:
                    combo.setCurrentIndex(
                        self._files.index(current)
                    )

                elif self._files:
                    combo.setCurrentIndex(0)

            finally:
                combo.blockSignals(False)

        self._populate_multi_controls()

        self._emit_selection()

    # ==========================================================
    # MULTI CONTROLS
    # ==========================================================

    def _populate_multi_controls(self) -> None:
        """
        Rebuild Selected and Available lists.

        The selected order is preserved.

        If there are no selected subtitles yet and this is a
        JOIN/MERGE operation, the first two files are selected.
        """

        current_selected = self._selected_multi_files()

        # If nothing is selected, choose the first two.
        if (
            not current_selected
            and self.is_multi_operation()
        ):
            current_selected = self._files[:2]

        # Remove files that no longer exist.
        current_selected = [
            filepath
            for filepath in current_selected
            if filepath in self._files
        ]

        self._building_multi_ui = True

        try:
            self._rebuild_selected_list(
                current_selected
            )

            self._rebuild_available_list(
                current_selected
            )

        finally:
            self._building_multi_ui = False

        self._update_multi_info()

    def _rebuild_selected_list(
        self,
        selected_files: List[str],
    ) -> None:
        self.selected_subtitle_list.blockSignals(
            True
        )

        try:
            self.selected_subtitle_list.clear()

            for index, filepath in enumerate(
                selected_files,
                start=1,
            ):
                item = QListWidgetItem()

                item.setData(
                    Qt.UserRole,
                    filepath,
                )

                item.setSizeHint(
                    self._selected_row_size_hint()
                )

                self.selected_subtitle_list.addItem(
                    item
                )

                row = self._create_selected_row(
                    index,
                    filepath,
                )

                self.selected_subtitle_list.setItemWidget(
                    item,
                    row,
                )

        finally:
            self.selected_subtitle_list.blockSignals(
                False
            )

    def _rebuild_available_list(
        self,
        selected_files: List[str],
    ) -> None:
        selected_set = set(
            selected_files
        )

        self.available_subtitle_list.blockSignals(
            True
        )

        try:
            self.available_subtitle_list.clear()

            for index, filepath in enumerate(
                self._files,
                start=1,
            ):
                if filepath in selected_set:
                    continue

                item = QListWidgetItem()

                item.setData(
                    Qt.UserRole,
                    filepath,
                )

                item.setFlags(
                    item.flags()
                    | Qt.ItemIsUserCheckable
                    | Qt.ItemIsEnabled
                )

                item.setCheckState(
                    Qt.Unchecked
                )

                label = os.path.basename(
                    filepath
                )

                item.setText(
                    f"☐ {label}"
                )

                item.setToolTip(
                    filepath
                )

                self.available_subtitle_list.addItem(
                    item
                )

        finally:
            self.available_subtitle_list.blockSignals(
                False
            )

    # ==========================================================
    # SELECTED ROW
    # ==========================================================

    def _create_selected_row(
        self,
        index: int,
        filepath: str,
    ) -> QWidget:
        row = QWidget()

        layout = QHBoxLayout(row)

        layout.setContentsMargins(
            4,
            3,
            4,
            3,
        )

        layout.setSpacing(6)

        number_label = QLabel(
            str(index)
        )

        number_label.setMinimumWidth(
            22
        )

        number_label.setAlignment(
            Qt.AlignCenter
        )

        layout.addWidget(
            number_label
        )

        name_label = QLabel(
            os.path.basename(filepath)
        )

        name_label.setToolTip(
            filepath
        )

        name_label.setMinimumWidth(
            120
        )

        layout.addWidget(
            name_label,
            1,
        )

        if self._operation == "join_parts":
            settings = self._join_settings.setdefault(
                filepath,
                {
                    "offset": 0.0,
                    "gap": 0.0,
                },
            )

            offset_label = QLabel(
                "Offset"
            )

            layout.addWidget(
                offset_label
            )

            offset_spin = self._time_spin(
                minimum=-86400
            )

            offset_spin.setValue(
                settings.get(
                    "offset",
                    0.0,
                )
            )

            offset_spin.setFixedWidth(
                105
            )

            offset_spin.valueChanged.connect(
                lambda value, path=filepath:
                self._set_join_offset(
                    path,
                    value,
                )
            )

            layout.addWidget(
                offset_spin
            )

            # The first file has NO GAP.
            if index > 1:
                gap_label = QLabel(
                    "Gap"
                )

                layout.addWidget(
                    gap_label
                )

                gap_spin = self._time_spin(
                    minimum=-86400
                )

                gap_spin.setValue(
                    settings.get(
                        "gap",
                        0.0,
                    )
                )

                gap_spin.setFixedWidth(
                    105
                )

                gap_spin.valueChanged.connect(
                    lambda value, path=filepath:
                    self._set_join_gap(
                        path,
                        value,
                    )
                )

                layout.addWidget(
                    gap_spin
                )

        return row

    @staticmethod
    def _selected_row_size_hint():
        from PySide6.QtCore import QSize

        return QSize(
            0,
            48,
        )

    # ==========================================================
    # JOIN SETTINGS
    # ==========================================================

    def _set_join_offset(
        self,
        filepath: str,
        value: float,
    ) -> None:
        settings = self._join_settings.setdefault(
            filepath,
            {
                "offset": 0.0,
                "gap": 0.0,
            },
        )

        settings["offset"] = float(
            value
        )

    def _set_join_gap(
        self,
        filepath: str,
        value: float,
    ) -> None:
        settings = self._join_settings.setdefault(
            filepath,
            {
                "offset": 0.0,
                "gap": 0.0,
            },
        )

        settings["gap"] = float(
            value
        )

    # ==========================================================
    # MULTI SELECTION
    # ==========================================================

    def _selected_multi_files(self) -> List[str]:
        files: List[str] = []

        for index in range(
            self.selected_subtitle_list.count()
        ):
            item = self.selected_subtitle_list.item(
                index
            )

            if item is None:
                continue

            filepath = item.data(
                Qt.UserRole
            )

            if filepath:
                files.append(
                    str(filepath)
                )

        return files

    def _available_item_changed(
        self,
        item: QListWidgetItem,
    ) -> None:
        if self._building_multi_ui:
            return

        if item.checkState() != Qt.Checked:
            return

        filepath = item.data(
            Qt.UserRole
        )

        if not filepath:
            return

        selected = self._selected_multi_files()

        if filepath in selected:
            return

        if len(selected) >= self.MAX_MULTI_SUBTITLES:
            self._building_multi_ui = True

            try:
                item.setCheckState(
                    Qt.Unchecked
                )

            finally:
                self._building_multi_ui = False

            self._update_multi_info()

            return

        selected.append(
            str(filepath)
        )

        self._rebuild_multi_lists(
            selected
        )

        self._emit_selection()

    def _rebuild_multi_lists(
        self,
        selected: List[str],
    ) -> None:
        self._building_multi_ui = True

        try:
            self._rebuild_selected_list(
                selected
            )

            self._rebuild_available_list(
                selected
            )

            self._update_multi_info()

        finally:
            self._building_multi_ui = False

    def _selected_current_item_changed(
        self,
        current: Optional[QListWidgetItem],
        previous: Optional[QListWidgetItem],
    ) -> None:
        self._update_multi_info()

    # ==========================================================
    # REMOVE
    # ==========================================================

    def remove_selected_item(self) -> None:
        row = (
            self.selected_subtitle_list.currentRow()
        )

        if row < 0:
            return

        selected = self._selected_multi_files()

        if row >= len(selected):
            return

        selected.pop(row)

        self._rebuild_multi_lists(
            selected
        )

        self._emit_selection()

    # ==========================================================
    # ORDER
    # ==========================================================

    def move_selected_up(self) -> None:
        row = (
            self.selected_subtitle_list.currentRow()
        )

        if row <= 0:
            return

        selected = self._selected_multi_files()

        if row >= len(selected):
            return

        selected[row - 1], selected[row] = (
            selected[row],
            selected[row - 1],
        )

        self._rebuild_multi_lists(
            selected
        )

        self.selected_subtitle_list.setCurrentRow(
            row - 1
        )

        self._emit_selection()

    def move_selected_down(self) -> None:
        row = (
            self.selected_subtitle_list.currentRow()
        )

        if row < 0:
            return

        selected = self._selected_multi_files()

        if row >= len(selected) - 1:
            return

        selected[row], selected[row + 1] = (
            selected[row + 1],
            selected[row],
        )

        self._rebuild_multi_lists(
            selected
        )

        self.selected_subtitle_list.setCurrentRow(
            row + 1
        )

        self._emit_selection()

    # ==========================================================
    # MULTI INFO
    # ==========================================================

    def _update_multi_info(self) -> None:
        count = len(
            self._selected_multi_files()
        )

        if not self._files:
            self.multi_selection_info.setText(
                "No subtitles loaded."
            )

        elif count == 0:
            self.multi_selection_info.setText(
                "Select at least 2 subtitles."
            )

        elif count == 1:
            self.multi_selection_info.setText(
                "Select at least 1 more subtitle."
            )

        elif count >= self.MAX_MULTI_SUBTITLES:
            self.multi_selection_info.setText(
                f"{count} subtitles selected. "
                "Maximum reached."
            )

        else:
            self.multi_selection_info.setText(
                f"{count} subtitles selected."
            )

    # ==========================================================
    # NORMAL SELECTION
    # ==========================================================

    def selected_file(self) -> Optional[str]:
        combo = self._active_combo()

        if combo is None:
            return None

        filepath = combo.currentData()

        if not filepath:
            return None

        return str(filepath)

    def selected_files(self) -> List[str]:
        if self.is_multi_operation():
            return self._selected_multi_files()

        filepath = self.selected_file()

        if filepath is None:
            return []

        return [filepath]

    def _active_combo(
        self,
    ) -> Optional[QComboBox]:
        mapping = {
            "offset": self.normal_subtitle_combo,
            "two_points": self.two_point_subtitle_combo,
            "points": self.points_subtitle_combo,
            "start_end": self.start_end_subtitle_combo,
            "fit": self.simple_subtitle_combo,
            "clamp": self.simple_subtitle_combo,
            "validate": self.validate_subtitle_combo,
        }

        return mapping.get(
            self._operation
        )

    def _emit_selection(self) -> None:
        self.selection_changed.emit(
            self.selected_files()
        )

    def _selection_changed(
        self,
        *args: Any,
    ) -> None:
        self._emit_selection()

    # ==========================================================
    # OPERATION UI
    # ==========================================================

    def _update_operation_ui(self) -> None:
        operation = self._operation

        mapping = {
            "offset": 0,
            "two_points": 1,
            "points": 2,
            "start_end": 3,
            "join_parts": 4,
            "merge_tracks": 4,
            "fit": 5,
            "clamp": 5,
            "validate": 6,
        }

        self.stack.setCurrentIndex(
            mapping.get(
                operation,
                0,
            )
        )

        if operation == "join_parts":
            self.multi_description.setText(
                "Select 2–4 subtitle files. "
                "The selected order is the join order. "
                "Each subtitle has its own Offset; "
                "every subtitle after the first also has "
                "its own Gap."
            )

            self.selected_title.setText(
                "Selected subtitles (2–4)"
            )

        elif operation == "merge_tracks":
            self.multi_description.setText(
                "Select 2–4 subtitle files to merge "
                "into one subtitle track. "
                "Change their order with ↑ and ↓."
            )

            self.selected_title.setText(
                "Selected subtitles (2–4)"
            )

        self._rebuild_multi_lists(
            self._selected_multi_files()
        )

        self._emit_selection()

    # ==========================================================
    # TWO POINTS
    # ==========================================================

    def capture_video_point_1(self) -> None:
        self.video_point_1.setValue(
            self._current_video_seconds()
        )

    def capture_video_point_2(self) -> None:
        self.video_point_2.setValue(
            self._current_video_seconds()
        )

    # ==========================================================
    # MULTI POINTS
    # ==========================================================

    def add_current_point(self) -> None:
        video_time = (
            self._current_video_seconds()
        )

        subtitle_time = (
            self.multi_subtitle_time.value()
        )

        point = {
            "subtitle_time": subtitle_time,
            "video_time": video_time,
        }

        self._sync_points.append(
            point
        )

        self.points_list.addItem(
            (
                f"Subtitle {subtitle_time:.3f}s"
                f"  →  "
                f"Video {video_time:.3f}s"
            )
        )

    def remove_selected_point(self) -> None:
        row = self.points_list.currentRow()

        if row < 0:
            return

        self.points_list.takeItem(
            row
        )

        if row < len(
            self._sync_points
        ):
            self._sync_points.pop(
                row
            )

    def clear_points(self) -> None:
        self._sync_points.clear()
        self.points_list.clear()

    def sync_points(
        self,
    ) -> List[Dict[str, float]]:
        return [
            dict(point)
            for point in self._sync_points
        ]

    # ==========================================================
    # START / END
    # ==========================================================

    def use_video_duration(self) -> None:
        duration = self._get_video_duration()

        if duration is None:
            return

        self.start_end_duration.setValue(
            duration
        )

    # ==========================================================
    # OUTPUT
    # ==========================================================

    def select_output(self) -> None:
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "Save Subtitle",
            self._suggested_output_path(),
            (
                "SRT Files (*.srt);;"
                "VTT Files (*.vtt);;"
                "All Files (*)"
            ),
        )

        if filepath:
            self.multi_operation_output_edit.setText(
                filepath
            )

    def _suggested_output_path(self) -> str:
        files = self.selected_files()

        if files:
            base, _ = os.path.splitext(
                files[0]
            )

            if self._operation == "join_parts":
                return base + "_joined.srt"

            if self._operation == "merge_tracks":
                return base + "_merged.srt"

        return ""

    # ==========================================================
    # SETTINGS
    # ==========================================================

    def build_settings(
        self,
        video_duration: Optional[float] = None,
    ) -> Dict[str, Any]:

        operation = self._operation

        # ------------------------------------------------------
        # JOIN / MERGE
        # ------------------------------------------------------

        if operation in self.MULTI_OPERATIONS:

            files = self._selected_multi_files()

            if len(files) < 2:
                raise ValueError(
                    "Select at least two subtitle files."
                )

            if len(files) > self.MAX_MULTI_SUBTITLES:
                raise ValueError(
                    "Select no more than "
                    f"{self.MAX_MULTI_SUBTITLES} subtitles."
                )

            output = (
                self.multi_operation_output_edit
                .text()
                .strip()
            )

            if not output:
                raise ValueError(
                    "Select an output file."
                )

            # --------------------------------------------------
            # JOIN
            # --------------------------------------------------

            if operation == "join_parts":

                parts: List[Dict[str, Any]] = []

                for index, filepath in enumerate(
                    files
                ):
                    settings = (
                        self._join_settings.get(
                            filepath,
                            {
                                "offset": 0.0,
                                "gap": 0.0,
                            },
                        )
                    )

                    part: Dict[str, Any] = {
                        "subtitle_file": filepath,
                        "offset": float(
                            settings.get(
                                "offset",
                                0.0,
                            )
                        ),
                    }

                    # FIRST PART HAS OFFSET ONLY.
                    if index > 0:
                        part["gap"] = float(
                            settings.get(
                                "gap",
                                0.0,
                            )
                        )

                    parts.append(part)

                return {
                    "operation": operation,
                    "subtitle_files": files,
                    "parts": parts,
                    "output": output,
                }

            # --------------------------------------------------
            # MERGE
            # --------------------------------------------------

            return {
                "operation": operation,
                "subtitle_files": files,
                "output": output,
            }

        # ------------------------------------------------------
        # NORMAL OPERATIONS
        # ------------------------------------------------------

        subtitle = self.selected_file()

        if not subtitle:
            raise ValueError(
                "Select a subtitle file."
            )

        output = self._default_output_path(
            subtitle
        )

        # ------------------------------------------------------
        # OFFSET
        # ------------------------------------------------------

        if operation == "offset":

            return {
                "operation": operation,
                "subtitle_file": subtitle,
                "output": output,
                "offset": self.offset_spin.value(),
                "video_duration": video_duration,
            }

        # ------------------------------------------------------
        # TWO POINTS
        # ------------------------------------------------------

        if operation == "two_points":

            subtitle_point_1 = (
                self.subtitle_point_1.value()
            )

            subtitle_point_2 = (
                self.subtitle_point_2.value()
            )

            video_point_1 = (
                self.video_point_1.value()
            )

            video_point_2 = (
                self.video_point_2.value()
            )

            if subtitle_point_1 == subtitle_point_2:
                raise ValueError(
                    "Subtitle points must be different."
                )

            if video_point_1 == video_point_2:
                raise ValueError(
                    "Video points must be different."
                )

            return {
                "operation": operation,
                "subtitle_file": subtitle,
                "output": output,
                "subtitle_point_1": subtitle_point_1,
                "video_point_1": video_point_1,
                "subtitle_point_2": subtitle_point_2,
                "video_point_2": video_point_2,
                "video_duration": video_duration,
            }

        # ------------------------------------------------------
        # POINTS
        # ------------------------------------------------------

        if operation == "points":

            if len(self._sync_points) < 2:
                raise ValueError(
                    "At least two synchronization "
                    "points are required."
                )

            return {
                "operation": operation,
                "subtitle_file": subtitle,
                "output": output,
                "points": [
                    dict(point)
                    for point in self._sync_points
                ],
                "video_duration": video_duration,
            }

        # ------------------------------------------------------
        # START / END
        # ------------------------------------------------------

        if operation == "start_end":

            duration = (
                self.start_end_duration.value()
            )

            if duration <= 0:
                raise ValueError(
                    "Video duration must be greater than zero."
                )

            return {
                "operation": operation,
                "subtitle_file": subtitle,
                "output": output,
                "video_duration": duration,
            }

        # ------------------------------------------------------
        # FIT
        # ------------------------------------------------------

        if operation == "fit":

            if video_duration is None:
                raise ValueError(
                    "Load a video before fitting subtitles."
                )

            return {
                "operation": operation,
                "subtitle_file": subtitle,
                "output": output,
                "video_duration": video_duration,
            }

        # ------------------------------------------------------
        # CLAMP
        # ------------------------------------------------------

        if operation == "clamp":

            if video_duration is None:
                raise ValueError(
                    "Load a video before clamping subtitles."
                )

            return {
                "operation": operation,
                "subtitle_file": subtitle,
                "output": output,
                "video_duration": video_duration,
            }

        # ------------------------------------------------------
        # VALIDATE
        # ------------------------------------------------------

        if operation == "validate":

            return {
                "operation": "validate",
                "subtitle_file": subtitle,
            }

        raise ValueError(
            f"Unsupported operation: {operation}"
        )

    # ==========================================================
    # DEFAULT OUTPUT
    # ==========================================================

    @staticmethod
    def _default_output_path(
        subtitle: str,
    ) -> str:
        base, extension = os.path.splitext(
            subtitle
        )

        extension = (
            extension.lower()
            if extension
            else ".srt"
        )

        return (
            base + "_synced" + extension
        )

    # ==========================================================
    # TIME SPIN
    # ==========================================================

    @staticmethod
    def _time_spin(
        minimum: float = 0,
    ) -> QDoubleSpinBox:

        spin = QDoubleSpinBox()

        spin.setRange(
            minimum,
            86400,
        )

        spin.setDecimals(3)
        spin.setSingleStep(0.1)
        spin.setSuffix(" sec")

        return spin

    # ==========================================================
    # STYLE
    # ==========================================================

    def apply_style(self) -> None:
        self.setStyleSheet(
            """
            QComboBox,
            QLineEdit,
            QDoubleSpinBox {
                background: #0f172a;
                color: #e5e7eb;
                border: 1px solid #334155;
                border-radius: 7px;
                padding: 7px;
            }

            QComboBox:focus,
            QLineEdit:focus,
            QDoubleSpinBox:focus {
                border: 1px solid #3b82f6;
            }

            QListWidget {
                background: #0f172a;
                color: #e5e7eb;
                border: 1px solid #334155;
                border-radius: 7px;
                padding: 4px;
            }

            QListWidget::item {
                color: #e5e7eb;
                padding: 2px;
                border-radius: 5px;
            }

            QListWidget::item:selected {
                background: #1e40af;
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

            QPushButton:disabled {
                background: #111827;
                color: #6b7280;
            }

            QLabel {
                color: #cbd5e1;
            }

            QCheckBox {
                color: #e5e7eb;
                spacing: 8px;
            }
            """
        )

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.apply_style()