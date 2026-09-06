from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path


# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent

# Change this if your main application file has a different name.
MAIN_FILE = PROJECT_ROOT / "main.py"

# Directories to watch.
WATCH_DIRECTORIES = [
    PROJECT_ROOT / "cli",
    PROJECT_ROOT / "core",
    PROJECT_ROOT / "services",
    PROJECT_ROOT / "jobs",
]

# File types that trigger a restart.
WATCH_EXTENSIONS = {
    ".py",
}

# Files/directories to ignore.
IGNORED_NAMES = {
    "__pycache__",
    ".git",
    ".venv",
    "venv",
    "env",
}

RESTART_DELAY = 0.5


# ============================================================
# FILE WATCHING
# ============================================================

def get_python_files() -> list[Path]:
    files: list[Path] = []

    for directory in WATCH_DIRECTORIES:
        if not directory.exists():
            continue

        for path in directory.rglob("*"):
            if not path.is_file():
                continue

            if path.suffix.lower() not in WATCH_EXTENSIONS:
                continue

            if any(
                ignored in path.parts
                for ignored in IGNORED_NAMES
            ):
                continue

            files.append(path)

    # Also watch the main application file.
    if MAIN_FILE.exists():
        files.append(MAIN_FILE)

    return files


def get_file_state() -> dict[Path, int]:
    state: dict[Path, int] = {}

    for path in get_python_files():
        try:
            state[path] = path.stat().st_mtime_ns
        except OSError:
            pass

    return state


# ============================================================
# APPLICATION
# ============================================================

def start_application() -> subprocess.Popen:
    print()
    print("=" * 60)
    print("Starting Veyra...")
    print("=" * 60)
    print()

    return subprocess.Popen(
        [
            sys.executable,
            str(MAIN_FILE),
        ],
        cwd=str(PROJECT_ROOT),
    )


def stop_application(
    process: subprocess.Popen,
) -> None:
    if process.poll() is not None:
        return

    print()
    print("Stopping Veyra...")

    process.terminate()

    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


# ============================================================
# MAIN DEVELOPMENT LOOP
# ============================================================

def main() -> int:
    if not MAIN_FILE.exists():
        print(
            f"ERROR: Could not find main application file:"
        )
        print(
            f"       {MAIN_FILE}"
        )
        print()
        print(
            "Change MAIN_FILE in dev.py to point to your"
        )
        print(
            "actual Veyra entry point."
        )
        return 1

    print()
    print("=" * 60)
    print("VEYRA DEVELOPMENT MODE")
    print("=" * 60)
    print()
    print("Watching Python files for changes.")
    print("Save a file and Veyra will restart automatically.")
    print()
    print("Press Ctrl+C here to stop development mode.")
    print()

    process = start_application()

    previous_state = get_file_state()

    try:
        while True:
            time.sleep(RESTART_DELAY)

            current_state = get_file_state()

            if current_state != previous_state:
                print()
                print("-" * 60)
                print("Python file changed.")
                print("Reloading Veyra...")
                print("-" * 60)

                stop_application(process)

                # Give the filesystem a moment to finish writing.
                time.sleep(RESTART_DELAY)

                process = start_application()

                previous_state = get_file_state()

            else:
                # If Veyra was closed manually, restart it.
                if process.poll() is not None:
                    print()
                    print("Veyra was closed.")
                    print("Restarting...")

                    time.sleep(RESTART_DELAY)

                    process = start_application()

                    previous_state = get_file_state()

    except KeyboardInterrupt:
        print()
        print("Stopping development mode...")

        stop_application(process)

        print("Veyra development mode stopped.")

        return 0


if __name__ == "__main__":
    sys.exit(main())

