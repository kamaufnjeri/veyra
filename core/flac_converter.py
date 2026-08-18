from __future__ import annotations

import os
import subprocess
import sys
import tempfile


class FLACConverter:

    def __init__(
        self,
        wav_filepath: str,
        include_before: float = 0.25,
        include_after: float = 0.25,
        error_messages_callback=None,
    ):
        self.wav_filepath = wav_filepath
        self.include_before = include_before
        self.include_after = include_after
        self.error_messages_callback = (
            error_messages_callback
        )

    # ----------------------------------------------------------
    # Find executable
    # ----------------------------------------------------------

    def which(self, program):

        def is_exe(file_path):
            return (
                os.path.isfile(file_path)
                and os.access(file_path, os.X_OK)
            )

        fpath, _ = os.path.split(program)

        if fpath:

            if is_exe(program):
                return program

        else:

            for path in os.environ.get(
                "PATH",
                ""
            ).split(os.pathsep):

                path = path.strip('"')

                exe_file = os.path.join(
                    path,
                    program,
                )

                if is_exe(exe_file):
                    return exe_file

        return None

    # ----------------------------------------------------------
    # FFmpeg
    # ----------------------------------------------------------

    def ffmpeg_check(self):

        if self.which("ffmpeg"):
            return "ffmpeg"

        if self.which("ffmpeg.exe"):
            return "ffmpeg.exe"

        return None

    # ----------------------------------------------------------
    # Convert
    # ----------------------------------------------------------

    def __call__(self, region):

        try:

            ffmpeg = self.ffmpeg_check()

            if not ffmpeg:
                raise RuntimeError(
                    "Cannot find ffmpeg executable"
                )

            if "\\" in self.wav_filepath:
                self.wav_filepath = (
                    self.wav_filepath.replace(
                        "\\",
                        "/",
                    )
                )

            if not os.path.isfile(
                self.wav_filepath
            ):
                raise FileNotFoundError(
                    f"WAV file does not exist: "
                    f"{self.wav_filepath}"
                )

            start, end = region

            start = max(
                0,
                start - self.include_before,
            )

            end += self.include_after

            temp = tempfile.NamedTemporaryFile(
                suffix=".flac",
                delete=False,
            )

            temp.close()

            command = [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-v",
                "error",
                "-ss",
                str(start),
                "-t",
                str(end - start),
                "-y",
                "-i",
                self.wav_filepath,
                "-ac",
                "1",
                "-ar",
                "48000",
                temp.name,
            ]

            if sys.platform == "win32":

                subprocess.check_output(
                    command,
                    stdin=open(
                        os.devnull
                    ),
                    creationflags=(
                        subprocess.CREATE_NO_WINDOW
                    ),
                )

            else:

                subprocess.check_output(
                    command,
                    stdin=open(
                        os.devnull
                    ),
                )

            with open(
                temp.name,
                "rb",
            ) as file:

                content = file.read()

            # Remove temporary FLAC file.
            try:
                os.unlink(temp.name)
            except OSError:
                pass

            return content

        except KeyboardInterrupt:

            self._error(
                "Cancelling all tasks"
            )

            return None

        except Exception as exc:

            self._error(exc)

            return None

    # ----------------------------------------------------------
    # Error
    # ----------------------------------------------------------

    def _error(self, error):

        if self.error_messages_callback:
            self.error_messages_callback(error)
        else:
            print(error)