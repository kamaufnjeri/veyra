from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
QFileDialog,
QFrame,
QGroupBox,
QHBoxLayout,
QLabel,
QListWidget,
QListWidgetItem,
QPushButton,
QScrollArea,
QSizePolicy,
QVBoxLayout,
QWidget,
)

from .media_selection_dialog import MediaSelectionDialog

# ==========================================================================

# FILE TYPES

# ==========================================================================

VIDEO_EXTENSIONS = {
".mp4",
".mkv",
".mov",
".avi",
".webm",
".m4v",
".ts",
".mpeg",
".mpg",
".3gp",
}

AUDIO_EXTENSIONS = {
".mp3",
".wav",
".flac",
".aac",
".m4a",
".ogg",
".opus",
".wma",
}

SUBTITLE_EXTENSIONS = {
".srt",
".ass",
".ssa",
".vtt",
".sub",
".sbv",
}

# ==========================================================================

# GROUP DATA

# ==========================================================================

@dataclass
class JoinGroup:
    video: list[Path] = field(default_factory=list)
    audio: list[Path] = field(default_factory=list)
    subtitles: list[Path] = field(default_factory=list)

@dataclass
class MuxGroup:
    video: Path | None = None
    audio: list[Path] = field(default_factory=list)
    subtitles: list[Path] = field(default_factory=list)

@dataclass
class BurnGroup:
    video: Path | None = None
    subtitle: Path | None = None

# ==========================================================================

# MEDIA GROUP COLUMN

# ==========================================================================

class MediaGroupColumn(QFrame):
    """
    One media-type column inside a group.


    The column is responsible for:
    - displaying files
    - ordering files
    - removing files
    - browsing for new files

    Selection from the shared Media Library is handled by
    MediaSelectionDialog, not by this widget directly.
    """

    filesChanged = Signal()
    filesAdded = Signal(object)
    selectRequested = Signal()

    def __init__(
        self,
        title: str,
        media_type: str,
        *,
        allow_multiple: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.title_text = title
        self.media_type = media_type
        self.allow_multiple = allow_multiple

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )

        self._build_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        title = QLabel(self.title_text)
        title.setStyleSheet("font-weight: 600;")
        layout.addWidget(title)

        self.list_widget = QListWidget()

        if self.allow_multiple:
            self.list_widget.setSelectionMode(
                QListWidget.SelectionMode.ExtendedSelection
            )
        else:
            self.list_widget.setSelectionMode(
                QListWidget.SelectionMode.SingleSelection
            )

        self.list_widget.itemSelectionChanged.connect(
            self._update_controls
        )

        layout.addWidget(self.list_widget)

        controls = QHBoxLayout()

        self.select_button = QPushButton("Select...")
        self.browse_button = QPushButton("Browse")

        self.move_up_button = QPushButton("↑")
        self.move_down_button = QPushButton("↓")
        self.remove_button = QPushButton("Remove Selected")

        self.move_up_button.setToolTip("Move selected item up")
        self.move_down_button.setToolTip("Move selected item down")

        self.select_button.clicked.connect(
            self.selectRequested.emit
        )
        self.browse_button.clicked.connect(self.browse)

        self.move_up_button.clicked.connect(
            self.move_selected_up
        )
        self.move_down_button.clicked.connect(
            self.move_selected_down
        )
        self.remove_button.clicked.connect(
            self.remove_selected
        )

        controls.addWidget(self.select_button)
        controls.addWidget(self.browse_button)
        controls.addStretch()

        controls.addWidget(self.move_up_button)
        controls.addWidget(self.move_down_button)
        controls.addWidget(self.remove_button)

        layout.addLayout(controls)

        self._update_controls()

    # ------------------------------------------------------------------
    # Files
    # ------------------------------------------------------------------

    def files(self) -> list[Path]:
        result: list[Path] = []

        for index in range(self.list_widget.count()):
            item = self.list_widget.item(index)
            path = item.data(Qt.ItemDataRole.UserRole)

            if path is not None:
                result.append(Path(path))

        return result

    def set_files(self, files: list[Path]) -> None:
        self.list_widget.blockSignals(True)

        self.list_widget.clear()

        seen: set[str] = set()

        for raw_path in files:
            path = Path(raw_path)
            key = str(path)

            if key in seen:
                continue

            seen.add(key)

            item = QListWidgetItem(path.name)
            item.setToolTip(str(path))
            item.setData(
                Qt.ItemDataRole.UserRole,
                path,
            )

            self.list_widget.addItem(item)

        self.list_widget.blockSignals(False)

        self.filesChanged.emit()
        self._update_controls()

    def add_file(
        self,
        path: Path,
        *,
        emit: bool = True,
    ) -> bool:
        path = Path(path)

        existing = {
            str(existing_path)
            for existing_path in self.files()
        }

        if str(path) in existing:
            return False

        item = QListWidgetItem(path.name)
        item.setToolTip(str(path))
        item.setData(
            Qt.ItemDataRole.UserRole,
            path,
        )

        self.list_widget.addItem(item)

        if emit:
            self.filesChanged.emit()

        self._update_controls()

        return True

    def add_files(
        self,
        files: list[Path],
        *,
        emit_added: bool = False,
    ) -> list[Path]:
        added: list[Path] = []

        for path in files:
            if self.add_file(path, emit=False):
                added.append(Path(path))

        if added:
            self.filesChanged.emit()

            if emit_added:
                self.filesAdded.emit(added)

        self._update_controls()

        return added

    def clear(self) -> None:
        if self.list_widget.count() == 0:
            return

        self.list_widget.clear()
        self.filesChanged.emit()
        self._update_controls()

    # ------------------------------------------------------------------
    # Selection dialog
    # ------------------------------------------------------------------

    def set_select_enabled(self, enabled: bool) -> None:
        self.select_button.setEnabled(enabled)

    # ------------------------------------------------------------------
    # Ordering
    # ------------------------------------------------------------------

    def remove_selected(self) -> None:
        selected_rows = sorted(
            {
                self.list_widget.row(item)
                for item in self.list_widget.selectedItems()
            },
            reverse=True,
        )

        if not selected_rows:
            return

        for row in selected_rows:
            self.list_widget.takeItem(row)

        self.filesChanged.emit()
        self._update_controls()

    def move_selected_up(self) -> None:
        selected_rows = [
            self.list_widget.row(item)
            for item in self.list_widget.selectedItems()
        ]

        if not selected_rows:
            return

        selected_rows.sort()

        if selected_rows[0] == 0:
            return

        for row in selected_rows:
            item = self.list_widget.takeItem(row)
            self.list_widget.insertItem(row - 1, item)
            item.setSelected(True)

        self.filesChanged.emit()

    def move_selected_down(self) -> None:
        selected_rows = [
            self.list_widget.row(item)
            for item in self.list_widget.selectedItems()
        ]

        if not selected_rows:
            return

        selected_rows.sort(reverse=True)

        if selected_rows[0] >= self.list_widget.count() - 1:
            return

        for row in selected_rows:
            item = self.list_widget.takeItem(row)
            self.list_widget.insertItem(row + 1, item)
            item.setSelected(True)

        self.filesChanged.emit()

    # ------------------------------------------------------------------
    # Browse
    # ------------------------------------------------------------------

    def browse(self) -> None:
        if self.media_type == "video":
            file_filter = (
                "Video Files (*.mp4 *.mkv *.mov *.avi *.webm "
                "*.m4v *.ts *.mpeg *.mpg *.3gp)"
            )
        elif self.media_type == "audio":
            file_filter = (
                "Audio Files (*.mp3 *.wav *.flac *.aac "
                "*.m4a *.ogg *.opus *.wma)"
            )
        elif self.media_type == "subtitle":
            file_filter = (
                "Subtitle Files (*.srt *.ass *.ssa *.vtt *.sub *.sbv)"
            )
        else:
            file_filter = "All Files (*)"

        if self.allow_multiple:
            paths, _ = QFileDialog.getOpenFileNames(
                self,
                f"Browse {self.title_text}",
                "",
                file_filter,
            )
        else:
            path, _ = QFileDialog.getOpenFileName(
                self,
                f"Browse {self.title_text}",
                "",
                file_filter,
            )

            paths = [path] if path else []

        if not paths:
            return

        self.add_files(
            [Path(path) for path in paths],
            emit_added=True,
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @Slot()
    def _update_controls(self) -> None:
        selected = self.list_widget.selectedItems()

        has_selection = bool(selected)

        self.move_up_button.setEnabled(
            self.allow_multiple and has_selection
        )
        self.move_down_button.setEnabled(
            self.allow_multiple and has_selection
        )
        self.remove_button.setEnabled(has_selection)


# ==========================================================================

# MEDIA GROUP CARD

# ==========================================================================

class MediaGroupCard(QGroupBox):
    """
    Represents one Join/Mux/Burn group.


    Group selections are local to this card.

    The card receives the shared available files through providers,
    but it never uses the Media Library's current selection directly.
    """

    removeRequested = Signal(object)
    mediaAdded = Signal(object)
    subtitlesAdded = Signal(object)

    def __init__(
        self,
        mode: str,
        index: int,
        *,
        available_media_provider: Callable[[], list[Path]] | None = None,
        available_subtitles_provider: Callable[[], list[Path]] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        if mode not in {"join", "mux", "burn"}:
            raise ValueError(
                f"Unsupported group mode: {mode}"
            )

        self.mode = mode
        self.index = index

        self._available_media_provider = (
            available_media_provider
        )
        self._available_subtitles_provider = (
            available_subtitles_provider
        )

        self._build_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self._update_title()

        layout = QVBoxLayout(self)

        header = QHBoxLayout()

        self.group_label = QLabel()
        self.group_label.setStyleSheet(
            "font-weight: 600;"
        )

        remove_button = QPushButton("Remove Group")
        remove_button.clicked.connect(
            lambda: self.removeRequested.emit(self)
        )

        header.addWidget(self.group_label)
        header.addStretch()
        header.addWidget(remove_button)

        layout.addLayout(header)

        columns_layout = QHBoxLayout()

        if self.mode == "join":
            self.video_column = self._create_column(
                "Video",
                "video",
                allow_multiple=True,
            )

            self.audio_column = self._create_column(
                "Audio",
                "audio",
                allow_multiple=True,
            )

            self.subtitle_column = self._create_column(
                "Subtitles",
                "subtitle",
                allow_multiple=True,
            )

            columns_layout.addWidget(self.video_column)
            columns_layout.addWidget(self.audio_column)
            columns_layout.addWidget(self.subtitle_column)

        elif self.mode == "mux":
            self.video_column = self._create_column(
                "Video",
                "video",
                allow_multiple=False,
            )

            self.audio_column = self._create_column(
                "Audio",
                "audio",
                allow_multiple=True,
            )

            self.subtitle_column = self._create_column(
                "Subtitles",
                "subtitle",
                allow_multiple=True,
            )

            columns_layout.addWidget(self.video_column)
            columns_layout.addWidget(self.audio_column)
            columns_layout.addWidget(self.subtitle_column)

        else:
            self.video_column = self._create_column(
                "Video",
                "video",
                allow_multiple=False,
            )

            self.subtitle_column = self._create_column(
                "Subtitle",
                "subtitle",
                allow_multiple=False,
            )

            columns_layout.addWidget(self.video_column)
            columns_layout.addWidget(self.subtitle_column)

        layout.addLayout(columns_layout)

        self.refresh_select_buttons()

    def _create_column(
        self,
        title: str,
        media_type: str,
        *,
        allow_multiple: bool,
    ) -> MediaGroupColumn:
        column = MediaGroupColumn(
            title,
            media_type,
            allow_multiple=allow_multiple,
            parent=self,
        )

        column.filesAdded.connect(
            self._column_files_added
        )

        column.selectRequested.connect(
            lambda column=column: self._select_column(
                column
            )
        )

        return column

    def _update_title(self) -> None:
        self.setTitle(f"Group {self.index}")

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------

    def _select_column(
        self,
        column: MediaGroupColumn,
    ) -> None:
        is_subtitle = (
            column.media_type == "subtitle"
        )

        if is_subtitle:
            provider = self._available_subtitles_provider
        else:
            provider = self._available_media_provider

        available = (
            provider()
            if provider is not None
            else []
        )

        if not available:
            return

        if is_subtitle:
            allowed_extensions = SUBTITLE_EXTENSIONS
        elif column.media_type == "video":
            allowed_extensions = VIDEO_EXTENSIONS
        else:
            allowed_extensions = AUDIO_EXTENSIONS

        dialog = MediaSelectionDialog(
            title=f"Select {column.title_text}",
            files=available,
            allowed_extensions=allowed_extensions,
            allow_multiple=column.allow_multiple,
            existing_files=column.files(),
            parent=self,
        )

        if dialog.exec() != dialog.DialogCode.Accepted:
            return

        selected = dialog.selected_files()

        if not selected:
            return

        if column.allow_multiple:
            column.add_files(
                selected,
                emit_added=False,
            )
        else:
            column.set_files(
                selected[:1]
            )

    # ------------------------------------------------------------------
    # Available files
    # ------------------------------------------------------------------

    def refresh_select_buttons(self) -> None:
        media = (
            self._available_media_provider()
            if self._available_media_provider is not None
            else []
        )

        subtitles = (
            self._available_subtitles_provider()
            if self._available_subtitles_provider is not None
            else []
        )

        if self.mode in {"join", "mux", "burn"}:
            self.video_column.set_select_enabled(
                self._has_extension(
                    media,
                    VIDEO_EXTENSIONS,
                )
            )

        if self.mode in {"join", "mux"}:
            self.audio_column.set_select_enabled(
                self._has_extension(
                    media,
                    AUDIO_EXTENSIONS,
                )
            )

            self.subtitle_column.set_select_enabled(
                self._has_extension(
                    subtitles,
                    SUBTITLE_EXTENSIONS,
                )
            )

        elif self.mode == "burn":
            self.subtitle_column.set_select_enabled(
                self._has_extension(
                    subtitles,
                    SUBTITLE_EXTENSIONS,
                )
            )

    @staticmethod
    def _has_extension(
        files: list[Path],
        extensions: set[str],
    ) -> bool:
        return any(
            Path(path).suffix.lower() in extensions
            for path in files
        )

    # ------------------------------------------------------------------
    # New files from Browse
    # ------------------------------------------------------------------

    @Slot(object)
    def _column_files_added(
        self,
        files: object,
    ) -> None:
        if not isinstance(files, list):
            return

        paths = [
            Path(path)
            for path in files
        ]

        sender = self.sender()

        if (
            isinstance(sender, MediaGroupColumn)
            and sender.media_type == "subtitle"
        ):
            self.subtitlesAdded.emit(paths)
        else:
            self.mediaAdded.emit(paths)

        self.refresh_select_buttons()

    # ------------------------------------------------------------------
    # Index
    # ------------------------------------------------------------------

    def set_index(self, index: int) -> None:
        self.index = index
        self._update_title()

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def join_data(self) -> JoinGroup:
        return JoinGroup(
            video=self.video_column.files(),
            audio=self.audio_column.files(),
            subtitles=self.subtitle_column.files(),
        )

    def mux_data(self) -> MuxGroup:
        videos = self.video_column.files()

        return MuxGroup(
            video=videos[0] if videos else None,
            audio=self.audio_column.files(),
            subtitles=self.subtitle_column.files(),
        )

    def burn_data(self) -> BurnGroup:
        videos = self.video_column.files()
        subtitles = self.subtitle_column.files()

        return BurnGroup(
            video=videos[0] if videos else None,
            subtitle=(
                subtitles[0]
                if subtitles
                else None
            ),
        )


# ==========================================================================

# MEDIA GROUP WIDGET

# ==========================================================================

class MediaGroupWidget(QWidget):
    """
    Reusable group manager for Join, Mux and Burn operations.


    There are two distinct concepts:

    1. available_media / available_subtitles
    Files that can be selected from the shared Media Library.

    2. group-local files
    Files actually selected into each group.

    Updating available files never overwrites group-local selections.
    """

    groupChanged = Signal()
    mediaAdded = Signal(object)
    subtitlesAdded = Signal(object)

    def __init__(
        self,
        mode: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        if mode not in {"join", "mux", "burn"}:
            raise ValueError(
                f"Unsupported group mode: {mode}"
            )

        self.mode = mode

        self.available_media: list[Path] = []
        self.available_subtitles: list[Path] = []

        self.group_cards: list[MediaGroupCard] = []

        self._build_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        title = QLabel("Groups")
        title.setStyleSheet(
            "font-size: 16px; font-weight: 700;"
        )
        layout.addWidget(title)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(
            QFrame.Shape.NoFrame
        )

        self.groups_container = QWidget()
        self.groups_layout = QVBoxLayout(
            self.groups_container
        )

        self.groups_layout.setAlignment(
            Qt.AlignmentFlag.AlignTop
        )

        self.scroll_area.setWidget(
            self.groups_container
        )

        layout.addWidget(self.scroll_area)

        add_group_button = QPushButton("Add Group")
        add_group_button.clicked.connect(
            self.add_group
        )

        layout.addWidget(add_group_button)

        self.add_group()

    # ------------------------------------------------------------------
    # Available media
    # ------------------------------------------------------------------

    def set_available_media(
        self,
        media: list[Path],
    ) -> None:
        self.available_media = [
            Path(path)
            for path in media
        ]

        self._refresh_select_buttons()

    def set_available_subtitles(
        self,
        subtitles: list[Path],
    ) -> None:
        self.available_subtitles = [
            Path(path)
            for path in subtitles
        ]

        self._refresh_select_buttons()

    # Compatibility aliases

    def set_media(
        self,
        media: list[Path],
    ) -> None:
        self.set_available_media(media)

    def set_subtitles(
        self,
        subtitles: list[Path],
    ) -> None:
        self.set_available_subtitles(subtitles)

    # ------------------------------------------------------------------
    # Group management
    # ------------------------------------------------------------------

    def add_group(self) -> MediaGroupCard:
        index = len(self.group_cards) + 1

        card = MediaGroupCard(
            self.mode,
            index,
            available_media_provider=lambda: list(
                self.available_media
            ),
            available_subtitles_provider=lambda: list(
                self.available_subtitles
            ),
            parent=self.groups_container,
        )

        card.removeRequested.connect(
            self.remove_group
        )

        card.mediaAdded.connect(
            self.mediaAdded.emit
        )

        card.subtitlesAdded.connect(
            self.subtitlesAdded.emit
        )

        self.group_cards.append(card)

        self.groups_layout.addWidget(card)

        card.refresh_select_buttons()

        self.groupChanged.emit()

        return card

    @Slot(object)
    def remove_group(
        self,
        card: object,
    ) -> None:
        if not isinstance(card, MediaGroupCard):
            return

        if card not in self.group_cards:
            return

        if len(self.group_cards) == 1:
            card.join_data() if self.mode == "join" else None

            if self.mode == "mux":
                data = card.mux_data()
                _ = data
            elif self.mode == "burn":
                data = card.burn_data()
                _ = data

            self._clear_card(card)
            self.groupChanged.emit()
            return

        self.group_cards.remove(card)

        self.groups_layout.removeWidget(card)
        card.deleteLater()

        self._renumber_groups()
        self.groupChanged.emit()

    @staticmethod
    def _clear_card(
        card: MediaGroupCard,
    ) -> None:
        if hasattr(card, "video_column"):
            card.video_column.clear()

        if hasattr(card, "audio_column"):
            card.audio_column.clear()

        if hasattr(card, "subtitle_column"):
            card.subtitle_column.clear()

    def _renumber_groups(self) -> None:
        for index, card in enumerate(
            self.group_cards,
            start=1,
        ):
            card.set_index(index)

    def _refresh_select_buttons(self) -> None:
        for card in self.group_cards:
            card.refresh_select_buttons()

    # ------------------------------------------------------------------
    # Group data
    # ------------------------------------------------------------------

    def groups(self) -> list[JoinGroup | MuxGroup | BurnGroup]:
        result: list[
            JoinGroup | MuxGroup | BurnGroup
        ] = []

        for card in self.group_cards:
            if self.mode == "join":
                data = card.join_data()

                if (
                    data.video
                    or data.audio
                    or data.subtitles
                ):
                    result.append(data)

            elif self.mode == "mux":
                data = card.mux_data()

                if (
                    data.video is not None
                    or data.audio
                    or data.subtitles
                ):
                    result.append(data)

            else:
                data = card.burn_data()

                if (
                    data.video is not None
                    or data.subtitle is not None
                ):
                    result.append(data)

        return result

    def join_data(self) -> list[JoinGroup]:
        if self.mode != "join":
            raise RuntimeError(
                "join_data() is only valid for join mode."
            )

        return [
            card.join_data()
            for card in self.group_cards
            if (
                card.join_data().video
                or card.join_data().audio
                or card.join_data().subtitles
            )
        ]

    def mux_data(self) -> list[MuxGroup]:
        if self.mode != "mux":
            raise RuntimeError(
                "mux_data() is only valid for mux mode."
            )

        return [
            card.mux_data()
            for card in self.group_cards
            if (
                card.mux_data().video is not None
                or card.mux_data().audio
                or card.mux_data().subtitles
            )
        ]

    def burn_data(self) -> list[BurnGroup]:
        if self.mode != "burn":
            raise RuntimeError(
                "burn_data() is only valid for burn mode."
            )

        return [
            card.burn_data()
            for card in self.group_cards
            if (
                card.burn_data().video is not None
                or card.burn_data().subtitle is not None
            )
        ]

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def clear(self) -> None:
        for card in self.group_cards:
            self._clear_card(card)

        self.groupChanged.emit()

    def reset(self) -> None:
        for card in list(self.group_cards):
            self.groups_layout.removeWidget(card)
            card.deleteLater()

        self.group_cards.clear()

        self.add_group()

        self.groupChanged.emit()

