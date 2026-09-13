from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


OPERATIONS = [
    ("Convert", "convert"),
    ("Cut", "cut"),
    ("Join", "join"),
    ("Burn Subtitles", "burn_subtitles"),
    ("Mux", "mux"),
    ("Compress", "compress"),
    ("Extract", "extract"),
]


class OperationItem(QFrame):
    """
    A single clickable operation.

    Visual states:

        NORMAL
            White bold text
            Transparent background

        HOVER
            White bold text
            Strong highlighted background

        ACTIVE
            White bold text
            Strong blue background

        DISABLED
            Muted text
    """

    clicked = Signal(str)

    def __init__(
        self,
        label: str,
        value: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.label = label
        self.value = value

        self._active = False
        self._enabled = True

        self.setObjectName(
            "operationItem"
        )

        self.setMinimumHeight(44)

        self.setCursor(
            Qt.CursorShape.PointingHandCursor
        )

        layout = QHBoxLayout(self)

        layout.setContentsMargins(
            18,
            10,
            18,
            10,
        )

        layout.setSpacing(0)

        self.label_widget = QLabel(
            label
        )

        self.label_widget.setObjectName(
            "operationItemLabel"
        )

        self.label_widget.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )

        layout.addWidget(
            self.label_widget
        )

        self._update_style()

    def set_active(
        self,
        active: bool,
    ) -> None:
        self._active = active
        self._update_style()

    def set_enabled(
        self,
        enabled: bool,
    ) -> None:
        self._enabled = enabled

        self.setEnabled(
            enabled
        )

        if enabled:
            self.setCursor(
                Qt.CursorShape.PointingHandCursor
            )
        else:
            self.setCursor(
                Qt.CursorShape.ArrowCursor
            )

        self._update_style()

    def mousePressEvent(
        self,
        event,
    ) -> None:
        if (
            self._enabled
            and event.button()
            == Qt.MouseButton.LeftButton
        ):
            self.clicked.emit(
                self.value
            )

        event.accept()

    def _update_style(self) -> None:
        # ----------------------------------------------------------
        # DISABLED
        # ----------------------------------------------------------

        if not self._enabled:
            self.setStyleSheet(
                """
                QFrame#operationItem {
                    background: transparent;
                    border: 1px solid transparent;
                    border-radius: 8px;
                }

                QLabel#operationItemLabel {
                    color: #777777;
                    font-size: 14px;
                    font-weight: 700;
                }
                """
            )
            return

        # ----------------------------------------------------------
        # ACTIVE
        # ----------------------------------------------------------

        if self._active:
            self.setStyleSheet(
                """
                QFrame#operationItem {
                    background: #4169e1;
                    border: 1px solid #5f83ff;
                    border-radius: 8px;
                }

                QLabel#operationItemLabel {
                    color: #ffffff;
                    font-size: 14px;
                    font-weight: 700;
                }
                """
            )
            return

        # ----------------------------------------------------------
        # NORMAL + HOVER
        # ----------------------------------------------------------

        self.setStyleSheet(
            """
            QFrame#operationItem {
                background: transparent;
                border: 1px solid transparent;
                border-radius: 8px;
            }

            QFrame#operationItem:hover {
                background: #4b5563;
                border: 1px solid #6b7280;
            }

            QLabel#operationItemLabel {
                color: #ffffff;
                font-size: 14px;
                font-weight: 700;
            }

            QFrame#operationItem:hover QLabel#operationItemLabel {
                color: #ffffff;
                font-size: 14px;
                font-weight: 700;
            }
            """
        )


class OperationSelector(QGroupBox):
    """
    Horizontal operation selector.

    Operations are displayed as visible clickable
    operation cards.

    The selected operation remains highlighted.
    """

    operationChanged = Signal(str)

    def __init__(
        self,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            "Operation",
            parent,
        )

        self.items: list[
            OperationItem
        ] = []

        self._operation = (
            OPERATIONS[0][1]
        )

        self._enabled = True

        self._build_ui()

        self.set_operation(
            self._operation
        )

    def _build_ui(self) -> None:
        outer_layout = QVBoxLayout(
            self
        )

        outer_layout.setContentsMargins(
            10,
            10,
            10,
            10,
        )

        outer_layout.setSpacing(
            0
        )

        # ----------------------------------------------------------
        # HORIZONTAL SCROLL AREA
        # ----------------------------------------------------------

        self.scroll_area = QScrollArea()

        self.scroll_area.setObjectName(
            "operationScrollArea"
        )

        self.scroll_area.setWidgetResizable(
            True
        )

        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )

        self.scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self.scroll_area.setFrameShape(
            QFrame.Shape.NoFrame
        )

        self.scroll_area.setMinimumHeight(
            60
        )

        # ----------------------------------------------------------
        # CONTAINER
        # ----------------------------------------------------------

        container = QWidget()

        container.setObjectName(
            "operationContainer"
        )

        layout = QHBoxLayout(
            container
        )

        layout.setContentsMargins(
            0,
            4,
            0,
            4,
        )

        layout.setSpacing(
            8
        )

        # ----------------------------------------------------------
        # OPERATIONS
        # ----------------------------------------------------------

        for label, value in OPERATIONS:
            item = OperationItem(
                label=label,
                value=value,
                parent=container,
            )

            item.clicked.connect(
                self._operation_clicked
            )

            self.items.append(
                item
            )

            layout.addWidget(
                item
            )

        layout.addStretch()

        self.scroll_area.setWidget(
            container
        )

        outer_layout.addWidget(
            self.scroll_area
        )

        # ----------------------------------------------------------
        # SCROLL AREA STYLE
        # ----------------------------------------------------------

        self.setStyleSheet(
            """
            QScrollArea#operationScrollArea {
                background: transparent;
                border: none;
            }

            QScrollArea#operationScrollArea > QWidget {
                background: transparent;
            }

            QWidget#operationContainer {
                background: transparent;
            }
            """
        )

    @property
    def operation(self) -> str:
        return self._operation

    def set_operation(
        self,
        operation: str,
    ) -> None:
        valid_operations = {
            value
            for _, value in OPERATIONS
        }

        if operation not in valid_operations:
            return

        changed = (
            operation
            != self._operation
        )

        self._operation = operation

        for item in self.items:
            item.set_active(
                item.value
                == operation
            )

        if changed:
            self.operationChanged.emit(
                operation
            )

    def _operation_clicked(
        self,
        operation: str,
    ) -> None:
        self.set_operation(
            operation
        )

    def set_enabled(
        self,
        enabled: bool,
    ) -> None:
        self._enabled = enabled

        for item in self.items:
            item.set_enabled(
                enabled
            )

    def operation_items(
        self,
    ) -> list[tuple[str, str]]:
        return list(
            OPERATIONS
        )

