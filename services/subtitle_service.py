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

from core.audio_transcriber import AudioTranscriber
from core.subtitle_formatter import SubtitleFormatter
from core.language import Language, is_same_language
from core.subtitle_writer import SubtitleWriter
from core.subtitle_translator import SubtitlesTranslator


class SubtitleService:
    """
    Subtitle creation pipeline.

    Pipeline:

        1. Check source SRT.
        2. If source SRT exists, ask whether to overwrite.
        3. If source SRT is missing or overwrite was accepted:
               Faster-Whisper transcribes the media.
        4. Write source-language SRT.
        5. Ask whether translation should happen.
        6. If target SRT exists, ask whether to overwrite.
        7. If translation is required:
               NLLB Translate performs the translation.
        8. Write target-language SRT.

    IMPORTANT:

        Faster-Whisper is ALWAYS used with task="transcribe".

        NLLB is used for ALL translations, including:

            es -> en
            fr -> en
            de -> en
            en -> es
            en -> fr
            etc.

        Whisper's built-in translation task is deliberately NOT used.
    """

    def __init__(
        self,
        source_language: str = "en",
        target_language: Optional[str] = None,
        subtitle_format: str = "srt",
        progress_callback: Optional[Callable[..., None]] = None,
        error_callback: Optional[Callable[[Any], None]] = None,
        overwrite_callback: Optional[Callable[[str], bool]] = None,
        translate_callback: Optional[Callable[..., bool]] = None,
        language_registry: Optional[Language] = None,
    ):
        # ------------------------------------------------------
        # Language registry
        # ------------------------------------------------------

        self.lang_registry = (
            language_registry or Language()
        )

        self.source_language = self._resolve_language(
            source_language
        )

        self.target_language = None

        if target_language:
            resolved_target = self._resolve_language(
                target_language
            )

            if not is_same_language(
                self.source_language,
                resolved_target,
                self._error,
            ):
                self.target_language = resolved_target

        # ------------------------------------------------------
        # Settings
        # ------------------------------------------------------

        self.subtitle_format = (
            str(subtitle_format)
            .strip()
            .lower()
            .lstrip(".")
        )

        self.progress_callback = progress_callback
        self.error_callback = error_callback
        self.overwrite_callback = overwrite_callback
        self.translate_callback = translate_callback

        # ------------------------------------------------------
        # Translation engine
        #
        # ALWAYS NLLB.
        # ------------------------------------------------------

        self.translation_engine = (
            "NLLB"
            if self.target_language
            else None
        )

        # ------------------------------------------------------
        # Whisper
        #
        # NEVER use Whisper's translate task.
        # ------------------------------------------------------

        self.whisper_task = "transcribe"

        # ------------------------------------------------------
        # Formatter
        # ------------------------------------------------------

        self.formatter = SubtitleFormatter(
            format_type=self.subtitle_format,
            error_messages_callback=self._error,
        )

        # ------------------------------------------------------
        # Transcriber
        # ------------------------------------------------------

        self.transcriber = AudioTranscriber(
            language=self.source_language,
            task="transcribe",
            progress_callback=self._core_progress,
            error_callback=self._error,
        )

    # ==========================================================
    # LANGUAGE
    # ==========================================================
    def _translator_progress(
        self,
        info: str,
        percentage: int,
    ) -> None:

        self._progress(
            info,
            "",
            percentage,
        )

    def _resolve_language(
        self,
        language: str,
    ) -> str:

        if self.lang_registry.exists(language):
            return self.lang_registry.get(language).code

        if self.lang_registry.name_exists(language):
            return self.lang_registry.get_by_name(language).code

        return self._normalize_language(language)

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
    # PUBLIC API
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

        if not os.path.isfile(media_filepath):
            error = FileNotFoundError(
                f"Media file does not exist: "
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

        # ======================================================
        # STEP 1
        #
        # Decide what to do with SOURCE SRT.
        # ======================================================

        source_exists = os.path.isfile(
            source_subtitle
        )

        transcribe_required = False
        write_source = False

        if source_exists:

            self._progress(
                "Source subtitle already exists",
                filename,
                2,
            )

            overwrite_source = (
                self._should_overwrite(
                    source_subtitle,
                    'source'
                )
            )

            if overwrite_source:

                transcribe_required = True
                write_source = True

            else:

                # IMPORTANT:
                #
                # We keep the existing source SRT.
                #
                # We DO NOT transcribe again.
                #
                # Translation can still happen later.
                #
                transcribe_required = False
                write_source = False

        else:

            transcribe_required = True
            write_source = True

        # ======================================================
        # STEP 2
        #
        # Ask whether translation should happen.
        # ======================================================

        translate_required = False

        if self.target_language:

            translate_required = (
                self._should_translate(
                    filename=filename,
                    source_subtitle=source_subtitle,
                    translated_subtitle=translated_subtitle,
                )
            )

        # ======================================================
        # STEP 3
        #
        # Target already exists and user says NO.
        #
        # If there is also no transcription required,
        # we can finish immediately.
        # ======================================================

        if (
            not transcribe_required
            and not translate_required
        ):

            self._progress(
                "Existing subtitles kept",
                filename,
                100,
            )

            return {
                "media": media_filepath,
                "source_subtitle": source_subtitle,
                "translated_subtitle": translated_subtitle,
                "regions": 0,
                "recognized_segments": 0,
                "transcription_task": "transcribe",
                "translation_engine": (
                    "NLLB"
                    if self.target_language
                    else None
                ),
            }

        # ======================================================
        # Data that will be used for translation.
        # ======================================================

        regions: List[
            Tuple[float, float]
        ] = []

        transcripts: List[str] = []

        try:

            # ==================================================
            # STEP 4
            #
            # TRANSCRIBE
            # ==================================================

            if transcribe_required:

                self._progress(
                    "Extracting audio and transcribing",
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
                        "Speech recognition produced "
                        "no subtitles."
                    )

                for item in transcription_results:

                    if not isinstance(item, dict):
                        continue

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

                    text = str(
                        text
                    ).strip()

                    if not text:
                        continue

                    try:
                        start = float(
                            region[0]
                        )

                        end = float(
                            region[1]
                        )

                    except (
                        TypeError,
                        ValueError,
                    ):
                        continue

                    if end <= start:
                        continue

                    regions.append(
                        (
                            start,
                            end,
                        )
                    )

                    transcripts.append(
                        text
                    )

                if not transcripts:
                    raise RuntimeError(
                        "Speech recognition produced "
                        "no usable subtitles."
                    )

                self._progress(
                    "Transcription complete",
                    filename,
                    60,
                )

                # ----------------------------------------------
                # Write source SRT
                # ----------------------------------------------

                if write_source:

                    self._write_subtitle(
                        filepath=source_subtitle,
                        regions=regions,
                        transcripts=transcripts,
                        filename=filename,
                        progress_message=(
                            "Writing source subtitle"
                        ),
                    )

            # ==================================================
            # STEP 5
            #
            # If translation is requested but we did NOT
            # transcribe, load the existing source SRT.
            #
            # This is the important case:
            #
            # source.srt exists
            # user says NO to overwrite
            # user says YES to translation
            #
            # We translate the existing SRT instead of
            # retranscribing the video.
            # ==================================================

            if (
                translate_required
                and not transcribe_required
            ):

                self._progress(
                    "Reading existing source subtitle",
                    filename,
                    55,
                )

                (
                    regions,
                    transcripts,
                ) = self._read_source_subtitle(
                    source_subtitle
                )

                if not transcripts:
                    raise RuntimeError(
                        "The existing source subtitle "
                        "contains no usable subtitle lines."
                    )

            # ==================================================
            # STEP 6
            #
            # TRANSLATION
            #
            # ALWAYS ARGOS.
            # ==================================================

            if translate_required:

                if not self.target_language:
                    raise RuntimeError(
                        "Translation was requested but "
                        "no target language is configured."
                    )

                if not transcripts:
                    raise RuntimeError(
                        "There are no subtitles available "
                        "for translation."
                    )

                self._progress(
                    (
                        "Starting offline NLLB CTranslate2 "
                        f"translation "
                        f"{self.source_language} -> "
                        f"{self.target_language}"
                    ),
                    filename,
                    65,
                )

                translator = SubtitlesTranslator(
                    source_language=self.source_language,
                    target_language=self.target_language,
                    error_messages_callback=self._error,
                    batch_size=32,
                )

                if not translator.is_available:

                    raise RuntimeError(
                        "NLLB CTranslate2 failed to initialize.\n"
                        f"Model path: {translator.model_path}\n"
                        f"Source: {self.source_language}\n"
                        f"Target: {self.target_language}"
                    )

                self._progress(
                    "Translating subtitles offline",
                    filename,
                    70,
                )

                translated_transcripts = (
                    translator(
                        transcripts
                    )
                )

                if (
                    not translated_transcripts
                    or len(translated_transcripts)
                    != len(transcripts)
                ):

                    raise RuntimeError(
                        "NLLB CTranslate2 returned an "
                        "invalid number of subtitle lines."
                    )

                self._write_subtitle(
                    filepath=translated_subtitle,
                    regions=regions,
                    transcripts=translated_transcripts,
                    filename=filename,
                    progress_message=(
                        "Writing translated subtitle"
                    ),
                )
                # ----------------------------------------------
                

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
                "source_subtitle": source_subtitle,
                "translated_subtitle": translated_subtitle,
                "regions": len(regions),
                "recognized_segments": len(
                    transcripts
                ),
                "transcription_task": "transcribe",
                "translation_engine": (
                    "NLLB"
                    if self.target_language
                    else None
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
    # TRANSLATION QUESTION
    # ==========================================================

    def _should_translate(
        self,
        filename: str,
        source_subtitle: str,
        translated_subtitle: Optional[str],
    ) -> bool:

        if not self.target_language:
            return False

        # ------------------------------------------------------
        # If source == target, translation makes no sense.
        # ------------------------------------------------------

        if is_same_language(
            self.source_language,
            self.target_language,
            self._error,
        ):
            return False

        # ------------------------------------------------------
        # Ask the application/UI whether translation should
        # happen.
        #
        # If no callback is supplied, safe default is NO.
        # ------------------------------------------------------

        if self.translate_callback:

            try:

                return bool(
                    self.translate_callback(
                        self.source_language,
                        self.target_language,
                        source_subtitle,
                        translated_subtitle,
                    )
                )

            except TypeError:

                try:
                    return bool(
                        self.translate_callback(
                            self.target_language,
                            'Target/Translation'
                        )
                    )

                except TypeError:

                    try:
                        return bool(
                            self.translate_callback()
                        )

                    except Exception as exc:
                        self._error(exc)
                        return False

                except Exception as exc:
                    self._error(exc)
                    return False

            except Exception as exc:
                self._error(exc)
                return False

        # ------------------------------------------------------
        # If there is no translation callback, don't silently
        # translate.
        # ------------------------------------------------------

        self._progress(
            (
                "Translation not requested "
                "(no translation callback)"
            ),
            filename,
            62,
        )

        return False

    # ==========================================================
    # OVERWRITE
    # ==========================================================

    def _should_overwrite(
        self,
        filepath: str,
        type
    ) -> bool:

        if not os.path.exists(filepath):
            return True

        if self.overwrite_callback:

            try:

                return bool(
                    self.overwrite_callback(
                        filepath, 
                        "Source/Original"
                    )
                )

            except Exception as exc:

                self._error(exc)

                return False

        # ------------------------------------------------------
        # SAFE DEFAULT
        #
        # Never overwrite automatically.
        # ------------------------------------------------------

        return False

    # ==========================================================
    # READ EXISTING SOURCE SRT
    # ==========================================================

    def _read_source_subtitle(
        self,
        filepath: str,
    ) -> Tuple[
        List[Tuple[float, float]],
        List[str],
    ]:

        if not os.path.isfile(filepath):

            raise FileNotFoundError(
                f"Source subtitle does not exist: "
                f"{filepath}"
            )

        try:

            # --------------------------------------------------
            # Prefer SubtitleFormatter if it exposes a reader.
            # --------------------------------------------------

            reader = getattr(
                self.formatter,
                "read",
                None,
            )

            if callable(reader):

                parsed = reader(
                    filepath
                )

                parsed_regions: List[
                    Tuple[float, float]
                ] = []

                parsed_texts: List[str] = []

                for item in parsed:

                    if isinstance(
                        item,
                        dict,
                    ):

                        region = item.get(
                            "region"
                        )

                        text = item.get(
                            "text",
                            "",
                        )

                    else:

                        try:
                            region, text = item
                        except Exception:
                            continue

                    if (
                        not region
                        or len(region) != 2
                    ):
                        continue

                    text = str(
                        text
                    ).strip()

                    if not text:
                        continue

                    parsed_regions.append(
                        (
                            float(region[0]),
                            float(region[1]),
                        )
                    )

                    parsed_texts.append(
                        text
                    )

                if parsed_texts:

                    return (
                        parsed_regions,
                        parsed_texts,
                    )

            # --------------------------------------------------
            # Built-in SRT parser.
            #
            # This is used when SubtitleFormatter does not
            # expose a reader.
            # --------------------------------------------------

            return self._parse_srt(
                filepath
            )

        except Exception as exc:

            raise RuntimeError(
                f"Failed to read source subtitle "
                f"'{filepath}': {exc}"
            ) from exc

    # ==========================================================
    # SIMPLE SRT READER
    # ==========================================================

    @staticmethod
    def _parse_srt(
        filepath: str,
    ) -> Tuple[
        List[Tuple[float, float]],
        List[str],
    ]:

        with open(
            filepath,
            "r",
            encoding="utf-8-sig",
        ) as file:

            content = file.read()

        blocks = content.replace(
            "\r\n",
            "\n",
        ).replace(
            "\r",
            "\n",
        ).split(
            "\n\n"
        )

        regions: List[
            Tuple[float, float]
        ] = []

        texts: List[str] = []

        for block in blocks:

            lines = [
                line.strip()
                for line in block.split("\n")
            ]

            lines = [
                line
                for line in lines
                if line
            ]

            if len(lines) < 3:
                continue

            # ----------------------------------------------
            # Usually:
            #
            # 1
            # 00:00:01,000 --> 00:00:03,000
            # Hello
            # ----------------------------------------------

            timing_line = None

            timing_index = -1

            for index, line in enumerate(lines):

                if "-->" in line:

                    timing_line = line
                    timing_index = index
                    break

            if timing_line is None:
                continue

            try:

                start_text, end_text = (
                    timing_line.split(
                        "-->",
                        1,
                    )
                )

                start = (
                    SubtitleService
                    ._srt_timestamp_to_seconds(
                        start_text.strip()
                    )
                )

                end = (
                    SubtitleService
                    ._srt_timestamp_to_seconds(
                        end_text.strip()
                    )
                )

            except Exception:
                continue

            if end <= start:
                continue

            subtitle_text = "\n".join(
                lines[
                    timing_index + 1:
                ]
            ).strip()

            if not subtitle_text:
                continue

            regions.append(
                (
                    start,
                    end,
                )
            )

            texts.append(
                subtitle_text
            )

        return regions, texts

    # ==========================================================
    # SRT TIMESTAMP
    # ==========================================================

    @staticmethod
    def _srt_timestamp_to_seconds(
        timestamp: str,
    ) -> float:

        timestamp = timestamp.strip()

        timestamp = timestamp.replace(
            ",",
            ".",
        )

        parts = timestamp.split(
            ":"
        )

        if len(parts) != 3:
            raise ValueError(
                f"Invalid SRT timestamp: {timestamp}"
            )

        hours = float(
            parts[0]
        )

        minutes = float(
            parts[1]
        )

        seconds = float(
            parts[2]
        )

        return (
            hours * 3600
            + minutes * 60
            + seconds
        )

    # ==========================================================
    # WRITE SUBTITLE
    # ==========================================================

    def _write_subtitle(
        self,
        filepath: str,
        regions: List[
            Tuple[float, float]
        ],
        transcripts: List[str],
        filename: str,
        progress_message: str,
    ) -> None:

        if len(regions) != len(transcripts):

            raise ValueError(
                "Subtitle regions and transcript "
                "counts do not match."
            )

        formatted = self.formatter(
            list(
                zip(
                    regions,
                    transcripts,
                )
            )
        )

        if formatted is None:

            raise RuntimeError(
                "Failed to format subtitles."
            )

        self._progress(
            progress_message,
            filename,
            90,
        )

        writer = SubtitleWriter(
            error_callback=self._error
        )

        saved = writer.write(
            filepath=filepath,
            content=formatted,
        )

        if not saved:

            raise RuntimeError(
                f"Failed to write subtitle: "
                f"{filepath}"
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

        if not self.progress_callback:
            return

        percentage = max(
            0,
            min(
                100,
                int(percentage),
            ),
        )

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

                return

            except Exception:
                pass

        print(
            error
        )