import sys

from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class MainWindow(QWidget):

    def __init__(self):
        super().__init__()

        self.setWindowTitle(
            "Subtitle Batch Processor"
        )

        self.resize(700, 500)

        layout = QVBoxLayout(self)

        title = QLabel(
            "Subtitle Batch Processor"
        )

        button = QPushButton(
            "Select Media Files"
        )

        layout.addWidget(title)
        layout.addWidget(button)


app = QApplication(sys.argv)

window = MainWindow()
window.show()

sys.exit(app.exec())