from __future__ import annotations

import os
import shutil

from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Tuple,
)

import pysubs2

from core.audio_transcriber import AudioTranscriber
from core.subtitle_formatter import SubtitleFormatter
from core.language import Language, is_same_language
from core.subtitle_writer import SubtitleWriter
from core.subtitle_translator import SubtitlesTranslator
from core.media_subtitle import (
    EmbeddedSubtitle,
    MediaSubtitleExtractor,
    MediaSubtitleInspector,
)
from core.temp_manager import (
    create_temp_file,
    remove_temp_file,
)

BATCH_SIZE = 100

class SubtitleService:
    """
    Subtitle creation pipeline.

    SOURCE PRIORITY
    ---------------

        1. Matching embedded text subtitle
        2. Single / selected unknown-language embedded text subtitle
        3. Existing external source subtitle
        4. Google transcription

    TARGET PRIORITY
    ---------------

        1. Matching embedded target text subtitle
        2. Existing external target subtitle
        3. Translation

    TRANSLATION
    -----------

    Translation uses:

        SRTranslator
            +
        TranslatePy

    Translation is performed in batches.

    Example:

        subtitles 1-200
            -> SrtFile.translate()

        subtitles 201-400
            -> SrtFile.translate()

        ...

    If a batch fails, SubtitlesTranslator falls back to
    individual TranslatePy translation for that batch.

    IMPORTANT
    ---------

    Embedded text subtitles ALWAYS have priority over external
    subtitle files.

    An embedded text subtitle with missing/unknown language
    metadata is still usable.

    If there is exactly one embedded text subtitle and its
    language is unknown, it is treated as the source subtitle.

    Google is ONLY used when there is no usable embedded text
    subtitle and no usable external source subtitle.

    Translation is AUTOMATIC when:

        source subtitle exists
        AND target language is configured
        AND no usable target subtitle exists.

    translate_callback is OPTIONAL. It is only used as a
    confirmation/UI hook when supplied.
    """

    LANGUAGE_ALIASES = {
        "eng": "en",
        "english": "en",

        "spa": "es",
        "esp": "es",
        "spanish": "es",

        "fra": "fr",
        "fre": "fr",
        "french": "fr",

        "deu": "de",
        "ger": "de",
        "german": "de",

        "ita": "it",
        "italian": "it",

        "por": "pt",
        "ptg": "pt",
        "portuguese": "pt",

        "jpn": "ja",
        "japanese": "ja",

        "kor": "ko",
        "korean": "ko",

        "zho": "zh",
        "chi": "zh",
        "chinese": "zh",

        "rus": "ru",
        "russian": "ru",

        "ara": "ar",
        "arabic": "ar",

        "hin": "hi",
        "hindi": "hi",

        "nld": "nl",
        "dut": "nl",
        "dutch": "nl",

        "pol": "pl",
        "polish": "pl",

        "tur": "tr",
        "turkish": "tr",

        "swe": "sv",
        "swedish": "sv",

        "dan": "da",
        "danish": "da",

        "nor": "no",
        "norwegian": "no",

        "fin": "fi",
        "finnish": "fi",

        "ces": "cs",
        "cze": "cs",
        "czech": "cs",

        "hun": "hu",
        "hungarian": "hu",

        "ron": "ro",
        "rum": "ro",
        "romanian": "ro",

        "ukr": "uk",
        "ukrainian": "uk",

        "vie": "vi",
        "vietnamese": "vi",

        "tha": "th",
        "thai": "th",

        "heb": "he",
        "hebrew": "he",

        "ind": "id",
        "indonesian": "id",

        "msa": "ms",
        "may": "ms",
        "malay": "ms",

        "fil": "tl",
        "tgl": "tl",
        "tagalog": "tl",
    }

    # ==========================================================
    # INIT
    # ==========================================================

    def __init__(
        self,
        source_language: str = "en",
        target_language: Optional[str] = None,
        subtitle_format: str = "srt",
        vad_mode: str = "silero",
        audio_source: str = "wav",
        progress_callback: Optional[Callable[..., None]] = None,
        error_callback: Optional[Callable[[Any], None]] = None,
        overwrite_callback: Optional[Callable[..., bool]] = None,
        translate_callback: Optional[Callable[..., bool]] = None,
        language_registry: Optional[Language] = None,
        overwrite_existing: bool = False,
    ):

        self.media_subtitle_inspector = MediaSubtitleInspector(
            error_callback=self._error,
        )

        self.media_subtitle_extractor = MediaSubtitleExtractor(
            error_callback=self._error,
        )

        self.lang_registry = (
            language_registry or Language()
        )

        self.source_language = self._resolve_language(
            source_language
        )

        self.target_language: Optional[str] = None

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
        self.overwrite_existing = overwrite_existing

        self.formatter = SubtitleFormatter(
            format_type=self.subtitle_format,
            error_messages_callback=self._error,
        )
        self.audio_source = (
            str(audio_source or "wav")
            .strip()
            .lower()
        )

        if self.audio_source not in {
            "wav",
            "video",
        }:
            raise ValueError(
                "Unsupported audio source: "
                f"{self.audio_source}. "
                "Valid sources are: wav, video, auto"
            )

        self.vad_mode = (
            str(vad_mode or "silero")
            .strip()
            .lower()
        )

        if self.vad_mode not in {
            "silero",
            "fixed",
        }:
            raise ValueError(
                "Unsupported VAD mode: "
                f"{self.vad_mode}. "
                "Valid modes are: silero, fixed"
            )



        self.transcriber = AudioTranscriber(
            language=self.source_language,
            vad_mode=self.vad_mode,
            audio_source=self.audio_source,
            progress_callback=self._core_progress,
            error_callback=self._error,
            include_before=0.25,
            include_after=0.25,
        )

    # ==========================================================
    # LANGUAGE
    # ==========================================================

    @classmethod
    def _normalize_language(
        cls,
        language: Optional[str],
    ) -> str:

        if not language:
            return ""

        value = (
            str(language)
            .strip()
            .lower()
            .replace("_", "-")
        )

        if value in {
            "",
            "unknown",
            "und",
            "undefined",
            "none",
            "null",
        }:
            return ""

        primary = value.split("-", 1)[0]

        return cls.LANGUAGE_ALIASES.get(
            value,
            cls.LANGUAGE_ALIASES.get(
                primary,
                primary,
            ),
        )

    # ==========================================================
    # SUBTITLE FORMAT
    # ==========================================================

    @staticmethod
    def _normalize_subtitle_format(
        filepath: str,
    ) -> str:

        return (
            os.path.splitext(filepath)[1]
            .lower()
            .lstrip(".")
        )

    # ==========================================================
    # CONVERT TO SRT
    # ==========================================================

    @staticmethod
    def _convert_subtitle_to_srt(
        input_filepath: str,
        output_filepath: str,
    ) -> str:

        input_format = (
            SubtitleService
            ._normalize_subtitle_format(
                input_filepath
            )
        )

        if input_format == "srt":

            if (
                os.path.abspath(input_filepath)
                !=
                os.path.abspath(output_filepath)
            ):

                shutil.copyfile(
                    input_filepath,
                    output_filepath,
                )

            return output_filepath

        subtitles = pysubs2.load(
            input_filepath,
            encoding="utf-8",
        )

        subtitles.save(
            output_filepath,
            format_="srt",
            encoding="utf-8",
        )

        return output_filepath

    # ==========================================================
    # CONVERT SRT TO REQUESTED FORMAT
    # ==========================================================

    @staticmethod
    def _convert_srt_to_format(
        input_srt: str,
        output_filepath: str,
    ) -> str:

        output_format = (
            SubtitleService
            ._normalize_subtitle_format(
                output_filepath
            )
        )

        if output_format == "srt":

            if (
                os.path.abspath(input_srt)
                !=
                os.path.abspath(output_filepath)
            ):

                shutil.copyfile(
                    input_srt,
                    output_filepath,
                )

            return output_filepath

        subtitles = pysubs2.load(
            input_srt,
            encoding="utf-8",
        )

        subtitles.save(
            output_filepath,
            format_=output_format,
            encoding="utf-8",
        )

        return output_filepath

    # ==========================================================
    # RESOLVE LANGUAGE
    # ==========================================================

    def _resolve_language(
        self,
        language: str,
    ) -> str:

        if not language:
            return ""

        try:

            if self.lang_registry.exists(
                language
            ):

                code = (
                    self.lang_registry
                    .get(language)
                    .code
                )

                return self._normalize_language(
                    code
                )

        except Exception:
            pass

        try:

            if self.lang_registry.name_exists(
                language
            ):

                code = (
                    self.lang_registry
                    .get_by_name(language)
                    .code
                )

                return self._normalize_language(
                    code
                )

        except Exception:
            pass

        return self._normalize_language(
            language
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
    # EMBEDDED INSPECTION
    # ==========================================================

    def inspect_embedded_subtitles(
        self,
        media_filepath: str,
    ) -> List[EmbeddedSubtitle]:

        return self.media_subtitle_inspector.inspect(
            media_filepath
        )

    def _subtitle_language(
        self,
        subtitle: EmbeddedSubtitle,
    ) -> str:

        return self._normalize_language(
            subtitle.language
        )

    # ==========================================================
    # FIND EMBEDDED SUBTITLE
    # ==========================================================

    def _find_embedded_subtitle(
        self,
        subtitles: List[EmbeddedSubtitle],
        language: str,
    ) -> Optional[EmbeddedSubtitle]:

        requested = self._normalize_language(
            language
        )

        if not requested:
            return None

        exact_text_matches: List[
            EmbeddedSubtitle
        ] = []

        exact_image_matches: List[
            EmbeddedSubtitle
        ] = []

        unknown_text_matches: List[
            EmbeddedSubtitle
        ] = []

        for subtitle in subtitles:

            actual = self._subtitle_language(
                subtitle
            )

            if not actual:

                if subtitle.extractable:

                    unknown_text_matches.append(
                        subtitle
                    )

                continue

            if actual != requested:
                continue

            if subtitle.extractable:

                exact_text_matches.append(
                    subtitle
                )

            else:

                exact_image_matches.append(
                    subtitle
                )

        if exact_text_matches:

            return self._choose_embedded_candidate(
                exact_text_matches
            )

        if unknown_text_matches:

            return self._choose_embedded_candidate(
                unknown_text_matches
            )

        if exact_image_matches:

            return self._choose_embedded_candidate(
                exact_image_matches
            )

        return None

    # ==========================================================
    # CHOOSE EMBEDDED CANDIDATE
    # ==========================================================

    @staticmethod
    def _choose_embedded_candidate(
        subtitles: List[EmbeddedSubtitle],
    ) -> Optional[EmbeddedSubtitle]:

        if not subtitles:
            return None

        text = [
            item
            for item in subtitles
            if item.extractable
        ]

        candidates = text or list(subtitles)

        non_forced = [
            item
            for item in candidates
            if not item.forced
        ]

        if non_forced:

            candidates = non_forced

        defaults = [
            item
            for item in candidates
            if item.default
        ]

        if defaults:

            return defaults[0]

        return candidates[0]

    # ==========================================================
    # EMBEDDED EXTRACTION
    # ==========================================================

    def _extract_embedded_subtitle(
        self,
        media_filepath: str,
        stream: EmbeddedSubtitle,
        output_filepath: str,
    ) -> str:

        self._progress(
            (
                "Extracting embedded "
                f"{self._subtitle_language(stream) or 'unknown'} "
                "subtitle"
            ),
            os.path.basename(media_filepath),
            8,
        )

        return self.media_subtitle_extractor.extract(
            media_filepath=media_filepath,
            stream=stream,
            output_filepath=output_filepath,
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

        # ======================================================
        # OUTPUT PATHS
        # ======================================================

        source_subtitle = (
            f"{base_name}."
            f"{self.source_language}."
            f"{self.subtitle_format}"
        )

        translated_subtitle: Optional[str] = None

        if self.target_language:

            translated_subtitle = (
                f"{base_name}."
                f"{self.target_language}."
                f"{self.subtitle_format}"
            )

        # ======================================================
        # INSPECT
        # ======================================================

        self._progress(
            "Inspecting embedded subtitles",
            filename,
            3,
        )

        embedded_subtitles = (
            self.inspect_embedded_subtitles(
                media_filepath
            )
        )

        # ======================================================
        # REPORT STREAMS
        # ======================================================

        if embedded_subtitles:

            self._progress(
                (
                    f"Found {len(embedded_subtitles)} "
                    "embedded subtitle stream(s)"
                ),
                filename,
                5,
            )

            for subtitle in embedded_subtitles:

                raw_language = (
                    subtitle.language
                    or "unknown"
                )

                normalized_language = (
                    self._subtitle_language(
                        subtitle
                    )
                    or "unknown"
                )

                codec = (
                    subtitle.codec
                    or "unknown"
                )

                kind = (
                    "text"
                    if subtitle.extractable
                    else "image"
                )

                self._progress(
                    (
                        "Embedded subtitle: "
                        f"{raw_language} -> "
                        f"{normalized_language} / "
                        f"{codec} / "
                        f"{kind}"
                    ),
                    filename,
                    6,
                )

        else:

            self._progress(
                "No embedded subtitles found",
                filename,
                6,
            )

        # ======================================================
        # FIND SOURCE
        # ======================================================

        embedded_source = (
            self._find_embedded_subtitle(
                embedded_subtitles,
                self.source_language,
            )
        )

        if embedded_source:

            self._progress(
                (
                    "Selected embedded source subtitle: "
                    f"{embedded_source.language or 'unknown'} "
                    f"-> "
                    f"{self._subtitle_language(embedded_source) or 'unknown'} "
                    f"({embedded_source.codec or 'unknown'}) / "
                    f"{'text' if embedded_source.extractable else 'image'}"
                ),
                filename,
                7,
            )

        else:

            self._progress(
                (
                    "No embedded source subtitle matched "
                    f"language '{self.source_language}'"
                ),
                filename,
                7,
            )

        # ======================================================
        # FIND TARGET
        # ======================================================

        embedded_target: Optional[
            EmbeddedSubtitle
        ] = None

        if self.target_language:

            embedded_target = (
                self._find_embedded_subtitle(
                    embedded_subtitles,
                    self.target_language,
                )
            )

            if embedded_target:

                self._progress(
                    (
                        "Selected embedded target subtitle: "
                        f"{embedded_target.language or 'unknown'} "
                        f"-> "
                        f"{self._subtitle_language(embedded_target) or 'unknown'} "
                        f"({embedded_target.codec or 'unknown'}) / "
                        f"{'text' if embedded_target.extractable else 'image'}"
                    ),
                    filename,
                    7,
                )

        # ======================================================
        # SOURCE DECISION
        # ======================================================

        source_exists = os.path.isfile(
            source_subtitle
        )

        source_available = False
        transcribe_required = False

        # ------------------------------------------------------
        # 1. EMBEDDED SOURCE TEXT
        # ------------------------------------------------------

        if (
            embedded_source
            and embedded_source.extractable
            and not self.overwrite_existing
        ):

            self._progress(
                (
                    "Embedded source text subtitle found; "
                    "extracting it instead of using Google"
                ),
                filename,
                10,
            )

            self._extract_embedded_subtitle(
                media_filepath=media_filepath,
                stream=embedded_source,
                output_filepath=source_subtitle,
            )

            source_available = os.path.isfile(
                source_subtitle
            )

            if not source_available:

                raise RuntimeError(
                    "Embedded subtitle extraction completed "
                    "but source subtitle file was not created."
                )

            self._progress(
                (
                    "Embedded source subtitle extracted: "
                    f"{source_subtitle}"
                ),
                filename,
                15,
            )

        # ------------------------------------------------------
        # 2. EXISTING EXTERNAL SOURCE
        # ------------------------------------------------------

        elif (
            source_exists
            and not self.overwrite_existing
        ):

            self._progress(
                (
                    "No usable embedded source text subtitle; "
                    "using existing external source subtitle"
                ),
                filename,
                15,
            )

            source_available = True

        # ------------------------------------------------------
        # 3. OVERWRITE
        # ------------------------------------------------------

        elif self.overwrite_existing:

            self._progress(
                (
                    "Overwrite enabled; ignoring embedded and "
                    "existing source subtitles. Google will "
                    "regenerate the source subtitle."
                ),
                filename,
                15,
            )

            transcribe_required = True

        # ------------------------------------------------------
        # 4. EMBEDDED IMAGE SOURCE
        # ------------------------------------------------------

        elif (
            embedded_source
            and not embedded_source.extractable
        ):

            self._progress(
                (
                    "Embedded source subtitle is image-based "
                    "and cannot be directly extracted as text"
                ),
                filename,
                15,
            )

            if source_exists:

                source_available = True

            else:

                transcribe_required = True

        # ------------------------------------------------------
        # 5. NOTHING
        # ------------------------------------------------------

        else:

            self._progress(
                (
                    "No usable embedded or external source "
                    "subtitle found; Google will transcribe "
                    "the audio"
                ),
                filename,
                15,
            )

            transcribe_required = True

        # ======================================================
        # TARGET DECISION
        # ======================================================

        target_exists = bool(
            translated_subtitle
            and os.path.isfile(
                translated_subtitle
            )
        )

        translate_required = False

        if self.target_language:

            # --------------------------------------------------
            # EMBEDDED TARGET
            # --------------------------------------------------

            if (
                embedded_target
                and embedded_target.extractable
                and not self.overwrite_existing
            ):

                self._progress(
                    (
                        "Embedded target text subtitle found; "
                        "using it instead of translation"
                    ),
                    filename,
                    18,
                )

                self._extract_embedded_subtitle(
                    media_filepath=media_filepath,
                    stream=embedded_target,
                    output_filepath=translated_subtitle,
                )

                target_exists = os.path.isfile(
                    translated_subtitle
                )

                if not target_exists:

                    raise RuntimeError(
                        "Embedded target subtitle extraction "
                        "completed but target subtitle file "
                        "was not created."
                    )

            # --------------------------------------------------
            # OVERWRITE TARGET
            # --------------------------------------------------

            elif self.overwrite_existing:

                self._progress(
                    (
                        "Overwrite enabled; ignoring embedded and "
                        "existing target subtitles. Translation "
                        "will regenerate the target subtitle."
                    ),
                    filename,
                    20,
                )

                translate_required = True

            # --------------------------------------------------
            # EXISTING TARGET
            # --------------------------------------------------

            elif (
                target_exists
                and not self.overwrite_existing
            ):

                self._progress(
                    (
                        "Existing target subtitle found; "
                        "translation skipped"
                    ),
                    filename,
                    20,
                )

            # --------------------------------------------------
            # EMBEDDED IMAGE TARGET
            # --------------------------------------------------

            elif (
                embedded_target
                and not embedded_target.extractable
            ):

                self._progress(
                    (
                        "Embedded target subtitle is image-based; "
                        "it cannot be directly extracted as text"
                    ),
                    filename,
                    20,
                )

                if (
                    target_exists
                    and not self.overwrite_existing
                ):

                    self._progress(
                        "Using existing external target subtitle",
                        filename,
                        21,
                    )

                else:

                    translate_required = (
                        self._should_translate(
                            filename=filename,
                            source_subtitle=source_subtitle,
                            translated_subtitle=translated_subtitle,
                        )
                    )

            # --------------------------------------------------
            # NO EMBEDDED TARGET
            # --------------------------------------------------

            else:

                translate_required = (
                    self._should_translate(
                        filename=filename,
                        source_subtitle=source_subtitle,
                        translated_subtitle=translated_subtitle,
                    )
                )

        # ======================================================
        # NOTHING TO DO
        # ======================================================

        if (
            not transcribe_required
            and not translate_required
        ):

            self._progress(
                "Subtitles complete",
                filename,
                100,
            )

            return self._build_result(
                media_filepath=media_filepath,
                source_subtitle=source_subtitle,
                translated_subtitle=translated_subtitle,
                regions=0,
                recognized_segments=0,
            )

        regions: List[
            Tuple[float, float]
        ] = []

        transcripts: List[str] = []

        try:

            # ==================================================
            # TRANSCRIBE
            # ==================================================

            if transcribe_required:

                self._progress(
                    "Extracting audio and transcribing",
                    filename,
                    20,
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

                    if not isinstance(
                        item,
                        dict,
                    ):
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

                self._write_subtitle(
                    filepath=source_subtitle,
                    regions=regions,
                    transcripts=transcripts,
                    filename=filename,
                    progress_message=(
                        "Writing source subtitle"
                    ),
                )

                source_available = True

            # ==================================================
            # READ SOURCE FOR TRANSLATION
            # ==================================================

            if translate_required:

                if not source_available:

                    source_available = os.path.isfile(
                        source_subtitle
                    )

                if not source_available:

                    raise RuntimeError(
                        "Translation was requested but "
                        "no source subtitle is available."
                    )

                self._progress(
                    (
                        "Reading source subtitle for "
                        "translation"
                    ),
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
                        "The source subtitle contains "
                        "no usable subtitle lines."
                    )

                self._progress(
                    (
                        f"Loaded {len(transcripts)} "
                        "subtitle lines for translation"
                    ),
                    filename,
                    60,
                )

            # ==================================================
            # TRANSLATION
            # ==================================================

            if translate_required:

                if not self.target_language:

                    raise RuntimeError(
                        "Translation was requested but "
                        "no target language is configured."
                    )

                if not translated_subtitle:

                    raise RuntimeError(
                        "Target subtitle filepath is missing."
                    )

                self._progress(
                    (
                        "Starting SRTranslator / TranslatePy "
                        f"translation "
                        f"{self.source_language} -> "
                        f"{self.target_language}"
                    ),
                    filename,
                    65,
                )

                source_format = (
                    self._normalize_subtitle_format(
                        source_subtitle
                    )
                )

                temporary_source_srt: Optional[
                    str
                ] = None

                translated_srt: Optional[
                    str
                ] = None

                translator: Optional[
                    SubtitlesTranslator
                ] = None

                try:

                    # --------------------------------------------------
                    # CONVERT SOURCE TO SRT IF NECESSARY
                    # --------------------------------------------------

                    if source_format == "srt":

                        translation_source_srt = (
                            source_subtitle
                        )

                    else:

                        temporary_source_srt = create_temp_file(
                            suffix=".srt",
                            prefix="source_",
                        )

                        self._progress(
                            (
                                f"Converting source "
                                f"{source_format.upper()} "
                                "to SRT"
                            ),
                            filename,
                            66,
                        )

                        self._convert_subtitle_to_srt(
                            source_subtitle,
                            temporary_source_srt,
                        )

                        translation_source_srt = (
                            temporary_source_srt
                        )

                    # --------------------------------------------------
                    # TEMPORARY TRANSLATED SRT
                    # --------------------------------------------------

                    translated_srt = create_temp_file(
                        suffix=".srt",
                        prefix="translated_",
                    )

                    # --------------------------------------------------
                    # SUBTITLE TRANSLATOR
                    #
                    # 200 subtitles per bulk batch.
                    # --------------------------------------------------

                    translator = SubtitlesTranslator(
                        source_language=self.source_language,
                        target_language=self.target_language,
                        error_messages_callback=self._error,
                        progress_callback=(
                            lambda percentage:
                            self._translation_progress(
                                percentage,
                                filename,
                            )
                        ),
                        batch_size=BATCH_SIZE,
                        retry_count=3,
                        retry_delay=1.0,
                    )

                    if not translator.is_available:

                        raise RuntimeError(
                            "SRTranslator failed to initialize."
                        )

                    self._progress(
                        (
                            "Translating with "
                            "SRTranslator / TranslatePy "
                            f"{self.source_language} -> "
                            f"{self.target_language} "
                            f"(batches of {BATCH_SIZE})"
                        ),
                        filename,
                        70,
                    )

                    # --------------------------------------------------
                    # THIS IS THE ONLY TRANSLATION CALL.
                    #
                    # It creates translated_srt.
                    #
                    # There is intentionally NO translated_transcripts
                    # variable here.
                    # --------------------------------------------------

                    translator.translate_srt(
                        translation_source_srt,
                        translated_srt,
                    )

                    if not os.path.isfile(
                        translated_srt
                    ):

                        raise RuntimeError(
                            "SRTranslator completed but did not "
                            "create the translated SRT."
                        )

                    # --------------------------------------------------
                    # CONVERT TRANSLATED SRT TO REQUESTED FORMAT
                    # --------------------------------------------------

                    output_format = (
                        self._normalize_subtitle_format(
                            translated_subtitle
                        )
                    )

                    self._progress(
                        (
                            "Converting translated SRT "
                            f"to {output_format.upper()}"
                        ),
                        filename,
                        95,
                    )

                    if os.path.isfile(
                        translated_subtitle
                    ):

                        try:

                            os.remove(
                                translated_subtitle
                            )

                        except OSError as exc:

                            raise RuntimeError(
                                "Cannot replace existing target "
                                f"subtitle: "
                                f"{translated_subtitle}"
                            ) from exc

                    self._convert_srt_to_format(
                        translated_srt,
                        translated_subtitle,
                    )

                    if not os.path.isfile(
                        translated_subtitle
                    ):

                        raise RuntimeError(
                            "Translated subtitle conversion "
                            "completed but the target file "
                            "was not created."
                        )

                    self._progress(
                        (
                            "Translation complete: "
                            f"{translated_subtitle}"
                        ),
                        filename,
                        98,
                    )

                finally:

                    if translator:

                        try:

                            translator.close()

                        except Exception:

                            pass

                    remove_temp_file(
                        temporary_source_srt
                    )

                    remove_temp_file(
                        translated_srt
                    )

            # ==================================================
            # COMPLETE
            # ==================================================

            self._progress(
                "Subtitles complete",
                filename,
                100,
            )

            return self._build_result(
                media_filepath=media_filepath,
                source_subtitle=source_subtitle,
                translated_subtitle=translated_subtitle,
                regions=len(regions),
                recognized_segments=len(
                    transcripts
                ),
            )

        except KeyboardInterrupt:

            self._error(
                "Cancelling task execution"
            )

            raise

        except Exception as exc:

            self._error(exc)

            raise

    # ==========================================================
    # RESULT
    # ==========================================================

    @staticmethod
    def _existing_file(
        filepath: Optional[str],
    ) -> Optional[str]:

        if (
            filepath
            and os.path.isfile(filepath)
        ):

            return filepath

        return None

    def _build_result(
        self,
        media_filepath: str,
        source_subtitle: str,
        translated_subtitle: Optional[str],
        regions: int,
        recognized_segments: int,
    ) -> Dict[str, Any]:

        return {
            "media": media_filepath,

            "source_subtitle": self._existing_file(
                source_subtitle
            ),

            "translated_subtitle": self._existing_file(
                translated_subtitle
            ),

            "regions": regions,

            "recognized_segments": (
                recognized_segments
            ),

            "transcription_task": "transcribe",
        }

    # ==========================================================
    # TRANSLATION PROGRESS
    # ==========================================================

    def _translation_progress(
        self,
        percentage: int,
        filename: str,
    ) -> None:

        percentage = max(
            0,
            min(
                100,
                int(percentage),
            ),
        )

        # Map translator's 0-100 progress into
        # service's 70-95 range.
        service_percentage = int(
            70
            + (
                percentage
                * 0.25
            )
        )

        service_percentage = max(
            70,
            min(
                95,
                service_percentage,
            ),
        )

        self._progress(
            "Translation in progress",
            filename,
            service_percentage,
        )

    # ==========================================================
    # TRANSLATION DECISION
    # ==========================================================

    def _should_translate(
        self,
        filename: str,
        source_subtitle: str,
        translated_subtitle: Optional[str],
    ) -> bool:

        if not self.target_language:

            return False

        if is_same_language(
            self.source_language,
            self.target_language,
            self._error,
        ):

            self._progress(
                (
                    "Source and target languages are identical; "
                    "translation skipped"
                ),
                filename,
                62,
            )

            return False

        if (
            translated_subtitle
            and os.path.isfile(
                translated_subtitle
            )
            and not self.overwrite_existing
        ):

            self._progress(
                (
                    "Target subtitle already exists; "
                    "translation skipped"
                ),
                filename,
                62,
            )

            return False

        # ------------------------------------------------------
        # OPTIONAL CALLBACK
        # ------------------------------------------------------

        if self.translate_callback:

            try:

                decision = self.translate_callback(
                    self.source_language,
                    self.target_language,
                    source_subtitle,
                    translated_subtitle,
                )

                return bool(decision)

            except TypeError:

                try:

                    decision = self.translate_callback(
                        self.target_language,
                        "Target/Translation",
                    )

                    return bool(decision)

                except TypeError:

                    try:

                        decision = self.translate_callback()

                        return bool(decision)

                    except Exception as exc:

                        self._error(exc)

                        self._progress(
                            (
                                "Translation callback failed; "
                                "continuing automatically"
                            ),
                            filename,
                            63,
                        )

                        return True

                except Exception as exc:

                    self._error(exc)

                    self._progress(
                        (
                            "Translation callback failed; "
                            "continuing automatically"
                        ),
                        filename,
                        63,
                    )

                    return True

            except Exception as exc:

                self._error(exc)

                self._progress(
                    (
                        "Translation callback failed; "
                        "continuing automatically"
                    ),
                    filename,
                    63,
                )

                return True

        # ------------------------------------------------------
        # AUTOMATIC TRANSLATION
        # ------------------------------------------------------

        self._progress(
            (
                "No existing target subtitle; "
                "automatic translation requested"
            ),
            filename,
            62,
        )

        return True

    # ==========================================================
    # READ SOURCE SUBTITLE
    # ==========================================================

    def _read_source_subtitle(
        self,
        filepath: str,
    ) -> Tuple[
        List[Tuple[float, float]],
        List[str],
    ]:

        if not os.path.isfile(
            filepath
        ):

            raise FileNotFoundError(
                f"Source subtitle does not exist: "
                f"{filepath}"
            )

        try:

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

                    parsed_regions.append(
                        (
                            start,
                            end,
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

            return self._parse_srt(
                filepath
            )

        except Exception as exc:

            raise RuntimeError(
                f"Failed to read source subtitle "
                f"'{filepath}': {exc}"
            ) from exc

    # ==========================================================
    # SRT PARSER
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

        content = (
            content
            .replace("\r\n", "\n")
            .replace("\r", "\n")
        )

        blocks = content.split(
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

            if len(lines) < 2:

                continue

            timing_line = None
            timing_index = -1

            for index, line in enumerate(
                lines
            ):

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
                    self_timestamp_to_seconds(
                        start_text.strip()
                    )
                )

                end_timestamp = (
                    end_text
                    .strip()
                    .split()[0]
                )

                end = (
                    self_timestamp_to_seconds(
                        end_timestamp
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

        return (
            regions,
            texts,
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

        if len(regions) != len(
            transcripts
        ):

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

                return

            except Exception:

                pass

        print(error)


# ==============================================================
# SRT TIMESTAMP
# ==============================================================

def self_timestamp_to_seconds(
    timestamp: str,
) -> float:

    timestamp = (
        timestamp
        .strip()
        .replace(",", ".")
    )

    parts = timestamp.split(":")

    if len(parts) != 3:

        raise ValueError(
            f"Invalid SRT timestamp: "
            f"{timestamp}"
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