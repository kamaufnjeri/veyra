from __future__ import annotations

import threading
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import parse_qs, urlparse


class MediaInfo:
    """
    Lightweight yt-dlp media/playlist identification.

    Returns only:

        playlist
        playlist_index
        title
        webpage_url

    No formats.
    No audio formats.
    No subtitles.
    No thumbnails.
    No full media metadata.
    """

    def __init__(
        self,
        progress_callback: Optional[Callable[..., None]] = None,
        error_callback: Optional[Callable[[Any], None]] = None,
    ) -> None:
        self.progress_callback = progress_callback
        self.error_callback = error_callback

        self._cancel_event = threading.Event()
        self._ydl = None

    # ==========================================================
    # PUBLIC
    # ==========================================================

    def fetch_info(
        self,
        settings: Any,
    ) -> Dict[str, Any]:

        self.reset_cancel()

        try:
            import yt_dlp
        except ImportError as exc:
            raise RuntimeError(
                "yt-dlp is not installed."
            ) from exc

        settings = self._normalize_settings(settings)
        urls = self._get_urls(settings)

        if not urls:
            raise ValueError(
                "No valid media URL was provided."
            )

        results: List[Dict[str, Any]] = []

        total_urls = len(urls)

        for url_number, url in enumerate(urls, 1):

            self._check_cancelled()

            is_playlist = self._has_playlist(url)

            self._progress(
                f"Processing URL {url_number}/{total_urls}",
                url,
                0,
            )

            options = self._build_options(
                settings,
                self,
                is_playlist=is_playlist,
            )

            try:

                with yt_dlp.YoutubeDL(options) as ydl:

                    self._ydl = ydl

                    info = ydl.extract_info(
                        url,
                        download=False,
                    )

                    self._check_cancelled()

                    if not info:
                        message = (
                            "yt-dlp returned no information "
                            f"for: {url}"
                        )

                        self._error(message)

                        results.append({
                            "playlist": is_playlist,
                            "playlist_index": None,
                            "title": None,
                            "webpage_url": url,
                            "error": message,
                        })

                        continue

                    extracted = self._extract_entries(
                        info,
                        source_url=url,
                        requested_playlist=is_playlist,
                    )

                    # --------------------------------------------------
                    # IMPORTANT:
                    #
                    # If the URL contains ?list= but yt-dlp returned
                    # a single video, don't silently return [].
                    #
                    # Try the playlist URL separately.
                    # --------------------------------------------------

                    if (
                        is_playlist
                        and not extracted
                    ):
                        extracted = self._extract_playlist_fallback(
                            ydl,
                            url,
                        )

                    results.extend(extracted)

                    self._progress(
                        f"Found {len(extracted)} item(s)",
                        url,
                        100,
                    )

            except yt_dlp.utils.DownloadError as exc:

                message = str(exc)

                self._error(message)

                results.append({
                    "playlist": is_playlist,
                    "playlist_index": None,
                    "title": None,
                    "webpage_url": url,
                    "error": message,
                })

            except Exception as exc:

                message = str(exc)

                self._error(message)

                results.append({
                    "playlist": is_playlist,
                    "playlist_index": None,
                    "title": None,
                    "webpage_url": url,
                    "error": message,
                })

            finally:
                self._ydl = None

        return {
            "type": "media_info",
            "results": results,
            "count": len(results),
            "cancelled": False,
        }

    # ==========================================================
    # PLAYLIST DETECTION
    # ==========================================================

    @staticmethod
    def _has_playlist(url: str) -> bool:

        try:
            parsed = urlparse(url)
            query = parse_qs(parsed.query)

            return bool(query.get("list"))

        except Exception:
            return False

    # ==========================================================
    # EXTRACT ENTRIES
    # ==========================================================

    @classmethod
    def _extract_entries(
        cls,
        info: Dict[str, Any],
        source_url: str,
        requested_playlist: bool,
    ) -> List[Dict[str, Any]]:

        results: List[Dict[str, Any]] = []

        # ------------------------------------------------------
        # ACTUAL PLAYLIST
        # ------------------------------------------------------

        if info.get("_type") == "playlist":

            entries = info.get("entries")

            if entries is None:
                return results

            for fallback_index, entry in enumerate(
                entries,
                1,
            ):

                if entry is None:
                    continue

                if not isinstance(entry, dict):
                    continue

                playlist_index = (
                    entry.get("playlist_index")
                    or fallback_index
                )

                result = cls._make_entry(
                    entry=entry,
                    playlist=True,
                    playlist_index=playlist_index,
                    fallback_url=None,
                )

                # Keep entries even when title is missing,
                # provided we have a usable URL/ID.
                if (
                    result["webpage_url"]
                    or result["title"]
                ):
                    results.append(result)

            return results

        # ------------------------------------------------------
        # REQUESTED PLAYLIST BUT YT-DLP RETURNED VIDEO
        # ------------------------------------------------------

        if requested_playlist:

            # Do NOT treat the video as the playlist result.
            #
            # The caller requested the playlist, so returning
            # the single watch URL here would be misleading.
            return results

        # ------------------------------------------------------
        # SINGLE VIDEO
        # ------------------------------------------------------

        return [
            cls._make_entry(
                entry=info,
                playlist=False,
                playlist_index=None,
                fallback_url=source_url,
            )
        ]

    # ==========================================================
    # PLAYLIST FALLBACK
    # ==========================================================

    @classmethod
    def _extract_playlist_fallback(
        cls,
        ydl: Any,
        url: str,
    ) -> List[Dict[str, Any]]:

        """
        Some YouTube URLs containing both ?v= and ?list=
        can initially resolve as the video.

        Convert:

            https://youtube.com/watch?v=VIDEO&list=PLAYLIST

        into a playlist-focused URL and extract that.
        """

        playlist_id = cls._get_playlist_id(url)

        if not playlist_id:
            return []

        playlist_url = (
            "https://www.youtube.com/playlist?list="
            + playlist_id
        )

        try:

            info = ydl.extract_info(
                playlist_url,
                download=False,
            )

        except Exception:
            return []

        if not isinstance(info, dict):
            return []

        entries = info.get("entries") or []

        results: List[Dict[str, Any]] = []

        for fallback_index, entry in enumerate(
            entries,
            1,
        ):

            if not isinstance(entry, dict):
                continue

            playlist_index = (
                entry.get("playlist_index")
                or fallback_index
            )

            result = cls._make_entry(
                entry=entry,
                playlist=True,
                playlist_index=playlist_index,
                fallback_url=None,
            )

            if (
                result["webpage_url"]
                or result["title"]
            ):
                results.append(result)

        return results

    # ==========================================================
    # PLAYLIST ID
    # ==========================================================

    @staticmethod
    def _get_playlist_id(
        url: str,
    ) -> Optional[str]:

        try:

            parsed = urlparse(url)

            query = parse_qs(
                parsed.query
            )

            values = query.get("list")

            if not values:
                return None

            playlist_id = values[0].strip()

            return playlist_id or None

        except Exception:

            return None

    # ==========================================================
    # MAKE ENTRY
    # ==========================================================

    @classmethod
    def _make_entry(
        cls,
        entry: Dict[str, Any],
        playlist: bool,
        playlist_index: Optional[int],
        fallback_url: Optional[str],
    ) -> Dict[str, Any]:

        title = entry.get("title")

        if title is not None:
            title = str(title).strip()

        return {
            "playlist": bool(playlist),

            "playlist_index": playlist_index,

            "title": title or None,

            "webpage_url": cls._entry_url(
                entry,
                fallback=fallback_url,
            ),
        }

    # ==========================================================
    # ENTRY URL
    # ==========================================================

    @staticmethod
    def _entry_url(
        entry: Dict[str, Any],
        fallback: Optional[str] = None,
    ) -> Optional[str]:

        # ------------------------------------------------------
        # Direct webpage URL
        # ------------------------------------------------------

        for key in (
            "webpage_url",
            "original_url",
        ):

            value = entry.get(key)

            if isinstance(value, str):

                value = value.strip()

                if value.startswith("http"):
                    return value

        # ------------------------------------------------------
        # URL field
        # ------------------------------------------------------

        value = entry.get("url")

        if isinstance(value, str):

            value = value.strip()

            if value.startswith("http"):
                return value

        # ------------------------------------------------------
        # YouTube ID
        # ------------------------------------------------------

        video_id = entry.get("id")

        if isinstance(video_id, str):

            video_id = video_id.strip()

            if video_id:

                extractor = str(
                    entry.get("extractor_key")
                    or entry.get("extractor")
                    or ""
                ).lower()

                if "youtube" in extractor:

                    return (
                        "https://www.youtube.com/watch?v="
                        + video_id
                    )

                # yt-dlp flat YouTube entries sometimes don't
                # contain extractor_key. The ID is still enough
                # when the URL is a YouTube playlist.
                if entry.get("ie_key") == "Youtube":

                    return (
                        "https://www.youtube.com/watch?v="
                        + video_id
                    )

        return fallback

    # ==========================================================
    # SETTINGS
    # ==========================================================

    @staticmethod
    def _normalize_settings(
        settings: Any,
    ) -> Dict[str, Any]:

        if isinstance(settings, str):

            url = settings.strip()

            if not url:
                raise ValueError(
                    "Media URL is empty."
                )

            return {
                "url": url,
            }

        if not isinstance(settings, dict):

            raise TypeError(
                "settings must be a URL string "
                "or dictionary, got "
                f"{type(settings).__name__}."
            )

        result = dict(settings)

        url = result.get("url")

        if isinstance(url, dict):

            result["url"] = (
                url.get("url")
                or url.get("webpage_url")
                or url.get("original_url")
                or ""
            ).strip()

            if not result["url"]:
                result.pop("url")

        return result

    # ==========================================================
    # URLS
    # ==========================================================

    @classmethod
    def _get_urls(
        cls,
        settings: Dict[str, Any],
    ) -> List[str]:

        values = settings.get("videos")

        if not isinstance(
            values,
            (list, tuple),
        ):
            values = [
                settings.get("url")
            ]

        urls: List[str] = []

        seen = set()

        for value in values:

            url = cls._extract_url(value)

            if url and url not in seen:

                seen.add(url)
                urls.append(url)

        return urls

    @staticmethod
    def _extract_url(
        value: Any,
    ) -> Optional[str]:

        if isinstance(value, str):

            value = value.strip()

            return value or None

        if isinstance(value, dict):

            for key in (
                "url",
                "webpage_url",
                "original_url",
            ):

                candidate = value.get(key)

                if isinstance(candidate, str):

                    candidate = candidate.strip()

                    if candidate:
                        return candidate

        return None

    # ==========================================================
    # YT-DLP OPTIONS
    # ==========================================================

    @staticmethod
    def _build_options(
        settings: Dict[str, Any],
        owner: "MediaInfo",
        is_playlist: bool,
    ) -> Dict[str, Any]:

        options: Dict[str, Any] = {

            # Do not print anything to stdout.
            "quiet": True,

            "no_warnings": True,

            # Continue through unavailable playlist entries.
            "ignoreerrors": True,

            # IMPORTANT:
            # Only return flat playlist entries.
            "extract_flat": "in_playlist",

            # IMPORTANT:
            # True  -> playlist
            # False -> individual video
            "noplaylist": not is_playlist,

            "logger": _YTDLPLogger(owner),

            "http_headers": {
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/131.0 Safari/537.36"
                )
            },

            "remote_components": {
                "ejs": ["github"],
            },
        }

        # ------------------------------------------------------
        # COOKIES
        # ------------------------------------------------------

        if settings.get("cookies") is True:

            browser = str(
                settings.get(
                    "cookie_browser",
                    "firefox",
                )
                or "firefox"
            ).strip().lower()

            if browser:

                options[
                    "cookiesfrombrowser"
                ] = (
                    browser,
                )

        return options

    # ==========================================================
    # CANCEL
    # ==========================================================

    def cancel(self) -> None:

        self._cancel_event.set()

        ydl = self._ydl

        if ydl is None:
            return

        try:

            downloader = getattr(
                ydl,
                "_downloader",
                None,
            )

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

    def _check_cancelled(self) -> None:

        if self._cancel_event.is_set():

            raise RuntimeError(
                "Media information fetch cancelled."
            )

    # ==========================================================
    # CALLBACKS
    # ==========================================================

    def _error(
        self,
        message: Any,
    ) -> None:

        if not self.error_callback:
            return

        try:

            self.error_callback(message)

        except Exception:
            pass

    def _progress(
        self,
        info: str,
        filename: str,
        percentage: int,
    ) -> None:

        callback = self.progress_callback

        if not callback:
            return

        try:

            callback(
                info,
                filename,
                percentage,
            )

            return

        except TypeError:
            pass

        except Exception:
            return

        try:

            callback(
                info,
                filename,
                percentage,
                None,
                None,
                None,
            )

        except Exception:
            pass


class _YTDLPLogger:

    def __init__(
        self,
        owner: MediaInfo,
    ) -> None:

        self.owner = owner

    def debug(
        self,
        message: str,
    ) -> None:
        pass

    def info(
        self,
        message: str,
    ) -> None:
        pass

    def warning(
        self,
        message: str,
    ) -> None:

        if message:

            self.owner._progress(
                str(message),
                "yt-dlp",
                0,
            )

    def error(
        self,
        message: str,
    ) -> None:

        self.owner._error(message)