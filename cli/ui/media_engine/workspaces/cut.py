from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QHBoxLayout,
    QSpinBox,
    QWidget,
)

from media.models import CutterSettings
from jobs.media_engine_processor import MediaEngineJob

from .base import Workspace


class TimeInput(QWidget):
    changed = Signal()

    def __init__(
        self,
        parent=None,
    ):
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.hours = QSpinBox()
        self.hours.setRange(0, 23)
        self.hours.setSuffix(" h")

        self.minutes = QSpinBox()
        self.minutes.setRange(0, 59)
        self.minutes.setSuffix(" m")

        self.seconds = QDoubleSpinBox()
        self.seconds.setRange(0, 59.999)
        self.seconds.setDecimals(3)
        self.seconds.setSuffix(" s")

        layout.addWidget(self.hours)
        layout.addWidget(self.minutes)
        layout.addWidget(self.seconds)

        self.hours.valueChanged.connect(
            lambda _: self.changed.emit()
        )
        self.minutes.valueChanged.connect(
            lambda _: self.changed.emit()
        )
        self.seconds.valueChanged.connect(
            lambda _: self.changed.emit()
        )

    def value(self) -> float:
        return (
            self.hours.value() * 3600
            + self.minutes.value() * 60
            + self.seconds.value()
        )

    def set_value(
        self,
        seconds: float,
    ):
        seconds = max(0.0, float(seconds))

        hours = int(seconds // 3600)

        remainder = seconds - hours * 3600

        minutes = int(remainder // 60)

        seconds = remainder - minutes * 60

        self.hours.setValue(hours)
        self.minutes.setValue(minutes)
        self.seconds.setValue(seconds)


class CutWorkspace(Workspace):
    def __init__(self, parent=None):
        super().__init__(
            "Cut Settings",
            parent,
        )

        form = QFormLayout()

        self.mode = QComboBox()
        self.mode.addItem(
            "Fixed Duration",
            "duration",
        )
        self.mode.addItem(
            "Number of Parts",
            "parts",
        )
        self.mode.addItem(
            "Timestamps",
            "timestamps",
        )
        self.mode.addItem(
            "Start / End",
            "start_end",
        )

        self.duration = QDoubleSpinBox()
        self.duration.setRange(0.001, 999999)
        self.duration.setValue(60.0)
        self.duration.setSuffix(" seconds")

        self.parts = QSpinBox()
        self.parts.setRange(2, 9999)
        self.parts.setValue(2)

        self.start = TimeInput()
        self.end = TimeInput()
        self.end.set_value(60)

        self.cut_subtitles = QCheckBox(
            "Cut subtitles"
        )
        self.cut_subtitles.setChecked(True)

        form.addRow(
            "Cut Method:",
            self.mode,
        )
        form.addRow(
            "Duration:",
            self.duration,
        )
        form.addRow(
            "Parts:",
            self.parts,
        )
        form.addRow(
            "Start:",
            self.start,
        )
        form.addRow(
            "End:",
            self.end,
        )
        form.addRow(
            "",
            self.cut_subtitles,
        )

        self.layout.addLayout(form)

        self.timestamp_input = TimeInput()

        timestamp_buttons = QHBoxLayout()

        self.add_timestamp_button = QPushButton(
            "Add Timestamp"
        )
        self.remove_timestamp_button = QPushButton(
            "Remove"
        )
        self.clear_timestamp_button = QPushButton(
            "Clear"
        )

        timestamp_buttons.addWidget(
            self.add_timestamp_button
        )
        timestamp_buttons.addWidget(
            self.remove_timestamp_button
        )
        timestamp_buttons.addWidget(
            self.clear_timestamp_button
        )

        self.timestamp_list = QListWidget()

        self.layout.addWidget(
            self.timestamp_input
        )
        self.layout.addLayout(
            timestamp_buttons
        )
        self.layout.addWidget(
            self.timestamp_list
        )

        self.mode.currentIndexChanged.connect(
            self._mode_changed
        )

        self.add_timestamp_button.clicked.connect(
            self._add_timestamp
        )
        self.remove_timestamp_button.clicked.connect(
            self._remove_timestamp
        )
        self.clear_timestamp_button.clicked.connect(
            self.timestamp_list.clear
        )

        self._mode_changed()

    def _mode_changed(self):
        mode = self.mode.currentData()

        self.duration.setVisible(
            mode == "duration"
        )

        self.parts.setVisible(
            mode == "parts"
        )

        self.start.setVisible(
            mode == "start_end"
        )

        self.end.setVisible(
            mode == "start_end"
        )

        self.timestamp_input.setVisible(
            mode == "timestamps"
        )
        self.timestamp_list.setVisible(
            mode == "timestamps"
        )
        self.add_timestamp_button.setVisible(
            mode == "timestamps"
        )
        self.remove_timestamp_button.setVisible(
            mode == "timestamps"
        )
        self.clear_timestamp_button.setVisible(
            mode == "timestamps"
        )

    def _add_timestamp(self):
        value = self.timestamp_input.value()

        if value <= 0:
            return

        values = self._timestamps()

        if value in values:
            return

        values.append(value)
        values.sort()

        self.timestamp_list.clear()

        for timestamp in values:
            item = QListWidgetItem(
                self._format_timestamp(timestamp)
            )

            item.setData(
                32,
                timestamp,
            )

            self.timestamp_list.addItem(item)

    def _remove_timestamp(self):
        row = self.timestamp_list.currentRow()

        if row >= 0:
            self.timestamp_list.takeItem(row)

    def _timestamps(self) -> list[float]:
        values = []

        for row in range(
            self.timestamp_list.count()
        ):
            value = self.timestamp_list.item(row).data(32)

            try:
                values.append(float(value))
            except (TypeError, ValueError):
                pass

        return values

    @staticmethod
    def _format_timestamp(
        seconds: float,
    ) -> str:
        hours = int(seconds // 3600)

        seconds -= hours * 3600

        minutes = int(seconds // 60)

        seconds -= minutes * 60

        return (
            f"{hours:02d}:"
            f"{minutes:02d}:"
            f"{seconds:06.3f}"
        )

    def build_jobs(
        self,
        media,
        output_directory,
        output_name,
        shared,
    ):
        mode = self.mode.currentData()

        common = dict(shared)

        if mode == "duration":
            duration = self.duration.value()

            if duration <= 0:
                raise ValueError(
                    "Duration must be greater than zero."
                )

            settings = CutterSettings(
                **common,
                mode="duration",
                duration=duration,
                cut_subtitles=self.cut_subtitles.isChecked(),
            )

        elif mode == "parts":
            parts = self.parts.value()

            if parts < 2:
                raise ValueError(
                    "Number of parts must be at least 2."
                )

            settings = CutterSettings(
                **common,
                mode="parts",
                parts=parts,
                cut_subtitles=self.cut_subtitles.isChecked(),
            )

        elif mode == "timestamps":
            timestamps = tuple(
                self._timestamps()
            )

            if not timestamps:
                raise ValueError(
                    "Add at least one timestamp."
                )

            settings = CutterSettings(
                **common,
                mode="timestamps",
                timestamps=timestamps,
                cut_subtitles=self.cut_subtitles.isChecked(),
            )

        else:
            start = self.start.value()
            end = self.end.value()

            if end <= start:
                raise ValueError(
                    "End must be greater than start."
                )

            settings = CutterSettings(
                **common,
                mode="start_end",
                start=start,
                end=end,
                cut_subtitles=self.cut_subtitles.isChecked(),
            )

        settings.validate()

        jobs = []

        for source in media:
            directory = (
                output_directory
                or source.parent
            )

            name = output_name.strip()

            if name:
                base = (
                    f"{source.stem}_{name}"
                    if len(media) > 1
                    else name
                )
            else:
                base = source.stem

            jobs.append(
                MediaEngineJob(
                    operation="cut",
                    inputs=(source,),
                    output=directory,
                    options={
                        "output_base_name": base,
                    },
                    settings=settings,
                )
            )

        return jobs

    def reset(self):
        self.mode.setCurrentIndex(0)
        self.duration.setValue(60)
        self.parts.setValue(2)
        self.start.set_value(0)
        self.end.set_value(60)
        self.cut_subtitles.setChecked(True)
        self.timestamp_list.clear()