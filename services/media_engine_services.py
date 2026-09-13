from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from media.burner import SubtitleBurner
from media.compressor import MediaCompressor
from media.cutter import MediaCutter
from media.converter import MediaConverter
from media.extractor import MediaExtractor
from media.inspector import MediaInspector
from media.joiner import MediaJoiner
from media.muxer import MediaMuxer
from media.models import (
    BurnerSettings,
    BurnResult,
    CompressorSettings,
    CompressResult,
    ConvertResult,
    ConverterSettings,
    CutResult,
    CutterSettings,
    ExtractResult,
    ExtractorSettings,
    JoinResult,
    JoinerSettings,
    MuxResult,
    MuxerSettings,
)


class MediaEngineService:
    """
    High-level facade for the complete media engine.

    Provides a single public API for:

        - inspecting media
        - converting media
        - cutting media
        - joining media
        - muxing media
        - compressing media
        - extracting media
        - burning subtitles

    The service delegates the actual work to specialized
    media operation classes.

    Operation responsibilities:

        inspect
            Inspect media streams and metadata.

        convert
            Convert or re-encode a media file.

        cut
            Split media into segments.

        join
            Sequentially join compatible media files.

        mux
            Combine independent video/audio/subtitle streams.

        compress
            Reduce video/audio size or quality.

        extract
            Extract video, audio, or subtitle streams.

        burn_subtitles
            Permanently render subtitles into video.
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

        # ========================================================
        # INSPECTOR
        # ========================================================

        self.inspector = MediaInspector()

        # ========================================================
        # CONVERTER
        # ========================================================

        self.converter = MediaConverter(
            **common,
        )

        # ========================================================
        # CUTTER
        # ========================================================

        self.cutter = MediaCutter(
            **common,
        )

        # ========================================================
        # JOINER
        # ========================================================

        self.joiner = MediaJoiner(
            **common,
        )

        # ========================================================
        # MUXER
        # ========================================================

        self.muxer = MediaMuxer(
            **common,
        )

        # ========================================================
        # COMPRESSOR
        # ========================================================

        self.compressor = MediaCompressor(
            **common,
        )

        # ========================================================
        # EXTRACTOR
        # ========================================================

        self.extractor = MediaExtractor(
            **common,
        )

        # ========================================================
        # SUBTITLE BURNER
        # ========================================================

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
        Sequentially join compatible media files.

        Examples:

            video + video -> video

            audio + audio -> audio

            video(with audio) + video(with audio)
                -> video(with audio)

        Sidecar subtitles are handled by MediaJoiner.
        """

        return self.joiner.join(
            inputs,
            output,
            settings,
        )

    # ============================================================
    # MUX
    # ============================================================

    def mux(
        self,
        inputs: Sequence[str | Path],
        output: str | Path,
        settings: MuxerSettings | None = None,
    ) -> MuxResult:
        """
        Combine independent media streams.

        Examples:

            video + audio -> video/audio

            video + subtitle -> video/subtitle

            video + audio + subtitle
                -> video/audio/subtitle

        Muxing does not concatenate media sequentially.
        """

        return self.muxer.mux(
            inputs,
            output,
            settings,
        )

    # ============================================================
    # COMPRESS
    # ============================================================

    def compress(
        self,
        input_path: str | Path,
        output_path: str | Path,
        settings: CompressorSettings | None = None,
    ) -> CompressResult:
        """
        Compress media to reduce file size and/or quality.

        Supports:

            - video compression
            - audio compression
            - video + audio compression
        """

        return self.compressor.compress(
            input_path,
            output_path,
            settings,
        )

    # ============================================================
    # EXTRACT
    # ============================================================

    def extract(
        self,
        input_path: str | Path,
        output_path: str | Path,
        settings: ExtractorSettings | None = None,
    ) -> ExtractResult:
        """
        Extract a media stream.

        Supported stream types include:

            - audio
            - video
            - subtitle
        """

        return self.extractor.extract(
            input_path,
            output_path,
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