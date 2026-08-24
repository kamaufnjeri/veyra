from __future__ import annotations

import os
import threading
from typing import Any, Callable, Dict, List, Optional


class AudioDownloader:
    """
    Audio downloader based on yt-dlp.

    Audio is extracted using FFmpeg through yt-dlp.
    """

    AUDIO_FORMAT = "mp3"

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
            settings
        )

        if not urls:

            raise ValueError(
                "No audio URL was provided."
            )

        options = self._build_options(
            settings,
            output_directory,
        )

        results: List[
            Dict[str, Any]
        ] = []

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
                            f"Downloading audio "
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
                            "yt-dlp returned no audio information."
                        )

                    for entry in self._flatten_entries(
                        info
                    ):

                        results.append(
                            self._build_result(
                                entry,
                                output_directory,
                            )
                        )

        finally:

            self._ydl = None

        return {
            "type": "audio",
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
    ) -> Dict[str, Any]:

        quality = settings.get(
            "audio_quality",
            "best",
        )

        retries = int(
            settings.get(
                "retries",
                10,
            )
        )

        fragments = int(
            settings.get(
                "fragments",
                4,
            )
        )

        playlist_folder = bool(
            settings.get(
                "playlist_folder",
                True,
            )
        )

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

        options: Dict[str, Any] = {

            "format": (
                "bestaudio/"
                "best"
            ),

            "outtmpl": output_template,

            "noplaylist": False,

            "concurrent_fragment_downloads": max(
                1,
                min(
                    32,
                    fragments,
                ),
            ),

            "retries": max(
                0,
                retries,
            ),

            "fragment_retries": max(
                0,
                retries,
            ),

            "continuedl": True,

            "progress_hooks": [
                self._progress_hook
            ],

            "postprocessor_hooks": [
                self._postprocessor_hook
            ],

            "quiet": True,

            "no_warnings": True,

            "ignoreerrors": False,

            "logger": _YTDLPLogger(
                self
            ),

            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": (
                        self.AUDIO_FORMAT
                    ),
                    "preferredquality": (
                        self._audio_quality(
                            quality
                        )
                    ),
                }
            ],

        }

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

        if settings.get(
            "sponsorblock",
            False,
        ):

            options[
                "sponsorblock_remove"
            ] = [
                "sponsor",
                "selfpromo",
                "interaction",
                "intro",
                "outro",
                "preview",
            ]

        return options

    @staticmethod
    def _audio_quality(
        quality: Any,
    ) -> str:

        quality = str(
            quality or "best"
        ).lower()

        if quality == "best":
            return "0"

        try:

            quality_int = int(
                quality
            )

        except (
            TypeError,
            ValueError,
        ):

            return "0"

        return str(
            max(
                0,
                min(
                    320,
                    quality_int,
                ),
            )
        )

    # ==========================================================
    # URLS
    # ==========================================================

    @staticmethod
    def _get_urls(
        settings: Dict[str, Any],
    ) -> List[str]:

        videos = settings.get(
            "videos",
            [],
        )

        urls = []

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
    # RESULTS
    # ==========================================================

    @staticmethod
    def _flatten_entries(
        info: Dict[str, Any],
    ) -> List[Dict[str, Any]]:

        entries = info.get(
            "entries"
        )

        if not entries:
            return [info]

        return [
            entry
            for entry in entries
            if entry
        ]

    @staticmethod
    def _build_result(
        info: Dict[str, Any],
        output_directory: str,
    ) -> Dict[str, Any]:

        filepath = (
            info.get(
                "_filename"
            )
            or info.get(
                "filename"
            )
        )

        requested = info.get(
            "requested_downloads"
        )

        if requested:

            for item in requested:

                candidate = (
                    item.get(
                        "filepath"
                    )
                    or item.get(
                        "filename"
                    )
                )

                if candidate:

                    filepath = candidate
                    break

        return {
            "id": info.get(
                "id"
            ),

            "title": info.get(
                "title"
            ),

            "url": (
                info.get(
                    "webpage_url"
                )
                or info.get(
                    "original_url"
                )
            ),

            "filepath": (
                os.path.abspath(
                    filepath
                )
                if filepath
                else None
            ),

            "duration": info.get(
                "duration"
            ),

            "output": output_directory,

            "type": "audio",
        }

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

            filename = os.path.basename(
                data.get(
                    "filename",
                    "",
                )
            )

            self._progress(
                "Downloading audio",
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
                "Audio download finished",
                os.path.basename(
                    data.get(
                        "filename",
                        "",
                    )
                ),
                100,
            )

    def _postprocessor_hook(
        self,
        data: Dict[str, Any],
    ) -> None:

        if data.get(
            "status"
        ) == "started":

            self._progress(
                "Extracting audio",
                "Audio",
                95,
            )

        elif data.get(
            "status"
        ) == "finished":

            self._progress(
                "Audio extraction complete",
                "Audio",
                98,
            )

    # ==========================================================
    # HELPERS
    # ==========================================================

    def _check_cancelled(self):

        if self._cancel_event.is_set():

            raise RuntimeError(
                "Audio download cancelled."
            )

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
        owner: AudioDownloader,
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