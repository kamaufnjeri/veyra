from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from media.burner import SubtitleBurner
from media.cutter import MediaCutter
from media.converter import MediaConverter
from media.inspector import MediaInspector
from media.joiner import MediaJoiner
from media.models import (
    BurnerSettings,
    BurnResult,
    ConvertResult,
    ConverterSettings,
    CutResult,
    CutterSettings,
    JoinResult,
    JoinerSettings,
)


class MediaEngineService:
    """
    High-level facade for the media engine.

    Provides a single API for:

        - inspecting media
        - converting media
        - cutting media
        - joining media
        - burning subtitles

    The service delegates the actual work to the specialized
    media operation classes.
    """

    def __init__(
        self,
        *,
        ffmpeg: str = "ffmpeg",
        ffprobe: str = "ffprobe",
        progress_callback=None,
        cancellation_callback=None,
    ) -> None:

        common = {
            "ffmpeg": ffmpeg,
            "ffprobe": ffprobe,
            "progress_callback": progress_callback,
            "cancellation_callback": cancellation_callback,
        }

        self.inspector = MediaInspector()

        self.converter = MediaConverter(
            **common,
        )

        self.cutter = MediaCutter(
            **common,
        )

        self.joiner = MediaJoiner(
            **common,
        )

        self.burner = SubtitleBurner(
            **common,
        )

    # ============================================================
    # INSPECT
    # ============================================================

    def inspect(
        self,
        input_path: str | Path,
        *,
        include_subtitle_text: bool = False,
        include_raw: bool = False,
    ) -> dict[str, Any]:
        """
        Inspect a media file and return a JSON-friendly structure.
        """

        return self.inspector.inspect(
            input_path,
            include_subtitle_text=include_subtitle_text,
            include_raw=include_raw,
        )

    def inspect_json(
        self,
        input_path: str | Path,
        *,
        include_subtitle_text: bool = False,
        include_raw: bool = False,
        indent: int = 2,
    ) -> str:
        """
        Inspect media and return the result as JSON.
        """

        return self.inspector.inspect_json(
            input_path,
            include_subtitle_text=include_subtitle_text,
            include_raw=include_raw,
            indent=indent,
        )

    # ============================================================
    # CONVERT
    # ============================================================

    def convert(
        self,
        input_path: str | Path,
        output_path: str | Path,
        settings: ConverterSettings | None = None,
    ) -> ConvertResult:
        """
        Convert, remux, or re-encode media.
        """

        return self.converter.convert(
            input_path,
            output_path,
            settings,
        )

    # ============================================================
    # CUT
    # ============================================================

    def cut(
        self,
        input_path: str | Path,
        settings: CutterSettings | None = None,
    ) -> CutResult:
        """
        Cut media into one or more segments.
        """

        return self.cutter.cut(
            input_path,
            settings,
        )

    # ============================================================
    # JOIN
    # ============================================================

    def join(
        self,
        inputs: Sequence[str | Path],
        output: str | Path,
        settings: JoinerSettings | None = None,
    ) -> JoinResult:
        """
        Join multiple media files into one output.
        """

        return self.joiner.join(
            inputs,
            output,
            settings,
        )

    # ============================================================
    # BURN SUBTITLES
    # ============================================================

    def burn_subtitles(
        self,
        video: str | Path,
        subtitle: str | Path,
        output: str | Path,
        settings: BurnerSettings | None = None,
    ) -> BurnResult:
        """
        Permanently burn subtitles into a video.
        """

        return self.burner.burn(
            video,
            subtitle,
            output,
            settings,
        )
