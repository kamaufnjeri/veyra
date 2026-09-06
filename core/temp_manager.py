from __future__ import annotations

import atexit
import os
import shutil
import tempfile
from typing import Optional


# ==============================================================
# VEYRA TEMP DIRECTORY
# ==============================================================

APP_TEMP_DIR = "/tmp/veyra"


# ==============================================================
# STARTUP CLEANUP
# ==============================================================

def cleanup_veyra_temp() -> None:
    """
    Delete all Veyra temporary files.

    Safe to call multiple times.
    """

    if not os.path.isdir(APP_TEMP_DIR):
        return

    try:

        shutil.rmtree(
            APP_TEMP_DIR,
            ignore_errors=True,
        )

    except Exception as exc:

        print(
            f"Failed to clean Veyra temporary files: {exc}"
        )


def initialize_veyra_temp() -> str:
    """
    Clean old temporary files from previous sessions
    and create a fresh Veyra temporary directory.
    """

    # Remove leftovers from a previous crash/session.
    cleanup_veyra_temp()

    os.makedirs(
        APP_TEMP_DIR,
        exist_ok=True,
    )

    return APP_TEMP_DIR


# ==============================================================
# CREATE TEMP FILE
# ==============================================================

def create_temp_file(
    suffix: str = "",
    prefix: str = "veyra_",
    delete: bool = False,
) -> str:
    """
    Create a temporary file inside /tmp/veyra.

    Returns the filepath.
    """

    os.makedirs(
        APP_TEMP_DIR,
        exist_ok=True,
    )

    temp_file = tempfile.NamedTemporaryFile(
        dir=APP_TEMP_DIR,
        prefix=prefix,
        suffix=suffix,
        delete=delete,
    )

    filepath = temp_file.name

    # Close it immediately so other libraries can use it.
    temp_file.close()

    return filepath


# ==============================================================
# CREATE TEMP DIRECTORY
# ==============================================================

def create_temp_directory(
    prefix: str = "veyra_",
) -> str:
    """
    Create a temporary directory inside /tmp/veyra.
    """

    os.makedirs(
        APP_TEMP_DIR,
        exist_ok=True,
    )

    return tempfile.mkdtemp(
        dir=APP_TEMP_DIR,
        prefix=prefix,
    )


# ==============================================================
# DELETE SPECIFIC TEMP FILE
# ==============================================================

def remove_temp_file(
    filepath: Optional[str],
) -> None:
    """
    Safely remove a temporary file.
    """

    if not filepath:
        return

    try:

        if os.path.isfile(filepath):

            os.remove(filepath)

    except OSError:

        pass


# ==============================================================
# APPLICATION EXIT CLEANUP
# ==============================================================

atexit.register(
    cleanup_veyra_temp
)


# ==============================================================
# INITIALIZE ON IMPORT
# ==============================================================

initialize_veyra_temp()