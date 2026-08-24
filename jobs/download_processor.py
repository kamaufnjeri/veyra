from __future__ import annotations

import os
import signal
import threading

from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
)

from core.media_info import MediaInfo
from services.media_service import MediaService


class JobCancelled(Exception):
    """
    Raised when a media job is cancelled.
    """


class MediaJobProcessor:
    """
    High-level media job processor.

    Exactly four download modes:

        video
        audio
        subtitles
        video_subtitles

    MediaInfo:
        metadata only.

    MediaService:
        actual media download
        subtitle download
        media processing
        encoding/remuxing.

    Progress callback:

        callback(
            info,
            filename,
            percentage,
            downloaded,
            speed,
            eta,
        )
    """

    DOWNLOAD_MODES = {
        "video_subtitles",
        "video",
        "audio",
        "subtitles",
    }

    OVERWRITE_MODES = {
        "keep",
        "ask",
        "overwrite",
    }

    def __init__(
        self,
        download_mode: str = "video_subtitles",
        output: Optional[str] = None,

        quality: str = "best",
        container: str = "mp4",

        audio_quality: str = "best",

        download_subtitles: bool = True,
        subtitle_language: str = "en",
        subtitle_type: str = "any",
        subtitle_format: str = "srt",

        save_separate_subtitle: bool = True,
        embed_subtitles: bool = False,

        playlist_folder: bool = True,
        avoid_duplicates: bool = True,

        fragments: int = 8,
        retries: int = 10,

        cookies: bool = False,
        sponsorblock: bool = False,

        progress_callback: Optional[
            Callable[..., None]
        ] = None,

        error_callback: Optional[
            Callable[[Any], None]
        ] = None,

        overwrite_callback: Optional[
            Callable[[str, str], bool]
        ] = None,

        overwrite_mode: str = "keep",

        overwrite_existing: Optional[
            bool
        ] = None,
    ) -> None:

        self.download_mode = str(
            download_mode
        ).strip().lower()

        self.output = (
            os.path.abspath(
                os.path.expanduser(
                    output
                )
            )
            if output
            else os.path.join(
                os.path.expanduser(
                    "~"
                ),
                "Videos",
                "Veyra",
            )
        )

        self.quality = str(
            quality
        )

        self.container = str(
            container
        )

        self.audio_quality = str(
            audio_quality
        )

        self.download_subtitles = bool(
            download_subtitles
        )

        self.subtitle_language = str(
            subtitle_language
        )

        self.subtitle_type = str(
            subtitle_type
        )

        self.subtitle_format = str(
            subtitle_format
        )

        # Always separate.
        self.save_separate_subtitle = True

        # Always false.
        self.embed_subtitles = False

        self.playlist_folder = bool(
            playlist_folder
        )

        self.avoid_duplicates = bool(
            avoid_duplicates
        )

        self.fragments = max(
            1,
            int(
                fragments
            ),
        )

        self.retries = max(
            0,
            int(
                retries
            ),
        )

        self.cookies = bool(
            cookies
        )

        self.sponsorblock = bool(
            sponsorblock
        )

        self.progress_callback = (
            progress_callback
        )

        self.error_callback = (
            error_callback
        )

        self.overwrite_callback = (
            overwrite_callback
        )

        self.cancelled = False

        self._active_service = None
        self._active_media_info = None

        self._original_sigint_handler = None

        if overwrite_existing is not None:

            overwrite_mode = (
                "overwrite"
                if overwrite_existing
                else "keep"
            )

        overwrite_mode = str(
            overwrite_mode
        ).strip().lower()

        if self.download_mode not in (
            self.DOWNLOAD_MODES
        ):

            raise ValueError(
                "Invalid download_mode. "
                "Expected one of: "
                + ", ".join(
                    sorted(
                        self.DOWNLOAD_MODES
                    )
                )
            )

        if overwrite_mode not in (
            self.OVERWRITE_MODES
        ):

            raise ValueError(
                "Invalid overwrite_mode. "
                "Expected 'keep', 'ask', or "
                "'overwrite'."
            )

        self.overwrite_mode = (
            overwrite_mode
        )

    # ==========================================================
    # CANCEL
    # ==========================================================

    def cancel(
        self,
    ) -> None:

        self.cancelled = True

        media_info = (
            self._active_media_info
        )

        if media_info is not None:

            cancel = getattr(
                media_info,
                "cancel",
                None,
            )

            if callable(cancel):

                try:

                    cancel()

                except Exception as exc:

                    self._report_error(
                        exc
                    )

        service = (
            self._active_service
        )

        if service is not None:

            cancel = getattr(
                service,
                "cancel",
                None,
            )

            if callable(cancel):

                try:

                    cancel()

                except Exception as exc:

                    self._report_error(
                        exc
                    )

    def check_cancelled(
        self,
    ) -> None:

        if self.cancelled:

            raise JobCancelled(
                "Media processing cancelled."
            )

    # ==========================================================
    # SIGNAL
    # ==========================================================

    def _install_signal_handler(
        self,
    ) -> None:

        try:

            if (
                threading.current_thread()
                is not threading.main_thread()
            ):

                return

            self._original_sigint_handler = (
                signal.getsignal(
                    signal.SIGINT
                )
            )

            signal.signal(
                signal.SIGINT,
                self._handle_sigint,
            )

        except (
            ValueError,
            AttributeError,
            RuntimeError,
        ):

            pass

    def _restore_signal_handler(
        self,
    ) -> None:

        if (
            self._original_sigint_handler
            is None
        ):

            return

        try:

            signal.signal(
                signal.SIGINT,
                self._original_sigint_handler,
            )

        except (
            ValueError,
            AttributeError,
            RuntimeError,
        ):

            pass

        finally:

            self._original_sigint_handler = (
                None
            )

    def _handle_sigint(
        self,
        signum: int,
        frame: Any,
    ) -> None:

        self.cancel()

        self._report_error(
            "Interrupted by user (Ctrl+C)."
        )

    # ==========================================================
    # SERVICE
    # ==========================================================

    def _create_service(
        self,
    ) -> MediaService:

        service = MediaService(
            progress_callback=(
                self._progress
            ),
            error_callback=(
                self._report_error
            ),
            finished_callback=None,
            cancelled_callback=None,
        )

        self._active_service = (
            service
        )

        return service

    # ==========================================================
    # MEDIA INFO
    # ==========================================================

    def _create_media_info(
        self,
    ) -> MediaInfo:

        media_info = MediaInfo(
            progress_callback=(
                self._progress
            ),
            error_callback=(
                self._report_error
            ),
        )

        self._active_media_info = (
            media_info
        )

        return media_info

    # ==========================================================
    # SETTINGS
    # ==========================================================

    def _build_settings(
        self,
        url: str,
    ) -> Dict[str, Any]:

        return {

            "url": url,

            "download_mode": (
                self.download_mode
            ),

            "output": self.output,

            "quality": self.quality,

            "container": self.container,

            "audio_quality": (
                self.audio_quality
            ),

            "download_subtitles": (
                self.download_subtitles
            ),

            "subtitle_language": (
                self.subtitle_language
            ),

            "subtitle_type": (
                self.subtitle_type
            ),

            "subtitle_format": (
                self.subtitle_format
            ),

            "save_separate_subtitle": True,

            "embed_subtitles": False,

            "playlist_folder": (
                self.playlist_folder
            ),

            "avoid_duplicates": (
                self.avoid_duplicates
            ),

            "fragments": self.fragments,

            "retries": self.retries,

            "cookies": self.cookies,

            "sponsorblock": (
                self.sponsorblock
            ),

            "overwrite_mode": (
                self.overwrite_mode
            ),
        }

    # ==========================================================
    # DISPLAY
    # ==========================================================

    @staticmethod
    def _display_name(
        settings: Dict[str, Any],
    ) -> str:

        title = str(
            settings.get(
                "title",
                "",
            )
            or ""
        ).strip()

        if title:
            return title

        url = str(
            settings.get(
                "url",
                "",
            )
            or ""
        ).strip()

        return url

    # ==========================================================
    # MEDIA INFO
    # ==========================================================

    def fetch_media_info(
        self,
        settings: Dict[str, Any],
    ) -> Dict[str, Any]:

        media_info = (
            self._create_media_info()
        )

        self._progress(
            "Fetching media information",
            self._display_name(
                settings
            ),
            0,
            "--",
            "--",
            "--:--",
        )

        try:

            return media_info.fetch_info(
                settings
            )

        finally:

            self._active_media_info = None

    # ==========================================================
    # ONE URL
    # ==========================================================

    def process(
        self,
        url: str,
    ) -> Dict[str, Any]:

        self.check_cancelled()

        url = str(
            url or ""
        ).strip()

        if not url:

            raise ValueError(
                "Media URL cannot be empty."
            )

        settings = (
            self._build_settings(
                url
            )
        )

        # ------------------------------------------------------
        # Metadata.
        # ------------------------------------------------------

        info = self.fetch_media_info(
            settings
        )

        self.check_cancelled()

        # ------------------------------------------------------
        # Actual media download.
        # ------------------------------------------------------

        service = (
            self._create_service()
        )

        try:

            self._progress(
                "Starting download",
                self._display_name(
                    settings
                ),
                0,
                "--",
                "--",
                "--:--",
            )

            result = service.download(
                settings
            )

            self.check_cancelled()

        finally:

            self._active_service = None

        if result is None:

            result = {}

        elif not isinstance(
            result,
            dict,
        ):

            result = {
                "result": result
            }

        result.setdefault(
            "url",
            url,
        )

        result.setdefault(
            "download_mode",
            self.download_mode,
        )

        result.setdefault(
            "media_info",
            info,
        )

        return result

    # ==========================================================
    # ITEM
    # ==========================================================

    def process_item(
        self,
        item: Dict[str, Any],
    ) -> Dict[str, Any]:

        self.check_cancelled()

        if not isinstance(
            item,
            dict,
        ):

            raise TypeError(
                "Media item must be a dictionary."
            )

        url = str(
            item.get(
                "url",
                "",
            )
            or ""
        ).strip()

        if not url:

            raise ValueError(
                "Media item does not contain a URL."
            )

        result = self.process(
            url
        )

        for key in (
            "title",
            "thumbnail",
            "id",
            "duration",
        ):

            if key in item:

                result.setdefault(
                    key,
                    item[key],
                )

        return result

    # ==========================================================
    # URLS
    # ==========================================================

    def process_urls(
        self,
        urls: List[str],
    ) -> List[Dict[str, Any]]:

        items = [
            {
                "url": url,
                "title": "",
            }
            for url in urls
        ]

        return self.process_items(
            items
        )

    # ==========================================================
    # ITEMS
    # ==========================================================

    def process_items(
        self,
        media_items: List[
            Dict[str, Any]
        ],
    ) -> List[Dict[str, Any]]:

        results: List[
            Dict[str, Any]
        ] = []

        total_items = len(
            media_items
        )

        if total_items == 0:

            return results

        self.cancelled = False

        self._install_signal_handler()

        try:

            for index, item in enumerate(
                media_items,
                start=1,
            ):

                self.check_cancelled()

                title = ""
                url = ""

                if isinstance(
                    item,
                    dict,
                ):

                    title = str(
                        item.get(
                            "title",
                            "",
                        )
                        or ""
                    )

                    url = str(
                        item.get(
                            "url",
                            "",
                        )
                        or ""
                    ).strip()

                self._progress(
                    (
                        f"Processing item "
                        f"{index} of "
                        f"{total_items}"
                    ),
                    title or url,
                    0,
                    "--",
                    "--",
                    "--:--",
                    current=index,
                    total=total_items,
                )

                try:

                    result = (
                        self.process_item(
                            item
                        )
                    )

                    self.check_cancelled()

                    results.append(
                        result
                    )

                except JobCancelled:

                    raise

                except KeyboardInterrupt:

                    self.cancel()

                    raise JobCancelled(
                        "Media processing "
                        "cancelled by user."
                    )

                except Exception as exc:

                    if self.cancelled:

                        raise JobCancelled(
                            "Media processing "
                            "cancelled."
                        )

                    self._report_error(
                        exc
                    )

                    continue

        finally:

            self._restore_signal_handler()

            self._active_service = None
            self._active_media_info = None

        return results

    # ==========================================================
    # GUI SETTINGS
    # ==========================================================

    def process_settings(
        self,
        settings: Dict[str, Any],
    ) -> List[Dict[str, Any]]:

        if not isinstance(
            settings,
            dict,
        ):

            raise TypeError(
                "Download settings must be a dictionary."
            )

        self._apply_settings(
            settings
        )

        self.cancelled = False

        videos = settings.get(
            "videos"
        )

        if (
            isinstance(
                videos,
                list,
            )
            and videos
        ):

            return self.process_items(
                videos
            )

        url = str(
            settings.get(
                "url",
                "",
            )
            or ""
        ).strip()

        if not url:

            raise ValueError(
                "Download settings do not contain a URL."
            )

        return self.process_urls(
            [
                url
            ]
        )

    # ==========================================================
    # APPLY SETTINGS
    # ==========================================================

    def _apply_settings(
        self,
        settings: Dict[str, Any],
    ) -> None:

        if "download_mode" in settings:

            mode = str(
                settings[
                    "download_mode"
                ]
            ).strip().lower()

            if mode not in (
                self.DOWNLOAD_MODES
            ):

                raise ValueError(
                    f"Invalid download mode: {mode}"
                )

            self.download_mode = mode

        if "output" in settings:

            output = str(
                settings[
                    "output"
                ]
                or ""
            ).strip()

            if output:

                self.output = (
                    os.path.abspath(
                        os.path.expanduser(
                            output
                        )
                    )
                )

        if "quality" in settings:

            self.quality = str(
                settings[
                    "quality"
                ]
            )

        if "container" in settings:

            self.container = str(
                settings[
                    "container"
                ]
            )

        if "audio_quality" in settings:

            self.audio_quality = str(
                settings[
                    "audio_quality"
                ]
            )

        if "download_subtitles" in settings:

            self.download_subtitles = bool(
                settings[
                    "download_subtitles"
                ]
            )

        if "subtitle_language" in settings:

            self.subtitle_language = str(
                settings[
                    "subtitle_language"
                ]
            )

        if "subtitle_type" in settings:

            self.subtitle_type = str(
                settings[
                    "subtitle_type"
                ]
            )

        if "subtitle_format" in settings:

            self.subtitle_format = str(
                settings[
                    "subtitle_format"
                ]
            )

        # ------------------------------------------------------
        # These are hard requirements.
        # ------------------------------------------------------

        self.save_separate_subtitle = True
        self.embed_subtitles = False

        if "playlist_folder" in settings:

            self.playlist_folder = bool(
                settings[
                    "playlist_folder"
                ]
            )

        if "avoid_duplicates" in settings:

            self.avoid_duplicates = bool(
                settings[
                    "avoid_duplicates"
                ]
            )

        if "fragments" in settings:

            self.fragments = max(
                1,
                int(
                    settings[
                        "fragments"
                    ]
                ),
            )

        if "retries" in settings:

            self.retries = max(
                0,
                int(
                    settings[
                        "retries"
                    ]
                ),
            )

        if "cookies" in settings:

            self.cookies = bool(
                settings[
                    "cookies"
                ]
            )

        if "sponsorblock" in settings:

            self.sponsorblock = bool(
                settings[
                    "sponsorblock"
                ]
            )

        if "overwrite_mode" in settings:

            overwrite_mode = str(
                settings[
                    "overwrite_mode"
                ]
            ).strip().lower()

            if overwrite_mode not in (
                self.OVERWRITE_MODES
            ):

                raise ValueError(
                    "Invalid overwrite_mode. "
                    "Expected 'keep', 'ask', or "
                    "'overwrite'."
                )

            self.overwrite_mode = (
                overwrite_mode
            )

    # ==========================================================
    # OVERWRITE
    # ==========================================================

    def should_overwrite(
        self,
        filepath: str,
        media_type: str = "media",
    ) -> bool:

        self.check_cancelled()

        if self.overwrite_mode == "keep":

            return False

        if self.overwrite_mode == "overwrite":

            return True

        if self.overwrite_mode == "ask":

            if not self.overwrite_callback:

                return False

            try:

                return bool(
                    self.overwrite_callback(
                        filepath,
                        media_type,
                    )
                )

            except JobCancelled:

                raise

            except Exception as exc:

                self._report_error(
                    exc
                )

                return False

        return False

    # ==========================================================
    # PROGRESS
    # ==========================================================

    def _progress(
        self,
        info: str = "",
        filename: str = "",
        percentage: Any = 0,
        downloaded: Any = "--",
        speed: Any = "--",
        eta: Any = "--:--",
        **kwargs: Any,
    ) -> None:

        if not self.progress_callback:
            return

        # ------------------------------------------------------
        # Batch information.
        # ------------------------------------------------------

        current = kwargs.get(
            "current",
            0,
        )

        total = kwargs.get(
            "total",
            0,
        )

        # ------------------------------------------------------
        # Optional progress dictionary compatibility.
        # ------------------------------------------------------

        progress_data = kwargs.get(
            "progress"
        )

        if isinstance(
            progress_data,
            dict,
        ):

            percentage = progress_data.get(
                "percentage",
                percentage,
            )

            downloaded = progress_data.get(
                "downloaded",
                downloaded,
            )

            speed = progress_data.get(
                "speed",
                speed,
            )

            eta = progress_data.get(
                "eta",
                eta,
            )

            current = progress_data.get(
                "current",
                current,
            )

            total = progress_data.get(
                "total",
                total,
            )

        # ------------------------------------------------------
        # Percentage.
        # ------------------------------------------------------

        try:

            percentage = float(
                percentage
            )

        except (
            TypeError,
            ValueError,
        ):

            percentage = 0.0

        percentage = max(
            0.0,
            min(
                100.0,
                percentage,
            ),
        )

        if percentage.is_integer():

            percentage_value = int(
                percentage
            )

        else:

            percentage_value = round(
                percentage,
                1,
            )

        # ------------------------------------------------------
        # Batch values.
        # ------------------------------------------------------

        try:

            current = int(
                current
            )

        except (
            TypeError,
            ValueError,
        ):

            current = 0

        try:

            total = int(
                total
            )

        except (
            TypeError,
            ValueError,
        ):

            total = 0

        downloaded = (
            str(downloaded)
            if downloaded not in (
                None,
                "",
            )
            else "--"
        )

        speed = (
            str(speed)
            if speed not in (
                None,
                "",
            )
            else "--"
        )

        eta = (
            str(eta)
            if eta not in (
                None,
                "",
            )
            else "--:--"
        )

        # ------------------------------------------------------
        # New callback.
        #
        # callback(
        #     info,
        #     filename,
        #     percentage,
        #     downloaded,
        #     speed,
        #     eta
        # )
        # ------------------------------------------------------

        try:

            self.progress_callback(
                info,
                filename,
                percentage_value,
                downloaded,
                speed,
                eta,
            )

            return

        except TypeError:

            pass

        except Exception:

            return

        # ------------------------------------------------------
        # Legacy callback.
        # ------------------------------------------------------

        try:

            self.progress_callback(
                info,
                filename,
                percentage_value,
            )

        except Exception:

            pass

    # ==========================================================
    # ERROR
    # ==========================================================

    def _report_error(
        self,
        error: Any,
    ) -> None:

        if self.error_callback:

            try:

                self.error_callback(
                    error
                )

                return

            except Exception:

                pass


# ==============================================================
# COMPATIBILITY FUNCTION
# ==============================================================

def process(
    url: str,
    download_mode: str = "video_subtitles",
    output: Optional[str] = None,

    quality: str = "best",
    container: str = "mp4",

    audio_quality: str = "best",

    download_subtitles: bool = True,
    subtitle_language: str = "en",
    subtitle_type: str = "any",
    subtitle_format: str = "srt",

    save_separate_subtitle: bool = True,
    embed_subtitles: bool = False,

    playlist_folder: bool = True,
    avoid_duplicates: bool = True,

    fragments: int = 8,
    retries: int = 10,

    cookies: bool = False,
    sponsorblock: bool = False,

    progress_callback: Optional[
        Callable[..., None]
    ] = None,

    error_callback: Optional[
        Callable[[Any], None]
    ] = None,

    overwrite_callback: Optional[
        Callable[[str, str], bool]
    ] = None,

    overwrite_mode: str = "keep",
) -> Dict[str, Any]:

    processor = MediaJobProcessor(

        download_mode=(
            download_mode
        ),

        output=output,

        quality=quality,

        container=container,

        audio_quality=(
            audio_quality
        ),

        download_subtitles=(
            download_subtitles
        ),

        subtitle_language=(
            subtitle_language
        ),

        subtitle_type=(
            subtitle_type
        ),

        subtitle_format=(
            subtitle_format
        ),

        save_separate_subtitle=True,

        embed_subtitles=False,

        playlist_folder=(
            playlist_folder
        ),

        avoid_duplicates=(
            avoid_duplicates
        ),

        fragments=fragments,

        retries=retries,

        cookies=cookies,

        sponsorblock=sponsorblock,

        progress_callback=(
            progress_callback
        ),

        error_callback=(
            error_callback
        ),

        overwrite_callback=(
            overwrite_callback
        ),

        overwrite_mode=(
            overwrite_mode
        ),
    )

    return processor.process(
        url
    )