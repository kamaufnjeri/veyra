from __future__ import annotations

import os
import threading
from typing import Any, Callable, Dict, List, Optional


class VideoDownloader:
    """
    yt-dlp based media downloader.

    SUPPORTED MODES
    ----------------
        video
            Video + audio.

        audio
            Audio only.

        subtitles
            Subtitles only.

        video_subtitles
            Video + audio + separate subtitles.

    IMPORTANT
    ---------
    VideoDownloader ONLY downloads media.

    It does NOT encode video.

    MediaService owns MediaEncoder and decides whether the
    downloaded video actually needs processing.

    SUBTITLES
    ---------
    Subtitles are always saved separately.

    They are NEVER embedded into the video.
    """

    VALID_MODES = {
        "video",
        "audio",
        "subtitles",
        "video_subtitles",
    }

    VALID_SUBTITLE_FORMATS = {
        "srt",
        "vtt",
    }

    AUDIO_FORMAT = "mp3"

    SUBTITLE_EXTENSIONS = {
        ".srt",
        ".vtt",
        ".ass",
        ".ssa",
        ".ttml",
        ".srv1",
        ".srv2",
        ".srv3",
        ".srv4",
    }

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

    def download(
        self,
        settings: Dict[str, Any],
        media_result: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:

        self.reset_cancel()

        try:
            import yt_dlp
        except ImportError as exc:
            raise RuntimeError(
                "yt-dlp is not installed."
            ) from exc

        mode = self._get_mode(settings)

        output_directory = self._prepare_output(
            settings
        )

        urls = self._get_urls(settings)

        if not urls and media_result:
            if isinstance(media_result, dict):
                media_url = media_result.get("url")

                if media_url:
                    urls = [
                        str(media_url).strip()
                    ]

        if not urls:
            raise ValueError(
                "No download URL was provided."
            )

        options = self._build_options(
            settings=settings,
            output_directory=output_directory,
            mode=mode,
        )

        results: List[Dict[str, Any]] = []

        try:

            with yt_dlp.YoutubeDL(options) as ydl:

                self._ydl = ydl

                for url in urls:

                    self._check_cancelled()

                    display_name = (
                        self._url_name(url)
                    )

                    self._progress(
                        self._starting_message(mode),
                        display_name,
                        0,
                        "--",
                        "--",
                        "--:--",
                    )

                    try:

                        info = ydl.extract_info(
                            url,
                            download=True,
                        )

                    except Exception as exc:

                        if mode == "video_subtitles":

                            # A subtitle failure must not destroy
                            # a successfully downloaded video.
                            #
                            # However, retry metadata extraction
                            # only if the actual media information
                            # cannot be obtained.
                            self._notify_subtitle_warning(
                                exc
                            )

                            try:

                                info = ydl.extract_info(
                                    url,
                                    download=False,
                                )

                            except Exception:

                                raise

                        else:

                            raise

                    self._check_cancelled()

                    if not info:

                        raise RuntimeError(
                            "yt-dlp returned no information."
                        )

                    entries = self._flatten_entries(
                        info
                    )

                    for entry in entries:

                        self._check_cancelled()

                        result = self._build_result(
                            entry=entry,
                            output_directory=output_directory,
                            mode=mode,
                            settings=settings,
                        )

                        results.append(
                            result
                        )

                    self._progress(
                        self._complete_message(mode),
                        display_name,
                        100,
                        "Complete",
                        "--",
                        "00:00",
                    )

        finally:

            self._ydl = None

        return self._build_download_response(
            results=results,
            output_directory=output_directory,
            mode=mode,
        )

    # ==========================================================
    # MODE
    # ==========================================================

    @classmethod
    def _get_mode(
        cls,
        settings: Dict[str, Any],
    ) -> str:

        mode = str(
            settings.get(
                "download_mode",
                settings.get(
                    "mode",
                    settings.get(
                        "type",
                        "video",
                    ),
                ),
            )
            or "video"
        ).strip().lower()

        aliases = {
            "video+subtitles": "video_subtitles",
            "video_subtitle": "video_subtitles",
            "video-with-subtitles": "video_subtitles",
            "video_with_subtitles": "video_subtitles",
            "subtitle": "subtitles",
            "audio_only": "audio",
            "video_only": "video",
        }

        mode = aliases.get(
            mode,
            mode,
        )

        if mode not in cls.VALID_MODES:

            raise ValueError(
                f"Invalid download mode: {mode}. "
                f"Expected one of: "
                f"{', '.join(sorted(cls.VALID_MODES))}"
            )

        return mode

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
    # YT-DLP OPTIONS
    # ==========================================================

    def _build_options(
        self,
        settings: Dict[str, Any],
        output_directory: str,
        mode: str,
    ) -> Dict[str, Any]:

        quality = str(
            settings.get(
                "quality",
                "best",
            )
            or "best"
        ).strip().lower()

        audio_quality = str(
            settings.get(
                "audio_quality",
                "best",
            )
            or "best"
        ).strip().lower()

        container = str(
            settings.get(
                "container",
                "mp4",
            )
            or "mp4"
        ).strip().lower().lstrip(".")

        retries = max(
            0,
            self._safe_int(
                settings.get(
                    "retries",
                    10,
                ),
                10,
            ),
        )

        fragments = max(
            1,
            min(
                32,
                self._safe_int(
                    settings.get(
                        "fragments",
                        8,
                    ),
                    8,
                ),
            ),
        )

        playlist_folder = bool(
            settings.get(
                "playlist_folder",
                True,
            )
        )

        avoid_duplicates = bool(
            settings.get(
                "avoid_duplicates",
                True,
            )
        )

        options: Dict[str, Any] = {

            "outtmpl": self._build_output_template(
                output_directory,
                playlist_folder,
            ),

            # We want playlists when a playlist URL is supplied.
            "noplaylist": False,

            # Parallel fragmented downloading.
            "concurrent_fragment_downloads": fragments,

            "retries": retries,
            "fragment_retries": retries,

            "continuedl": True,

            "quiet": True,
            "no_warnings": True,

            "ignoreerrors": False,

            "overwrites": not avoid_duplicates,

            "progress_hooks": [
                self._progress_hook,
            ],

            "postprocessor_hooks": [
                self._postprocessor_hook,
            ],

            "logger": _YTDLPLogger(self),

            # --------------------------------------------------
            # NEVER EMBED SUBTITLES
            # --------------------------------------------------

            "embedsubtitles": False,
            "embed_subtitles": False,

            # No thumbnails / metadata sidecars.
            "writethumbnail": False,
            "writeinfojson": False,
            "writedescription": False,
            "writeannotations": False,

            "addmetadata": False,
            "embedthumbnail": False,

            # --------------------------------------------------
            # HEADERS
            # --------------------------------------------------

            "http_headers": {
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/131.0 Safari/537.36"
                )
            },
        }

        # ======================================================
        # AUDIO
        # ======================================================

        if mode == "audio":

            options["format"] = (
                "bestaudio/best"
            )

            options["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": self.AUDIO_FORMAT,
                    "preferredquality": self._audio_quality(
                        audio_quality
                    ),
                }
            ]

        # ======================================================
        # VIDEO
        # ======================================================

        elif mode in {
            "video",
            "video_subtitles",
        }:

            options["format"] = (
                self._video_format(
                    quality,
                    container,
                )
            )

            if container in {
                "mp4",
                "mkv",
                "webm",
            }:

                options[
                    "merge_output_format"
                ] = container

        # ======================================================
        # SUBTITLES
        #
        # video_subtitles is intentionally ONE yt-dlp job.
        #
        # yt-dlp downloads:
        #
        #     video
        #     audio
        #     subtitles
        #
        # together.
        # ======================================================

        if mode in {
            "subtitles",
            "video_subtitles",
        }:

            self._apply_subtitle_options(
                options,
                settings,
            )

        # Subtitle-only mode.
        if mode == "subtitles":

            options["skip_download"] = True

        # ======================================================
        # COOKIES
        # ======================================================

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

        # ======================================================
        # SPONSORBLOCK
        # ======================================================

        if settings.get(
            "sponsorblock"
        ) is True:

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

    # ==========================================================
    # VIDEO FORMAT
    # ==========================================================

    @staticmethod
    def _video_format(
        quality: str,
        container: str,
    ) -> str:

        quality = str(
            quality or "best"
        ).strip().lower()

        # ------------------------------------------------------
        # MP4
        #
        # Prefer H264 + AAC.
        #
        # H264 is preferred because it avoids an expensive
        # AV1/VP9 -> H264 conversion later.
        # ------------------------------------------------------

        if container == "mp4":

            if quality == "best":

                return (
                    "bestvideo[vcodec^=avc1]"
                    "+"
                    "bestaudio[acodec^=mp4a]"
                    "/"
                    "bestvideo[vcodec^=avc1]"
                    "+"
                    "bestaudio[ext=m4a]"
                    "/"
                    "bestvideo[vcodec^=avc1]"
                    "+"
                    "bestaudio"
                    "/"
                    "bestvideo+bestaudio"
                    "/"
                    "best"
                )

            height = (
                VideoDownloader._quality_height(
                    quality
                )
            )

            if height is None:

                return (
                    "bestvideo[vcodec^=avc1]"
                    "+"
                    "bestaudio[acodec^=mp4a]"
                    "/"
                    "bestvideo[vcodec^=avc1]"
                    "+"
                    "bestaudio"
                    "/"
                    "bestvideo+bestaudio"
                    "/"
                    "best"
                )

            return (
                f"bestvideo[vcodec^=avc1]"
                f"[height<={height}]"
                "+"
                "bestaudio[acodec^=mp4a]"
                "/"
                f"bestvideo[vcodec^=avc1]"
                f"[height<={height}]"
                "+"
                "bestaudio"
                "/"
                f"bestvideo[height<={height}]"
                "+"
                "bestaudio"
                "/"
                f"best[height<={height}]"
                "/"
                "best"
            )

        # ------------------------------------------------------
        # WEBM
        # ------------------------------------------------------

        if container == "webm":

            if quality == "best":

                return (
                    "bestvideo[ext=webm]"
                    "+"
                    "bestaudio[ext=webm]"
                    "/"
                    "bestvideo+bestaudio"
                    "/"
                    "best"
                )

            height = (
                VideoDownloader._quality_height(
                    quality
                )
            )

            if height is None:

                return (
                    "bestvideo[ext=webm]"
                    "+"
                    "bestaudio[ext=webm]"
                    "/"
                    "best"
                )

            return (
                f"bestvideo[ext=webm]"
                f"[height<={height}]"
                "+"
                "bestaudio[ext=webm]"
                "/"
                f"bestvideo[height<={height}]"
                "+"
                "bestaudio"
                "/"
                f"best[height<={height}]"
                "/"
                "best"
            )

        # ------------------------------------------------------
        # MKV
        # ------------------------------------------------------

        if quality == "best":

            return (
                "bestvideo+bestaudio/best"
            )

        height = (
            VideoDownloader._quality_height(
                quality
            )
        )

        if height is None:

            return (
                "bestvideo+bestaudio/best"
            )

        return (
            f"bestvideo[height<={height}]"
            "+"
            "bestaudio/"
            f"best[height<={height}]"
            "/"
            "best"
        )

    @staticmethod
    def _quality_height(
        quality: str,
    ) -> Optional[int]:

        try:

            height = int(
                quality
            )

        except (
            TypeError,
            ValueError,
        ):

            return None

        return max(
            144,
            min(
                4320,
                height,
            ),
        )

    # ==========================================================
    # SUBTITLES
    # ==========================================================

    def _apply_subtitle_options(
        self,
        options: Dict[str, Any],
        settings: Dict[str, Any],
    ) -> None:

        language = str(
            settings.get(
                "subtitle_language",
                "en",
            )
            or "en"
        ).strip().lower()

        subtitle_type = str(
            settings.get(
                "subtitle_type",
                "any",
            )
            or "any"
        ).strip().lower()

        subtitle_format = str(
            settings.get(
                "subtitle_format",
                "srt",
            )
            or "srt"
        ).strip().lower().lstrip(".")

        if subtitle_format not in (
            self.VALID_SUBTITLE_FORMATS
        ):

            subtitle_format = "srt"

        options[
            "subtitleslangs"
        ] = self._subtitle_languages(
            language
        )

        options[
            "subtitlesformat"
        ] = subtitle_format

        # ------------------------------------------------------
        # CRITICAL:
        #
        # NEVER EMBED.
        # ------------------------------------------------------

        options[
            "embedsubtitles"
        ] = False

        options[
            "embed_subtitles"
        ] = False

        if subtitle_type == "original":

            options[
                "writesubtitles"
            ] = True

            options[
                "writeautomaticsub"
            ] = False

        elif subtitle_type == "auto":

            options[
                "writesubtitles"
            ] = False

            options[
                "writeautomaticsub"
            ] = True

        elif subtitle_type == "translated":

            # yt-dlp's subtitle language selection is handled
            # through subtitleslangs. Translation availability
            # depends on the extractor/source.
            options[
                "writesubtitles"
            ] = True

            options[
                "writeautomaticsub"
            ] = True

        else:

            # "any"
            options[
                "writesubtitles"
            ] = True

            options[
                "writeautomaticsub"
            ] = True

    @staticmethod
    def _subtitle_languages(
        language: str,
    ) -> List[str]:

        language = str(
            language or "en"
        ).strip().lower()

        if language in {
            "",
            "any",
            "*",
        }:

            return [
                "all"
            ]

        return [
            language
        ]

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

    @staticmethod
    def _build_output_template(
        output_directory: str,
        playlist_folder: bool,
    ) -> str:

        if playlist_folder:

            return os.path.join(
                output_directory,
                "%(playlist_title,playlist)s",
                "%(title)s.%(ext)s",
            )

        return os.path.join(
            output_directory,
            "%(title)s.%(ext)s",
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

        urls: List[str] = []

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

                    value = str(
                        url
                    ).strip()

                    if value:
                        urls.append(
                            value
                        )

        if not urls:

            url = settings.get(
                "url"
            )

            if url:

                value = str(
                    url
                ).strip()

                if value:
                    urls.append(
                        value
                    )

        return list(
            dict.fromkeys(
                urls
            )
        )

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
    # RESULT
    # ==========================================================

    def _build_result(
        self,
        entry: Dict[str, Any],
        output_directory: str,
        mode: str,
        settings: Dict[str, Any],
    ) -> Dict[str, Any]:

        filepath = self._find_media_filepath(
            entry,
            mode,
        )

        subtitle_files: List[str] = []

        if mode in {
            "subtitles",
            "video_subtitles",
        }:

            subtitle_files = (
                self._find_subtitle_files(
                    info=entry,
                    output_directory=output_directory,
                    media_filepath=filepath,
                    settings=settings,
                )
            )

        absolute_filepath = (
            os.path.abspath(filepath)
            if filepath
            else None
        )

        absolute_subtitles = [
            os.path.abspath(path)
            for path in subtitle_files
            if path
        ]

        subtitle_format = str(
            settings.get(
                "subtitle_format",
                "srt",
            )
            or "srt"
        ).strip().lower().lstrip(".")

        return {

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
                or entry.get(
                    "original_url"
                )
            ),

            "filepath": absolute_filepath,
            "path": absolute_filepath,

            "duration": entry.get(
                "duration"
            ),

            "uploader": entry.get(
                "uploader"
            ),

            "language": (
                str(
                    settings.get(
                        "subtitle_language",
                        "en",
                    )
                    or "en"
                )
                if mode in {
                    "subtitles",
                    "video_subtitles",
                }
                else None
            ),

            "subtitle_format": (
                subtitle_format
                if mode in {
                    "subtitles",
                    "video_subtitles",
                }
                else None
            ),

            "subtitles": absolute_subtitles,

            "subtitle_filepath": (
                absolute_subtitles[0]
                if absolute_subtitles
                else None
            ),

            "has_subtitles": bool(
                absolute_subtitles
            ),

            "subtitles_available": bool(
                absolute_subtitles
            ),

            "subtitles_embedded": False,

            "output": output_directory,

            "type": mode,
            "mode": mode,
        }

    # ==========================================================
    # MEDIA FILE
    # ==========================================================

    @staticmethod
    def _find_media_filepath(
        info: Dict[str, Any],
        mode: str,
    ) -> Optional[str]:

        if mode == "subtitles":

            return None

        requested_downloads = info.get(
            "requested_downloads"
        )

        if isinstance(
            requested_downloads,
            list,
        ):

            for item in requested_downloads:

                if not isinstance(
                    item,
                    dict,
                ):
                    continue

                candidate = (
                    item.get(
                        "filepath"
                    )
                    or item.get(
                        "filename"
                    )
                )

                if (
                    candidate
                    and os.path.isfile(
                        str(candidate)
                    )
                ):

                    return str(
                        candidate
                    )

        candidate = (
            info.get(
                "_filename"
            )
            or info.get(
                "filename"
            )
        )

        if candidate:

            candidate = str(
                candidate
            )

            if os.path.isfile(
                candidate
            ):

                return candidate

        # yt-dlp may expose the final filepath here.
        candidate = info.get(
            "_filename"
        )

        if candidate:

            candidate = str(
                candidate
            )

            if os.path.isfile(
                candidate
            ):

                return candidate

        return None

    # ==========================================================
    # SUBTITLES
    # ==========================================================

    @classmethod
    def _find_subtitle_files(
        cls,
        info: Dict[str, Any],
        output_directory: str,
        media_filepath: Optional[str],
        settings: Dict[str, Any],
    ) -> List[str]:

        found: List[str] = []

        # ------------------------------------------------------
        # 1. requested_subtitles
        # ------------------------------------------------------

        requested_subtitles = info.get(
            "requested_subtitles"
        )

        if isinstance(
            requested_subtitles,
            dict,
        ):

            for subtitle in (
                requested_subtitles.values()
            ):

                if not isinstance(
                    subtitle,
                    dict,
                ):
                    continue

                filepath = subtitle.get(
                    "filepath"
                )

                if (
                    filepath
                    and os.path.isfile(
                        str(filepath)
                    )
                ):

                    found.append(
                        os.path.abspath(
                            str(filepath)
                        )
                    )

        # ------------------------------------------------------
        # 2. requested_downloads
        # ------------------------------------------------------

        requested_downloads = info.get(
            "requested_downloads"
        )

        if isinstance(
            requested_downloads,
            list,
        ):

            for item in requested_downloads:

                if not isinstance(
                    item,
                    dict,
                ):
                    continue

                filepath = (
                    item.get(
                        "filepath"
                    )
                    or item.get(
                        "filename"
                    )
                )

                if not filepath:
                    continue

                filepath = str(
                    filepath
                )

                extension = (
                    os.path.splitext(
                        filepath
                    )[1].lower()
                )

                if (
                    extension
                    in cls.SUBTITLE_EXTENSIONS
                    and os.path.isfile(
                        filepath
                    )
                ):

                    found.append(
                        os.path.abspath(
                            filepath
                        )
                    )

        # ------------------------------------------------------
        # 3. Look next to the media file.
        # ------------------------------------------------------

        if media_filepath:

            media_dir = os.path.dirname(
                os.path.abspath(
                    media_filepath
                )
            )

            media_stem = os.path.splitext(
                os.path.basename(
                    media_filepath
                )
            )[0]

            if os.path.isdir(
                media_dir
            ):

                try:

                    for filename in os.listdir(
                        media_dir
                    ):

                        extension = (
                            os.path.splitext(
                                filename
                            )[1].lower()
                        )

                        if extension not in (
                            ".srt",
                            ".vtt",
                        ):
                            continue

                        filepath = os.path.join(
                            media_dir,
                            filename,
                        )

                        if not os.path.isfile(
                            filepath
                        ):
                            continue

                        # Prefer subtitle files belonging to
                        # this media item.
                        stem = os.path.splitext(
                            filename
                        )[0]

                        if (
                            stem == media_stem
                            or stem.startswith(
                                media_stem + "."
                            )
                            or stem.startswith(
                                media_stem + "_"
                            )
                        ):

                            found.append(
                                os.path.abspath(
                                    filepath
                                )
                            )

                except OSError:
                    pass

        # ------------------------------------------------------
        # 4. Last-resort output scan.
        # ------------------------------------------------------

        if os.path.isdir(
            output_directory
        ):

            try:

                for root, _, files in os.walk(
                    output_directory
                ):

                    for filename in files:

                        extension = (
                            os.path.splitext(
                                filename
                            )[1].lower()
                        )

                        if extension not in (
                            ".srt",
                            ".vtt",
                        ):
                            continue

                        filepath = os.path.join(
                            root,
                            filename,
                        )

                        if os.path.isfile(
                            filepath
                        ):

                            found.append(
                                os.path.abspath(
                                    filepath
                                )
                            )

            except OSError:
                pass

        # ------------------------------------------------------
        # Remove duplicates.
        # ------------------------------------------------------

        return list(
            dict.fromkeys(
                found
            )
        )

    # ==========================================================
    # RESPONSE
    # ==========================================================

    @staticmethod
    def _build_download_response(
        results: List[Dict[str, Any]],
        output_directory: str,
        mode: str,
    ) -> Dict[str, Any]:

        first = (
            results[0]
            if results
            else {}
        )

        return {

            "type": mode,
            "mode": mode,

            "items": results,
            "count": len(results),

            "output": output_directory,

            "cancelled": False,
            "completed": True,

            "filepath": first.get(
                "filepath"
            ),

            "path": first.get(
                "filepath"
            ),

            "subtitle_filepath": first.get(
                "subtitle_filepath"
            ),

            "subtitles": first.get(
                "subtitles",
                [],
            ),

            "has_subtitles": bool(
                first.get(
                    "has_subtitles"
                )
            ),

            "subtitles_available": bool(
                first.get(
                    "subtitles_available"
                )
            ),

            "subtitles_embedded": False,

            "title": first.get(
                "title"
            ),

            "url": first.get(
                "url"
            ),
        }

    # ==========================================================
    # PROGRESS HOOK
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
            str(
                data.get(
                    "filename",
                    data.get(
                        "tmpfilename",
                        "",
                    ),
                )
                or ""
            )
        )

        if status == "downloading":

            downloaded = (
                data.get(
                    "downloaded_bytes"
                )
                or 0
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

            if total:

                percentage = (
                    downloaded
                    * 100.0
                    / total
                )

            else:

                percentage = 0.0

            speed = data.get(
                "speed"
            )

            eta = data.get(
                "eta"
            )

            self._progress(
                "Downloading",
                filename,
                percentage,
                self._format_bytes(
                    downloaded
                ),
                self._format_speed(
                    speed
                ),
                self._format_seconds(
                    eta
                ),
            )

        elif status == "finished":

            self._progress(
                "Download finished",
                filename,
                100,
                self._format_bytes(
                    data.get(
                        "downloaded_bytes"
                    )
                ),
                self._format_speed(
                    data.get(
                        "speed"
                    )
                ),
                "00:00",
            )

    # ==========================================================
    # POSTPROCESSOR
    # ==========================================================

    def _postprocessor_hook(
        self,
        data: Dict[str, Any],
    ) -> None:

        self._check_cancelled()

        status = data.get(
            "status"
        )

        if status == "started":

            self._progress(
                "Processing download",
                "Media",
                100,
                "--",
                "--",
                "--:--",
            )

        elif status == "finished":

            self._progress(
                "Download processing complete",
                "Media",
                100,
                "Complete",
                "--",
                "00:00",
            )

    # ==========================================================
    # PROGRESS
    # ==========================================================

    def _progress(
        self,
        info: str,
        filename: str,
        percentage: Any,
        downloaded: Any = "--",
        speed: Any = "--",
        eta: Any = "--:--",
    ) -> None:

        if not self.progress_callback:
            return

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
                    int(
                        percentage
                    ),
                )

            except Exception:
                pass

        except Exception:
            pass

    # ==========================================================
    # FORMATTING
    # ==========================================================

    @staticmethod
    def _format_bytes(
        value: Any,
    ) -> str:

        if value is None:
            return "--"

        try:

            value = float(
                value
            )

        except (
            TypeError,
            ValueError,
        ):

            return "--"

        units = (
            "B",
            "KB",
            "MB",
            "GB",
            "TB",
        )

        index = 0

        while (
            value >= 1024
            and index < len(
                units
            ) - 1
        ):

            value /= 1024
            index += 1

        return (
            f"{value:.1f} "
            f"{units[index]}"
        )

    @classmethod
    def _format_speed(
        cls,
        value: Any,
    ) -> str:

        if value is None:
            return "--"

        try:

            value = float(
                value
            )

        except (
            TypeError,
            ValueError,
        ):

            return "--"

        return (
            cls._format_bytes(
                value
            )
            + "/s"
        )

    @staticmethod
    def _format_seconds(
        value: Any,
    ) -> str:

        if value is None:
            return "--:--"

        try:

            value = int(
                value
            )

        except (
            TypeError,
            ValueError,
        ):

            return "--:--"

        hours, remainder = divmod(
            value,
            3600,
        )

        minutes, seconds = divmod(
            remainder,
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

    @staticmethod
    def _audio_quality(
        quality: str,
    ) -> str:

        mapping = {
            "best": "320",
            "high": "320",
            "medium": "192",
            "low": "128",
        }

        return mapping.get(
            quality,
            quality
            if str(
                quality
            ).isdigit()
            else "320",
        )

    @staticmethod
    def _safe_int(
        value: Any,
        default: int,
    ) -> int:

        try:

            return int(
                value
            )

        except (
            TypeError,
            ValueError,
        ):

            return default

    @staticmethod
    def _starting_message(
        mode: str,
    ) -> str:

        return {

            "video":
                "Starting video + audio download",

            "audio":
                "Starting audio download",

            "subtitles":
                "Starting subtitle download",

            "video_subtitles":
                "Starting video + audio + subtitles",

        }.get(
            mode,
            "Starting download",
        )

    @staticmethod
    def _complete_message(
        mode: str,
    ) -> str:

        return {

            "video":
                "Video + audio download complete",

            "audio":
                "Audio download complete",

            "subtitles":
                "Subtitle download complete",

            "video_subtitles":
                "Video + audio + subtitles complete",

        }.get(
            mode,
            "Download complete",
        )

    @staticmethod
    def _url_name(
        url: str,
    ) -> str:

        return str(
            url
        )

    # ==========================================================
    # SUBTITLE WARNING
    # ==========================================================

    def _notify_subtitle_warning(
        self,
        error: Any,
    ) -> None:

        self._progress(
            "Subtitle download unavailable",
            "Subtitles",
            100,
            "--",
            "--",
            "00:00",
        )

        if self.error_callback:

            try:

                self.error_callback(
                    f"Subtitle warning: {error}"
                )

            except Exception:
                pass

    # ==========================================================
    # CANCEL CHECK
    # ==========================================================

    def _check_cancelled(
        self,
    ) -> None:

        if self._cancel_event.is_set():

            raise RuntimeError(
                "Download cancelled."
            )


class _YTDLPLogger:

    def __init__(
        self,
        owner: VideoDownloader,
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
        pass

    def error(
        self,
        message: str,
    ) -> None:

        self.owner._progress(
            str(
                message
            ),
            "yt-dlp",
            0,
            "--",
            "--",
            "--:--",
        )