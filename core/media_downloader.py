from __future__ import annotations

import os
import re
import threading

from typing import Any, Callable, Dict, List, Optional, Set


class MediaDownloader:
    """
    yt-dlp based media downloader.

    Modes
    -----

        video
            Video + audio.

        audio
            Audio only.

        subtitles
            Subtitle files only.

        video_subtitles
            Video + audio with optional subtitles.

    Subtitle behavior
    -----------------

        embed_subtitles=False
        save_separate_subtitle=True
            -> separate subtitle file

        embed_subtitles=True
        save_separate_subtitle=True
            -> embedded + separate subtitle file

        embed_subtitles=True
        save_separate_subtitle=False
            -> embedded subtitle only

        embed_subtitles=False
        save_separate_subtitle=False
            -> no subtitles

    IMPORTANT
    ---------

    Subtitle embedding is explicitly registered using:

        FFmpegEmbedSubtitle

    rather than relying only on the `embedsubtitles` option.

    FFmpeg must be installed and available to yt-dlp.
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

    MEDIA_EXTENSIONS = {
        ".mp4",
        ".mkv",
        ".webm",
        ".mov",
        ".avi",
        ".flv",
        ".ts",
        ".m4v",
        ".mp3",
        ".m4a",
        ".opus",
        ".ogg",
        ".wav",
        ".flac",
    }

    SUBTITLE_EXTENSIONS = {
        ".srt",
        ".vtt",
        ".ass",
        ".ssa",
        ".ttml",
        ".tt",
        ".dfxp",
        ".srv1",
        ".srv2",
        ".srv3",
        ".srv4",
    }

    # Matches:
    #
    #   video.f135.mp4
    #   video.f140.m4a
    #   video.f248.webm
    #   video.f248-something.webm
    #
    TEMP_FORMAT_RE = re.compile(
        r"\.f\d+(?:-[A-Za-z0-9_]+)?$",
        re.IGNORECASE,
    )

    # Containers supported by FFmpegEmbedSubtitlePP in yt-dlp.
    EMBEDDABLE_CONTAINERS = {
        "mp4",
        "mov",
        "m4a",
        "webm",
        "mkv",
        "mka",
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

        self._temporary_files: Set[str] = set()
        self._final_files: Set[str] = set()
        self._subtitle_files: Set[str] = set()

        self._current_filename = ""
        self._current_output_directory = ""

        # Overall download progress.
        self._download_totals: Dict[str, int] = {}
        self._downloaded_bytes: Dict[str, int] = {}

    # ==========================================================
    # PUBLIC
    # ==========================================================

    def download(
        self,
        settings: Dict[str, Any],
        media_result: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:

        self.reset_cancel()

        self._temporary_files.clear()
        self._final_files.clear()
        self._subtitle_files.clear()

        self._current_filename = ""

        self._download_totals.clear()
        self._downloaded_bytes.clear()

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

        self._current_output_directory = (
            output_directory
        )

        urls = self._get_urls(settings)

        if not urls and media_result:

            media_url = (
                media_result.get("url")
                if isinstance(media_result, dict)
                else None
            )

            if media_url:

                value = str(
                    media_url
                ).strip()

                if value:
                    urls = [value]

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

        completed = False
        cancelled = False

        try:

            with yt_dlp.YoutubeDL(options) as ydl:

                self._ydl = ydl

                for url in urls:

                    self._check_cancelled()

                    self._current_filename = (
                        self._url_name(url)
                    )

                    self._progress(
                        self._starting_message(
                            mode,
                            settings,
                        ),
                        self._current_filename,
                        0,
                        "--",
                        "--",
                        "--:--",
                    )

                    info = ydl.extract_info(
                        url,
                        download=True,
                    )

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
                            output_directory=(
                                output_directory
                            ),
                            mode=mode,
                            settings=settings,
                        )

                        results.append(result)

                    self._progress(
                        self._complete_message(
                            mode,
                            settings,
                        ),
                        self._current_filename,
                        100,
                        "Complete",
                        "--",
                        "00:00",
                    )

            completed = True

        except Exception as exc:

            cancelled = (
                self._cancel_event.is_set()
                or self._is_cancel_exception(exc)
            )

            if not cancelled:
                self._report_error(exc)

            raise

        finally:

            self._ydl = None

            # NEVER perform cleanup from a postprocessor hook.
            #
            # All yt-dlp postprocessors must finish first.
            if completed and not cancelled:

                try:

                    self._cleanup_intermediate_files(
                        results=results,
                        output_directory=output_directory,
                    )

                except Exception as exc:
                    self._report_error(exc)

        return self._build_download_response(
            results=results,
            output_directory=output_directory,
            mode=mode,
            settings=settings,
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
            "video subtitles": "video_subtitles",

            "subtitle": "subtitles",
            "subtitle_only": "subtitles",
            "subtitles_only": "subtitles",

            "audio_only": "audio",
            "audio-only": "audio",

            "video_only": "video",
            "video-only": "video",
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
    # OPTIONS
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

        allowed_containers = {
            "mp4",
            "mkv",
            "webm",
            "mov",
            "avi",
            "ts",
            "m4v",
        }

        if container not in allowed_containers:
            container = "mp4"

        embed = self._as_bool(
            settings.get(
                "embed_subtitles",
                False,
            )
        )

        separate = self._as_bool(
            settings.get(
                "save_separate_subtitle",
                True,
            )
        )

        subtitle_requested = (
            mode in {
                "subtitles",
                "video_subtitles",
            }
            and (
                embed
                or separate
            )
        )

        # ------------------------------------------------------
        # IMPORTANT:
        #
        # FFmpegEmbedSubtitlePP only supports:
        #
        # mp4, mov, m4a, webm, mkv, mka
        #
        # If embedding was requested but an unsupported output
        # container was selected, automatically use MKV.
        # ------------------------------------------------------

        if (
            mode == "video_subtitles"
            and embed
            and container
            not in self.EMBEDDABLE_CONTAINERS
        ):

            container = "mkv"

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

        playlist_folder = self._as_bool(
            settings.get(
                "playlist_folder",
                True,
            )
        )

        avoid_duplicates = self._as_bool(
            settings.get(
                "avoid_duplicates",
                True,
            )
        )

        options: Dict[str, Any] = {

            # --------------------------------------------------
            # Output
            # --------------------------------------------------

            "outtmpl": self._build_output_template(
                output_directory,
                playlist_folder,
            ),

            "noplaylist": False,

            # --------------------------------------------------
            # Download
            # --------------------------------------------------

            "concurrent_fragment_downloads": fragments,

            "retries": retries,

            "fragment_retries": retries,

            "file_access_retries": retries,

            "continuedl": True,

            # --------------------------------------------------
            # Console
            # --------------------------------------------------

            "quiet": True,

            "no_warnings": True,

            "ignoreerrors": False,

            "overwrites": not avoid_duplicates,

            # --------------------------------------------------
            # Progress
            # --------------------------------------------------

            "progress_hooks": [
                self._progress_hook,
            ],

            "postprocessor_hooks": [
                self._postprocessor_hook,
            ],

            "logger": _YTDLPLogger(
                self
            ),

            # --------------------------------------------------
            # Disable unwanted sidecars
            # --------------------------------------------------

            "writethumbnail": False,

            "writeinfojson": False,

            "writedescription": False,

            "writeannotations": False,

            "addmetadata": False,

            "embedthumbnail": False,

            # --------------------------------------------------
            # HTTP
            # --------------------------------------------------

            "http_headers": {
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/131.0 Safari/537.36"
                ),
                "Accept-Language": (
                    "en-US,en;q=0.9"
                ),
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
                    "preferredquality": (
                        self._audio_quality(
                            audio_quality
                        )
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
                    quality=quality,
                    container=container,
                )
            )

            options["merge_output_format"] = (
                container
            )

        # ======================================================
        # SUBTITLE DOWNLOAD
        # ======================================================

        if subtitle_requested:

            self._apply_subtitle_options(
                options=options,
                settings=settings,
            )

        # ======================================================
        # SUBTITLE-ONLY
        # ======================================================

        if mode == "subtitles":

            options["skip_download"] = True

        # ======================================================
        # EXPLICIT SUBTITLE EMBEDDING
        # ======================================================

        # This is the important fix.
        #
        # Do NOT rely solely on:
        #
        #     "embedsubtitles": True
        #
        # Explicitly install FFmpegEmbedSubtitle.
        #
        if (
            mode == "video_subtitles"
            and embed
        ):

            postprocessors = list(
                options.get(
                    "postprocessors",
                    [],
                )
            )

            postprocessors.append(
                {
                    "key": "FFmpegEmbedSubtitle",

                    # True means:
                    #
                    #   Keep the separately downloaded subtitle.
                    #
                    # False means:
                    #
                    #   Delete the subtitle after embedding.
                    #
                    "already_have_subtitle": (
                        separate
                    ),
                }
            )

            options["postprocessors"] = (
                postprocessors
            )

            # Keep this too because it correctly tells yt-dlp
            # that subtitle embedding is desired.
            options["embedsubtitles"] = True

        # ======================================================
        # COOKIES
        # ======================================================

        if self._as_bool(
            settings.get(
                "cookies",
                False,
            )
        ):

            browser = str(
                settings.get(
                    "cookie_browser",
                    "firefox",
                )
                or "firefox"
            ).strip().lower()

            if browser:

                options["cookiesfrombrowser"] = (
                    browser,
                )

        # ======================================================
        # SPONSORBLOCK
        # ======================================================

        if self._as_bool(
            settings.get(
                "sponsorblock",
                False,
            )
        ):

            options["sponsorblock_remove"] = [
                "sponsor",
                "selfpromo",
                "interaction",
                "intro",
                "outro",
                "preview",
            ]

        return options

    # ==========================================================
    # SUBTITLE OPTIONS
    # ==========================================================

    @staticmethod
    def _subtitles_requested(
        settings: Dict[str, Any],
    ) -> bool:

        embed = MediaDownloader._as_bool(
            settings.get(
                "embed_subtitles",
                False,
            )
        )

        separate = MediaDownloader._as_bool(
            settings.get(
                "save_separate_subtitle",
                True,
            )
        )

        return embed or separate

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
            "srt",
            "vtt",
        ):
            subtitle_format = "srt"

        embed = self._as_bool(
            settings.get(
                "embed_subtitles",
                False,
            )
        )

        separate = self._as_bool(
            settings.get(
                "save_separate_subtitle",
                True,
            )
        )

        if not embed and not separate:
            return

        # ------------------------------------------------------
        # Language
        # ------------------------------------------------------

        options["subtitleslangs"] = (
            self._subtitle_languages(
                language
            )
        )

        # ------------------------------------------------------
        # Format
        #
        # Use a preference expression instead of forcing one
        # format too aggressively.
        # ------------------------------------------------------

        options["subtitlesformat"] = (
            subtitle_format
        )

        # ------------------------------------------------------
        # Original subtitles
        # ------------------------------------------------------

        if subtitle_type == "original":

            options["writesubtitles"] = True

            options["writeautomaticsub"] = False

        # ------------------------------------------------------
        # Automatic subtitles
        # ------------------------------------------------------

        elif subtitle_type == "auto":

            options["writesubtitles"] = False

            options["writeautomaticsub"] = True

        # ------------------------------------------------------
        # Both / any
        # ------------------------------------------------------

        else:

            options["writesubtitles"] = True

            options["writeautomaticsub"] = True

        # ------------------------------------------------------
        # Explicitly tell yt-dlp that embedding is desired.
        #
        # The actual FFmpegEmbedSubtitle postprocessor is added
        # by _build_options().
        # ------------------------------------------------------

        options["embedsubtitles"] = embed

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
            return ["all"]

        return [
            language
        ]

    # ==========================================================
    # VIDEO FORMAT
    # ==========================================================

    @classmethod
    def _video_format(
        cls,
        quality: str,
        container: str,
    ) -> str:

        quality = str(
            quality or "best"
        ).strip().lower()

        # ------------------------------------------------------
        # MP4
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

            height = cls._quality_height(
                quality
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

            height = cls._quality_height(
                quality
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
        # MKV / MOV / others
        # ------------------------------------------------------

        if quality == "best":

            return (
                "bestvideo+bestaudio/best"
            )

        height = cls._quality_height(
            quality
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
            (list, tuple, set),
        ):

            for item in videos:

                if isinstance(
                    item,
                    dict,
                ):
                    url = item.get("url")
                else:
                    url = item

                if not url:
                    continue

                value = str(
                    url
                ).strip()

                if value:
                    urls.append(value)

        if not urls:

            url = settings.get(
                "url"
            )

            if url:

                value = str(
                    url
                ).strip()

                if value:
                    urls.append(value)

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
            return [info]

        flattened: List[Dict[str, Any]] = []

        for entry in entries:

            if not entry:
                continue

            if not isinstance(
                entry,
                dict,
            ):
                continue

            if entry.get("entries"):

                flattened.extend(
                    MediaDownloader._flatten_entries(
                        entry
                    )
                )

            else:

                flattened.append(
                    entry
                )

        return flattened

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

        filepath = (
            self._find_media_filepath(
                info=entry,
                mode=mode,
            )
        )

        separate = self._as_bool(
            settings.get(
                "save_separate_subtitle",
                True,
            )
        )

        embed = self._as_bool(
            settings.get(
                "embed_subtitles",
                False,
            )
        )

        subtitle_files: List[str] = []

        if (
            mode in {
                "subtitles",
                "video_subtitles",
            }
            and separate
        ):

            subtitle_files = (
                self._find_subtitle_files(
                    info=entry,
                    output_directory=(
                        output_directory
                    ),
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

        self._subtitle_files.update(
            absolute_subtitles
        )

        if absolute_filepath:
            self._final_files.add(
                absolute_filepath
            )

        temporary_files = (
            self._find_intermediate_files_for_media(
                filepath=filepath,
                info=entry,
            )
        )

        self._temporary_files.update(
            temporary_files
        )

        subtitle_format = str(
            settings.get(
                "subtitle_format",
                "srt",
            )
            or "srt"
        ).strip().lower().lstrip(".")

        if subtitle_format not in (
            "srt",
            "vtt",
        ):
            subtitle_format = "srt"

        return {
            "id": entry.get("id"),

            "title": entry.get("title"),

            "url": (
                entry.get("webpage_url")
                or entry.get("original_url")
            ),

            "filepath": absolute_filepath,

            "path": absolute_filepath,

            "duration": entry.get("duration"),

            "uploader": entry.get("uploader"),

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
                or (
                    embed
                    and mode == "video_subtitles"
                    and absolute_filepath
                )
            ),

            "subtitles_available": bool(
                absolute_subtitles
                or (
                    embed
                    and mode == "video_subtitles"
                    and absolute_filepath
                )
            ),

            "subtitles_embedded": (
                embed
                and mode == "video_subtitles"
                and bool(absolute_filepath)
            ),

            "embed_subtitles": embed,

            "save_separate_subtitle": separate,

            "output": output_directory,

            "type": mode,

            "mode": mode,

            "_temporary_files": [
                os.path.abspath(path)
                for path in temporary_files
            ],
        }

    # ==========================================================
    # MEDIA FILE
    # ==========================================================

    @classmethod
    def _find_media_filepath(
        cls,
        info: Dict[str, Any],
        mode: str,
    ) -> Optional[str]:

        if mode == "subtitles":
            return None

        candidates: List[str] = []

        for key in (
            "filepath",
            "_filename",
            "filename",
        ):

            value = info.get(key)

            if value:
                candidates.append(
                    str(value)
                )

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

                for key in (
                    "filepath",
                    "filename",
                ):

                    value = item.get(key)

                    if value:
                        candidates.append(
                            str(value)
                        )

        candidates = list(
            dict.fromkeys(
                candidates
            )
        )

        existing: List[str] = []

        for candidate in candidates:

            candidate = os.path.abspath(
                os.path.expanduser(
                    candidate
                )
            )

            if not os.path.isfile(candidate):
                continue

            extension = (
                os.path.splitext(
                    candidate
                )[1].lower()
            )

            if extension not in cls.MEDIA_EXTENSIONS:
                continue

            existing.append(candidate)

        if not existing:
            return None

        normal_files = [
            path
            for path in existing
            if not cls._is_temporary_format_file(
                path
            )
        ]

        if normal_files:
            return normal_files[0]

        return None

    # ==========================================================
    # SUBTITLE FILES
    # ==========================================================

    @classmethod
    def _find_subtitle_files(
        cls,
        info: Dict[str, Any],
        output_directory: str,
        media_filepath: Optional[str],
        settings: Dict[str, Any],
    ) -> List[str]:

        found: Set[str] = set()

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

                if not filepath:
                    continue

                filepath = os.path.abspath(
                    os.path.expanduser(
                        str(filepath)
                    )
                )

                if os.path.isfile(filepath):

                    found.add(filepath)

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
                    item.get("filepath")
                    or item.get("filename")
                )

                if not filepath:
                    continue

                filepath = os.path.abspath(
                    os.path.expanduser(
                        str(filepath)
                    )
                )

                extension = (
                    os.path.splitext(
                        filepath
                    )[1].lower()
                )

                if (
                    extension in cls.SUBTITLE_EXTENSIONS
                    and os.path.isfile(filepath)
                ):

                    found.add(filepath)

        search_directories: Set[str] = set()

        if media_filepath:

            search_directories.add(
                os.path.dirname(
                    os.path.abspath(
                        media_filepath
                    )
                )
            )

        search_directories.add(
            os.path.abspath(
                output_directory
            )
        )

        stems: Set[str] = set()

        if media_filepath:

            media_stem = os.path.splitext(
                os.path.basename(
                    media_filepath
                )
            )[0]

            stems.add(media_stem)

        for directory in search_directories:

            if not os.path.isdir(directory):
                continue

            try:

                for filename in os.listdir(
                    directory
                ):

                    extension = (
                        os.path.splitext(
                            filename
                        )[1].lower()
                    )

                    if extension not in {
                        ".srt",
                        ".vtt",
                        ".ass",
                        ".ssa",
                        ".ttml",
                        ".tt",
                        ".dfxp",
                    }:
                        continue

                    filepath = os.path.abspath(
                        os.path.join(
                            directory,
                            filename,
                        )
                    )

                    if not os.path.isfile(filepath):
                        continue

                    if stems:

                        stem = os.path.splitext(
                            filename
                        )[0]

                        matches = any(
                            stem == base
                            or stem.startswith(
                                base + "."
                            )
                            or stem.startswith(
                                base + "_"
                            )
                            for base in stems
                        )

                        if not matches:
                            continue

                    found.add(filepath)

            except OSError:
                pass

        requested_format = str(
            settings.get(
                "subtitle_format",
                "srt",
            )
            or "srt"
        ).strip().lower().lstrip(".")

        if requested_format in {
            "srt",
            "vtt",
        }:

            matching = [
                path
                for path in found
                if (
                    os.path.splitext(path)[1]
                    .lower()
                    .lstrip(".")
                    == requested_format
                )
            ]

            if matching:
                found = set(matching)

        return sorted(found)

    # ==========================================================
    # INTERMEDIATE FILES
    # ==========================================================

    @classmethod
    def _find_intermediate_files_for_media(
        cls,
        filepath: Optional[str],
        info: Dict[str, Any],
    ) -> List[str]:

        found: Set[str] = set()

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
                    item.get("filepath")
                    or item.get("filename")
                )

                if not candidate:
                    continue

                candidate = os.path.abspath(
                    os.path.expanduser(
                        str(candidate)
                    )
                )

                if (
                    os.path.isfile(candidate)
                    and cls._is_temporary_format_file(
                        candidate
                    )
                ):

                    found.add(candidate)

        if filepath:

            final_path = os.path.abspath(
                filepath
            )

            directory = os.path.dirname(
                final_path
            )

            final_stem = os.path.splitext(
                os.path.basename(
                    final_path
                )
            )[0]

            if os.path.isdir(directory):

                try:

                    for filename in os.listdir(
                        directory
                    ):

                        candidate = os.path.abspath(
                            os.path.join(
                                directory,
                                filename,
                            )
                        )

                        if not os.path.isfile(candidate):
                            continue

                        if candidate == final_path:
                            continue

                        if not cls._is_temporary_format_file(
                            candidate
                        ):
                            continue

                        candidate_stem = (
                            os.path.splitext(
                                filename
                            )[0]
                        )

                        if (
                            candidate_stem.startswith(
                                final_stem + "."
                            )
                            or candidate_stem.startswith(
                                final_stem + "_"
                            )
                        ):

                            found.add(candidate)

                except OSError:
                    pass

        return sorted(found)

    @classmethod
    def _is_temporary_format_file(
        cls,
        filepath: str,
    ) -> bool:

        filename = os.path.basename(
            str(filepath)
        )

        stem = os.path.splitext(
            filename
        )[0]

        return bool(
            cls.TEMP_FORMAT_RE.search(
                stem
            )
        )

    # ==========================================================
    # CLEANUP
    # ==========================================================

    def _cleanup_intermediate_files(
        self,
        results: List[Dict[str, Any]],
        output_directory: str,
    ) -> None:

        protected: Set[str] = {
            os.path.abspath(path)
            for path in self._final_files
        }

        protected.update(
            os.path.abspath(path)
            for path in self._subtitle_files
        )

        temporary: Set[str] = {
            os.path.abspath(path)
            for path in self._temporary_files
        }

        for result in results:

            for path in result.get(
                "_temporary_files",
                [],
            ):

                if path:
                    temporary.add(
                        os.path.abspath(
                            str(path)
                        )
                    )

            filepath = result.get(
                "filepath"
            )

            if filepath:
                protected.add(
                    os.path.abspath(
                        str(filepath)
                    )
                )

            for subtitle in result.get(
                "subtitles",
                [],
            ):

                if subtitle:
                    protected.add(
                        os.path.abspath(
                            str(subtitle)
                        )
                    )

        temporary.update(
            self._scan_for_intermediate_files(
                output_directory=output_directory,
                protected=protected,
                results=results,
            )
        )

        for path in sorted(temporary):

            path = os.path.abspath(path)

            if path in protected:
                continue

            if not os.path.isfile(path):
                continue

            if not self._is_temporary_format_file(
                path
            ):
                continue

            try:

                os.remove(path)

            except OSError as exc:

                self._report_error(
                    RuntimeError(
                        "Could not remove temporary "
                        f"media file '{path}': {exc}"
                    )
                )

    def _scan_for_intermediate_files(
        self,
        output_directory: str,
        protected: Set[str],
        results: List[Dict[str, Any]],
    ) -> Set[str]:

        found: Set[str] = set()

        final_paths: Set[str] = {
            os.path.abspath(
                str(result["filepath"])
            )
            for result in results
            if result.get("filepath")
        }

        if not os.path.isdir(
            output_directory
        ):
            return found

        try:

            for root, _dirs, files in os.walk(
                output_directory
            ):

                for filename in files:

                    candidate = os.path.abspath(
                        os.path.join(
                            root,
                            filename,
                        )
                    )

                    if candidate in protected:
                        continue

                    if candidate in final_paths:
                        continue

                    if not self._is_temporary_format_file(
                        candidate
                    ):
                        continue

                    candidate_stem = (
                        os.path.splitext(
                            filename
                        )[0]
                    )

                    for final_path in final_paths:

                        final_stem = (
                            os.path.splitext(
                                os.path.basename(
                                    final_path
                                )
                            )[0]
                        )

                        if (
                            candidate_stem.startswith(
                                final_stem + "."
                            )
                            or candidate_stem.startswith(
                                final_stem + "_"
                            )
                        ):

                            found.add(candidate)
                            break

        except OSError:
            pass

        return found

    # ==========================================================
    # RESPONSE
    # ==========================================================

    @staticmethod
    def _build_download_response(
        results: List[Dict[str, Any]],
        output_directory: str,
        mode: str,
        settings: Dict[str, Any],
    ) -> Dict[str, Any]:

        public_results: List[Dict[str, Any]] = []

        for item in results:

            public_item = dict(item)

            public_item.pop(
                "_temporary_files",
                None,
            )

            public_results.append(
                public_item
            )

        first = (
            public_results[0]
            if public_results
            else {}
        )

        return {
            "type": mode,

            "mode": mode,

            "items": public_results,

            "count": len(public_results),

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

            "subtitles_embedded": bool(
                first.get(
                    "subtitles_embedded"
                )
            ),

            "embed_subtitles": (
                MediaDownloader._as_bool(
                    settings.get(
                        "embed_subtitles",
                        False,
                    )
                )
            ),

            "save_separate_subtitle": (
                MediaDownloader._as_bool(
                    settings.get(
                        "save_separate_subtitle",
                        True,
                    )
                )
            ),

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

        if filename:
            self._current_filename = filename

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

            key = str(
                data.get(
                    "filename",
                    data.get(
                        "tmpfilename",
                        filename,
                    ),
                )
                or filename
            )

            if total > 0:

                self._download_totals[key] = (
                    int(total)
                )

            self._downloaded_bytes[key] = (
                int(downloaded)
            )

            overall_downloaded = sum(
                self._downloaded_bytes.values()
            )

            overall_total = sum(
                self._download_totals.values()
            )

            percentage = (
                overall_downloaded
                * 100.0
                / overall_total
                if overall_total
                else 0.0
            )

            self._progress(
                "Downloading",
                filename or self._current_filename,
                percentage,
                self._format_bytes(
                    overall_downloaded
                ),
                self._format_speed(
                    data.get("speed")
                ),
                self._format_seconds(
                    data.get("eta")
                ),
            )

        elif status == "finished":

            finished_filename = (
                filename
                or self._current_filename
            )

            key = str(
                data.get(
                    "filename",
                    data.get(
                        "tmpfilename",
                        finished_filename,
                    ),
                )
                or finished_filename
            )

            downloaded = (
                data.get(
                    "downloaded_bytes"
                )
                or self._downloaded_bytes.get(
                    key,
                    0,
                )
            )

            total = (
                data.get(
                    "total_bytes"
                )
                or data.get(
                    "total_bytes_estimate"
                )
                or self._download_totals.get(
                    key,
                    0,
                )
            )

            if total:
                self._download_totals[key] = (
                    int(total)
                )

            self._downloaded_bytes[key] = (
                int(downloaded)
            )

            if finished_filename:

                full_path = (
                    self._resolve_hook_path(
                        finished_filename
                    )
                )

                if full_path:

                    if self._is_temporary_format_file(
                        full_path
                    ):

                        self._temporary_files.add(
                            full_path
                        )

                    elif os.path.isfile(
                        full_path
                    ):

                        self._final_files.add(
                            full_path
                        )

            overall_downloaded = sum(
                self._downloaded_bytes.values()
            )

            overall_total = sum(
                self._download_totals.values()
            )

            percentage = (
                overall_downloaded
                * 100.0
                / overall_total
                if overall_total
                else 0.0
            )

            self._progress(
                "Download finished",
                finished_filename,
                percentage,
                self._format_bytes(
                    overall_downloaded
                ),
                "--",
                "--:--",
            )

    # ==========================================================
    # POSTPROCESSOR HOOK
    # ==========================================================

    def _postprocessor_hook(
        self,
        data: Dict[str, Any],
    ) -> None:

        self._check_cancelled()

        status = data.get(
            "status"
        )

        postprocessor = str(
            data.get(
                "postprocessor",
                "",
            )
            or ""
        )

        info_dict = data.get(
            "info_dict"
        )

        if not isinstance(
            info_dict,
            dict,
        ):
            info_dict = {}

        paths: List[str] = []

        for key in (
            "filepath",
            "_filename",
            "filename",
        ):

            value = info_dict.get(key)

            if value:

                path = self._resolve_hook_path(
                    str(value)
                )

                if path:
                    paths.append(path)

        direct_filepath = data.get(
            "filepath"
        )

        if direct_filepath:

            path = self._resolve_hook_path(
                str(direct_filepath)
            )

            if path:
                paths.append(path)

        for path in paths:

            if self._is_temporary_format_file(
                path
            ):

                self._temporary_files.add(path)

            elif os.path.isfile(path):

                self._final_files.add(path)

        requested_subtitles = (
            info_dict.get(
                "requested_subtitles"
            )
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

                subtitle_path = subtitle.get(
                    "filepath"
                )

                if not subtitle_path:
                    continue

                subtitle_path = (
                    self._resolve_hook_path(
                        str(
                            subtitle_path
                        )
                    )
                )

                if (
                    subtitle_path
                    and os.path.isfile(
                        subtitle_path
                    )
                ):

                    self._subtitle_files.add(
                        subtitle_path
                    )

        if status == "started":

            message = (
                f"Processing {postprocessor}"
                if postprocessor
                else "Processing download"
            )

            self._progress(
                message,
                self._current_filename
                or "Media",
                0,
                "--",
                "--",
                "--:--",
            )

        elif status == "finished":

            message = (
                f"Finished {postprocessor}"
                if postprocessor
                else "Download processing complete"
            )

            self._progress(
                message,
                self._current_filename
                or "Media",
                100,
                "Complete",
                "--",
                "00:00",
            )

    # ==========================================================
    # PATH
    # ==========================================================

    @staticmethod
    def _resolve_hook_path(
        filepath: str,
    ) -> Optional[str]:

        filepath = str(
            filepath or ""
        ).strip()

        if not filepath:
            return None

        return os.path.abspath(
            os.path.expanduser(
                filepath
            )
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
            value = float(value)
        except (
            TypeError,
            ValueError,
        ):
            return "--"

        if value < 0:
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
            and index < len(units) - 1
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
            value = float(value)
        except (
            TypeError,
            ValueError,
        ):
            return "--"

        if value < 0:
            return "--"

        return (
            cls._format_bytes(value)
            + "/s"
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

        if value < 0:
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

    # ==========================================================
    # AUDIO QUALITY
    # ==========================================================

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

    # ==========================================================
    # HELPERS
    # ==========================================================

    @staticmethod
    def _safe_int(
        value: Any,
        default: int,
    ) -> int:

        try:
            return int(value)
        except (
            TypeError,
            ValueError,
        ):
            return default

    @staticmethod
    def _as_bool(
        value: Any,
    ) -> bool:

        if isinstance(
            value,
            bool,
        ):
            return value

        if value is None:
            return False

        if isinstance(
            value,
            (int, float),
        ):
            return bool(value)

        value = str(
            value
        ).strip().lower()

        return value in {
            "1",
            "true",
            "yes",
            "y",
            "on",
        }

    # ==========================================================
    # MESSAGES
    # ==========================================================

    @staticmethod
    def _starting_message(
        mode: str,
        settings: Dict[str, Any],
    ) -> str:

        if mode == "video_subtitles":

            embed = MediaDownloader._as_bool(
                settings.get(
                    "embed_subtitles",
                    False,
                )
            )

            separate = MediaDownloader._as_bool(
                settings.get(
                    "save_separate_subtitle",
                    True,
                )
            )

            if embed and separate:

                return (
                    "Starting video + audio "
                    "+ embedded + separate subtitles"
                )

            if embed:

                return (
                    "Starting video + audio "
                    "+ embedded subtitles"
                )

            if separate:

                return (
                    "Starting video + audio "
                    "+ separate subtitles"
                )

            return (
                "Starting video + audio download"
            )

        return {
            "video": (
                "Starting video + audio download"
            ),
            "audio": (
                "Starting audio download"
            ),
            "subtitles": (
                "Starting subtitle download"
            ),
        }.get(
            mode,
            "Starting download",
        )

    @staticmethod
    def _complete_message(
        mode: str,
        settings: Dict[str, Any],
    ) -> str:

        if mode == "video_subtitles":

            embed = MediaDownloader._as_bool(
                settings.get(
                    "embed_subtitles",
                    False,
                )
            )

            separate = MediaDownloader._as_bool(
                settings.get(
                    "save_separate_subtitle",
                    True,
                )
            )

            if embed and separate:

                return (
                    "Video + audio + embedded "
                    "+ separate subtitles complete"
                )

            if embed:

                return (
                    "Video + audio + embedded "
                    "subtitles complete"
                )

            if separate:

                return (
                    "Video + audio + separate "
                    "subtitles complete"
                )

            return (
                "Video + audio download complete"
            )

        return {
            "video": (
                "Video + audio download complete"
            ),
            "audio": (
                "Audio download complete"
            ),
            "subtitles": (
                "Subtitle download complete"
            ),
        }.get(
            mode,
            "Download complete",
        )

    @staticmethod
    def _url_name(
        url: str,
    ) -> str:

        return str(url)

    # ==========================================================
    # CANCEL CHECK
    # ==========================================================

    def _check_cancelled(self) -> None:

        if self._cancel_event.is_set():

            raise RuntimeError(
                "Download cancelled."
            )

    @staticmethod
    def _is_cancel_exception(
        error: BaseException,
    ) -> bool:

        message = str(
            error
        ).lower()

        return (
            "cancel" in message
            or "interrupted" in message
        )

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


class _YTDLPLogger:

    def __init__(
        self,
        owner: MediaDownloader,
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
            str(message),
            "yt-dlp",
            0,
            "--",
            "--",
            "--:--",
        )