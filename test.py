from pathlib import Path

from core.subtitle_translator import SubtitlesTranslator


INPUT_FILE = (
    "/home/florence/Downloads/Corazon Salvaje/"
    "Corazon Salvaje - Capitulo 02_(480p).es.srt"
)

OUTPUT_FILE = (
    "/home/florence/Downloads/Corazon Salvaje/"
    "Corazon Salvaje - Capitulo 02_(480p).en.test.srt"
)


def on_progress(percent: int):
    print(f"Progress: {percent}%")


def on_error(message: str):
    print(f"ERROR: {message}")


def main():

    print("=" * 70)
    print("CORAZON SALVAJE SUBTITLE TRANSLATION TEST")
    print("=" * 70)
    print()

    print(f"Input : {INPUT_FILE}")
    print(f"Output: {OUTPUT_FILE}")
    print()

    if not Path(INPUT_FILE).exists():
        print("ERROR: Input subtitle file does not exist.")
        return

    translator = SubtitlesTranslator(
        source_language="es",
        target_language="en",

        # Translate 200 subtitles at a time using
        # SrtFile.translate().
        batch_size=100,

        # Only used if a bulk batch fails.
        retry_count=3,
        retry_delay=1.0,

        error_messages_callback=on_error,
        progress_callback=on_progress,
    )

    try:

        print("Starting translation...")
        print()

        result = translator.translate_srt(
            INPUT_FILE,
            OUTPUT_FILE,
        )

        print()
        print("=" * 70)
        print("TEST COMPLETE")
        print("=" * 70)
        print()
        print(f"Translated file: {result}")

    except Exception as exc:

        print()
        print("=" * 70)
        print("TRANSLATION FAILED")
        print("=" * 70)
        print()
        print(
            f"{type(exc).__name__}: {exc}"
        )

    finally:
        translator.close()


if __name__ == "__main__":
    main()