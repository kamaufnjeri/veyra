from __future__ import annotations

import glob
import os
import threading
from typing import Any, Callable, Dict, List, Optional


class SubtitleDownloader:
    """
    Subtitle downloader based on yt-dlp.

    Supported subtitle types:

        any
        original
        auto
        translated

    The downloader prefers:

        original
        ↓
        automatic
        ↓
        translated

    when "any" is selected.

    Actual subtitle selection is based on the requested
    language and available subtitle metadata.
    """

    def __init__(
        self,
        progress_callback: Optional[
            Callable[..., None]
        ] = None,
        error_callback: Optional[
            Callable[[Any], None]
        ] = None,
    ):

        self.progress_callback = (
            progress_callback
        )

        self.error_callback = (
            error_callback
        )

        self._cancel_event = threading.Event()

        self._ydl = None

    # ==========================================================
    # PUBLIC API
    # ==========================================================

    def download(
        self,
        settings: Dict[str, Any],
        media_result: Optional[
            Dict[str, Any]
        ] = None,
    ) -> Dict[str, Any]:

        self.reset_cancel()

        try:

            import yt_dlp

        except ImportError as exc:

            raise RuntimeError(
                "yt-dlp is not installed."
            ) from exc

        output_directory = self._prepare_output(
            settings
        )

        urls = self._get_urls(
            settings,
            media_result,
        )

        if not urls:

            raise ValueError(
                "No subtitle URL was provided."
            )

        subtitle_language = str(
            settings.get(
                "subtitle_language",
                "en",
            )
        ).strip().lower()

        subtitle_type = str(
            settings.get(
                "subtitle_type",
                "any",
            )
        ).strip().lower()

        options = self._build_options(
            settings,
            output_directory,
            subtitle_language,
            subtitle_type,
        )

        results = []

        try:

            with yt_dlp.YoutubeDL(
                options
            ) as ydl:

                self._ydl = ydl

                for index, url in enumerate(
                    urls,
                    start=1,
                ):

                    self._check_cancelled()

                    self._progress(
                        (
                            f"Downloading subtitles "
                            f"{index}/{len(urls)}"
                        ),
                        url,
                        0,
                    )

                    info = ydl.extract_info(
                        url,
                        download=True,
                    )

                    if not info:

                        raise RuntimeError(
                            "yt-dlp returned no subtitle information."
                        )

                    entries = self._flatten_entries(
                        info
                    )

                    for entry in entries:

                        filepath = (
                            self._find_subtitle_file(
                                output_directory,
                                entry,
                                subtitle_language,
                            )
                        )

                        results.append(
                            {
                                "id": entry.get(
                                    "id"
                                ),
                                "title": entry.get(
                                    "title"
                                ),
                                "url": (
                                    entry.get(
                                        "webpage_url"
                                    )
                                    or url
                                ),
                                "filepath": filepath,
                                "language": (
                                    subtitle_language
                                ),
                                "subtitle_type": (
                                    subtitle_type
                                ),
                                "type": "subtitle",
                            }
                        )

        finally:

            self._ydl = None

        return {
            "type": "subtitle",
            "items": results,
            "count": len(results),
            "output": output_directory,
            "cancelled": False,
        }

    def cancel(self) -> None:

        self._cancel_event.set()

        ydl = self._ydl

        if ydl is not None:

            try:

                downloader = getattr(
                    ydl,
                    "_downloader",
                    None,
                )

                if downloader:

                    close = getattr(
                        downloader,
                        "close",
                        None,
                    )

                    if callable(close):
                        close()

            except Exception:
                pass

    def reset_cancel(self) -> None:

        self._cancel_event.clear()

    # ==========================================================
    # OPTIONS
    # ==========================================================

    def _build_options(
        self,
        settings: Dict[str, Any],
        output_directory: str,
        language: str,
        subtitle_type: str,
    ) -> Dict[str, Any]:

        retries = int(
            settings.get(
                "retries",
                10,
            )
        )

        playlist_folder = bool(
            settings.get(
                "playlist_folder",
                True,
            )
        )

        # ------------------------------------------------------
        # OUTPUT
        # ------------------------------------------------------

        if playlist_folder:

            output_template = os.path.join(
                output_directory,
                "%(playlist_title,playlist)s",
                "%(title)s.%(ext)s",
            )

        else:

            output_template = os.path.join(
                output_directory,
                "%(title)s.%(ext)s",
            )

        # ------------------------------------------------------
        # SUBTITLE SELECTION
        # ------------------------------------------------------

        options: Dict[str, Any] = {

            "skip_download": True,

            "outtmpl": output_template,

            "subtitleslangs": [
                language
            ],

            "retries": max(
                0,
                retries,
            ),

            "fragment_retries": max(
                0,
                retries,
            ),

            "continuedl": True,

            "quiet": True,

            "no_warnings": True,

            "ignoreerrors": False,

            "writesubtitles": (
                subtitle_type
                in {
                    "any",
                    "original",
                }
            ),

            "writeautomaticsub": (
                subtitle_type
                in {
                    "any",
                    "auto",
                    "translated",
                }
            ),

            "progress_hooks": [
                self._progress_hook
            ],

            "postprocessor_hooks": [
                self._postprocessor_hook
            ],

            "logger": _YTDLPLogger(
                self
            ),

        }

        # ------------------------------------------------------
        # AUTO-TRANSLATED SUBTITLE
        #
        # yt-dlp uses the subtitle language requested by
        # subtitleslangs. For automatic captions, the service
        # requests that language.
        # ------------------------------------------------------

        if subtitle_type == "translated":

            options[
                "writesubtitles"
            ] = False

            options[
                "writeautomaticsub"
            ] = True

        # ------------------------------------------------------
        # COOKIES
        # ------------------------------------------------------

        if settings.get(
            "cookies",
            False,
        ):

            options[
                "cookiesfrombrowser"
            ] = (
                settings.get(
                    "cookie_browser",
                    "chrome",
                ),
            )

        return options

    # ==========================================================
    # URLS
    # ==========================================================

    @staticmethod
    def _get_urls(
        settings: Dict[str, Any],
        media_result: Optional[
            Dict[str, Any]
        ],
    ) -> List[str]:

        urls = []

        if media_result:

            items = media_result.get(
                "items",
                [],
            )

            if isinstance(
                items,
                list,
            ):

                for item in items:

                    if not isinstance(
                        item,
                        dict,
                    ):
                        continue

                    url = item.get(
                        "url"
                    )

                    if url:
                        urls.append(
                            str(url)
                        )

        if not urls:

            videos = settings.get(
                "videos",
                [],
            )

            if isinstance(
                videos,
                list,
            ):

                for item in videos:

                    if isinstance(
                        item,
                        dict,
                    ):

                        url = item.get(
                            "url"
                        )

                    else:

                        url = item

                    if url:
                        urls.append(
                            str(url).strip()
                        )

        if not urls:

            url = settings.get(
                "url"
            )

            if url:
                urls.append(
                    str(url).strip()
                )

        seen = set()
        unique = []

        for url in urls:

            if url in seen:
                continue

            seen.add(url)
            unique.append(url)

        return unique

    # ==========================================================
    # OUTPUT
    # ==========================================================

    @staticmethod
    def _prepare_output(
        settings: Dict[str, Any],
    ) -> str:

        output = str(
            settings.get(
                "output",
                "",
            )
            or ""
        ).strip()

        if not output:

            raise ValueError(
                "Output directory is required."
            )

        output = os.path.abspath(
            os.path.expanduser(
                output
            )
        )

        os.makedirs(
            output,
            exist_ok=True,
        )

        return output

    # ==========================================================
    # FIND SUBTITLE FILE
    # ==========================================================

    @staticmethod
    def _find_subtitle_file(
        output_directory: str,
        info: Dict[str, Any],
        language: str,
    ) -> Optional[str]:

        title = info.get(
            "title"
        )

        if not title:

            return None

        # Search recursively because playlist folders may
        # have been enabled.

        pattern = os.path.join(
            output_directory,
            "**",
            f"*{language}*.vtt",
        )

        matches = glob.glob(
            pattern,
            recursive=True,
        )

        if matches:

            return os.path.abspath(
                matches[-1]
            )

        pattern = os.path.join(
            output_directory,
            "**",
            f"*{language}*.srt",
        )

        matches = glob.glob(
            pattern,
            recursive=True,
        )

        if matches:

            return os.path.abspath(
                matches[-1]
            )

        return None

    # ==========================================================
    # ENTRIES
    # ==========================================================

    @staticmethod
    def _flatten_entries(
        info: Dict[str, Any],
    ) -> List[Dict[str, Any]]:

        entries = info.get(
            "entries"
        )

        if not entries:

            return [
                info
            ]

        return [
            entry
            for entry in entries
            if entry
        ]

    # ==========================================================
    # PROGRESS
    # ==========================================================

    def _progress_hook(
        self,
        data: Dict[str, Any],
    ) -> None:

        self._check_cancelled()

        status = data.get(
            "status"
        )

        filename = os.path.basename(
            data.get(
                "filename",
                "",
            )
        )

        if status == "downloading":

            downloaded = data.get(
                "downloaded_bytes",
                0,
            )

            total = (
                data.get(
                    "total_bytes"
                )
                or data.get(
                    "total_bytes_estimate"
                )
                or 0
            )

            percentage = 0

            if total:

                percentage = int(
                    downloaded
                    * 100
                    / total
                )

            self._progress(
                "Downloading subtitle",
                filename,
                percentage,
                self._format_bytes(
                    downloaded
                ),
                self._format_bytes(
                    data.get(
                        "speed"
                    )
                ),
                self._format_seconds(
                    data.get(
                        "eta"
                    )
                ),
            )

        elif status == "finished":

            self._progress(
                "Subtitle download finished",
                filename,
                100,
            )

    def _postprocessor_hook(
        self,
        data: Dict[str, Any],
    ) -> None:

        if data.get(
            "status"
        ) == "finished":

            self._progress(
                "Subtitle processing complete",
                "Subtitle",
                98,
            )

    # ==========================================================
    # CANCEL
    # ==========================================================

    def _check_cancelled(self):

        if self._cancel_event.is_set():

            raise RuntimeError(
                "Subtitle download cancelled."
            )

    # ==========================================================
    # HELPERS
    # ==========================================================

    def _progress(
        self,
        info: str,
        filename: str,
        percentage: int,
        downloaded: str = "--",
        speed: str = "--",
        eta: str = "--:--",
    ):

        if not self.progress_callback:
            return

        try:

            self.progress_callback(
                info,
                filename,
                percentage,
                downloaded,
                speed,
                eta,
            )

        except TypeError:

            try:

                self.progress_callback(
                    info,
                    filename,
                    percentage,
                )

            except Exception:
                pass

        except Exception:
            pass

    @staticmethod
    def _format_bytes(
        value: Any,
    ) -> str:

        if value is None:
            return "--"

        try:
            value = float(value)
        except (
            TypeError,
            ValueError,
        ):
            return "--"

        units = [
            "B",
            "KB",
            "MB",
            "GB",
            "TB",
        ]

        index = 0

        while (
            value >= 1024
            and index < len(units) - 1
        ):

            value /= 1024
            index += 1

        return (
            f"{value:.1f} "
            f"{units[index]}"
        )

    @staticmethod
    def _format_seconds(
        value: Any,
    ) -> str:

        if value is None:
            return "--:--"

        try:
            value = int(value)
        except (
            TypeError,
            ValueError,
        ):
            return "--:--"

        minutes, seconds = divmod(
            value,
            60,
        )

        hours, minutes = divmod(
            minutes,
            60,
        )

        if hours:

            return (
                f"{hours:02d}:"
                f"{minutes:02d}:"
                f"{seconds:02d}"
            )

        return (
            f"{minutes:02d}:"
            f"{seconds:02d}"
        )


class _YTDLPLogger:

    def __init__(
        self,
        owner: SubtitleDownloader,
    ):
        self.owner = owner

    def debug(self, message):
        pass

    def info(self, message):
        pass

    def warning(self, message):

        self.owner._progress(
            message,
            "yt-dlp",
            0,
        )

    def error(self, message):

        if self.owner.error_callback:

            try:
                self.owner.error_callback(
                    message
                )
            except Exception:
                pass