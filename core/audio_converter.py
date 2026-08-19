from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from typing import Optional, Tuple


class AudioConverter:
    """
    Convert audio/video input into Whisper-friendly audio.

    Default output:
        16 kHz
        mono
        PCM WAV

    Optional output:
        FLAC

    Designed for faster-whisper subtitle generation.

    Input:
        Any media file supported by FFmpeg.

    Output:
        (temporary_filepath, sample_rate)
    """

    def __init__(
        self,
        channels: int = 1,
        rate: int = 16000,
        output_format: str = "wav",
        progress_callback=None,
        error_messages_callback=None,
    ):
        self.channels = int(channels)
        self.rate = int(rate)

        self.output_format = (
            str(output_format)
            .strip()
            .lower()
        )

        if self.output_format not in {
            "wav",
            "flac",
        }:
            raise ValueError(
                "output_format must be "
                "'wav' or 'flac'"
            )

        self.progress_callback = (
            progress_callback
        )

        self.error_messages_callback = (
            error_messages_callback
        )

    # ==========================================================
    # EXECUTABLE DISCOVERY
    # ==========================================================

    @staticmethod
    def which(program: str) -> Optional[str]:

        def is_executable(
            filepath: str,
        ) -> bool:

            return (
                os.path.isfile(filepath)
                and os.access(
                    filepath,
                    os.X_OK,
                )
            )

        # Explicit path
        directory, _ = os.path.split(
            program
        )

        if directory:

            if is_executable(program):
                return program

            return None

        # PATH lookup
        for path in os.environ.get(
            "PATH",
            "",
        ).split(os.pathsep):

            path = path.strip('"')

            if not path:
                continue

            candidate = os.path.join(
                path,
                program,
            )

            if is_executable(candidate):
                return candidate

        return None

    # ==========================================================
    # FFMPEG
    # ==========================================================

    def ffmpeg_check(self) -> Optional[str]:

        return (
            self.which("ffmpeg")
            or self.which("ffmpeg.exe")
        )

    # ==========================================================
    # FFPROBE
    # ==========================================================

    def ffprobe_check(self) -> Optional[str]:

        return (
            self.which("ffprobe")
            or self.which("ffprobe.exe")
        )

    # ==========================================================
    # ERROR
    # ==========================================================

    def _error(
        self,
        error,
    ) -> None:

        if self.error_messages_callback:

            try:
                self.error_messages_callback(
                    error
                )
                return

            except Exception:
                pass

        print(error)

    # ==========================================================
    # PROGRESS
    # ==========================================================

    def _progress(
        self,
        info: str,
        filename: str,
        percentage: int,
        start_time=None,
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
    # FORMAT
    # ==========================================================

    @property
    def extension(self) -> str:

        return (
            ".wav"
            if self.output_format == "wav"
            else ".flac"
        )

    # ==========================================================
    # FFMPEG CODEC
    # ==========================================================

    def _codec_arguments(self):

        if self.output_format == "wav":

            return [
                "-c:a",
                "pcm_s16le",
            ]

        # FLAC is lossless.
        return [
            "-c:a",
            "flac",
            "-compression_level",
            "5",
        ]

    # ==========================================================
    # CONVERT
    # ==========================================================

    def __call__(
        self,
        media_filepath: str,
    ) -> Optional[
        Tuple[str, int]
    ]:

        media_filepath = os.path.abspath(
            os.path.normpath(
                media_filepath
            )
        )

        if not os.path.isfile(
            media_filepath
        ):

            error = FileNotFoundError(
                "The given file does not exist: "
                f"'{media_filepath}'"
            )

            self._error(error)

            return None

        ffmpeg = self.ffmpeg_check()

        if not ffmpeg:

            error = RuntimeError(
                "Cannot find ffmpeg executable. "
                "FFmpeg must be installed and "
                "available in PATH."
            )

            self._error(error)

            return None

        ffprobe = self.ffprobe_check()

        if not ffprobe:

            error = RuntimeError(
                "Cannot find ffprobe executable. "
                "FFprobe must be installed and "
                "available in PATH."
            )

            self._error(error)

            return None

        filename = os.path.basename(
            media_filepath
        )

        start_time = time.time()

        temp_filepath = None

        try:

            # ==================================================
            # 1. GET MEDIA DURATION
            # ==================================================

            ffprobe_command = [
                ffprobe,
                "-hide_banner",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default="
                "noprint_wrappers=1:"
                "nokey=1",
                media_filepath,
            ]

            if sys.platform == "win32":

                result = subprocess.run(
                    ffprobe_command,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=True,
                    creationflags=(
                        subprocess.CREATE_NO_WINDOW
                    ),
                )

            else:

                result = subprocess.run(
                    ffprobe_command,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=True,
                )

            duration_text = (
                result.stdout.strip()
            )

            try:
                total_duration = float(
                    duration_text
                )

            except ValueError:

                total_duration = 0.0

            # ==================================================
            # 2. CREATE TEMPORARY FILE
            # ==================================================

            temp = tempfile.NamedTemporaryFile(
                suffix=self.extension,
                delete=False,
            )

            temp_filepath = temp.name
            temp.close()

            # ==================================================
            # 3. BUILD FFMPEG COMMAND
            # ==================================================

            command = [
                ffmpeg,

                "-hide_banner",
                "-loglevel",
                "error",

                # Never ask questions.
                "-nostdin",

                "-y",

                "-i",
                media_filepath,

                # Whisper-friendly audio.
                "-vn",

                # Mono.
                "-ac",
                str(self.channels),

                # Whisper's native sampling rate.
                "-ar",
                str(self.rate),

                *self._codec_arguments(),

                # Progress output.
                "-progress",
                "pipe:1",

                "-nostats",

                temp_filepath,
            ]

            display_format = (
                self.output_format.upper()
            )

            info = (
                f"Converting '{filename}' "
                f"to {display_format} audio"
            )

            self._progress(
                info,
                filename,
                0,
                start_time,
            )

            # ==================================================
            # 4. START FFMPEG
            # ==================================================

            creationflags = 0

            if sys.platform == "win32":

                creationflags = (
                    subprocess.CREATE_NO_WINDOW
                )

            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=creationflags,
            )

            # ==================================================
            # 5. READ PROGRESS
            # ==================================================

            if process.stdout is not None:

                for raw_line in process.stdout:

                    line = raw_line.decode(
                        "utf-8",
                        errors="replace",
                    ).strip()

                    if not line:
                        continue

                    # FFmpeg emits:
                    #
                    # out_time_us=1234567
                    #
                    if line.startswith(
                        "out_time_us="
                    ):

                        try:

                            microseconds = int(
                                line.split(
                                    "=",
                                    1,
                                )[1]
                            )

                            current_seconds = (
                                microseconds
                                / 1_000_000.0
                            )

                            if (
                                total_duration > 0
                                and current_seconds >= 0
                            ):

                                percentage = int(
                                    (
                                        current_seconds
                                        / total_duration
                                    )
                                    * 100
                                )

                                self._progress(
                                    info,
                                    filename,
                                    min(
                                        percentage,
                                        99,
                                    ),
                                    start_time,
                                )

                        except (
                            ValueError,
                            IndexError,
                        ):
                            pass

            # ==================================================
            # 6. WAIT
            # ==================================================

            stdout, stderr = (
                process.communicate()
            )

            if process.returncode != 0:

                error_text = (
                    stderr.decode(
                        "utf-8",
                        errors="replace",
                    ).strip()
                )

                raise RuntimeError(
                    "FFmpeg audio conversion failed"
                    + (
                        f": {error_text}"
                        if error_text
                        else ""
                    )
                )

            # ==================================================
            # 7. VERIFY OUTPUT
            # ==================================================

            if not temp_filepath:

                raise RuntimeError(
                    "FFmpeg did not produce "
                    "an output path."
                )

            if not os.path.isfile(
                temp_filepath
            ):

                raise RuntimeError(
                    "FFmpeg completed but the "
                    "audio file was not created."
                )

            output_size = os.path.getsize(
                temp_filepath
            )

            if output_size <= 0:

                raise RuntimeError(
                    "FFmpeg created an empty "
                    "audio file."
                )

            # ==================================================
            # 8. COMPLETE
            # ==================================================

            self._progress(
                "Audio conversion complete",
                filename,
                100,
                start_time,
            )

            return (
                temp_filepath,
                self.rate,
            )

        except KeyboardInterrupt:

            if temp_filepath:

                try:
                    os.unlink(
                        temp_filepath
                    )
                except OSError:
                    pass

            self._error(
                "Cancelling all tasks"
            )

            return None

        except Exception as exc:

            if temp_filepath:

                try:
                    os.unlink(
                        temp_filepath
                    )
                except OSError:
                    pass

            self._error(exc)

            return None

    # ==========================================================
    # CLEANUP
    # ==========================================================

    @staticmethod
    def cleanup(
        filepath: Optional[str],
    ) -> None:

        if not filepath:
            return

        try:

            if os.path.isfile(
                filepath
            ):

                os.unlink(
                    filepath
                )

        except OSError:
            pass