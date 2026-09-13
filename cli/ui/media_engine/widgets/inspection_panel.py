from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtWidgets import (
    QGroupBox,
    QLabel,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class InspectionPanel(QGroupBox):
    def __init__(
        self,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("Inspection", parent)

        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        self.header = QLabel(
            "Select media to inspect."
        )
        self.header.setWordWrap(True)

        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setMinimumHeight(180)

        layout.addWidget(self.header)
        layout.addWidget(self.text)

    # =========================================================
    # PUBLIC API
    # =========================================================

    def clear(self) -> None:
        self.header.setText(
            "Select media to inspect."
        )
        self.text.clear()

    def show_path(
        self,
        path: Path,
    ) -> None:
        self.header.setText(
            f"Media: {path.name}"
        )

        self.text.setPlainText(
            "Inspecting media..."
        )

    def show_error(
        self,
        path: Path,
        error: Any,
    ) -> None:
        self.header.setText(
            f"Media: {path.name}"
        )

        self.text.setPlainText(
            f"Unable to inspect media.\n\n"
            f"{error}"
        )

    def show_cached(
        self,
        path: Path,
        value: Any,
    ) -> None:
        self.header.setText(
            f"Media: {path.name}"
        )

        self.text.setPlainText(
            self.format_readable(value)
        )

    # =========================================================
    # FORMAT
    # =========================================================

    def format_readable(
        self,
        value: Any,
        indent: int = 0,
    ) -> str:
        """
        Recursively format the complete inspection result.

        Nothing is discarded.
        Dictionaries, lists, tuples and nested structures are
        all displayed in a readable form instead of JSON blobs.
        """

        if isinstance(value, dict):
            lines: list[str] = []

            for key, item in value.items():
                label = self._humanize_key(
                    str(key)
                )

                if isinstance(
                    item,
                    dict,
                ):
                    lines.append(
                        f"{label}:"
                    )

                    nested = self.format_readable(
                        item,
                        indent + 1,
                    )

                    if nested:
                        lines.extend(
                            self._indent(
                                nested,
                                indent + 1,
                            )
                        )

                elif isinstance(
                    item,
                    (list, tuple),
                ):
                    lines.append(
                        f"{label}:"
                    )

                    nested = self.format_readable(
                        item,
                        indent + 1,
                    )

                    if nested:
                        lines.extend(
                            self._indent(
                                nested,
                                indent + 1,
                            )
                        )

                else:
                    lines.append(
                        f"{label}: "
                        f"{self._format_scalar(item)}"
                    )

            return "\n".join(lines)

        if isinstance(
            value,
            (list, tuple),
        ):
            lines = []

            for index, item in enumerate(
                value,
                start=1,
            ):
                if isinstance(
                    item,
                    dict,
                ):
                    lines.append(
                        f"Item {index}:"
                    )

                    nested = self.format_readable(
                        item,
                        indent + 1,
                    )

                    if nested:
                        lines.extend(
                            self._indent(
                                nested,
                                indent + 1,
                            )
                        )

                elif isinstance(
                    item,
                    (list, tuple),
                ):
                    lines.append(
                        f"Item {index}:"
                    )

                    nested = self.format_readable(
                        item,
                        indent + 1,
                    )

                    if nested:
                        lines.extend(
                            self._indent(
                                nested,
                                indent + 1,
                            )
                        )

                else:
                    lines.append(
                        f"{index}. "
                        f"{self._format_scalar(item)}"
                    )

            return "\n".join(lines)

        return self._format_scalar(
            value
        )

    # =========================================================
    # HELPERS
    # =========================================================

    @staticmethod
    def _indent(
        text: str,
        level: int,
    ) -> list[str]:
        prefix = "    " * level

        return [
            prefix + line
            for line in text.splitlines()
        ]

    @staticmethod
    def _humanize_key(
        key: str,
    ) -> str:
        return (
            key.replace(
                "_",
                " ",
            )
            .strip()
            .title()
        )

    @staticmethod
    def _format_scalar(
        value: Any,
    ) -> str:
        if value is None:
            return "—"

        if isinstance(
            value,
            bool,
        ):
            return "Yes" if value else "No"

        if isinstance(
            value,
            float,
        ):
            return f"{value:.3f}"

        return str(value)