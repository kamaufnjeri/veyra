from __future__ import annotations

import os
import sys

from jobs.media_processor import MediaJobProcessor


URL = "https://www.youtube.com/watch?v=XHTecPextHY"
OUTPUT = "./downloads"


def progress_callback(
    info,
    filename,
    percentage,
    downloaded,
    speed,
    eta,
    **kwargs,
):
    print(
        f"[PROGRESS] "
        f"{float(percentage):6.2f}% | "
        f"{str(downloaded):>12} | "
        f"{str(speed):>12} | "
        f"ETA {str(eta):>8} | "
        f"{info} | "
        f"{filename}",
        flush=True,
    )


def error_callback(error):
    print(
        f"[ERROR] {error}",
        file=sys.stderr,
        flush=True,
    )


def main():
    print("[TEST] Starting MediaJobProcessor")
    print(f"[TEST] URL: {URL}")
    print(f"[TEST] Output: {OUTPUT}")
    print("[TEST] Mode: video")
    print()

    processor = MediaJobProcessor(
        download_mode="video",
        output=OUTPUT,

        quality="best",
        container="mp4",
        audio_quality="best",

        # No subtitles for this test.
        download_subtitles=False,
        save_separate_subtitle=False,
        embed_subtitles=False,

        playlist_folder=True,
        avoid_duplicates=True,

        fragments=8,
        retries=10,

        cookies=False,
        sponsorblock=False,

        progress_callback=progress_callback,
        error_callback=error_callback,

        # Keep an existing final file instead of overwriting it.
        overwrite_mode="keep",
    )

    try:
        result = processor.process(URL)

        print()
        print("=" * 70)
        print("[TEST] PROCESS COMPLETE")
        print("=" * 70)

        print(f"Result type: {type(result).__name__}")

        if isinstance(result, dict):
            print(f"URL:       {result.get('url')}")
            print(f"Mode:      {result.get('download_mode')}")
            print(f"ID:        {result.get('id')}")
            print(f"Title:     {result.get('title')}")
            print(f"Filepath:  {result.get('filepath')}")
            print(f"Path:      {result.get('path')}")
            print(f"Completed: {result.get('completed')}")
            print(f"Cancelled: {result.get('cancelled')}")

            filepath = result.get("filepath")

            if filepath:
                filepath = os.path.abspath(str(filepath))

                print()
                print(f"[TEST] Final file: {filepath}")
                print(
                    f"[TEST] Exists: "
                    f"{os.path.isfile(filepath)}"
                )

                if os.path.isfile(filepath):
                    size = os.path.getsize(filepath)

                    print(
                        f"[TEST] Size: "
                        f"{size / (1024 * 1024):.2f} MB"
                    )

        print("=" * 70)

    except KeyboardInterrupt:
        print()
        print("[TEST] Ctrl+C detected")
        processor.cancel()

    except Exception as exc:
        print()
        print("=" * 70)
        print("[TEST] FAILED")
        print("=" * 70)
        print(f"{type(exc).__name__}: {exc}")
        print("=" * 70)

        raise


if __name__ == "__main__":
    main()