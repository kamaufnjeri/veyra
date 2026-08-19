from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time


class WavConverter:

    def __init__(
        self,
        channels: int = 1,
        rate: int = 16000,
        progress_callback=None,
        error_messages_callback=None,
    ):
        self.channels = channels
        self.rate = rate
        self.progress_callback = progress_callback
        self.error_messages_callback = (
            error_messages_callback
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
            media_filepath = media_filepath.replace(
                "\\",
                "/",
            )

        if not os.path.isfile(media_filepath):

            error = (
                f"The given file does not exist: "
                f"'{media_filepath}'"
            )

            self._error(error)
            raise FileNotFoundError(error)

        ffmpeg = self.ffmpeg_check()

        if not ffmpeg:

            error = (
                "Cannot find ffmpeg executable"
            )

            self._error(error)
            raise RuntimeError(error)

        temp = tempfile.NamedTemporaryFile(
            suffix=".wav",
            delete=False,
        )

        temp.close()

        try:

            filename = os.path.basename(
                media_filepath
            )

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

                temp.name,
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

            self._progress(
                info,
                filename,
                100,
                start_time,
            )

            return (
                temp.name,
                self.rate,
            )

        except KeyboardInterrupt:

            try:
                os.unlink(temp.name)
            except OSError:
                pass

            self._error(
                "Cancelling all tasks"
            )

            raise

        except Exception as exc:

            try:
                os.unlink(temp.name)
            except OSError:
                pass

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

    def _error(self, error):

        if self.error_messages_callback:

            try:
                self.error_messages_callback(
                    error
                )
            except Exception:
                pass

        else:
            print(error)