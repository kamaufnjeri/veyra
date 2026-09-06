from __future__ import annotations

import os
import signal
import subprocess
import threading
from dataclasses import dataclass
from typing import Callable, Sequence

from .exceptions import MediaCancelledError, MediaCommandError


@dataclass(frozen=True)
class CommandResult:
    command: tuple[str, ...]
    return_code: int

    stdout: str
    stderr: str


class CommandRunner:
    """
    Safe subprocess runner.

    Features:

    - captures stdout/stderr
    - supports cancellation
    - supports callbacks
    - starts ffmpeg in its own process group
    - avoids sequential stdout/stderr readline deadlocks
    """

    def __init__(self) -> None:
        self._process: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()

    @property
    def process(self) -> subprocess.Popen[str] | None:
        return self._process

    def run(
        self,
        command: Sequence[str],
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        cancel_event: threading.Event | None = None,
        stdout_callback: Callable[[str], None] | None = None,
        stderr_callback: Callable[[str], None] | None = None,
    ) -> CommandResult:
        """
        Execute a command.

        stdout/stderr are drained concurrently so a noisy ffmpeg process
        cannot deadlock because one pipe fills.
        """

        command = tuple(str(item) for item in command)

        process_env = None

        if env is not None:
            process_env = os.environ.copy()
            process_env.update(env)

        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=process_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True,
            start_new_session=True,
        )

        with self._lock:
            self._process = process

        stdout_lines: list[str] = []
        stderr_lines: list[str] = []

        def read_stdout() -> None:
            assert process.stdout is not None

            for line in process.stdout:
                stdout_lines.append(line)

                if stdout_callback:
                    stdout_callback(line.rstrip("\n"))

        def read_stderr() -> None:
            assert process.stderr is not None

            for line in process.stderr:
                stderr_lines.append(line)

                if stderr_callback:
                    stderr_callback(line.rstrip("\n"))

        stdout_thread = threading.Thread(
            target=read_stdout,
            daemon=True,
        )

        stderr_thread = threading.Thread(
            target=read_stderr,
            daemon=True,
        )

        stdout_thread.start()
        stderr_thread.start()

        try:
            while process.poll() is None:
                if cancel_event and cancel_event.is_set():
                    self.terminate()

                    raise MediaCancelledError(
                        "Media operation was cancelled."
                    )

                process.wait(timeout=0.1)

        except subprocess.TimeoutExpired:
            pass

        while process.poll() is None:
            if cancel_event and cancel_event.is_set():
                self.terminate()

                raise MediaCancelledError(
                    "Media operation was cancelled."
                )

            try:
                process.wait(timeout=0.1)
            except subprocess.TimeoutExpired:
                continue

        stdout_thread.join()
        stderr_thread.join()

        return_code = process.returncode

        with self._lock:
            self._process = None

        result = CommandResult(
            command=command,
            return_code=return_code,
            stdout="".join(stdout_lines),
            stderr="".join(stderr_lines),
        )

        if return_code != 0:
            raise MediaCommandError(
                "Media command failed.",
                command=list(command),
                return_code=return_code,
                stdout=result.stdout,
                stderr=result.stderr,
            )

        return result

    def terminate(self) -> None:
        """Terminate the running process and its children."""

        with self._lock:
            process = self._process

        if process is None:
            return

        if process.poll() is not None:
            return

        try:
            os.killpg(
                os.getpgid(process.pid),
                signal.SIGTERM,
            )
        except ProcessLookupError:
            return

        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(
                    os.getpgid(process.pid),
                    signal.SIGKILL,
                )
            except ProcessLookupError:
                pass