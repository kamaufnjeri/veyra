from __future__ import annotations

import os
import signal
import threading

from typing import Any, Callable, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from core.media_info import MediaInfo
from services.media_service import MediaService


class JobCancelled(Exception):
    """Raised when a media job is cancelled."""


class MediaJobProcessor:
    """
    High-level media job processor.

    Modes:
        video
        audio
        subtitles
        video_subtitles

    MediaInfo:
        Metadata only.

    MediaService:
        Downloading, subtitles, post-processing, embedding,
        remuxing, encoding and final cleanup.

    Progress callback:
        callback(info, filename, percentage, downloaded, speed, eta)

    IMPORTANT
    ---------
    Temporary yt-dlp files such as:

        *.f135.mp4
        *.f140.m4a
        *.part
        *.ytdl
        intermediate media files

    must NOT be deleted while yt-dlp or FFmpeg is still using them.

    MediaService is therefore responsible for the actual cleanup after
    its complete post-processing pipeline has finished.

    This class only passes the correct settings through and ensures that
    the service remains active until the complete pipeline is finished.
    """

    DOWNLOAD_MODES = {
        "video",
        "audio",
        "subtitles",
        "video_subtitles",
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
        progress_callback: Optional[Callable[..., None]] = None,
        error_callback: Optional[Callable[[Any], None]] = None,
        overwrite_callback: Optional[
            Callable[[str, str], bool]
        ] = None,
        overwrite_mode: str = "keep",
        overwrite_existing: Optional[bool] = None,
    ) -> None:

        self.download_mode = self._mode(download_mode)
        self.output = self._output(output)

        self.quality = str(quality)
        self.container = str(container)
        self.audio_quality = str(audio_quality)

        self.download_subtitles = bool(download_subtitles)
        self.subtitle_language = str(subtitle_language)
        self.subtitle_type = str(subtitle_type)
        self.subtitle_format = str(subtitle_format)

        self.save_separate_subtitle = bool(
            save_separate_subtitle
        )

        self.embed_subtitles = bool(embed_subtitles)

        self.playlist_folder = bool(playlist_folder)
        self.avoid_duplicates = bool(avoid_duplicates)

        self.fragments = max(1, int(fragments))
        self.retries = max(0, int(retries))

        self.cookies = bool(cookies)
        self.sponsorblock = bool(sponsorblock)

        self.progress_callback = progress_callback
        self.error_callback = error_callback
        self.overwrite_callback = overwrite_callback

        self.cancelled = False

        self._active_service: Optional[MediaService] = None
        self._active_media_info: Optional[MediaInfo] = None

        self._original_sigint_handler = None

        if overwrite_existing is not None:
            overwrite_mode = (
                "overwrite"
                if overwrite_existing
                else "keep"
            )

        self.overwrite_mode = (
            str(overwrite_mode)
            .strip()
            .lower()
        )

        if self.overwrite_mode not in self.OVERWRITE_MODES:
            raise ValueError(
                "Invalid overwrite_mode. "
                "Expected 'keep', 'ask', or 'overwrite'."
            )

    # ==========================================================
    # HELPERS
    # ==========================================================

    @classmethod
    def _mode(cls, mode: str) -> str:
        mode = str(mode).strip().lower()

        if mode not in cls.DOWNLOAD_MODES:
            raise ValueError(
                "Invalid download_mode. Expected one of: "
                + ", ".join(sorted(cls.DOWNLOAD_MODES))
            )

        return mode

    @staticmethod
    def _output(output: Optional[str]) -> str:
        return (
            os.path.abspath(
                os.path.expanduser(output)
            )
            if output
            else os.path.join(
                os.path.expanduser("~"),
                "Videos",
                "Veyra",
            )
        )

    @staticmethod
    def _display_name(
        settings: Dict[str, Any],
    ) -> str:

        title = str(
            settings.get("title", "") or ""
        ).strip()

        media_id = str(
            settings.get("id", "") or ""
        ).strip()

        url = str(
            settings.get("url", "") or ""
        ).strip()

        if title and media_id:
            return f"{title} [{media_id}]"

        return (
            title
            or media_id
            or url
            or "Media"
        )

    # ==========================================================
    # CANCEL
    # ==========================================================

    def cancel(self) -> None:
        """
        Cancel the currently running media operation.

        MediaService / MediaInfo own the actual process termination.
        """

        self.cancelled = True

        for obj in (
            self._active_media_info,
            self._active_service,
        ):
            cancel = getattr(obj, "cancel", None)

            if callable(cancel):
                try:
                    cancel()
                except Exception:
                    pass

    def check_cancelled(self) -> None:
        if self.cancelled:
            raise JobCancelled(
                "Media processing cancelled."
            )

    # ==========================================================
    # SIGNAL
    # ==========================================================

    def _install_signal_handler(self) -> None:
        if (
            threading.current_thread()
            is not threading.main_thread()
        ):
            return

        try:
            self._original_sigint_handler = (
                signal.getsignal(signal.SIGINT)
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

    def _restore_signal_handler(self) -> None:
        if self._original_sigint_handler is None:
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
            self._original_sigint_handler = None

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
    # SERVICE / MEDIA INFO
    # ==========================================================

    def _create_service(self) -> MediaService:
        """
        Create the MediaService.

        The service owns the complete media lifecycle:

            download
                ↓
            subtitle download
                ↓
            merge/remux
                ↓
            encode if necessary
                ↓
            embed subtitles if requested
                ↓
            rename final output
                ↓
            cleanup temporary files
                ↓
            return final result

        Do NOT perform file cleanup here.

        Cleaning files here would be too early and can delete files
        still required by FFmpeg or a yt-dlp postprocessor.
        """

        service = MediaService(
            progress_callback=self._progress,
            error_callback=self._report_error,
            finished_callback=None,
            cancelled_callback=None,
        )

        self._active_service = service

        return service

    def _create_media_info(self) -> MediaInfo:
        info = MediaInfo(
            progress_callback=self._progress,
            error_callback=self._report_error,
        )

        self._active_media_info = info

        return info

    # ==========================================================
    # SETTINGS
    # ==========================================================

    def _build_settings(
        self,
        url: str,
    ) -> Dict[str, Any]:

        return {
            "url": url,

            "download_mode": self.download_mode,

            "output": self.output,

            "quality": self.quality,

            "container": self.container,

            "audio_quality": self.audio_quality,

            "download_subtitles": (
                self.download_subtitles
            ),

            "subtitle_language": (
                self.subtitle_language
            ),

            "subtitle_type": self.subtitle_type,

            "subtitle_format": (
                self.subtitle_format
            ),

            # --------------------------------------------------
            # Subtitle output
            # --------------------------------------------------
            #
            # If True:
            #
            #     video.mp4
            #     video.en.srt
            #
            # If False and embed=True:
            #
            #     video.mp4
            #
            # The actual cleanup is performed by MediaService
            # only after embedding/post-processing completes.
            #
            "save_separate_subtitle": (
                self.save_separate_subtitle
            ),

            "embed_subtitles": (
                self.embed_subtitles
            ),

            # --------------------------------------------------
            # Output
            # --------------------------------------------------

            "playlist_folder": (
                self.playlist_folder
            ),

            "avoid_duplicates": (
                self.avoid_duplicates
            ),

            # --------------------------------------------------
            # Downloader
            # --------------------------------------------------

            "fragments": self.fragments,

            "retries": self.retries,

            "cookies": self.cookies,

            "sponsorblock": self.sponsorblock,

            # --------------------------------------------------
            # Existing-file behaviour
            # --------------------------------------------------

            "overwrite_mode": (
                self.overwrite_mode
            ),

            # --------------------------------------------------
            # Explicit cleanup instruction
            # --------------------------------------------------
            #
            # MediaService should perform cleanup only after the
            # entire post-processing chain has completed.
            #
            "cleanup": True,

            "cleanup_intermediate": True,

            "cleanup_postprocessor_files": True,

            # Useful for MediaService implementations which need
            # to distinguish the final output from temporary files.
            "cleanup_after_postprocessing": True,
        }

    def _apply_settings(
        self,
        settings: Dict[str, Any],
    ) -> None:

        if "download_mode" in settings:
            self.download_mode = self._mode(
                settings["download_mode"]
            )

        if settings.get("output"):
            self.output = self._output(
                settings["output"]
            )

        simple_strings = (
            "quality",
            "container",
            "audio_quality",
            "subtitle_language",
            "subtitle_type",
            "subtitle_format",
        )

        for key in simple_strings:
            if key in settings:
                setattr(
                    self,
                    key,
                    str(settings[key]),
                )

        simple_bools = (
            "download_subtitles",
            "save_separate_subtitle",
            "embed_subtitles",
            "playlist_folder",
            "avoid_duplicates",
            "cookies",
            "sponsorblock",
        )

        for key in simple_bools:
            if key in settings:
                setattr(
                    self,
                    key,
                    bool(settings[key]),
                )

        if "fragments" in settings:
            self.fragments = max(
                1,
                int(settings["fragments"]),
            )

        if "retries" in settings:
            self.retries = max(
                0,
                int(settings["retries"]),
            )

        if "overwrite_mode" in settings:
            mode = (
                str(settings["overwrite_mode"])
                .strip()
                .lower()
            )

            if mode not in self.OVERWRITE_MODES:
                raise ValueError(
                    "Invalid overwrite_mode. "
                    "Expected 'keep', 'ask', or 'overwrite'."
                )

            self.overwrite_mode = mode

    # ==========================================================
    # MEDIA INFO
    # ==========================================================

    def fetch_media_info(
        self,
        settings: Dict[str, Any],
    ) -> Dict[str, Any]:

        info = self._create_media_info()

        self._progress(
            "Fetching media information",
            self._display_name(settings),
            0,
            "--",
            "--",
            "--:--",
        )

        try:
            return info.fetch_info(settings)

        finally:
            self._active_media_info = None

    # ==========================================================
    # ONE ITEM
    # ==========================================================

    def process(
        self,
        url: str,
    ) -> Dict[str, Any]:

        self.check_cancelled()

        url = str(url or "").strip()

        if not url:
            raise ValueError(
                "Media URL cannot be empty."
            )

        settings = self._build_settings(url)

        # ------------------------------------------------------
        # Metadata
        # ------------------------------------------------------

        info = self.fetch_media_info(settings)

        self.check_cancelled()

        # ------------------------------------------------------
        # Actual download + processing
        # ------------------------------------------------------

        service = self._create_service()

        result: Any = None

        try:
            self._progress(
                "Starting download",
                self._display_name(settings),
                0,
                "--",
                "--",
                "--:--",
            )

            # IMPORTANT:
            #
            # service.download() MUST NOT return until:
            #
            #   1. yt-dlp download is complete
            #   2. audio/video merge is complete
            #   3. encoding/remuxing is complete
            #   4. subtitle processing is complete
            #   5. subtitle embedding is complete
            #   6. final filename has been established
            #   7. temporary files have been cleaned
            #
            # This is what prevents:
            #
            #   file.f135.mp4
            #   file.f140.m4a
            #   file.mp4
            #
            # from being left behind.

            result = service.download(settings)

            self.check_cancelled()

        finally:
            # Do not destroy/cancel the service here.
            #
            # download() has already returned, meaning the complete
            # service pipeline should have finished.
            #
            # We only release our reference.
            self._active_service = None

        if not isinstance(result, dict):
            result = (
                {}
                if result is None
                else {"result": result}
            )

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

    @staticmethod
    def _extract_video_id(url: str) -> Optional[str]:

        try:
            parsed = urlparse(url)

            # youtube.com/watch?v=...
            if parsed.hostname in {
                "youtube.com",
                "www.youtube.com",
                "m.youtube.com",
            }:
                return parse_qs(
                    parsed.query
                ).get("v", [None])[0]

            # youtu.be/...
            if parsed.hostname == "youtu.be":
                return parsed.path.strip("/").split("/")[0] or None

        except Exception:
            pass

        return None

    def process_item(
        self,
        item: Dict[str, Any],
    ) -> Dict[str, Any]:

        self.check_cancelled()

        if not isinstance(item, dict):
            raise TypeError(
                "Media item must be a dictionary."
            )

        url = str(
            item.get("url", "") or ""
        ).strip()

        if not url:
            raise ValueError(
                "Media item does not contain a URL."
            )

        # Build normal settings
        settings = self._build_settings(url)

        # IMPORTANT:
        # Preserve the original item metadata.
        for key in (
            "id",
            "title",
            "thumbnail",
            "duration",
        ):
            if key in item:
                settings[key] = item[key]

      

        result = self._process_one_settings(
            settings
        )

        if not isinstance(result, dict):
            result = {}

        # Always preserve the original item metadata.
        for key in (
            "id",
            "title",
            "thumbnail",
            "duration",
        ):
            if key in item:
                result[key] = item[key]


        return result

    def process_item(
        self,
        item: Dict[str, Any],
    ) -> Dict[str, Any]:

        self.check_cancelled()

        if not isinstance(item, dict):
            raise TypeError(
                "Media item must be a dictionary."
            )

        url = str(
            item.get("url", "") or ""
        ).strip()

        if not url:
            raise ValueError(
                "Media item does not contain a URL."
            )

        media_id = item.get("id")

        if not media_id:
            media_id = self._extract_video_id(url)

       

        settings = self._build_settings(url)

        # Preserve the ID.
        if media_id:
            settings["id"] = media_id

        for key in (
            "title",
            "thumbnail",
            "duration",
        ):
            if key in item:
                settings[key] = item[key]

        result = self._process_one_settings(
            settings
        )

        if not isinstance(result, dict):
            result = {}

        result["id"] = media_id

        for key in (
            "title",
            "thumbnail",
            "duration",
        ):
            if key in item:
                result.setdefault(
                    key,
                    item[key],
                )

       

        return result

    def _process_one_settings(
        self,
        settings: Dict[str, Any],
    ) -> Dict[str, Any]:

        self.check_cancelled()

        # ------------------------------------------------------
        # Metadata
        # ------------------------------------------------------

        info = self.fetch_media_info(settings)

        self.check_cancelled()

        # ------------------------------------------------------
        # Actual download
        # ------------------------------------------------------

        service = self._create_service()

        result: Any = None

        try:

            self._progress(
                "Starting download",
                self._display_name(settings),
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

        if not isinstance(result, dict):

            result = (
                {}
                if result is None
                else {
                    "result": result
                }
            )

        result.setdefault(
            "url",
            settings["url"],
        )

        result.setdefault(
            "download_mode",
            self.download_mode,
        )

        result.setdefault(
            "media_info",
            info,
        )

        # ------------------------------------------------------
        # IMPORTANT:
        # Preserve ID and other item metadata.
        # ------------------------------------------------------

        for key in (
            "id",
            "title",
            "thumbnail",
            "duration",
        ):

            if key in settings:

                result[key] = settings[key]

        return result
    # ==========================================================
    # BATCH
    # ==========================================================

    def process_urls(
        self,
        urls: List[str],
    ) -> List[Dict[str, Any]]:

        items = []

        for url in urls:

            url = str(url or "").strip()

            if not url:
                continue

            items.append(
                {
                    "id": self._extract_video_id(url),
                    "url": url,
                    "title": "",
                }
            )

        return self.process_items(items)

    def process_items(
        self,
        media_items: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:

        if not media_items:
            return []

        results: List[Dict[str, Any]] = []

        total = len(media_items)

        self.cancelled = False

        self._install_signal_handler()

        try:
            for index, item in enumerate(
                media_items,
                1,
            ):
                self.check_cancelled()

                title = ""
                url = ""

                if isinstance(item, dict):
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
                    f"Processing item {index} of {total}",
                    title or url,
                    0,
                    "--",
                    "--",
                    "--:--",
                    current=index,
                    total=total,
                )

                try:
                    result = self.process_item(item)

                    results.append(result)

                    self.check_cancelled()

                except JobCancelled:
                    raise

                except KeyboardInterrupt:
                    self.cancel()

                    raise JobCancelled(
                        "Media processing cancelled by user."
                    )

                except Exception as exc:
                    if self.cancelled:
                        raise JobCancelled(
                            "Media processing cancelled."
                        )

                    self._report_error(exc)

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

        if not isinstance(settings, dict):
            raise TypeError(
                "Download settings must be a dictionary."
            )

        self._apply_settings(settings)

        videos = settings.get("videos")

        if isinstance(videos, list) and videos:
            return self.process_items(videos)

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

        return self.process_urls([url])

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
            self._report_error(exc)

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

        progress = kwargs.get("progress")

        if isinstance(progress, dict):
            percentage = progress.get(
                "percentage",
                percentage,
            )

            downloaded = progress.get(
                "downloaded",
                downloaded,
            )

            speed = progress.get(
                "speed",
                speed,
            )

            eta = progress.get(
                "eta",
                eta,
            )

        try:
            percentage = float(percentage)

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

        percentage = (
            int(percentage)
            if percentage.is_integer()
            else round(percentage, 1)
        )

        downloaded = str(
            downloaded or "--"
        )

        speed = str(
            speed or "--"
        )

        eta = str(
            eta or "--:--"
        )

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

    # ==========================================================
    # ERROR
    # ==========================================================

    def _report_error(
        self,
        error: Any,
    ) -> None:

        if not self.error_callback:
            return

        try:
            self.error_callback(error)

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

    return MediaJobProcessor(
        download_mode=download_mode,
        output=output,
        quality=quality,
        container=container,
        audio_quality=audio_quality,
        download_subtitles=download_subtitles,
        subtitle_language=subtitle_language,
        subtitle_type=subtitle_type,
        subtitle_format=subtitle_format,
        save_separate_subtitle=save_separate_subtitle,
        embed_subtitles=embed_subtitles,
        playlist_folder=playlist_folder,
        avoid_duplicates=avoid_duplicates,
        fragments=fragments,
        retries=retries,
        cookies=cookies,
        sponsorblock=sponsorblock,
        progress_callback=progress_callback,
        error_callback=error_callback,
        overwrite_callback=overwrite_callback,
        overwrite_mode=overwrite_mode,
    ).process(url)