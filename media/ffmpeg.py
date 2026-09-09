from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Callable, Sequence
import threading


from .temp import create_temp_file, remove_temp_file


# ============================================================
# ERRORS
# ============================================================


class FFmpegError(Exception):
    """Raised when FFmpeg fails."""


class FFmpegCancelled(FFmpegError):
    """Raised when an FFmpeg operation is cancelled."""


# ============================================================
# CALLBACKS
# ============================================================


ProgressCallback = Callable[[float], None]
CancellationCallback = Callable[[], bool]


# ============================================================
# FFMPEG
# ============================================================


class FFmpeg:
    """
    Lightweight FFmpeg process wrapper.

    FFprobe is intentionally handled separately by FFProbe.

    This class is responsible only for:

        - FFmpeg execution
        - validation
        - progress
        - cancellation
        - temporary files
        - atomic replacement
        - cleanup

    Progress is read from FFmpeg's machine-readable:

        -progress pipe:1

    output rather than parsing human-readable FFmpeg status lines.
    """

    MAX_OUTPUT_LINES = 100

    def __init__(
        self,
        *,
        ffmpeg: str = "ffmpeg",
        progress_callback: ProgressCallback | None = None,
        cancellation_callback: CancellationCallback | None = None,
    ) -> None:

        if not ffmpeg:
            raise ValueError(
                "ffmpeg executable cannot be empty."
            )

        self.ffmpeg = str(ffmpeg)

        self.progress_callback = progress_callback

        self.cancellation_callback = (
            cancellation_callback
        )

        self._process: subprocess.Popen[str] | None = None

        self._temporary_files: set[Path] = set()

    # ========================================================
    # VALIDATION
    # ========================================================

    @staticmethod
    def validate_input(
        path: str | Path,
    ) -> Path:

        path = Path(path).expanduser()

        if not path.exists():
            raise FileNotFoundError(
                f"Input does not exist: {path}"
            )

        if not path.is_file():
            raise ValueError(
                f"Input is not a file: {path}"
            )

        if not os.access(path, os.R_OK):
            raise PermissionError(
                f"Input is not readable: {path}"
            )

        return path

    @staticmethod
    def validate_output(
        source: str | Path | None,
        output: str | Path,
        overwrite: bool = False,
    ) -> Path:

        output = Path(output).expanduser()

        if not str(output):
            raise ValueError(
                "Output path cannot be empty."
            )

        if source is not None:
            source = Path(source).expanduser()

            try:
                if output.resolve() == source.resolve():
                    raise ValueError(
                        "Output cannot be the same as input."
                    )
            except OSError:
                if output.absolute() == source.absolute():
                    raise ValueError(
                        "Output cannot be the same as input."
                    )

        output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        if not output.parent.is_dir():
            raise NotADirectoryError(
                f"Output parent is not a directory: "
                f"{output.parent}"
            )

        if not os.access(
            output.parent,
            os.W_OK,
        ):
            raise PermissionError(
                f"Output directory is not writable: "
                f"{output.parent}"
            )

        if output.exists():

            if output.is_dir():
                raise IsADirectoryError(
                    f"Output path is a directory: {output}"
                )

            if not overwrite:
                raise FileExistsError(
                    f"Output already exists: {output}"
                )

        return output

    # ========================================================
    # TEMPORARY FILES
    # ========================================================

    def temporary_path(
        self,
        suffix: str = "",
    ) -> Path:

        if suffix and not suffix.startswith("."):
            suffix = f".{suffix}"

        path = Path(
            create_temp_file(
                suffix=suffix,
                prefix="veyra_",
                delete=False,
            )
        )

        # FFmpeg needs to create the file itself.
        try:
            path.unlink()
        except FileNotFoundError:
            pass

        self._temporary_files.add(path)

        return path

    # ========================================================
    # COMMAND
    # ========================================================

    @staticmethod
    def _prepare_command(
        command: Sequence[str],
    ) -> list[str]:

        if not command:
            raise ValueError(
                "FFmpeg command cannot be empty."
            )

        command = [
            str(part)
            for part in command
        ]

        if not command[0]:
            raise ValueError(
                "FFmpeg executable cannot be empty."
            )

        return command

    @staticmethod
    def _add_progress_output(
        command: Sequence[str],
    ) -> list[str]:

        command = [
            str(part)
            for part in command
        ]

        if "-progress" in command:
            return command

        return [
            command[0],
            "-nostats",
            "-progress",
            "pipe:1",
            *command[1:],
        ]


    # ========================================================
    # RUN
    # ========================================================

    def run(
        self,
        command: Sequence[str],
        *,
        message: str | None = None,
        duration: float | None = None,
    ) -> None:
        """
        Execute FFmpeg.

        When duration is supplied, progress is calculated from
        FFmpeg's machine-readable progress output.

        The callback receives a value between:

            0.0 and 1.0
        """

        command = self._prepare_command(command)

        self._check_cancelled()

        if message:
            self._emit_message(message)

        self._emit_progress(0.0)

        started = time.monotonic()

        process: subprocess.Popen[str] | None = None

        output_lines: list[str] = []

        last_progress = 0.0

        try:

            command = self._add_progress_output(
                command
            )

            try:
                process = subprocess.Popen(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                )

            except FileNotFoundError as exc:
                raise FFmpegError(
                    f"FFmpeg was not found: {command[0]}"
                ) from exc

            except PermissionError as exc:
                raise FFmpegError(
                    f"FFmpeg executable is not executable: "
                    f"{command[0]}"
                ) from exc

            except OSError as exc:
                raise FFmpegError(
                    f"Unable to start FFmpeg: {exc}"
                ) from exc

            self._process = process

            stdout = process.stdout
            stderr = process.stderr

            if stdout is None:
                raise FFmpegError(
                    "FFmpeg did not provide progress output."
                )

            if stderr is None:
                raise FFmpegError(
                    "FFmpeg did not provide diagnostic output."
                )

            # ------------------------------------------------
            # IMPORTANT
            # ------------------------------------------------
            #
            # stdout contains:
            #
            #     out_time_ms=...
            #     speed=...
            #     progress=continue
            #
            # stderr contains normal FFmpeg diagnostics.
            #
            # We read both streams concurrently so that neither
            # pipe can fill up and block FFmpeg.
            # ------------------------------------------------

            stderr_lines: list[str] = []

            stderr_thread = threading.Thread(

                target=self._collect_stderr,
                args=(
                    stderr,
                    stderr_lines,
                ),
                daemon=True,
            )

            stderr_thread.start()

            for raw_line in stdout:

                self._check_cancelled(
                    terminate=True
                )

                line = raw_line.strip()

                if not line:
                    continue

                progress = self._parse_machine_progress(
                    line,
                    duration,
                )

                if progress is not None:

                    if progress >= last_progress:
                        last_progress = progress

                        self._emit_progress(
                            progress
                        )

            return_code = process.wait()

            stderr_thread.join(
                timeout=2.0
            )

            elapsed = (
                time.monotonic() - started
            )

            if return_code != 0:

                diagnostic = "\n".join(
                    stderr_lines[
                        -self.MAX_OUTPUT_LINES:
                    ]
                )

                raise FFmpegError(
                    self._format_error(
                        command,
                        return_code,
                        diagnostic,
                        elapsed,
                    )
                )

            # FFmpeg completed successfully.
            #
            # Always force the final progress value to 1.0.
            if last_progress < 1.0:
                self._emit_progress(1.0)

        except FFmpegCancelled:
            raise

        except KeyboardInterrupt as exc:
            self.cancel()

            raise FFmpegCancelled(
                "FFmpeg operation was cancelled by user."
            ) from exc

        finally:

            self._process = None

            if process is not None:
                self._close_process_pipes(
                    process
                )

    # ========================================================
    # STDERR
    # ========================================================

    @staticmethod
    def _collect_stderr(
        stderr,
        output_lines: list[str],
    ) -> None:
        """
        Collect FFmpeg diagnostics without blocking the main
        progress-reading loop.
        """

        try:

            for raw_line in stderr:

                line = raw_line.rstrip()

                if not line:
                    continue

                output_lines.append(line)

                if (
                    len(output_lines)
                    > FFmpeg.MAX_OUTPUT_LINES
                ):
                    del output_lines[
                        :-FFmpeg.MAX_OUTPUT_LINES
                    ]

        except (
            OSError,
            ValueError,
        ):
            pass

    # ========================================================
    # PROGRESS
    # ========================================================

    @staticmethod
    def _parse_machine_progress(
        line: str,
        duration: float | None,
    ) -> float | None:

        if duration is None or duration <= 0:
            return None

        if not line.startswith("out_time_us="):
            return None

        try:
            microseconds = int(
                line.split("=", 1)[1].strip()
            )
        except ValueError:
            return None

        elapsed = microseconds / 1_000_000

        return max(
            0.0,
            min(
                1.0,
                elapsed / duration,
            ),
        )


    @staticmethod
    def _parse_timestamp(
        value: str,
    ) -> float | None:
        """
        Parse:

            HH:MM:SS.microseconds
        """

        parts = value.split(":")

        if len(parts) != 3:
            return None

        try:

            hours = float(parts[0])
            minutes = float(parts[1])
            seconds = float(parts[2])

        except ValueError:
            return None

        return (
            hours * 3600
            + minutes * 60
            + seconds
        )

    def _emit_progress(
        self,
        progress: float,
    ) -> None:

        callback = self.progress_callback

        if callback is None:
            return

        try:
            callback(
                max(
                    0.0,
                    min(
                        1.0,
                        float(progress),
                    ),
                )
            )
        except Exception:
            pass

    def _emit_message(
        self,
        message: str,
    ) -> None:

        _ = message

    # ========================================================
    # CANCELLATION
    # ========================================================

    def _is_cancelled(self) -> bool:

        callback = self.cancellation_callback

        if callback is None:
            return False

        try:
            return bool(callback())
        except Exception:
            return False

    def _check_cancelled(
        self,
        *,
        terminate: bool = False,
    ) -> None:

        if not self._is_cancelled():
            return

        if terminate:
            self.cancel()

        raise FFmpegCancelled(
            "FFmpeg operation was cancelled."
        )

    def cancel(self) -> None:

        process = self._process

        if process is None:
            return

        if process.poll() is not None:
            return

        try:

            process.terminate()

            try:
                process.wait(
                    timeout=3.0
                )

            except subprocess.TimeoutExpired:

                try:
                    process.kill()
                except OSError:
                    pass

                try:
                    process.wait(
                        timeout=3.0
                    )
                except subprocess.TimeoutExpired:
                    pass

        except OSError:
            pass

        finally:

            self._close_process_pipes(
                process
            )

    @staticmethod
    def _close_process_pipes(
        process: subprocess.Popen[str],
    ) -> None:

        for pipe in (
            process.stdout,
            process.stdin,
            process.stderr,
        ):
            if pipe is None:
                continue

            try:
                pipe.close()
            except (
                OSError,
                ValueError,
            ):
                pass

    # ========================================================
    # ATOMIC OUTPUT
    # ========================================================

    def atomic_replace(
        self,
        source: str | Path,
        destination: str | Path,
    ) -> None:

        source = Path(source)
        destination = Path(destination)

        if not source.exists():
            raise FileNotFoundError(
                f"Temporary output does not exist: {source}"
            )

        if not source.is_file():
            raise ValueError(
                f"Temporary output is not a file: {source}"
            )

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        os.replace(
            source,
            destination,
        )

        self._temporary_files.discard(
            source
        )

    # ========================================================
    # CLEANUP
    # ========================================================

    def cleanup(self) -> None:

        if self._process is not None:
            self.cancel()

        for path in tuple(
            self._temporary_files
        ):
            remove_temp_file(
                str(path)
            )

        self._temporary_files.clear()

    # ========================================================
    # ERROR
    # ========================================================

    @staticmethod
    def _format_error(
        command: Sequence[str],
        return_code: int,
        output: str,
        elapsed: float,
    ) -> str:

        command_text = " ".join(
            str(part)
            for part in command
        )

        diagnostic = (
            output.strip()
            or "No diagnostic output."
        )

        return (
            f"FFmpeg failed "
            f"(exit code {return_code}) "
            f"after {elapsed:.2f}s.\n\n"
            f"Command:\n"
            f"{command_text}\n\n"
            f"Output:\n"
            f"{diagnostic}"
        )
