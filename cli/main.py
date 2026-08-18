from __future__ import annotations

import argparse
import os
import signal
import sys
import time
from datetime import timedelta

from jobs.processor import JobProcessor


# ==============================================================
# GLOBAL CANCELLATION
# ==============================================================

cancelled = False
processor_instance = None


# ==============================================================
# CTRL+C HANDLER
# ==============================================================

def handle_cancel(signum=None, frame=None):
    """
    Handle Ctrl+C.

    First Ctrl+C:
        - Marks the application as cancelled.
        - Tells JobProcessor to stop.

    Second Ctrl+C:
        - Immediately terminates the process.
    """

    global cancelled

    # ----------------------------------------------------------
    # Second Ctrl+C -> force kill
    # ----------------------------------------------------------

    if cancelled:
        print(
            "\n\nForce stopping Veyra...",
            flush=True,
        )

        os._exit(130)

    # ----------------------------------------------------------
    # First Ctrl+C
    # ----------------------------------------------------------

    cancelled = True

    print(
        "\n\nCtrl+C received.",
        flush=True,
    )

    print(
        "Cancelling Veyra...",
        flush=True,
    )

    processor = processor_instance

    if processor is not None:

        try:

            cancel_method = getattr(
                processor,
                "cancel",
                None,
            )

            if callable(cancel_method):
                cancel_method()

        except Exception as exc:

            print(
                f"Cancellation warning: {exc}",
                file=sys.stderr,
                flush=True,
            )


# ==============================================================
# INSTALL SIGNAL HANDLERS
# ==============================================================

def install_signal_handlers():
    """
    Install Ctrl+C / SIGINT handler.

    Ctrl+C sends SIGINT on normal terminals.
    """

    signal.signal(
        signal.SIGINT,
        handle_cancel,
    )

    # ----------------------------------------------------------
    # SIGTERM is useful when the process is terminated externally.
    # ----------------------------------------------------------

    if hasattr(signal, "SIGTERM"):

        signal.signal(
            signal.SIGTERM,
            handle_cancel,
        )


# ==============================================================
# PROGRESS
# ==============================================================

def show_progress(
    info,
    media_file_display_name,
    progress,
    start_time=None,
):
    """
    Display CLI processing progress.
    """

    if cancelled:
        return

    progress = max(
        0,
        min(
            100,
            int(progress),
        ),
    )

    if start_time is None:
        start_time = time.time()

    elapsed_time = (
        time.time() - start_time
    )

    if progress > 0:

        eta_seconds = (
            elapsed_time / progress
        ) * (
            100 - progress
        )

    else:

        eta_seconds = 0

    eta = timedelta(
        seconds=int(eta_seconds)
    )

    elapsed = timedelta(
        seconds=int(elapsed_time)
    )

    print(
        f"\r"
        f"[{progress:3d}%] "
        f"{media_file_display_name} - "
        f"{info} | "
        f"Elapsed: {elapsed} | "
        f"ETA: {eta}",
        end="",
        flush=True,
    )

    if progress >= 100:
        print(
            flush=True
        )


# ==============================================================
# OVERWRITE
# ==============================================================

def ask_overwrite(filepath: str) -> bool:
    """
    Ask the user whether an existing subtitle should be overwritten.
    """

    if cancelled:
        return False

    while True:

        print()

        print(
            "Subtitle file already exists:"
        )

        print(
            f"  {filepath}"
        )

        try:

            answer = input(
                "Overwrite it? [y]es / [n]o: "
            ).strip().lower()

        except KeyboardInterrupt:

            handle_cancel()

            return False

        if answer in (
            "y",
            "yes",
        ):

            return True

        if answer in (
            "n",
            "no",
        ):

            return False

        print(
            "Please enter 'y' or 'n'."
        )


# ==============================================================
# ERRORS
# ==============================================================

def show_error_messages(message):
    """
    Display an error message in the CLI.
    """

    if cancelled:
        return

    print(
        f"\nERROR: {message}",
        file=sys.stderr,
        flush=True,
    )


# ==============================================================
# MAIN
# ==============================================================

def main():
    """
    Main Veyra CLI entry point.
    """

    global processor_instance
    global cancelled

    cancelled = False

    # ----------------------------------------------------------
    # Install Ctrl+C handler BEFORE doing any work.
    # ----------------------------------------------------------

    install_signal_handlers()

    # ==========================================================
    # ARGUMENT PARSER
    # ==========================================================

    parser = argparse.ArgumentParser(
        description="Veyra subtitle generator"
    )

    # ----------------------------------------------------------
    # Input files
    # ----------------------------------------------------------

    parser.add_argument(
        "files",
        nargs="+",
        help="Media files to process",
    )

    # ----------------------------------------------------------
    # Source language
    # ----------------------------------------------------------

    parser.add_argument(
        "-s",
        "--source",
        "--source-language",
        dest="source",
        default="en",
        help="Source language (default: en)",
    )

    # ----------------------------------------------------------
    # Target language
    # ----------------------------------------------------------

    parser.add_argument(
        "-t",
        "--target",
        "--target-language",
        dest="target",
        default=None,
        help="Target translation language",
    )

    # ----------------------------------------------------------
    # Subtitle format
    # ----------------------------------------------------------

    parser.add_argument(
        "-f",
        "--format",
        default="srt",
        choices=[
            "srt",
            "vtt",
            "json",
            "raw",
        ],
        help="Subtitle format",
    )

    args = parser.parse_args()

    # ==========================================================
    # VALIDATE FILES
    # ==========================================================

    valid_files = []

    for filepath in args.files:

        filepath = os.path.abspath(
            filepath
        )

        if not os.path.isfile(filepath):

            print(
                f"File not found: {filepath}",
                file=sys.stderr,
            )

            continue

        valid_files.append(
            filepath
        )

    if not valid_files:

        print(
            "No valid media files were supplied.",
            file=sys.stderr,
        )

        return 1

    # ==========================================================
    # START TIME
    # ==========================================================

    start_time = time.time()

    # ==========================================================
    # PROGRESS CALLBACK
    # ==========================================================

    def progress_callback(
        info,
        filename,
        percentage,
        *_,
    ):

        show_progress(
            info,
            filename,
            percentage,
            start_time,
        )

    # ==========================================================
    # CREATE PROCESSOR
    # ==========================================================

    try:

        processor = JobProcessor(
            source_language=args.source,
            target_language=args.target,
            subtitle_format=args.format,
            progress_callback=progress_callback,
            error_callback=show_error_messages,
            overwrite_callback=ask_overwrite,
        )

        # Store globally so Ctrl+C can reach it.
        processor_instance = processor

    except KeyboardInterrupt:

        handle_cancel()

        return 130

    except Exception as error:

        show_error_messages(
            str(error)
        )

        return 1

    # ==========================================================
    # PROCESS FILES
    # ==========================================================

    try:

        results = processor.process_files(
            valid_files
        )

    except KeyboardInterrupt:

        handle_cancel(
            processor
        )

        return 130

    except Exception as error:

        if cancelled:
            return 130

        show_error_messages(
            str(error)
        )

        return 1

    finally:

        # ------------------------------------------------------
        # Give processor a chance to clean up.
        # ------------------------------------------------------

        if cancelled:

            try:

                cleanup = getattr(
                    processor,
                    "cleanup",
                    None,
                )

                if callable(cleanup):
                    cleanup()

            except Exception:
                pass

    # ==========================================================
    # CHECK CANCELLATION
    # ==========================================================

    if cancelled:
        return 130

    # ==========================================================
    # DISPLAY RESULTS
    # ==========================================================

    print(
        "\n",
        flush=True,
    )

    for result in results:

        if cancelled:
            return 130

        print(
            f"Media: "
            f"{result['media']}"
        )

        print(
            f"Source subtitle: "
            f"{result['source_subtitle']}"
        )

        if result.get(
            "translated_subtitle"
        ):

            print(
                f"Translated subtitle: "
                f"{result['translated_subtitle']}"
            )

        print()

    return 0


# ==============================================================
# ENTRY POINT
# ==============================================================

if __name__ == "__main__":

    try:

        exit_code = main()

        sys.exit(
            exit_code
        )

    except KeyboardInterrupt:

        # ------------------------------------------------------
        # This is a final safety net.
        # ------------------------------------------------------

        print(
            "\n\nVeyra cancelled.",
            flush=True,
        )

        sys.exit(130)