from __future__ import annotations

import os
import subprocess
import sys
import time

from core.temp_manager import (
    create_temp_file,
    remove_temp_file,
)


class WavConverter:

    def __init__(
        self,
        channels: int = 1,
        rate: int = 16000,
        progress_callback=None,
        error_messages_callback=None,
        audio_source: str = "wav",
    ):
        """
        audio_source:

            "wav"
                Always extract WAV.

            "video"
                Do not extract WAV. Return the original
                media filepath so the caller/transcriber
                can process the media directly.

            "auto"
                Try WAV extraction first. If extraction fails,
                fall back to the original media filepath.

        Default:
            "wav"
        """

        self.channels = channels
        self.rate = rate
        self.progress_callback = progress_callback
        self.error_messages_callback = (
            error_messages_callback
        )

        self.audio_source = (
            str(audio_source)
            .strip()
            .lower()
        )

        valid_sources = {
            "wav",
            "video",
            "auto",
        }

        if self.audio_source not in valid_sources:

            raise ValueError(
                "Invalid audio_source. "
                "Expected 'wav', 'video', or 'auto'."
            )

    # ==========================================================
    # FIND EXECUTABLE
    # ==========================================================

    @staticmethod
    def which(program):

        def is_exe(file_path):
            return (
                os.path.isfile(file_path)
                and os.access(file_path, os.X_OK)
            )

        fpath, _ = os.path.split(program)

        if fpath:

            if is_exe(program):
                return program

            return None

        for path in os.environ.get(
            "PATH",
            "",
        ).split(os.pathsep):

            path = path.strip('"')

            exe_file = os.path.join(
                path,
                program,
            )

            if is_exe(exe_file):
                return exe_file

        return None

    # ==========================================================
    # FFMPEG
    # ==========================================================

    def ffmpeg_check(self):

        if self.which("ffmpeg"):
            return "ffmpeg"

        if self.which("ffmpeg.exe"):
            return "ffmpeg.exe"

        return None

    # ==========================================================
    # CONVERT
    # ==========================================================

    def __call__(
        self,
        media_filepath: str,
    ):

        if "\\" in media_filepath:

            media_filepath = (
                media_filepath.replace(
                    "\\",
                    "/",
                )
            )

        if not os.path.isfile(
            media_filepath
        ):

            error = (
                f"The given file does not exist: "
                f"'{media_filepath}'"
            )

            self._error(error)

            raise FileNotFoundError(
                error
            )

        filename = os.path.basename(
            media_filepath
        )

        # ======================================================
        # DIRECT VIDEO MODE
        # ======================================================

        if self.audio_source == "video":

            self._progress(
                (
                    "Using media file directly "
                    "for speech transcription"
                ),
                filename,
                100,
                None,
            )

            return (
                media_filepath,
                self.rate,
            )

        # ======================================================
        # CHECK FFMPEG
        #
        # Only required when WAV extraction is requested.
        # ======================================================

        ffmpeg = self.ffmpeg_check()

        if not ffmpeg:

            error = (
                "Cannot find ffmpeg executable"
            )

            # --------------------------------------------------
            # AUTO MODE FALLBACK
            # --------------------------------------------------

            if self.audio_source == "auto":

                self._progress(
                    (
                        "FFmpeg unavailable; "
                        "falling back to media file"
                    ),
                    filename,
                    100,
                    None,
                )

                self._error(error)

                return (
                    media_filepath,
                    self.rate,
                )

            self._error(error)

            raise RuntimeError(
                error
            )

        # ======================================================
        # TEMP WAV
        # ======================================================

        wav_filepath = create_temp_file(
            suffix=".wav",
            prefix="audio_",
        )

        try:

            info = (
                f"Extracting speech audio from "
                f"'{filename}'"
            )

            start_time = time.time()

            command = [
                ffmpeg,

                "-hide_banner",
                "-loglevel",
                "error",

                "-y",

                "-i",
                media_filepath,

                # SpeechRecognition / Google:
                # mono, 16 kHz, PCM WAV
                "-ac",
                str(self.channels),

                "-ar",
                str(self.rate),

                "-sample_fmt",
                "s16",

                wav_filepath,
            ]

            if sys.platform == "win32":

                subprocess.run(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    check=True,
                    creationflags=(
                        subprocess.CREATE_NO_WINDOW
                    ),
                )

            else:

                subprocess.run(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    check=True,
                )

            # --------------------------------------------------
            # VERIFY OUTPUT
            # --------------------------------------------------

            if not os.path.isfile(
                wav_filepath
            ):

                raise RuntimeError(
                    "FFmpeg completed but the WAV "
                    "file was not created."
                )

            self._progress(
                info,
                filename,
                100,
                start_time,
            )

            # --------------------------------------------------
            # IMPORTANT
            #
            # Do NOT delete WAV here.
            # The transcription caller still needs it.
            # --------------------------------------------------

            return (
                wav_filepath,
                self.rate,
            )

        except KeyboardInterrupt:

            remove_temp_file(
                wav_filepath
            )

            self._error(
                "Cancelling all tasks"
            )

            raise

        except Exception as exc:

            # --------------------------------------------------
            # AUTO MODE
            #
            # WAV failed, so use the original media file.
            # --------------------------------------------------

            if self.audio_source == "auto":

                remove_temp_file(
                    wav_filepath
                )

                self._error(
                    (
                        "WAV extraction failed; "
                        "falling back to media file: "
                        f"{exc}"
                    )
                )

                self._progress(
                    (
                        "WAV extraction failed; "
                        "using media file directly "
                        "for transcription"
                    ),
                    filename,
                    100,
                    None,
                )

                return (
                    media_filepath,
                    self.rate,
                )

            # --------------------------------------------------
            # NORMAL WAV MODE
            # --------------------------------------------------

            remove_temp_file(
                wav_filepath
            )

            self._error(exc)

            raise

    # ==========================================================
    # PROGRESS
    # ==========================================================

    def _progress(
        self,
        info,
        filename,
        percentage,
        start_time=None,
    ):

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
        error,
    ):

        if self.error_messages_callback:

            try:

                self.error_messages_callback(
                    error
                )

            except Exception:
                pass

        else:

            print(error)