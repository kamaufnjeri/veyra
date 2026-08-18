# Veyra

Veyra is a local Python-based subtitle generator for video and audio files.

It uses **faster-whisper** for speech recognition and speech-to-English translation, with **Argos Translate** for subtitle translation into other languages.

---

## Features

- Generate subtitles from video and audio files
- Local speech recognition using faster-whisper
- Speech-to-English translation using faster-whisper
- Subtitle translation using Argos Translate
- Supports multiple media files
- Preserves subtitle timestamps
- Reuses existing subtitles when available
- Optional overwrite prompts
- Progress reporting
- Error handling
- Batch subtitle translation
- Supports SRT, VTT, JSON, and RAW output

---

## Requirements

- Python 3.10+
- FFmpeg
- FFprobe
- PyTorch
- faster-whisper
- Argos Translate

---

## Installation

Clone the repository:

```bash
git clone <repository-url>
cd veyra
```

Create a virtual environment:

```bash
python3 -m venv .venv
```

Activate the virtual environment on Linux/macOS:

```bash
source .venv/bin/activate
```

On Windows:

```powershell
.venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

---

## FFmpeg

Veyra requires FFmpeg and FFprobe.

### Ubuntu / Debian

```bash
sudo apt update
sudo apt install ffmpeg
```

Verify:

```bash
ffmpeg -version
ffprobe -version
```

---

## Whisper Models

Veyra uses `faster-whisper`.

The Whisper model is configured in:

```text
core/audio_transcriber.py
```

For CPU systems, `base` is a good balance between speed and accuracy.

Example:

```python
WhisperModel(
    model_size_or_path="base",
    device="cpu",
    compute_type="int8",
)
```

### Model Comparison

| Model | Speed | Accuracy |
|---|---|---|
| `tiny` | Very fast | Lower |
| `base` | Fast | Good |
| `small` | Medium | Better |
| `medium` | Slow | Very good |
| `large-v3` | Very slow on CPU | Excellent |

For most CPU systems:

```text
base + int8
```

is a good starting point.

---

# Translation Strategy

Veyra chooses the processing strategy based on the source and target languages.

## Non-English → English

For non-English speech translated directly into English, Veyra uses faster-whisper's built-in translation.

```text
Non-English Audio
        ↓
faster-whisper
task="translate"
        ↓
English Subtitles
```

Example:

```text
Spanish audio
      ↓
faster-whisper
      ↓
movie.en.srt
```

There is no unnecessary intermediate Spanish subtitle translation.

---

## English → English

When the source language is English and no different target language is requested:

```text
English Audio
      ↓
faster-whisper
task="transcribe"
      ↓
movie.en.srt
```

No translation engine is required.

---

## English → Other Language

Example: English → Swahili

```text
English Audio
      ↓
faster-whisper
task="transcribe"
      ↓
English Subtitles
      ↓
Argos Translate
      ↓
Swahili Subtitles
```

Output:

```text
movie.en.srt
movie.sw.srt
```

---

## Non-English → Non-English

Example: French → German

```text
French Audio
      ↓
faster-whisper
task="transcribe"
      ↓
French Subtitles
      ↓
Argos Translate
      ↓
German Subtitles
```

Output:

```text
movie.fr.srt
movie.de.srt
```

---

# Processing Pipeline

## Non-English → English

```text
Video / Audio
      ↓
faster-whisper
      ↓
Speech Translation
      ↓
English Subtitle Text
      ↓
Subtitle Formatter
      ↓
Subtitle Writer
      ↓
English Subtitle File
```

## Other Translation Requests

```text
Video / Audio
      ↓
faster-whisper
      ↓
Source-language Transcription
      ↓
Source Subtitle
      ↓
Argos Translate
      ↓
Translated Subtitle
```

---

# Basic Usage

Run Veyra from the project root:

```bash
python main.py input.mp4
```

Specify the source language:

```bash
python main.py input.mp4 --source-language en
```

Generate translated subtitles:

```bash
python main.py input.mp4 \
    --source-language en \
    --target-language sw
```

---

# CLI Options

Show all available options:

```bash
python main.py --help
```

Basic syntax:

```bash
python main.py <media-file>
```

Source language:

```bash
python main.py movie.mp4 --source-language en
```

Target language:

```bash
python main.py movie.mp4 \
    --source-language en \
    --target-language sw
```

Subtitle format:

```bash
python main.py movie.mp4 \
    --source-language en \
    --format srt
```

---

# Supported Languages

Common language codes include:

| Code | Language |
|---|---|
| `en` | English |
| `sw` | Swahili |
| `fr` | French |
| `de` | German |
| `es` | Spanish |
| `it` | Italian |
| `pt` | Portuguese |
| `ar` | Arabic |
| `zh` | Chinese |
| `ja` | Japanese |
| `ko` | Korean |

Example:

```bash
python main.py movie.mp4 \
    --source-language en \
    --target-language sw
```

---

# Output Formats

Veyra supports:

- `srt`
- `vtt`
- `json`
- `raw`

SRT:

```bash
python main.py movie.mp4 --format srt
```

VTT:

```bash
python main.py movie.mp4 --format vtt
```

JSON:

```bash
python main.py movie.mp4 --format json
```

RAW:

```bash
python main.py movie.mp4 --format raw
```

---

# Existing Subtitles

Veyra checks whether subtitle files already exist before performing expensive processing.

For example:

```text
movie.en.srt
```

If the source subtitle already exists, Veyra can reuse it instead of transcribing the audio again.

If a translated subtitle already exists:

```text
movie.sw.srt
```

Veyra can reuse it instead of translating the subtitles again.

If an existing subtitle is found and an overwrite callback is configured, Veyra asks:

```text
Overwrite it? [y]es / [n]o:
```

Choosing `n` keeps the existing subtitle.

Choosing `y` regenerates the subtitle.

---

# Multiple Files

Veyra supports processing multiple media files:

```bash
python main.py episode1.mp4 episode2.mp4 episode3.mp4
```

With translation:

```bash
python main.py \
    episode1.mp4 \
    episode2.mp4 \
    episode3.mp4 \
    --source-language en \
    --target-language sw
```

---

# Python API

Veyra can also be used directly from Python.

```python
from services.subtitle_service import SubtitleService

service = SubtitleService(
    source_language="en",
    target_language="sw",
    subtitle_format="srt",
)

result = service.create_subtitles("movie.mp4")

print(result)
```

Example result:

```python
{
    "media": "/path/to/movie.mp4",
    "source_subtitle": "/path/to/movie.en.srt",
    "translated_subtitle": "/path/to/movie.sw.srt",
    "regions": 125,
    "recognized_segments": 125,
    "transcription_task": "transcribe",
    "translation_engine": "argos",
}
```

---

# Non-English → English API

Example:

```python
from services.subtitle_service import SubtitleService

service = SubtitleService(
    source_language="es",
    target_language="en",
    subtitle_format="srt",
)

result = service.create_subtitles("movie.mp4")
```

Veyra uses:

```text
faster-whisper
task="translate"
```

The output is directly:

```text
movie.en.srt
```

Argos Translate is not required for this translation path.

---

# English → Other Language API

Example:

```python
from services.subtitle_service import SubtitleService

service = SubtitleService(
    source_language="en",
    target_language="sw",
    subtitle_format="srt",
)

result = service.create_subtitles("movie.mp4")
```

Processing:

```text
English Audio
      ↓
faster-whisper
      ↓
English Subtitles
      ↓
Argos Translate
      ↓
Swahili Subtitles
```

---

# Progress Callbacks

`SubtitleService` supports progress callbacks.

Example:

```python
def show_progress(stage, filename, percentage):
    print(
        f"{stage}: "
        f"{percentage}% - "
        f"{filename}"
    )


service = SubtitleService(
    source_language="en",
    target_language="sw",
    subtitle_format="srt",
    progress_callback=show_progress,
)

service.create_subtitles("movie.mp4")
```

---

# Error Callbacks

Errors can be handled with an error callback:

```python
def show_error(error):
    print(f"Error: {error}")


service = SubtitleService(
    source_language="en",
    target_language="sw",
    subtitle_format="srt",
    error_callback=show_error,
)

service.create_subtitles("movie.mp4")
```

---

# Ctrl+C / Cancellation

Veyra supports cancellation from the CLI.

Press:

```text
Ctrl+C
```

The process exits with status code:

```text
130
```

If the process does not stop, it can be terminated from another terminal:

```bash
pkill -f "python main.py"
```

Check whether it is still running:

```bash
ps aux | grep "python main.py"
```

---

# Performance

For CPU systems, `base` with `int8` is recommended when speed is important.

Example:

```python
WhisperModel(
    model_size_or_path="base",
    device="cpu",
    compute_type="int8",
)
```

Veyra also uses voice activity detection:

```python
vad_filter=True
```

This helps avoid processing long silent sections.

For higher accuracy, use:

```text
small
```

or:

```text
medium
```

However, larger models require significantly more processing time and memory.

---

# Translation Performance

Veyra translates subtitle lines in batches instead of translating each line individually.

This helps reduce translation overhead.

Veyra also:

- Preserves subtitle ordering
- Preserves timestamps
- Avoids translating empty lines
- Reuses existing translated subtitles
- Avoids unnecessary translation
- Processes subtitle translations in batches

---

# Project Structure

```text
veyra/
│
├── cli/
│   ├── __init__.py
│   └── main.py
│
├── core/
│   ├── __init__.py
│   ├── audio_transcriber.py
│   ├── language.py
│   ├── subtitle_formatter.py
│   ├── subtitle_translator.py
│   └── subtitle_writer.py
│
├── jobs/
│   ├── __init__.py
│   └── processor.py
│
├── services/
│   ├── __init__.py
│   └── subtitle_service.py
│
├── main.py
├── requirements.txt
├── README.md
└── .gitignore
```

---

# Troubleshooting

## FFmpeg Not Found

Check:

```bash
which ffmpeg
```

and:

```bash
which ffprobe
```

Install on Ubuntu/Debian:

```bash
sudo apt update
sudo apt install ffmpeg
```

---

## Python Dependency Missing

Activate the virtual environment:

```bash
source .venv/bin/activate
```

Then install dependencies:

```bash
pip install -r requirements.txt
```

---

## faster-whisper Error

Check:

```bash
pip show faster-whisper
```

Install if necessary:

```bash
pip install faster-whisper
```

---

## Argos Translate Error

Check:

```bash
pip show argostranslate
```

Install:

```bash
pip install argostranslate
```

If a language pair is unavailable, Veyra will report that an Argos translation model is not available.

---

## PyTorch Error

Check the installed PyTorch version:

```bash
python -c "import torch; print(torch.__version__)"
```

Check CUDA:

```bash
python -c "import torch; print(torch.cuda.is_available())"
```

For CPU processing:

```text
device=cpu
compute_type=int8
```

---

## No Subtitles Produced

If Whisper produces no subtitles, check:

- The media file contains an audio track.
- The audio is understandable.
- The source language is correct.
- FFmpeg is installed.
- The Whisper model is installed correctly.

Check the media file:

```bash
ffprobe input.mp4
```

---

# Development

Go to the project:

```bash
cd ~/Projects/veyra
```

Activate the virtual environment:

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Test the CLI:

```bash
python main.py --help
```

---

# Examples

## English Subtitles

```bash
python main.py episode.mp4 \
    --source-language en \
    --format srt
```

Output:

```text
episode.en.srt
```

---

## English → Swahili

```bash
python main.py episode.mp4 \
    --source-language en \
    --target-language sw \
    --format srt
```

Output:

```text
episode.en.srt
episode.sw.srt
```

---

## Spanish → English

```bash
python main.py episode.mp4 \
    --source-language es \
    --target-language en \
    --format srt
```

Processing:

```text
Spanish Audio
      ↓
faster-whisper
task="translate"
      ↓
English Subtitles
```

Output:

```text
episode.en.srt
```

---

## French → German

```bash
python main.py episode.mp4 \
    --source-language fr \
    --target-language de \
    --format srt
```

Processing:

```text
French Audio
      ↓
faster-whisper
task="transcribe"
      ↓
French Subtitles
      ↓
Argos Translate
      ↓
German Subtitles
```

Output:

```text
episode.fr.srt
episode.de.srt
```

---

# Git

Initialize the repository:

```bash
git init
```

Rename the default branch:

```bash
git branch -M main
```

Add files:

```bash
git add .
```

Create the first commit:

```bash
git commit -m "Initial Veyra subtitle generator"
```

Add the GitHub repository:

```bash
git remote add origin https://github.com/YOUR_USERNAME/veyra.git
```

Push:

```bash
git push -u origin main
```

---

# License

Add your project license here.