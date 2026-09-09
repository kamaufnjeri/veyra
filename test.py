from __future__ import annotations

from pathlib import Path
import shutil
import sys

from media.cutter import (
    CutError,
    CutSettings,
    MediaCutter,
)


INPUT = Path("input.mp4")
OUTPUT_DIR = Path("test_cutter_output")


def clean_output() -> None:
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


def progress(message, percent):
    print(f"[{percent:6.2f}%] {message}")


def run_test(
    name: str,
    settings: CutSettings,
) -> None:

    print()
    print("=" * 70)
    print(name)
    print("=" * 70)

    try:
        cutter = MediaCutter(
            progress_callback=progress,
        )

        result = cutter.cut(
            INPUT,
            settings,
        )

        print()
        print(f"SUCCESS: {name}")
        print(f"Source duration: {result.duration:.3f}s")
        print(f"Parts created: {len(result.parts)}")

        for part in result.parts:
            print(
                f"  Part {part.index}/{part.total}: "
                f"{part.start:.3f}s -> "
                f"{part.end:.3f}s "
                f"({part.duration:.3f}s)"
            )

            print(
                f"    Video: {part.output}"
            )

            for subtitle in part.subtitle_outputs:
                print(
                    f"    Subtitle: {subtitle}"
                )

    except Exception as exc:
        print()
        print(f"FAILED: {name}")
        print(f"{type(exc).__name__}: {exc}")


def main() -> None:

    if not INPUT.is_file():
        print(
            f"ERROR: {INPUT} was not found."
        )
        print(
            "Place input.mp4 next to test_cutter.py "
            "and run again."
        )
        sys.exit(1)

    clean_output()

    # ========================================================
    # 1. EQUAL PARTS
    #
    # Example:
    #
    # 20 minute video / 3
    #
    # produces:
    #
    # part 1 -> 0:00 - 6:40
    # part 2 -> 6:40 - 13:20
    # part 3 -> 13:20 - 20:00
    #
    # Names:
    #
    # input_1-of-3.mp4
    # input_2-of-3.mp4
    # input_3-of-3.mp4
    # ========================================================

    run_test(
        "TEST 1 - Equal parts",
        CutSettings(
            mode="parts",
            parts=3,
            output_directory=OUTPUT_DIR / "parts",
            mode_video="reencode",
            overwrite=True,
        ),
    )

    # ========================================================
    # 2. FIXED DURATION
    #
    # Example with duration=15 minutes:
    #
    # 20 minute video:
    #
    # part 1 -> 0:00 - 15:00
    # part 2 -> 15:00 - 20:00
    #
    # This verifies that the final remainder is preserved.
    # ========================================================

    run_test(
        "TEST 2 - Fixed duration",
        CutSettings(
            mode="duration",
            duration=15 * 60,
            output_directory=OUTPUT_DIR / "duration",
            mode_video="reencode",
            overwrite=True,
        ),
    )

    # ========================================================
    # 3. TIMESTAMPS
    #
    # Splits at:
    #
    # 5 minutes
    # 10 minutes
    # 15 minutes
    #
    # resulting in:
    #
    # 0:00 -> 5:00
    # 5:00 -> 10:00
    # 10:00 -> 15:00
    # 15:00 -> end
    #
    # Timestamp/range filenames use h/m/s.
    # ========================================================

    run_test(
        "TEST 3 - Timestamps",
        CutSettings(
            mode="timestamps",
            timestamps=(
                5 * 60,
                10 * 60,
                15 * 60,
            ),
            output_directory=OUTPUT_DIR / "timestamps",
            mode_video="reencode",
            overwrite=True,
        ),
    )

    # ========================================================
    # 4. SINGLE RANGE
    #
    # Extract:
    #
    # 2:00 -> 7:30
    #
    # Filename should look like:
    #
    # input_2m00s-7m30s.mp4
    #
    # Subtitle timestamps should start at 0.
    # ========================================================

    run_test(
        "TEST 4 - Specific range",
        CutSettings(
            mode="range",
            start=2 * 60,
            end=7 * 60 + 30,
            output_directory=OUTPUT_DIR / "range",
            mode_video="reencode",
            overwrite=True,
        ),
    )

    # ========================================================
    # 5. OLD MULTIPLE-DURATION MODE
    #
    # Explicit durations:
    #
    # 5 minutes
    # 3 minutes
    # 7 minutes
    #
    # This verifies backwards compatibility.
    # ========================================================

    run_test(
        "TEST 5 - Multiple durations",
        CutSettings(
            mode="durations",
            durations=(
                5 * 60,
                3 * 60,
                7 * 60,
            ),
            output_directory=OUTPUT_DIR / "durations",
            mode_video="reencode",
            overwrite=True,
        ),
    )

    # ========================================================
    # 6. FAST COPY
    #
    # Tests the fast-copy implementation separately.
    # ========================================================

    run_test(
        "TEST 6 - Fast copy",
        CutSettings(
            mode="duration",
            duration=5 * 60,
            output_directory=OUTPUT_DIR / "fast_copy",
            mode_video="fast_copy",
            overwrite=True,
        ),
    )

    # ========================================================
    # 7. SUBTITLE FORMAT CONVERSION
    #
    # Forces subtitles to SRT.
    #
    # This verifies:
    #
    # - subtitle discovery
    # - embedded subtitle extraction
    # - subtitle cropping
    # - timestamp reset to zero
    # - output naming
    # ========================================================

    run_test(
        "TEST 7 - Subtitles as SRT",
        CutSettings(
            mode="duration",
            duration=5 * 60,
            output_directory=OUTPUT_DIR / "subtitles_srt",
            mode_video="reencode",
            cut_subtitles=True,
            extract_embedded_subtitles=True,
            subtitle_output_format="srt",
            overwrite=True,
        ),
    )

    # ========================================================
    # 8. INVALID TIMESTAMP TEST
    #
    # This should raise an error if a timestamp is outside
    # the actual media duration.
    # ========================================================

    print()
    print("=" * 70)
    print("TEST 8 - Out-of-range timestamp")
    print("=" * 70)

    try:

        cutter = MediaCutter()

        cutter.cut(
            INPUT,
            CutSettings(
                mode="timestamps",
                timestamps=(
                    999999999,
                ),
                output_directory=OUTPUT_DIR / "invalid",
                overwrite=True,
            ),
        )

        print(
            "FAILED: Out-of-range timestamp "
            "did not raise an error."
        )

    except CutError as exc:

        print(
            "SUCCESS: Correctly raised CutError:"
        )
        print(f"  {exc}")

    except Exception as exc:

        print(
            "FAILED: Wrong exception type:"
        )
        print(
            f"  {type(exc).__name__}: {exc}"
        )

    print()
    print("=" * 70)
    print("ALL TESTS FINISHED")
    print("=" * 70)
    print()
    print(
        f"Output files are in: "
        f"{OUTPUT_DIR.resolve()}"
    )


if __name__ == "__main__":
    main()
