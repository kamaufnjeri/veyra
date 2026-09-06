from __future__ import annotations

from pathlib import Path

from .models import (
    ConversionResult,
    EncodeOptions,
    ProgressCallback,
)
from .probe import MediaProbe
from .transcoder import MediaTranscoder


class MediaConverter:
    """High-level video conversion API."""

    def __init__(
        self,
        probe: MediaProbe | None = None,
        transcoder: MediaTranscoder | None = None,
    ) -> None:
        self.probe = probe or MediaProbe()
        self.transcoder = transcoder or MediaTranscoder()

    def convert(
        self,
        input_path: str | Path,
        output_path: str | Path,
        *,
        options: EncodeOptions | None = None,
        overwrite: bool = True,
        progress_callback: ProgressCallback | None = None,
    ) -> ConversionResult:
        info = self.probe.inspect(input_path)

        output = self.transcoder.transcode(
            input_path,
            output_path,
            options=options,
            duration=info.duration,
            overwrite=overwrite,
            progress_callback=progress_callback,
        )

        return ConversionResult(
            input_path=info.path,
            output_path=output,
            duration=info.duration,
            reencoded=True,
        )