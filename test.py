from pathlib import Path

from jobs.media_engine_processor import (
MediaEngineJob,
MediaEngineProcessor,
)
from media.models import (
    BurnerSettings,
    )

VIDEO = Path("input.mp4")
SUBTITLE = Path("input.en.srt")
OUTPUT = Path("burned_output.mp4")

def show_progress(
    job: MediaEngineJob,
    progress: float,
    message: str,
    ) -> None:
    percent = progress * 100

    print(
        f"\r{message}: {percent:6.2f}%",
        end="",
        flush=True,
    )


def show_error(error) -> None:
    print(f"\nERROR: {error}")

def show_job(event, *args) -> None:
    print(f"\nJOB: {event}")

def main() -> None:

    processor = MediaEngineProcessor(
        ffmpeg="ffmpeg",
        ffprobe="ffprobe",
        progress_callback=show_progress,
        error_callback=show_error,
        job_callback=show_job,
    )

    settings = BurnerSettings(
        subtitle_font="DejaVu Sans",
        subtitle_font_size=40,
        subtitle_color="#FFFF00",
    )

    job = MediaEngineJob(
        operation="burn_subtitles",
        inputs=(
            VIDEO,
            SUBTITLE,
        ),
        output=OUTPUT,
        settings=settings,
    )

    try:

        result = processor.process(job)

        print("\n\nSubtitle burning completed.")
        print(result)

    except Exception as exc:

        print(f"\n\nFAILED: {exc}")


if __name__ == "__main__":
    main()