from __future__ import annotations

import os

from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Tuple,
)

from core.audio_transcriber import (
    AudioTranscriber,
)

from core.subtitle_formatter import (
    SubtitleFormatter,
)

from core.language import (
    Language,
    is_same_language,
)

from core.subtitle_writer import (
    SubtitleWriter,
)

from core.subtitle_translator import (
    SubtitlesTranslator,
)


class SubtitleService:
    """
    Complete subtitle generation pipeline.

    Translation strategy:

        Non-English -> English
            faster-whisper task="translate"

        English -> English
            faster-whisper task="transcribe"

        English -> Non-English
            faster-whisper task="transcribe"
            +
            Argos Translate

        Non-English -> Non-English
            faster-whisper task="transcribe"
            +
            Argos Translate

    Pipeline:

        media
          |
          v
        faster-whisper
          |
          +----------------------------+
          |                            |
       target=en                  target!=en
          |                            |
          v                            v
       English                   source language
       subtitles                      |
          |                            v
          |                       Argos Translate
          |                            |
          +-------------+--------------+
                        |
                        v
                  SubtitleFormatter
                        |
                        v
                   SubtitleWriter
    """

    def __init__(
        self,
        source_language: str = "en",
        target_language: Optional[str] = None,
        subtitle_format: str = "srt",
        progress_callback: Optional[
            Callable[..., None]
        ] = None,
        error_callback: Optional[
            Callable[[Any], None]
        ] = None,
        overwrite_callback: Optional[
            Callable[[str], bool]
        ] = None,
        language_registry: Optional[
            Language
        ] = None,
    ):
        self.lang_registry = (
            language_registry
            or Language()
        )

        # ======================================================
        # Resolve source language
        # ======================================================

        if self.lang_registry.exists(
            source_language
        ):
            self.source_language = (
                self.lang_registry
                .get(source_language)
                .code
            )

        elif self.lang_registry.name_exists(
            source_language
        ):
            self.source_language = (
                self.lang_registry
                .get_by_name(source_language)
                .code
            )

        else:
            self.source_language = (
                self._normalize_language(
                    source_language
                )
            )

        # ======================================================
        # Resolve target language
        # ======================================================

        self.target_language = None

        if target_language:

            if self.lang_registry.exists(
                target_language
            ):
                resolved_target = (
                    self.lang_registry
                    .get(target_language)
                    .code
                )

            elif self.lang_registry.name_exists(
                target_language
            ):
                resolved_target = (
                    self.lang_registry
                    .get_by_name(target_language)
                    .code
                )

            else:
                resolved_target = (
                    self._normalize_language(
                        target_language
                    )
                )

            # Same language -> no translation.
            if not is_same_language(
                self.source_language,
                resolved_target,
                self._error,
            ):
                self.target_language = (
                    resolved_target
                )

        # ======================================================
        # Settings
        # ======================================================

        self.subtitle_format = (
            subtitle_format.lower()
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

        # ======================================================
        # Determine processing mode
        # ======================================================

        self.whisper_translation = (
            self.target_language == "en"
            and self.source_language != "en"
        )

        self.argos_translation = (
            self.target_language is not None
            and self.target_language != "en"
        )

        # ======================================================
        # Formatter
        # ======================================================

        self.formatter = SubtitleFormatter(
            format_type=self.subtitle_format
        )

        # ======================================================
        # Faster-whisper task
        # ======================================================

        if self.whisper_translation:

            # Non-English -> English.
            #
            # Whisper performs the translation itself.
            self.whisper_task = "translate"

        else:

            # Everything else is normal transcription.
            self.whisper_task = "transcribe"

        # ======================================================
        # Transcriber
        # ======================================================

        self.transcriber = AudioTranscriber(
            language=self.source_language,
            task=self.whisper_task,
            progress_callback=self._core_progress,
            error_callback=self._error,
        )

    # ==========================================================
    # Language
    # ==========================================================

    @staticmethod
    def _normalize_language(
        language: Optional[str],
    ) -> str:

        if not language:
            return ""

        return (
            str(language)
            .strip()
            .lower()
            .replace("_", "-")
            .split("-")[0]
        )

    # ==========================================================
    # Overwrite
    # ==========================================================

    def _should_overwrite(
        self,
        filepath: str,
    ) -> bool:
        """
        Determine whether an existing subtitle should
        be overwritten.
        """

        if not os.path.exists(filepath):
            return True

        if self.overwrite_callback:

            try:
                return bool(
                    self.overwrite_callback(
                        filepath
                    )
                )

            except Exception as exc:
                self._error(exc)
                return False

        # Safe default.
        return False

    # ==========================================================
    # Public API
    # ==========================================================

    def transcribe(
        self,
        media_filepath: str,
    ) -> Dict[str, Any]:

        return self.create_subtitles(
            media_filepath
        )

    def start_transcription(
        self,
        media_filepath: str,
    ) -> Dict[str, Any]:

        return self.create_subtitles(
            media_filepath
        )

    # ==========================================================
    # MAIN PIPELINE
    # ==========================================================

    def create_subtitles(
        self,
        media_filepath: str,
    ) -> Dict[str, Any]:

        media_filepath = os.path.abspath(
            media_filepath
        )

        if not os.path.isfile(
            media_filepath
        ):

            error = FileNotFoundError(
                "Media file does not exist: "
                f"{media_filepath}"
            )

            self._error(error)

            raise error

        filename = os.path.basename(
            media_filepath
        )

        base_name = os.path.splitext(
            media_filepath
        )[0]

        # ======================================================
        # IMPORTANT:
        #
        # For non-English -> English, faster-whisper produces
        # English directly.
        #
        # Therefore we do NOT create a fake source-language
        # subtitle containing English text.
        #
        # Example:
        #
        # Spanish audio -> English
        #
        # output:
        #     video.en.srt
        #
        # NOT:
        #     video.es.srt containing English.
        # ======================================================

        if self.whisper_translation:

            source_subtitle = None

            translated_subtitle = (
                f"{base_name}."
                f"{self.target_language}."
                f"{self.subtitle_format}"
            )

        else:

            source_subtitle = (
                f"{base_name}."
                f"{self.source_language}."
                f"{self.subtitle_format}"
            )

            translated_subtitle = None

            if self.target_language:

                translated_subtitle = (
                    f"{base_name}."
                    f"{self.target_language}."
                    f"{self.subtitle_format}"
                )

        try:

            # ==================================================
            # 1. GET TRANSCRIPTION
            # ==================================================

            regions: List[
                Tuple[float, float]
            ] = []

            transcripts: List[str] = []

            # --------------------------------------------------
            # For non-English -> English:
            #
            # The target subtitle itself is generated by
            # faster-whisper.
            # --------------------------------------------------

            if self.whisper_translation:

                self._progress(
                    "English target selected",
                    filename,
                    5,
                )

                self._progress(
                    "Using faster-whisper speech translation",
                    filename,
                    10,
                )

                transcription_results = (
                    self.transcriber.transcribe(
                        media_filepath
                    )
                )

                if not transcription_results:
                    raise RuntimeError(
                        "Speech translation failed "
                        "to produce output."
                    )

                for item in transcription_results:

                    region = item.get(
                        "region"
                    )

                    text = item.get(
                        "text",
                        "",
                    )

                    if (
                        not region
                        or len(region) != 2
                    ):
                        continue

                    if not text:
                        continue

                    regions.append(
                        (
                            float(region[0]),
                            float(region[1]),
                        )
                    )

                    transcripts.append(
                        text
                    )

                if not transcripts:
                    raise RuntimeError(
                        "Speech translation produced "
                        "no English subtitles."
                    )

                self._progress(
                    "English speech translation complete",
                    filename,
                    60,
                )

                # ----------------------------------------------
                # Write English directly.
                # ----------------------------------------------

                formatted_data = (
                    self.formatter(
                        list(
                            zip(
                                regions,
                                transcripts,
                            )
                        )
                    )
                )

                if formatted_data is None:
                    raise RuntimeError(
                        "Failed to format English subtitles."
                    )

                writer = SubtitleWriter(
                    error_callback=self._error
                )

                # ----------------------------------------------
                # Existing English subtitle?
                # ----------------------------------------------

                if os.path.exists(
                    translated_subtitle
                ):

                    self._progress(
                        "English subtitle already exists",
                        filename,
                        70,
                    )

                    if not self._should_overwrite(
                        translated_subtitle
                    ):

                        self._progress(
                            "Keeping existing English subtitle",
                            filename,
                            90,
                        )

                    else:

                        self._progress(
                            "Overwriting English subtitle",
                            filename,
                            90,
                        )

                        saved = writer.write(
                            filepath=(
                                translated_subtitle
                            ),
                            content=formatted_data,
                        )

                        if not saved:
                            raise RuntimeError(
                                "Failed to overwrite "
                                "English subtitle."
                            )

                else:

                    self._progress(
                        "Writing English subtitle",
                        filename,
                        90,
                    )

                    saved = writer.write(
                        filepath=(
                            translated_subtitle
                        ),
                        content=formatted_data,
                    )

                    if not saved:
                        raise RuntimeError(
                            "Failed to write "
                            "English subtitle."
                        )

                # ----------------------------------------------
                # Finished.
                # ----------------------------------------------

                self._progress(
                    "Subtitles complete",
                    filename,
                    100,
                )

                return {
                    "media": media_filepath,
                    "source_subtitle": None,
                    "translated_subtitle": (
                        translated_subtitle
                    ),
                    "regions": len(regions),
                    "recognized_segments": len(
                        transcripts
                    ),
                    "transcription_task": (
                        "translate"
                    ),
                    "translation_engine": (
                        "faster-whisper"
                    ),
                }

            # ==================================================
            # NORMAL TRANSCRIPTION
            #
            # Used for:
            #
            # English -> English
            # English -> other
            # Spanish -> French
            # French -> German
            # etc.
            # ==================================================

            if source_subtitle and os.path.exists(
                source_subtitle
            ):

                self._progress(
                    "Source subtitle already exists",
                    filename,
                    5,
                )

                overwrite_source = (
                    self._should_overwrite(
                        source_subtitle
                    )
                )

                if not overwrite_source:

                    # ------------------------------------------
                    # KEEP SOURCE
                    # ------------------------------------------

                    self._progress(
                        "Keeping existing source subtitle",
                        filename,
                        10,
                    )

                    existing_subtitles = (
                        self.formatter.read(
                            source_subtitle
                        )
                    )

                    if not existing_subtitles:
                        raise RuntimeError(
                            "Could not read existing "
                            "source subtitle."
                        )

                    for region, text in (
                        existing_subtitles
                    ):

                        regions.append(
                            (
                                float(region[0]),
                                float(region[1]),
                            )
                        )

                        transcripts.append(
                            text
                        )

                else:

                    # ------------------------------------------
                    # TRANSCRIBE
                    # ------------------------------------------

                    self._progress(
                        "Transcribing audio",
                        filename,
                        10,
                    )

                    transcription_results = (
                        self.transcriber.transcribe(
                            media_filepath
                        )
                    )

                    if not transcription_results:
                        raise RuntimeError(
                            "Audio transcription failed "
                            "to produce output."
                        )

                    for item in (
                        transcription_results
                    ):

                        region = item.get(
                            "region"
                        )

                        text = item.get(
                            "text",
                            "",
                        )

                        if (
                            not region
                            or len(region) != 2
                        ):
                            continue

                        if not text:
                            continue

                        regions.append(
                            (
                                float(region[0]),
                                float(region[1]),
                            )
                        )

                        transcripts.append(
                            text
                        )

                    if not transcripts:
                        raise RuntimeError(
                            "Speech recognition produced "
                            "no subtitles."
                        )

                    self._progress(
                        "Audio transcription complete",
                        filename,
                        60,
                    )

                    self._write_source_subtitle(
                        source_subtitle,
                        regions,
                        transcripts,
                        filename,
                        overwrite=True,
                    )

            else:

                # ----------------------------------------------
                # SOURCE DOES NOT EXIST
                # ----------------------------------------------

                self._progress(
                    "Source subtitle does not exist",
                    filename,
                    5,
                )

                self._progress(
                    "Transcribing audio",
                    filename,
                    10,
                )

                transcription_results = (
                    self.transcriber.transcribe(
                        media_filepath
                    )
                )

                if not transcription_results:
                    raise RuntimeError(
                        "Audio transcription failed "
                        "to produce output."
                    )

                for item in (
                    transcription_results
                ):

                    region = item.get(
                        "region"
                    )

                    text = item.get(
                        "text",
                        "",
                    )

                    if (
                        not region
                        or len(region) != 2
                    ):
                        continue

                    if not text:
                        continue

                    regions.append(
                        (
                            float(region[0]),
                            float(region[1]),
                        )
                    )

                    transcripts.append(
                        text
                    )

                if not transcripts:
                    raise RuntimeError(
                        "Speech recognition produced "
                        "no subtitles."
                    )

                self._progress(
                    "Audio transcription complete",
                    filename,
                    60,
                )

                self._write_source_subtitle(
                    source_subtitle,
                    regions,
                    transcripts,
                    filename,
                    overwrite=False,
                )

            # ==================================================
            # 2. NO TARGET TRANSLATION
            # ==================================================

            if not self.target_language:

                self._progress(
                    "Subtitles complete",
                    filename,
                    100,
                )

                return {
                    "media": media_filepath,
                    "source_subtitle": (
                        source_subtitle
                    ),
                    "translated_subtitle": None,
                    "regions": len(regions),
                    "recognized_segments": len(
                        transcripts
                    ),
                    "transcription_task": (
                        "transcribe"
                    ),
                    "translation_engine": None,
                }

            # ==================================================
            # 3. TARGET IS SAME AS SOURCE
            # ==================================================

            if (
                self.target_language
                == self.source_language
            ):

                self._progress(
                    "Translation not required",
                    filename,
                    95,
                )

                self._progress(
                    "Subtitles complete",
                    filename,
                    100,
                )

                return {
                    "media": media_filepath,
                    "source_subtitle": (
                        source_subtitle
                    ),
                    "translated_subtitle": None,
                    "regions": len(regions),
                    "recognized_segments": len(
                        transcripts
                    ),
                    "transcription_task": (
                        "transcribe"
                    ),
                    "translation_engine": None,
                }

            # ==================================================
            # 4. ARGOS TRANSLATION
            #
            # At this point:
            #
            # target != English
            #
            # Therefore faster-whisper has already performed
            # normal transcription.
            # ==================================================

            self._progress(
                "Starting Argos translation",
                filename,
                65,
            )

            translator = SubtitlesTranslator(
                source_language=(
                    self.source_language
                ),
                target_language=(
                    self.target_language
                ),
                error_messages_callback=(
                    self._error
                ),
                batch_size=32,
            )

            if not translator.is_available:
                raise RuntimeError(
                    "Argos translation model is "
                    "not available for "
                    f"{self.source_language} -> "
                    f"{self.target_language}"
                )

            # --------------------------------------------------
            # Existing translated subtitle.
            # --------------------------------------------------

            if os.path.exists(
                translated_subtitle
            ):

                self._progress(
                    "Translated subtitle already exists",
                    filename,
                    70,
                )

                if not self._should_overwrite(
                    translated_subtitle
                ):

                    self._progress(
                        "Keeping existing translated subtitle",
                        filename,
                        95,
                    )

                    self._progress(
                        "Subtitles complete",
                        filename,
                        100,
                    )

                    return {
                        "media": media_filepath,
                        "source_subtitle": (
                            source_subtitle
                        ),
                        "translated_subtitle": (
                            translated_subtitle
                        ),
                        "regions": len(regions),
                        "recognized_segments": len(
                            transcripts
                        ),
                        "transcription_task": (
                            "transcribe"
                        ),
                        "translation_engine": (
                            "argos"
                        ),
                    }

            # --------------------------------------------------
            # Translate EVERYTHING in one call.
            #
            # Do NOT do:
            #
            # for text in transcripts:
            #     translator.translate(text)
            #
            # That would bring back the slow behavior.
            # --------------------------------------------------

            self._progress(
                "Translating subtitles",
                filename,
                70,
            )

            translated_transcripts = (
                translator(transcripts)
            )

            if (
                not translated_transcripts
                or len(
                    translated_transcripts
                )
                != len(transcripts)
            ):
                raise RuntimeError(
                    "Translation produced an invalid "
                    "number of subtitle lines."
                )

            # --------------------------------------------------
            # Format translated subtitles.
            # --------------------------------------------------

            formatted_translated_data = (
                self.formatter(
                    list(
                        zip(
                            regions,
                            translated_transcripts,
                        )
                    )
                )
            )

            if formatted_translated_data is None:
                raise RuntimeError(
                    "Failed to format translated subtitles."
                )

            # --------------------------------------------------
            # Write translation.
            # --------------------------------------------------

            writer = SubtitleWriter(
                error_callback=self._error
            )

            self._progress(
                "Writing translated subtitle",
                filename,
                95,
            )

            saved_translated = writer.write(
                filepath=translated_subtitle,
                content=formatted_translated_data,
            )

            if not saved_translated:
                raise RuntimeError(
                    "Failed to write translated subtitle."
                )

            # ==================================================
            # COMPLETE
            # ==================================================

            self._progress(
                "Subtitles complete",
                filename,
                100,
            )

            return {
                "media": media_filepath,
                "source_subtitle": (
                    source_subtitle
                ),
                "translated_subtitle": (
                    translated_subtitle
                ),
                "regions": len(regions),
                "recognized_segments": len(
                    transcripts
                ),
                "transcription_task": (
                    "transcribe"
                ),
                "translation_engine": (
                    "argos"
                ),
            }

        except KeyboardInterrupt:

            self._error(
                "Cancelling task execution"
            )

            raise

        except Exception as exc:

            self._error(exc)

            raise

    # ==========================================================
    # WRITE SOURCE SUBTITLE
    # ==========================================================

    def _write_source_subtitle(
        self,
        filepath: str,
        regions: List[
            Tuple[float, float]
        ],
        transcripts: List[str],
        filename: str,
        overwrite: bool = False,
    ) -> None:

        formatted_source_data = (
            self.formatter(
                list(
                    zip(
                        regions,
                        transcripts,
                    )
                )
            )
        )

        if formatted_source_data is None:
            raise RuntimeError(
                "Failed to format source subtitles."
            )

        writer = SubtitleWriter(
            error_callback=self._error
        )

        if overwrite:

            self._progress(
                "Overwriting source subtitle",
                filename,
                90,
            )

        else:

            self._progress(
                "Writing source subtitle",
                filename,
                90,
            )

        saved_source = writer.write(
            filepath=filepath,
            content=formatted_source_data,
        )

        if not saved_source:

            raise RuntimeError(
                "Failed to write source subtitle."
            )

    # ==========================================================
    # PROGRESS
    # ==========================================================

    def _progress(
        self,
        info: str,
        filename: str,
        percentage: int,
    ) -> None:

        percentage = max(
            0,
            min(
                100,
                int(percentage),
            ),
        )

        if not self.progress_callback:
            return

        try:

            self.progress_callback(
                info,
                filename,
                percentage,
            )

        except TypeError:

            try:

                self.progress_callback(
                    info,
                    filename,
                    percentage,
                    None,
                )

            except Exception:
                pass

        except Exception:
            pass

    # ==========================================================
    # CORE PROGRESS
    # ==========================================================

    def _core_progress(
        self,
        info: str,
        filename: str,
        percentage: int,
        start_time: Any = None,
    ) -> None:

        if not self.progress_callback:
            return

        try:

            self.progress_callback(
                info,
                filename,
                percentage,
                start_time,
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

    def _error(
        self,
        error: Any,
    ) -> None:

        if self.error_callback:

            try:
                self.error_callback(
                    error
                )

            except Exception:
                pass

        else:
            print(error)