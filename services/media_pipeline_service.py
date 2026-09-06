from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

from media import (
    BurnResult,
    ConversionResult,
    CutOptions,
    CutResult,
    EncodeOptions,
    ExtractionResult,
    JoinResult,
    MediaConcatenator,
    MediaConverter,
    MediaCutter,
    MediaExtractor,
    MediaInfo,
    MediaJoiner,
    MediaMuxer,
    MediaPart,
    MediaProbe,
    MuxResult,
    MuxSubtitle,
    SubtitleBurner,
)


class MediaPipelineService:
    """
    Public application-facing media API for Veyra.

    This class coordinates the specialized media components.
    """

    def __init__(
        self,
        *,
        probe: MediaProbe | None = None,
        converter: MediaConverter | None = None,
        concatenator: MediaConcatenator | None = None,
        joiner: MediaJoiner | None = None,
        muxer: MediaMuxer | None = None,
        extractor: MediaExtractor | None = None,
        cutter: MediaCutter | None = None,
        burner: SubtitleBurner | None = None,
    ) -> None:
        self.probe = probe or MediaProbe()

        self.converter = (
            converter
            or MediaConverter(
                probe=self.probe,
            )
        )

        self.concatenator = (
            concatenator
            or MediaConcatenator(
                probe=self.probe,
            )
        )

        self.joiner = (
            joiner
            or MediaJoiner(
                probe=self.probe,
                concatenator=self.concatenator,
            )
        )

        self.muxer = (
            muxer
            or MediaMuxer(
                probe=self.probe,
            )
        )

        self.extractor = (
            extractor
            or MediaExtractor(
                probe=self.probe,
            )
        )

        self.cutter = (
            cutter
            or MediaCutter(
                probe=self.probe,
            )
        )

        self.burner = burner or SubtitleBurner()

    # ------------------------------------------------------------------
    # INSPECTION
    # ------------------------------------------------------------------

    def inspect(
        self,
        path: str | Path,
    ) -> MediaInfo:
        """Inspect a media file."""

        return self.probe.inspect(path)

    def duration(
        self,
        path: str | Path,
    ) -> float:
        """Return media duration in seconds."""

        return self.probe.duration(path)

    # ------------------------------------------------------------------
    # CONVERSION
    # ------------------------------------------------------------------

    def convert(
        self,
        input_path: str | Path,
        output_path: str | Path,
        *,
        options: EncodeOptions | None = None,
        overwrite: bool = True,
        progress_callback: Callable[..., None] | None = None,
    ) -> ConversionResult:
        """Convert/transcode a video."""

        return self.converter.convert(
            input_path,
            output_path,
            options=options,
            overwrite=overwrite,
            progress_callback=progress_callback,
        )

    # ------------------------------------------------------------------
    # CONCATENATION
    # ------------------------------------------------------------------

    def concatenate(
        self,
        inputs: Iterable[str | Path],
        output: str | Path,
        *,
        reencode: bool = False,
        encode_options: EncodeOptions | None = None,
        overwrite: bool = True,
        progress_callback: Callable[..., None] | None = None,
    ) -> Path:
        """Concatenate video files only."""

        return self.concatenator.concatenate(
            inputs,
            output,
            reencode=reencode,
            encode_options=encode_options,
            overwrite=overwrite,
            progress_callback=progress_callback,
        )

    # ------------------------------------------------------------------
    # VIDEO + SUBTITLE JOINING
    # ------------------------------------------------------------------

    def join(
        self,
        parts: Sequence[MediaPart],
        output_video: str | Path,
        *,
        subtitle_outputs: Mapping[str, str | Path] | None = None,
        reencode: bool = False,
        encode_options: EncodeOptions | None = None,
        overwrite: bool = True,
        progress_callback: Callable[..., None] | None = None,
    ) -> JoinResult:
        """
        Join videos and their corresponding subtitles.

        Subtitle timestamps are shifted using the actual duration
        of each video.
        """

        return self.joiner.join(
            parts,
            output_video,
            subtitle_outputs=subtitle_outputs,
            reencode=reencode,
            encode_options=encode_options,
            overwrite=overwrite,
            progress_callback=progress_callback,
        )

    # ------------------------------------------------------------------
    # MUXING
    # ------------------------------------------------------------------

    def mux(
        self,
        video: str | Path,
        *,
        audio: str | Path | None = None,
        subtitles: Iterable[MuxSubtitle] | None = None,
        output: str | Path,
        overwrite: bool = True,
        video_codec: str = "copy",
        audio_codec: str = "copy",
    ) -> MuxResult:
        """Mux video, optional external audio and optional subtitles."""

        return self.muxer.mux(
            video,
            audio=audio,
            subtitles=subtitles,
            output=output,
            overwrite=overwrite,
            video_codec=video_codec,
            audio_codec=audio_codec,
        )

    # ------------------------------------------------------------------
    # EXTRACTION
    # ------------------------------------------------------------------

    def extract_audio(
        self,
        video: str | Path,
        output: str | Path,
        *,
        stream_index: int = 0,
        codec: str = "copy",
        overwrite: bool = True,
    ) -> ExtractionResult:
        """Extract an audio stream."""

        return self.extractor.audio(
            video,
            output,
            stream_index=stream_index,
            codec=codec,
            overwrite=overwrite,
        )

    def extract_subtitle(
        self,
        video: str | Path,
        output: str | Path,
        *,
        stream_index: int = 0,
        overwrite: bool = True,
    ) -> ExtractionResult:
        """Extract a subtitle stream."""

        return self.extractor.subtitle(
            video,
            output,
            stream_index=stream_index,
            overwrite=overwrite,
        )

    # ------------------------------------------------------------------
    # CUTTING
    # ------------------------------------------------------------------

    def trim(
        self,
        input_path: str | Path,
        output_path: str | Path,
        *,
        options: CutOptions | None = None,
        overwrite: bool = True,
    ) -> CutResult:
        """Trim a media file."""

        return self.cutter.trim(
            input_path,
            output_path,
            options=options,
            overwrite=overwrite,
        )

    # ------------------------------------------------------------------
    # BURNING SUBTITLES
    # ------------------------------------------------------------------

    def burn_subtitles(
        self,
        video: str | Path,
        subtitle: str | Path,
        output: str | Path,
        *,
        overwrite: bool = True,
        video_codec: str = "libx264",
        preset: str = "medium",
        crf: int = 20,
        audio_codec: str = "copy",
    ) -> BurnResult:
        """Permanently render subtitles into the video."""

        return self.burner.burn(
            video,
            subtitle,
            output,
            overwrite=overwrite,
            video_codec=video_codec,
            preset=preset,
            crf=crf,
            audio_codec=audio_codec,
        )