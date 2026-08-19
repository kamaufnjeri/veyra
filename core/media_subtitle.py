from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class EmbeddedSubtitle:
    """
    A subtitle stream found inside a media container.
    """

    stream_index: int
    language: Optional[str]
    title: Optional[str]
    codec: Optional[str]
    codec_long_name: Optional[str]
    forced: bool
    default: bool
    hearing_impaired: bool
    extractable: bool

    @property
    def is_image_based(self) -> bool:
        return not self.extractable


class MediaSubtitleInspector:
    """
    Inspects subtitle streams embedded in media files using ffprobe.
    """

    TEXT_CODECS = {
        "subrip",
        "srt",
        "ass",
        "ssa",
        "webvtt",
        "mov_text",
        "text",
        "ttml",
        "stpp",
        "smpte_tt",
    }

    IMAGE_CODECS = {
        "hdmv_pgs_subtitle",
        "pgssub",
        "dvd_subtitle",
        "dvdsub",
        "xsub",
        "dvb_subtitle",
        "dvbsub",
    }

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

    def __init__(
        self,
        ffprobe_path: str = "ffprobe",
        error_callback=None,
    ):
        self.ffprobe_path = ffprobe_path
        self.error_callback = error_callback

    # ==========================================================
    # PUBLIC
    # ==========================================================

    def inspect(
        self,
        media_filepath: str,
    ) -> List[EmbeddedSubtitle]:

        if not os.path.isfile(media_filepath):
            raise FileNotFoundError(
                f"Media file does not exist: {media_filepath}"
            )

        # IMPORTANT:
        # Keep this EXACTLY aligned with the ffprobe command
        # that works from the terminal:
        #
        # ffprobe -v error \
        #   -select_streams s \
        #   -show_entries stream=index,codec_name,codec_long_name,disposition:stream_tags=language,title \
        #   -of json \
        #   "file.mp4"
        #
        command = [
            self.ffprobe_path,
            "-v",
            "error",
            "-select_streams",
            "s",
            "-show_entries",
            "stream=index,codec_name,codec_long_name,disposition:"
            "stream_tags=language,title",
            "-of",
            "json",
            media_filepath,
        ]

        try:
            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )

        except FileNotFoundError as exc:
            raise RuntimeError(
                "ffprobe was not found.\n"
                "Install FFmpeg and make sure ffprobe "
                "is available on PATH."
            ) from exc

        if result.returncode != 0:
            raise RuntimeError(
                "ffprobe failed:\n"
                + result.stderr.strip()
            )

        raw_output = result.stdout or "{}"

        try:
            data = json.loads(raw_output)

        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "ffprobe returned invalid JSON:\n"
                f"{raw_output}"
            ) from exc

        subtitles: List[EmbeddedSubtitle] = []

        for stream in data.get("streams", []):

            subtitle = self._parse_stream(stream)

            subtitles.append(subtitle)

        return subtitles
    # ==========================================================
    # LANGUAGE MATCHING
    # ==========================================================

    @classmethod
    def find_language(
        cls,
        subtitles: List[EmbeddedSubtitle],
        language: str,
    ) -> List[EmbeddedSubtitle]:

        requested = cls.normalize_language(language)

        if not requested:
            return []

        exact: List[EmbeddedSubtitle] = []
        matches: List[EmbeddedSubtitle] = []

        for subtitle in subtitles:

            stream_language = cls.normalize_language(
                subtitle.language
            )

            if not stream_language:
                continue

            if stream_language == requested:
                exact.append(subtitle)
                continue

            if cls.same_language(
                stream_language,
                requested,
            ):
                matches.append(subtitle)

        return exact + matches

    @classmethod
    def choose_best(
        cls,
        subtitles: List[EmbeddedSubtitle],
        language: str,
    ) -> Optional[EmbeddedSubtitle]:

        candidates = cls.find_language(
            subtitles,
            language,
        )

        if not candidates:
            return None

        return cls.choose_best_candidate(
            candidates
        )

    @staticmethod
    def choose_best_candidate(
        subtitles: List[EmbeddedSubtitle],
    ) -> Optional[EmbeddedSubtitle]:

        if not subtitles:
            return None

        # ------------------------------------------------------
        # Text subtitles first.
        # ------------------------------------------------------

        text_candidates = [
            item
            for item in subtitles
            if item.extractable
        ]

        if text_candidates:
            candidates = text_candidates
        else:
            candidates = list(subtitles)

        # ------------------------------------------------------
        # Non-forced first.
        # ------------------------------------------------------

        non_forced = [
            item
            for item in candidates
            if not item.forced
        ]

        if non_forced:
            candidates = non_forced

        # ------------------------------------------------------
        # Default first.
        # ------------------------------------------------------

        defaults = [
            item
            for item in candidates
            if item.default
        ]

        if defaults:
            return defaults[0]

        return candidates[0]

    # ==========================================================
    # LANGUAGE NORMALIZATION
    # ==========================================================

    @classmethod
    def normalize_language(
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

    @classmethod
    def same_language(
        cls,
        first: Optional[str],
        second: Optional[str],
    ) -> bool:

        first_normalized = cls.normalize_language(
            first
        )

        second_normalized = cls.normalize_language(
            second
        )

        return (
            bool(first_normalized)
            and bool(second_normalized)
            and first_normalized == second_normalized
        )

    # ==========================================================
    # STREAM PARSER
    # ==========================================================

    def _parse_stream(
        self,
        stream: Dict[str, Any],
    ) -> EmbeddedSubtitle:

        codec = (
            str(
                stream.get("codec_name")
                or ""
            )
            .strip()
            .lower()
        )

        codec_long_name = (
            stream.get("codec_long_name")
        )

        disposition = (
            stream.get("disposition")
            or {}
        )

        tags = (
            stream.get("tags")
            or {}
        )

        # ----------------------------------------------------------
        # LANGUAGE
        #
        # ffprobe returns:
        #
        # "tags": {
        #     "language": "spa"
        # }
        #
        # We MUST read that value.
        # ----------------------------------------------------------

        language = (
            tags.get("language")
            or tags.get("LANGUAGE")
            or ""
        )

        language = str(
            language
        ).strip()

        # ----------------------------------------------------------
        # TITLE
        # ----------------------------------------------------------

        title = (
            tags.get("title")
            or tags.get("TITLE")
        )

        if title is not None:
            title = str(title).strip()

            if not title:
                title = None

        # ----------------------------------------------------------
        # NORMALIZE LANGUAGE
        #
        # spa -> es
        # eng -> en
        # etc.
        # ----------------------------------------------------------

        normalized_language = (
            self.normalize_language(language)
        )

        if not normalized_language:
            language = None

        # ----------------------------------------------------------
        # CODEC
        # ----------------------------------------------------------

        extractable = (
            codec in self.TEXT_CODECS
        )

        if codec in self.IMAGE_CODECS:
            extractable = False

        # ----------------------------------------------------------
        # CREATE OBJECT
        # ----------------------------------------------------------

        return EmbeddedSubtitle(
            stream_index=int(
                stream.get("index", -1)
            ),

            language=language,

            title=title,

            codec=(
                codec
                if codec
                else None
            ),

            codec_long_name=codec_long_name,

            forced=bool(
                disposition.get(
                    "forced",
                    0,
                )
            ),

            default=bool(
                disposition.get(
                    "default",
                    0,
                )
            ),

            hearing_impaired=bool(
                disposition.get(
                    "hearing_impaired",
                    0,
                )
            ),

            extractable=extractable,
        )
class MediaSubtitleExtractor:
    """
    Extracts an embedded text subtitle stream to SRT.
    """

    def __init__(
        self,
        ffmpeg_path: str = "ffmpeg",
        error_callback=None,
    ):
        self.ffmpeg_path = ffmpeg_path
        self.error_callback = error_callback

    # ==========================================================
    # PUBLIC
    # ==========================================================

    def extract(
        self,
        media_filepath: str,
        stream: EmbeddedSubtitle,
        output_filepath: str,
    ) -> str:

        if not stream.extractable:
            raise RuntimeError(
                "The selected subtitle stream is "
                "image-based and cannot be directly "
                "converted to text.\n"
                f"Codec: {stream.codec}"
            )

        if stream.stream_index < 0:
            raise RuntimeError(
                "Invalid embedded subtitle stream index."
            )

        output_filepath = os.path.abspath(
            output_filepath
        )

        os.makedirs(
            os.path.dirname(output_filepath),
            exist_ok=True,
        )

        # ------------------------------------------------------
        # Explicitly map the subtitle stream.
        #
        # -map 0:<stream index>
        #
        # mov_text -> srt is supported by FFmpeg.
        # ------------------------------------------------------

        command = [
            self.ffmpeg_path,
            "-y",
            "-v",
            "error",
            "-i",
            media_filepath,
            "-map",
            f"0:{stream.stream_index}",
            "-c:s",
            "srt",
            output_filepath,
        ]

        try:
            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )

        except FileNotFoundError as exc:
            raise RuntimeError(
                "ffmpeg was not found.\n"
                "Install FFmpeg and make sure ffmpeg "
                "is available on PATH."
            ) from exc

        if result.returncode != 0:
            raise RuntimeError(
                "Failed to extract embedded subtitle:\n"
                + (
                    result.stderr.strip()
                    or "FFmpeg returned a non-zero exit code."
                )
            )

        if not os.path.isfile(output_filepath):
            raise RuntimeError(
                "FFmpeg completed but did not create "
                f"the subtitle file: {output_filepath}"
            )

        if os.path.getsize(output_filepath) == 0:
            raise RuntimeError(
                "Extracted subtitle file is empty:\n"
                f"{output_filepath}"
            )

        return output_filepath