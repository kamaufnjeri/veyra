from __future__ import annotations

import os

from typing import (
    Any,
    Callable,
    Dict,
    Optional,
    Set,
)

from core.media_downloader import MediaDownloader
from core.media_encoder import MediaEncoder
from core.media_info import MediaInfo


class MediaService:
    """
    Main media orchestration service.

    Supported modes:

        video
            Video + audio.

        audio
            Audio only.

        subtitles
            Subtitles only.

        video_subtitles
            Video + audio with optional subtitle handling.

    Subtitle behavior:

        embed_subtitles=False
        save_separate_subtitle=True
            -> separate subtitle only

        embed_subtitles=True
        save_separate_subtitle=True
            -> embedded + separate

        embed_subtitles=True
        save_separate_subtitle=False
            -> embedded only

        embed_subtitles=False
        save_separate_subtitle=False
            -> no subtitles

    Defaults:

        embed_subtitles=False
        save_separate_subtitle=True

    Processing flow:

        Downloader
            ↓
        yt-dlp post-processing
            ↓
        final downloaded media
            ↓
        MediaEncoder compatibility check
            ↓
        final MP4
            ↓
        cleanup of temporary yt-dlp files

    MediaEncoder remains responsible only for final
    video compatibility/processing.
    """

    DOWNLOAD_MODES = {
        "video",
        "audio",
        "subtitles",
        "video_subtitles",
    }

    SUBTITLE_TYPES = {
        "any",
        "original",
        "auto",
        "translated",
    }

    SUBTITLE_FORMATS = {
        "srt",
        "vtt",
    }

    CONTAINERS = {
        "mp4",
        "mkv",
        "webm",
        "native",
    }

    def __init__(
        self,
        progress_callback: Optional[
            Callable[..., None]
        ] = None,
        error_callback: Optional[
            Callable[[Any], None]
        ] = None,
        finished_callback: Optional[
            Callable[..., None]
        ] = None,
        cancelled_callback: Optional[
            Callable[..., None]
        ] = None,
        video_downloader: Optional[
            MediaDownloader
        ] = None,
        encoder: Optional[
            MediaEncoder
        ] = None,
        media_info: Optional[
            MediaInfo
        ] = None,
    ) -> None:

        self.progress_callback = (
            progress_callback
        )

        self.error_callback = (
            error_callback
        )

        self.finished_callback = (
            finished_callback
        )

        self.cancelled_callback = (
            cancelled_callback
        )

        self.cancelled = False

        self._progress_stage = "idle"

        # ------------------------------------------------------
        # Downloader
        # ------------------------------------------------------

        self.video_downloader = (
            video_downloader
            or MediaDownloader(
                progress_callback=(
                    self._core_progress
                ),
                error_callback=(
                    self._error
                ),
            )
        )

        # ------------------------------------------------------
        # Encoder
        # ------------------------------------------------------

        self.encoder = (
            encoder
            or MediaEncoder(
                progress_callback=(
                    self._encoder_progress
                ),
                error_callback=(
                    self._error
                ),
            )
        )

        # ------------------------------------------------------
        # Media information
        # ------------------------------------------------------

        self.media_info = (
            media_info
            or MediaInfo(
                progress_callback=(
                    self._core_progress
                ),
                error_callback=(
                    self._error
                ),
            )
        )

    # ==========================================================
    # PUBLIC
    # ==========================================================

    def download(
        self,
        settings: Dict[str, Any],
    ) -> Dict[str, Any]:

        return self.create_media(
            settings
        )

    def start_download(
        self,
        settings: Dict[str, Any],
    ) -> Dict[str, Any]:

        return self.create_media(
            settings
        )

    # ==========================================================
    # CANCEL
    # ==========================================================

    def cancel(
        self,
    ) -> None:

        self.cancelled = True

        for component in (
            self.video_downloader,
            self.encoder,
        ):

            cancel = getattr(
                component,
                "cancel",
                None,
            )

            if callable(cancel):

                try:

                    cancel()

                except Exception as exc:

                    self._error(
                        exc
                    )

    def reset_cancel(
        self,
    ) -> None:

        self.cancelled = False

        for component in (
            self.video_downloader,
            self.encoder,
        ):

            reset = getattr(
                component,
                "reset_cancel",
                None,
            )

            if callable(reset):

                try:

                    reset()

                except Exception as exc:

                    self._error(
                        exc
                    )

    # ==========================================================
    # MAIN
    # ==========================================================

    def create_media(
        self,
        settings: Dict[str, Any],
    ) -> Dict[str, Any]:

        self.reset_cancel()

        settings = (
            self._normalize_settings(
                settings
            )
        )

        self._validate_settings(
            settings
        )

        mode = settings[
            "download_mode"
        ]

        filename = (
            self._display_name(
                settings
            )
        )

        self._progress_stage = (
            "preparing"
        )

        self._progress(
            "Preparing download",
            filename,
            0,
            "--",
            "--",
            "--:--",
        )

        if self.cancelled:

            return (
                self._cancelled_result(
                    settings
                )
            )

        try:

            if mode == "video":

                result = (
                    self._download_video(
                        settings
                    )
                )

            elif mode == "audio":

                result = (
                    self._download_audio(
                        settings
                    )
                )

            elif mode == "subtitles":

                result = (
                    self._download_subtitles(
                        settings
                    )
                )

            elif mode == "video_subtitles":

                result = (
                    self._download_video_with_subtitles(
                        settings
                    )
                )

            else:

                raise ValueError(
                    f"Unsupported download mode: "
                    f"{mode}"
                )

            if self.cancelled:

                self._cancelled(
                    settings
                )

                return (
                    self._cancelled_result(
                        settings
                    )
                )

            self._progress_stage = (
                "complete"
            )

            self._progress(
                "Download complete",
                filename,
                100,
                "Complete",
                "--",
                "00:00",
            )

            self._finished(
                result
            )

            return result

        except KeyboardInterrupt:

            self.cancel()

            self._cancelled(
                settings
            )

            raise

        except Exception as exc:

            if self.cancelled:

                self._cancelled(
                    settings
                )

                return (
                    self._cancelled_result(
                        settings
                    )
                )

            self._error(
                exc
            )

            raise

    # ==========================================================
    # VIDEO
    # ==========================================================

    def _download_video(
        self,
        settings: Dict[str, Any],
    ) -> Dict[str, Any]:

        filename = (
            self._display_name(
                settings
            )
        )

        self._progress_stage = (
            "video_download"
        )

        self._progress(
            "Downloading video + audio",
            filename,
            0,
            "--",
            "--",
            "--:--",
        )

        video_settings = dict(
            settings
        )

        video_settings[
            "download_mode"
        ] = "video"

        result = (
            self.video_downloader.download(
                video_settings
            )
        )

        if not result:

            raise RuntimeError(
                "Video downloader returned "
                "no result."
            )

        if self.cancelled:
            return result

        return self._process_video(
            result,
            filename,
            subtitle_mode=False,
        )

    # ==========================================================
    # VIDEO + SUBTITLES
    # ==========================================================

    def _download_video_with_subtitles(
        self,
        settings: Dict[str, Any],
    ) -> Dict[str, Any]:

        filename = (
            self._display_name(
                settings
            )
        )

        embed = bool(
            settings.get(
                "embed_subtitles",
                False,
            )
        )

        separate = bool(
            settings.get(
                "save_separate_subtitle",
                True,
            )
        )

        self._progress_stage = (
            "video_subtitles_video"
        )

        if embed and separate:

            message = (
                "Downloading video + audio "
                "+ embedded + separate subtitles"
            )

        elif embed:

            message = (
                "Downloading video + audio "
                "+ embedded subtitles"
            )

        elif separate:

            message = (
                "Downloading video + audio "
                "+ separate subtitles"
            )

        else:

            message = (
                "Downloading video + audio"
            )

        self._progress(
            message,
            filename,
            0,
            "--",
            "--",
            "--:--",
        )

        video_settings = dict(
            settings
        )

        video_settings[
            "download_mode"
        ] = "video_subtitles"

        result = (
            self.video_downloader.download(
                video_settings
            )
        )
        

        if not result:

            raise RuntimeError(
                "Video downloader returned "
                "no result."
            )

        result["embed_subtitles"] = embed
        result["save_separate_subtitle"] = separate
        if self.cancelled:
            return result

        # ------------------------------------------------------
        # yt-dlp has already completed subtitle processing
        # before download() returns.
        #
        # Therefore this is a boundary notification only.
        # We do NOT fake another 0-100 operation.
        # ------------------------------------------------------

        if embed or separate:

            self._progress_stage = (
                "video_subtitles_subtitles"
            )

            has_subtitles = bool(
                result.get(
                    "has_subtitles",
                    False,
                )
            )

            embedded = bool(
                result.get(
                    "subtitles_embedded",
                    False,
                )
            )

            if (
                embed
                and separate
                and has_subtitles
            ):

                self._progress(
                    "Subtitles embedded and "
                    "saved separately",
                    filename,
                    85,
                    "Complete",
                    "--",
                    "--:--",
                )

            elif embed and embedded:

                self._progress(
                    "Subtitles embedded",
                    filename,
                    85,
                    "Complete",
                    "--",
                    "--:--",
                )

            elif separate and has_subtitles:

                self._progress(
                    "Subtitles saved separately",
                    filename,
                    85,
                    "Complete",
                    "--",
                    "--:--",
                )

            else:

                self._progress(
                    "No subtitles available",
                    filename,
                    85,
                    "--",
                    "--",
                    "--:--",
                )

        # ------------------------------------------------------
        # Final video processing.
        # ------------------------------------------------------

        return self._process_video(
            result,
            filename,
            subtitle_mode=(
                embed or separate
            ),
        )

    # ==========================================================
    # VIDEO PROCESSING
    # ==========================================================

    def _process_video(
        self,
        result: Dict[str, Any],
        filename: str,
        subtitle_mode: bool = False,
    ) -> Dict[str, Any]:

        filepath = result.get("filepath")

        if not filepath:
            raise RuntimeError(
                "Downloaded video filepath was not returned."
            )

        filepath = os.path.abspath(str(filepath))

        if not os.path.isfile(filepath):
            raise RuntimeError(
                f"Downloaded video was not found: {filepath}"
            )

        self._progress_stage = (
            "video_subtitles_processing"
            if subtitle_mode
            else "video_processing"
        )

        self._progress(
            "Checking video compatibility",
            filename,
            90,
            "--",
            "--",
            "--:--",
        )

        original_filepath = filepath

        # Embedded subtitles are preserved ONLY when the
        # user explicitly selected embed_subtitles=True.
        preserve_subtitles = bool(
            subtitle_mode
            and result.get(
                "embed_subtitles",
                False,
            )
        )

        processed = self.encoder.encode(
            filepath,
            "mp4",
            preserve_subtitles=preserve_subtitles,
        )

        if processed:
            processed = os.path.abspath(str(processed))

            if not os.path.isfile(processed):
                raise RuntimeError(
                    "MediaEncoder returned a file that does not exist: "
                    f"{processed}"
                )

            result["filepath"] = processed
            result["path"] = processed

            # Only remove the original if the encoder produced
            # a different file.
            if (
                processed != original_filepath
                and os.path.isfile(original_filepath)
            ):
                self._safe_remove(original_filepath)

        self._cleanup_result_temporary_files(
            result=result,
            final_filepath=result.get("filepath"),
        )

        return result

    # ==========================================================
    # AUDIO
    # ==========================================================

    def _download_audio(
        self,
        settings: Dict[str, Any],
    ) -> Dict[str, Any]:

        filename = (
            self._display_name(
                settings
            )
        )

        self._progress_stage = (
            "audio"
        )

        self._progress(
            "Downloading audio",
            filename,
            0,
            "--",
            "--",
            "--:--",
        )

        audio_settings = dict(
            settings
        )

        audio_settings[
            "download_mode"
        ] = "audio"

        result = (
            self.video_downloader.download(
                audio_settings
            )
        )

        if not result:

            raise RuntimeError(
                "Audio downloader returned "
                "no result."
            )

        self._cleanup_result_temporary_files(
            result=result,
            final_filepath=result.get(
                "filepath"
            ),
        )

        return result

    # ==========================================================
    # SUBTITLES
    # ==========================================================

    def _download_subtitles(
        self,
        settings: Dict[str, Any],
    ) -> Dict[str, Any]:

        filename = (
            self._display_name(
                settings
            )
        )

        self._progress_stage = (
            "subtitles"
        )

        self._progress(
            "Downloading subtitles",
            filename,
            0,
            "--",
            "--",
            "--:--",
        )

        subtitle_settings = dict(
            settings
        )

        subtitle_settings[
            "download_mode"
        ] = "subtitles"

        # Subtitle-only mode is inherently separate.
        subtitle_settings[
            "embed_subtitles"
        ] = False

        subtitle_settings[
            "save_separate_subtitle"
        ] = True

        result = (
            self.video_downloader.download(
                subtitle_settings
            )
        )

        if not result:

            raise RuntimeError(
                "Subtitle downloader returned "
                "no result."
            )

        if not result.get(
            "has_subtitles",
            False,
        ):

            raise RuntimeError(
                "No subtitles were found."
            )

        self._cleanup_result_temporary_files(
            result=result,
            final_filepath=None,
        )

        return result

    # ==========================================================
    # TEMPORARY FILE CLEANUP
    # ==========================================================

    def _cleanup_result_temporary_files(
        self,
        result: Dict[str, Any],
        final_filepath: Optional[str],
    ) -> None:

        temporary_files = result.get(
            "_temporary_files",
            [],
        )

        if not isinstance(
            temporary_files,
            list,
        ):

            return

        final_path = (
            os.path.abspath(
                str(final_filepath)
            )
            if final_filepath
            else None
        )

        protected: Set[str] = set()

        if final_path:
            protected.add(
                final_path
            )

        subtitle_filepath = result.get(
            "subtitle_filepath"
        )

        if subtitle_filepath:

            protected.add(
                os.path.abspath(
                    str(
                        subtitle_filepath
                    )
                )
            )

        subtitles = result.get(
            "subtitles",
            [],
        )

        if isinstance(
            subtitles,
            list,
        ):

            for subtitle in subtitles:

                if subtitle:

                    protected.add(
                        os.path.abspath(
                            str(subtitle)
                        )
                    )

        for temporary in temporary_files:

            if not temporary:
                continue

            path = os.path.abspath(
                str(temporary)
            )

            if path in protected:
                continue

            self._safe_remove(
                path
            )

        # Remove internal metadata.
        result.pop(
            "_temporary_files",
            None,
        )

    @staticmethod
    def _safe_remove(
        filepath: str,
    ) -> None:

        try:

            filepath = os.path.abspath(
                str(filepath)
            )

            if os.path.isfile(
                filepath
            ):

                os.remove(
                    filepath
                )

        except OSError:
            pass

    # ==========================================================
    # NORMALIZATION
    # ==========================================================

    def _normalize_settings(
        self,
        settings: Dict[str, Any],
    ) -> Dict[str, Any]:

        settings = dict(
            settings or {}
        )

        mode = str(
            settings.get(
                "download_mode",
                "video_subtitles",
            )
            or "video_subtitles"
        ).strip().lower()

        aliases = {
            "video+subtitles": (
                "video_subtitles"
            ),
            "video_subtitle": (
                "video_subtitles"
            ),
            "video-with-subtitles": (
                "video_subtitles"
            ),
            "video_with_subtitles": (
                "video_subtitles"
            ),
            "subtitle": "subtitles",
            "audio_only": "audio",
            "video_only": "video",
        }

        mode = aliases.get(
            mode,
            mode,
        )

        settings[
            "download_mode"
        ] = mode

        settings[
            "url"
        ] = str(
            settings.get(
                "url",
                "",
            )
            or ""
        ).strip()

        raw_output = str(
            settings.get(
                "output",
                "",
            )
            or ""
        ).strip()

        settings[
            "output"
        ] = (
            os.path.abspath(
                os.path.expanduser(
                    raw_output
                )
            )
            if raw_output
            else ""
        )

        settings[
            "quality"
        ] = str(
            settings.get(
                "quality",
                "best",
            )
            or "best"
        ).strip().lower()

        settings[
            "container"
        ] = str(
            settings.get(
                "container",
                "mp4",
            )
            or "mp4"
        ).strip().lower().lstrip(".")

        settings[
            "audio_quality"
        ] = str(
            settings.get(
                "audio_quality",
                "best",
            )
            or "best"
        ).strip().lower()

        # ------------------------------------------------------
        # SUBTITLE DEFAULTS
        # ------------------------------------------------------

        settings[
            "embed_subtitles"
        ] = bool(
            settings.get(
                "embed_subtitles",
                False,
            )
        )

        settings[
            "save_separate_subtitle"
        ] = bool(
            settings.get(
                "save_separate_subtitle",
                True,
            )
        )

        settings[
            "download_subtitles"
        ] = (
            settings[
                "embed_subtitles"
            ]
            or settings[
                "save_separate_subtitle"
            ]
        )

        settings[
            "subtitle_language"
        ] = str(
            settings.get(
                "subtitle_language",
                "en",
            )
            or "en"
        ).strip().lower()

        settings[
            "subtitle_type"
        ] = str(
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

        if (
            subtitle_format
            not in self.SUBTITLE_FORMATS
        ):

            subtitle_format = "srt"

        settings[
            "subtitle_format"
        ] = subtitle_format

        # ------------------------------------------------------
        # OTHER SETTINGS
        # ------------------------------------------------------

        settings[
            "playlist_folder"
        ] = bool(
            settings.get(
                "playlist_folder",
                True,
            )
        )

        settings[
            "avoid_duplicates"
        ] = bool(
            settings.get(
                "avoid_duplicates",
                True,
            )
        )

        settings[
            "fragments"
        ] = self._integer_setting(
            settings.get(
                "fragments",
                8,
            ),
            default=8,
            minimum=1,
            maximum=32,
        )

        settings[
            "retries"
        ] = self._integer_setting(
            settings.get(
                "retries",
                10,
            ),
            default=10,
            minimum=0,
            maximum=100,
        )

        settings[
            "cookies"
        ] = bool(
            settings.get(
                "cookies",
                False,
            )
        )

        settings[
            "sponsorblock"
        ] = bool(
            settings.get(
                "sponsorblock",
                False,
            )
        )

        videos = settings.get(
            "videos",
            [],
        )

        if not isinstance(
            videos,
            list,
        ):

            videos = []

        settings[
            "videos"
        ] = videos

        return settings

    # ==========================================================
    # VALIDATION
    # ==========================================================

    def _validate_settings(
        self,
        settings: Dict[str, Any],
    ) -> None:

        mode = settings[
            "download_mode"
        ]

        if mode not in self.DOWNLOAD_MODES:

            raise ValueError(
                f"Invalid download mode: {mode}. "
                f"Valid modes are: "
                f"{', '.join(sorted(self.DOWNLOAD_MODES))}"
            )

        if (
            not settings["url"]
            and not settings["videos"]
        ):

            raise ValueError(
                "A URL or media item is required."
            )

        if not settings[
            "output"
        ]:

            raise ValueError(
                "Output directory is required."
            )

        container = settings[
            "container"
        ]

        if container not in self.CONTAINERS:

            raise ValueError(
                f"Unsupported container: "
                f"{container}"
            )

        subtitle_type = settings[
            "subtitle_type"
        ]

        if (
            subtitle_type
            not in self.SUBTITLE_TYPES
        ):

            raise ValueError(
                "Unsupported subtitle type: "
                f"{subtitle_type}"
            )

        subtitle_format = settings[
            "subtitle_format"
        ]

        if (
            subtitle_format
            not in self.SUBTITLE_FORMATS
        ):

            raise ValueError(
                "Unsupported subtitle format: "
                f"{subtitle_format}"
            )

        try:

            os.makedirs(
                settings["output"],
                exist_ok=True,
            )

        except OSError as exc:

            raise RuntimeError(
                "Cannot create output directory: "
                f"{settings['output']}"
            ) from exc

    # ==========================================================
    # DOWNLOADER PROGRESS
    # ==========================================================

    def _core_progress(
        self,
        info: str,
        filename: str,
        percentage: Any = 0,
        downloaded: Any = "--",
        speed: Any = "--",
        eta: Any = "--:--",
        *_args: Any,
    ) -> None:

        percentage = (
            self._safe_percentage_float(
                percentage
            )
        )

        stage = (
            self._progress_stage
        )

        # ------------------------------------------------------
        # Normal video download
        # ------------------------------------------------------

        if stage == "video_download":

            overall = (
                percentage * 0.90
            )

        # ------------------------------------------------------
        # Video + subtitles:
        #
        # Video/audio = 0–85%
        # Subtitle boundary = 85%
        # Processing = 90–100%
        # ------------------------------------------------------

        elif (
            stage
            == "video_subtitles_video"
        ):

            overall = (
                percentage * 0.85
            )

        elif (
            stage
            == "video_subtitles_subtitles"
        ):

            # Subtitle work has already happened inside
            # yt-dlp by the time this callback is reached.
            #
            # Keep this as a boundary rather than pretending
            # there is another real download operation.
            overall = 85.0

        # ------------------------------------------------------
        # Audio/subtitle-only.
        # ------------------------------------------------------

        elif stage in {
            "audio",
            "subtitles",
        }:

            overall = percentage

        else:

            overall = percentage

        self._emit_progress(
            info=info,
            filename=filename,
            percentage=overall,
            downloaded=downloaded,
            speed=speed,
            eta=eta,
        )

    # ==========================================================
    # ENCODER PROGRESS
    # ==========================================================

    def _encoder_progress(
        self,
        info: str,
        filename: str,
        percentage: Any = 0,
        downloaded: Any = "--",
        speed: Any = "--",
        eta: Any = "--:--",
        *_args: Any,
    ) -> None:

        percentage = (
            self._safe_percentage_float(
                percentage
            )
        )

        if self._progress_stage in {
            "video_processing",
            "video_subtitles_processing",
        }:

            overall = (
                90.0
                + (
                    percentage
                    * 0.10
                )
            )

        else:

            overall = percentage

        self._emit_progress(
            info=info,
            filename=filename,
            percentage=overall,
            downloaded=downloaded,
            speed=speed,
            eta=eta,
        )

    # ==========================================================
    # PROGRESS
    # ==========================================================

    def _progress(
        self,
        info: str,
        filename: str,
        percentage: Any = 0,
        downloaded: Any = "--",
        speed: Any = "--",
        eta: Any = "--:--",
    ) -> None:

        self._emit_progress(
            info=info,
            filename=filename,
            percentage=percentage,
            downloaded=downloaded,
            speed=speed,
            eta=eta,
        )

    def _emit_progress(
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

        percentage = (
            self._safe_percentage_float(
                percentage
            )
        )

        percentage_value = (
            int(percentage)
            if percentage.is_integer()
            else round(
                percentage,
                1,
            )
        )

        downloaded = (
            str(downloaded)
            if downloaded
            not in {
                None,
                "",
            }
            else "--"
        )

        speed = (
            str(speed)
            if speed
            not in {
                None,
                "",
            }
            else "--"
        )

        eta = (
            str(eta)
            if eta
            not in {
                None,
                "",
            }
            else "--:--"
        )

        try:

            self.progress_callback(
                info,
                filename,
                percentage_value,
                downloaded,
                speed,
                eta,
            )

        except TypeError:

            try:

                self.progress_callback(
                    info,
                    filename,
                    percentage_value,
                )

            except Exception:
                pass

        except Exception:
            pass

    # ==========================================================
    # HELPERS
    # ==========================================================

    @staticmethod
    def _safe_percentage_float(
        value: Any,
    ) -> float:

        try:

            return max(
                0.0,
                min(
                    100.0,
                    float(value),
                ),
            )

        except (
            TypeError,
            ValueError,
        ):

            return 0.0

    @staticmethod
    def _integer_setting(
        value: Any,
        default: int,
        minimum: int,
        maximum: int,
    ) -> int:

        try:

            value = int(
                value
            )

        except (
            TypeError,
            ValueError,
        ):

            value = default

        return max(
            minimum,
            min(
                maximum,
                value,
            ),
        )

    @staticmethod
    def _display_name(
        settings: Dict[str, Any],
    ) -> str:

        videos = settings.get(
            "videos",
            [],
        )

        if videos:

            first = videos[0]

            if isinstance(
                first,
                dict,
            ):

                title = first.get(
                    "title"
                )

                if title:

                    return str(
                        title
                    )

        url = settings.get(
            "url"
        )

        if url:

            return str(
                url
            )

        return "Media"

    # ==========================================================
    # RESULTS
    # ==========================================================

    @staticmethod
    def _cancelled_result(
        settings: Dict[str, Any],
    ) -> Dict[str, Any]:

        return {
            "url": settings.get(
                "url",
                "",
            ),

            "cancelled": True,

            "completed": False,

            "filepath": None,

            "path": None,

            "subtitle": None,

            "subtitle_filepath": None,

            "subtitles": [],

            "has_subtitles": False,

            "subtitles_available": False,

            "subtitles_embedded": False,

            "embed_subtitles": bool(
                settings.get(
                    "embed_subtitles",
                    False,
                )
            ),

            "save_separate_subtitle": bool(
                settings.get(
                    "save_separate_subtitle",
                    True,
                )
            ),
        }

    # ==========================================================
    # CALLBACKS
    # ==========================================================

    def _finished(
        self,
        result: Dict[str, Any],
    ) -> None:

        if not self.finished_callback:
            return

        try:

            self.finished_callback(
                result
            )

        except Exception as exc:

            self._error(
                exc
            )

    def _cancelled(
        self,
        settings: Dict[str, Any],
    ) -> None:

        if not self.cancelled_callback:
            return

        try:

            self.cancelled_callback(
                settings
            )

        except Exception as exc:

            self._error(
                exc
            )

    def _error(
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

        print(
            error
        )