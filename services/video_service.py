# services/video_service.py

from __future__ import annotations

import os
import subprocess
from typing import Callable, Optional


class VideoService:
    """
    Handles video conversion and subtitle embedding.

    Responsibilities:

        MP4 → MKV
        MKV → MP4
        AVI → MP4
        etc.

    and:

        video + subtitle → video with subtitles
    """

    def __init__(
        self,
        progress_callback: Optional[
            Callable[[str, str, int], None]
        ] = None,
        error_callback: Optional[
            Callable[[Exception], None]
        ] = None,
    ):

        self.progress_callback = progress_callback
        self.error_callback = error_callback

        self.ffmpeg = self._find_ffmpeg()

    # ==========================================================
    # FFMPEG
    # ==========================================================

    @staticmethod
    def _find_ffmpeg() -> str:

        import shutil

        ffmpeg = shutil.which("ffmpeg")

        if not ffmpeg:
            raise RuntimeError(
                "FFmpeg was not found. "
                "Install FFmpeg and make sure it is in PATH."
            )

        return ffmpeg

    # ==========================================================
    # PUBLIC METHOD
    # ==========================================================

    def process(
        self,
        media_filepath: str,
        source_subtitle: Optional[str] = None,
        translated_subtitle: Optional[str] = None,
        output_directory: Optional[str] = None,
        convert: bool = False,
        embed_subtitles: bool = False,
        output_format: Optional[str] = None,
    ) -> dict:

        media_filepath = os.path.abspath(
            media_filepath
        )

        if not os.path.isfile(media_filepath):
            raise FileNotFoundError(
                media_filepath
            )

        current_video = media_filepath

        # ------------------------------------------------------
        # 1. Convert video
        # ------------------------------------------------------

        if convert:

            current_video = self.convert_video(
                input_filepath=current_video,
                output_directory=output_directory,
                output_format=output_format,
            )

        # ------------------------------------------------------
        # 2. Embed translated subtitles if available
        # ------------------------------------------------------

        subtitle_to_embed = (
            translated_subtitle
            or source_subtitle
        )

        if (
            embed_subtitles
            and subtitle_to_embed
        ):

            current_video = (
                self.embed_subtitles(
                    video_filepath=current_video,
                    subtitle_filepath=subtitle_to_embed,
                    output_directory=output_directory,
                )
            )

        return {
            "input": media_filepath,
            "output": current_video,
        }

    # ==========================================================
    # CONVERT VIDEO
    # ==========================================================

    def convert_video(
        self,
        input_filepath: str,
        output_directory: Optional[str] = None,
        output_format: Optional[str] = None,
    ) -> str:

        if not output_format:
            output_format = "mp4"

        if output_directory:
            os.makedirs(
                output_directory,
                exist_ok=True,
            )
        else:
            output_directory = os.path.dirname(
                input_filepath
            )

        filename = os.path.splitext(
            os.path.basename(input_filepath)
        )[0]

        output_filepath = os.path.join(
            output_directory,
            f"{filename}_converted.{output_format}",
        )

        command = [
            self.ffmpeg,

            "-hide_banner",

            "-y",

            "-i",
            input_filepath,

            output_filepath,
        ]

        self._progress(
            "Converting video",
            input_filepath,
            0,
        )

        self._run_ffmpeg(
            command
        )

        self._progress(
            "Video conversion complete",
            input_filepath,
            100,
        )

        return output_filepath

    # ==========================================================
    # EMBED SUBTITLES
    # ==========================================================

    def embed_subtitles(
        self,
        video_filepath: str,
        subtitle_filepath: str,
        output_directory: Optional[str] = None,
    ) -> str:

        if not os.path.isfile(
            subtitle_filepath
        ):
            raise FileNotFoundError(
                f"Subtitle does not exist: "
                f"{subtitle_filepath}"
            )

        if output_directory:
            os.makedirs(
                output_directory,
                exist_ok=True,
            )
        else:
            output_directory = os.path.dirname(
                video_filepath
            )

        filename = os.path.splitext(
            os.path.basename(video_filepath)
        )[0]

        extension = os.path.splitext(
            video_filepath
        )[1]

        output_filepath = os.path.join(
            output_directory,
            f"{filename}_subtitled{extension}",
        )

        command = [
            self.ffmpeg,

            "-hide_banner",

            "-y",

            "-i",
            video_filepath,

            "-i",
            subtitle_filepath,

            "-map",
            "0",

            "-map",
            "1",

            "-c",
            "copy",

            "-c:s",
            "mov_text",

            output_filepath,
        ]

        self._progress(
            "Embedding subtitles",
            video_filepath,
            0,
        )

        self._run_ffmpeg(
            command
        )

        self._progress(
            "Subtitle embedding complete",
            video_filepath,
            100,
        )

        return output_filepath

    # ==========================================================
    # RUN FFMPEG
    # ==========================================================

    def _run_ffmpeg(
        self,
        command: list[str],
    ) -> None:

        try:

            process = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            if process.returncode != 0:

                error = (
                    process.stderr.strip()
                    or "FFmpeg failed."
                )

                raise RuntimeError(
                    error
                )

        except Exception as exc:

            self._error(exc)

            raise

    # ==========================================================
    # PROGRESS
    # ==========================================================

    def _progress(
        self,
        stage: str,
        filename: str,
        percentage: int,
    ) -> None:

        if self.progress_callback:

            self.progress_callback(
                stage,
                filename,
                percentage,
            )

    # ==========================================================
    # ERROR
    # ==========================================================

    def _error(
        self,
        error: Exception,
    ) -> None:

        if self.error_callback:
            self.error_callback(error)