# Veyra

Veyra is a Python-based tool for generating subtitles from video and audio files.

It can:

* Convert media files to WAV
* Detect speech regions
* Convert speech regions to FLAC
* Transcribe speech
* Translate subtitles
* Generate SRT, VTT, JSON, or raw subtitle output

## Requirements

* Python 3.10+
* FFmpeg
* FFprobe
* Internet connection for speech recognition and translation

## Installation

Clone or download the project:

```bash
git clone <repository-url>
cd veyra
```

Create a virtual environment:

```bash
python -m venv venv
```

Activate it on Linux/macOS:

```bash
source venv/bin/activate
```

On Windows:

```powershell
.venv\Scripts\activate
```

Install the Python dependencies:

```bash
pip install -r requirements.txt
```

## FFmpeg

Veyra requires both `ffmpeg` and `ffprobe`.

### Ubuntu/Debian

```bash
sudo apt update
sudo apt install ffmpeg
```

Check that they are installed:

```bash
ffmpeg -version
ffprobe -version
```

## Basic Usage

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

## Output Formats

Veyra supports the following subtitle formats:

* `srt`
* `vtt`
* `json`
* `raw`

Example:

```bash
python main.py input.mp4 --format srt
```

With translation:

```bash
python main.py input.mp4 \
    --source-language en \
    --target-language sw \
    --format srt
```

## Processing Pipeline

Veyra processes media through the following pipeline:

```text
Video / Audio
      ↓
WAV Converter
      ↓
Speech Region Finder
      ↓
FLAC Converter
      ↓
Speech Recognizer
      ↓
Translator (optional)
      ↓
Subtitle Formatter
      ↓
Subtitle Writer
      ↓
Subtitle File
```

For example:

```text
movie.mp4
   ↓
movie.en.srt
```

With translation:

```text
movie.mp4
   ↓
movie.en.srt
movie.sw.srt
```

## CLI Usage

Show all available options:

```bash
python main.py --help
```

Basic usage:

```bash
python main.py <media-file>
```

With language and format options:

```bash
python main.py movie.mp4 \
    --source-language en \
    --target-language sw \
    --format srt
```

## Python API

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

The result contains the generated subtitle paths:

```python
{
    "media": "/path/to/movie.mp4",
    "source_subtitle": "/path/to/movie.en.srt",
    "translated_subtitle": "/path/to/movie.sw.srt"
}
```

If translation is not required:

```python
service = SubtitleService(
    source_language="en",
    subtitle_format="srt",
)

result = service.create_subtitles("movie.mp4")
```

## Progress and Error Callbacks

`SubtitleService` supports callbacks for monitoring progress and handling errors.

```python
def show_progress(stage, filename, percentage):
    print(f"{stage}: {percentage}% - {filename}")


def show_error(error):
    print(f"Error: {error}")


service = SubtitleService(
    source_language="en",
    target_language="sw",
    subtitle_format="srt",
    progress_callback=show_progress,
    error_callback=show_error,
)

service.create_subtitles("movie.mp4")
```

## Project Structure

```text
veyra/
├── cli/
│   ├── __init__.py
│   └── main.py
│
├── core/
│   ├── __init__.py
│   ├── flac_converter.py
│   ├── language.py
│   ├── media_subtitle_embedder.py
│   ├── media_subtitle_remover.py
│   ├── media_subtitle_renderer.py
│   ├── speech_recognizer.py
│   ├── speech_region_finder.py
│   ├── srt_file_reader.py
│   ├── subtitle_formatter.py
│   ├── subtitle_stream_parser.py
│   ├── subtitle_writer.py
│   ├── translator.py
│   └── wav_converter.py
│
├── jobs/
│   ├── __init__.py
│   └── processor.py
│
├── services/
│   ├── __init__.py
│   ├── subtitle_service.py
│   └── video_service.py
│
├── main.py
├── requirements.txt
└── README.md
```

## Supported Languages

Language codes are used to select the source and target languages.

Common examples:

| Code | Language   |
| ---- | ---------- |
| `en` | English    |
| `sw` | Swahili    |
| `fr` | French     |
| `de` | German     |
| `es` | Spanish    |
| `it` | Italian    |
| `pt` | Portuguese |
| `ar` | Arabic     |
| `zh` | Chinese    |
| `ja` | Japanese   |
| `ko` | Korean     |

Example:

```bash
python main.py movie.mp4 \
    --source-language en \
    --target-language sw
```

## Troubleshooting

### FFmpeg Not Found

Check whether FFmpeg is available:

```bash
which ffmpeg
which ffprobe
```

If nothing is returned, install FFmpeg:

```bash
sudo apt update
sudo apt install ffmpeg
```

### Python Dependency Missing

Reinstall the project dependencies:

```bash
pip install -r requirements.txt
```

### `httpx` Not Found

Install `httpx`:

```bash
pip install httpx
```

### `pysrt` Not Found

Install `pysrt`:

```bash
pip install pysrt
```

### Permission Error

Make sure:

* The input media file can be read.
* The output directory can be written.
* Your user has permission to access the project directory.

## Development

Go to the project directory:

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

Check the CLI:

```bash
python main.py --help
```

## Examples

### Generate English Subtitles

```bash
python main.py episode.mp4 \
    --source-language en \
    --format srt
```

### Generate English Subtitles and Translate to Swahili

```bash
python main.py episode.mp4 \
    --source-language en \
    --target-language sw \
    --format srt
```

Generated subtitle files will be placed alongside the input media unless another output location is configured.

## License

Add your project license here.
