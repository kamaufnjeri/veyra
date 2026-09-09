from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path
from typing import Any, Optional


# ==============================================================
# ERRORS
# ==============================================================


class FFProbeError(Exception):
    """Raised when FFprobe fails."""


# ==============================================================
# FFPROBE
# ==============================================================


class FFProbe:
    """
    Small FFprobe wrapper.

    Responsibilities:

        - Execute FFprobe
        - Return parsed probe data
        - Read media duration
    """

    def __init__(
        self,
        executable: str = "ffprobe",
    ) -> None:

        if not executable:
            raise ValueError(
                "FFprobe executable cannot be empty."
            )

        self.executable = str(executable)

    # ==========================================================
    # PROBE
    # ==========================================================

    def probe(
        self,
        path: str | Path,
    ) -> dict[str, Any]:

        path = Path(path).expanduser()

        if not path.exists():
            raise FileNotFoundError(
                f"Media file does not exist: {path}"
            )

        if not path.is_file():
            raise ValueError(
                f"Media path is not a file: {path}"
            )

        if not path.is_file():
            raise FileNotFoundError(
                f"Media file does not exist: {path}"
            )

        command = [
            self.executable,

            "-v",
            "error",

            "-show_format",
            "-show_streams",

            "-of",
            "json",

            str(path),
        ]

        try:

            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=True,
            )

        except FileNotFoundError as exc:

            raise FFProbeError(
                f"FFprobe was not found: "
                f"{self.executable}"
            ) from exc

        except PermissionError as exc:

            raise FFProbeError(
                f"FFprobe executable is not executable: "
                f"{self.executable}"
            ) from exc

        except subprocess.CalledProcessError as exc:

            diagnostic = (
                exc.stderr.strip()
                or exc.stdout.strip()
                or "FFprobe failed."
            )

            raise FFProbeError(
                diagnostic
            ) from exc

        except OSError as exc:

            raise FFProbeError(
                f"Unable to start FFprobe: {exc}"
            ) from exc

        try:

            data = json.loads(
                result.stdout or "{}"
            )

        except json.JSONDecodeError as exc:

            raise FFProbeError(
                f"FFprobe returned invalid JSON "
                f"for {path}."
            ) from exc

        if not isinstance(data, dict):
            raise FFProbeError(
                f"FFprobe returned unexpected data "
                f"for {path}."
            )

        return data

    # ==========================================================
    # DURATION
    # ==========================================================

    def duration(
        self,
        path: str | Path,
    ) -> float:

        data = self.probe(path)

        # ------------------------------------------------------
        # FORMAT DURATION
        # ------------------------------------------------------

        format_data = data.get("format") or {}

        duration = self._number(
            format_data.get("duration")
        )

        if duration is not None and duration >= 0:
            return duration

        # ------------------------------------------------------
        # STREAM DURATION FALLBACK
        # ------------------------------------------------------

        durations = []

        for stream in data.get("streams", []):

            if not isinstance(stream, dict):
                continue

            value = self._number(
                stream.get("duration")
            )

            if value is not None and value >= 0:
                durations.append(value)

        if durations:
            return max(durations)

        raise FFProbeError(
            f"Unable to determine media duration: {path}"
        )

    # ==========================================================
    # HELPERS
    # ==========================================================

    @staticmethod
    def _number(
        value: Any,
    ) -> Optional[float]:

        try:

            number = float(value)

            if not math.isfinite(number):
                return None

            return number

        except (
            TypeError,
            ValueError,
        ):
            return None
