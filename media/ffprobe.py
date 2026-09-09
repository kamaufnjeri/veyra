from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path
from typing import Any, Optional


class FFProbeError(Exception):
    """Raised when FFprobe fails."""

class FFProbe:
    """Small FFprobe wrapper."""

    def __init__(self, executable: str = "ffprobe") -> None:
        self.executable = executable

    def probe(self, path: str | Path) -> dict[str, Any]:
        path = Path(path)

        if not path.is_file():
            raise FileNotFoundError(f"Media file does not exist: {path}")

        command = [
            self.executable,
            "-v", "error",
            "-show_format",
            "-show_streams",
            "-of", "json",
            str(path),
        ]

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=True,
            )
        except FileNotFoundError as exc:
            raise FFProbeError(
                f"FFprobe was not found: {self.executable}"
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise FFProbeError(
                exc.stderr.strip() or "FFprobe failed."
            ) from exc

        try:
            return json.loads(result.stdout or "{}")
        except json.JSONDecodeError as exc:
            raise FFProbeError(
                f"FFprobe returned invalid JSON for {path}."
            ) from exc
