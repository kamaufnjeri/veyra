Updated to include **Silero VAD** as a required dependency and mention its role in the transcription pipeline.

# Veyra

Veyra is a local Python-based subtitle generator for video and audio files.

It uses **SpeechRecognition with Google Speech Recognition** to transcribe audio, **Silero VAD** for voice activity detection, and Google's **GTX translation endpoint** to translate subtitles.

## Features

* Generate subtitles from video and audio files
* Voice activity detection with Silero VAD
* Google Speech Recognition transcription
* Subtitle translation using Google GTX
* Multiple media files
* Preserves subtitle timestamps
* Reuses existing subtitles
* Translation caching
* Retry and timeout handling
* Progress and error callbacks
* SRT, VTT, JSON, and RAW output

## Installation

```bash
git clone <repository-url>
cd veyra

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

On Windows:

```powershell
.venv\Scripts\activate
```

## FFmpeg

Ubuntu/Debian:

```bash
sudo apt update
sudo apt install ffmpeg
```

Verify:

```bash
ffmpeg -version
ffprobe -version
```

## How It Works

### Transcription

```text
Video / Audio
      ↓
FFmpeg
      ↓
Silero VAD
      ↓
SpeechRecognition
      ↓
Google Speech Recognition
      ↓
Subtitle text + timestamps
      ↓
SRT / VTT / JSON / RAW
```

Silero VAD is used to detect speech segments before sending audio for transcription. This helps Veyra distinguish speech from silence and other non-speech portions of the media.

### Translation

```text
Source subtitles
      ↓
Translation cache
      ↓
Google GTX
      ↓
Translated subtitles
```

Veyra uses a persistent HTTP session, caching, retries, timeouts, and an HTTPX fallback to make translation more reliable.

## Usage

Generate subtitles:

```bash
python main.py movie.mp4
```

Specify the source language:

```bash
python main.py movie.mp4 --source-language en
```

Translate English subtitles to Swahili:

```bash
python main.py movie.mp4 \
    --source-language en \
    --target-language sw
```

Specify the output format:

```bash
python main.py movie.mp4 \
    --source-language en \
    --format srt
```

Process multiple files:

```bash
python main.py episode1.mp4 episode2.mp4 episode3.mp4
```

Show all options:

```bash
python main.py --help
```

## Supported Languages

Common language codes include:

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

## Existing Subtitles

Veyra checks for existing subtitle files before doing expensive processing.

For example:

```text
movie.en.srt
```

can be reused instead of transcribing the audio again.

Translated subtitles can also be reused:

```text
movie.sw.srt
```

This helps avoid unnecessary processing and translation requests.

## Translation

The translator provides:

* Translation caching
* Configurable retries
* Request timeouts
* Persistent HTTP connections
* HTTPX fallback
* Empty-text handling
* Progress callbacks
* Error callbacks

Example:

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

## Voice Activity Detection

Veyra uses **Silero VAD** to identify portions of the audio that contain speech.

The VAD stage helps reduce unnecessary transcription of silent or non-speech sections while providing more accurate speech segment boundaries for subtitle generation.

```text
Audio
  ↓
Silero VAD
  ↓
Speech segments
  ↓
Google Speech Recognition
  ↓
Timestamped subtitles
```

Silero VAD is therefore a required component of Veyra's transcription pipeline.

## Network Requirement

Speech recognition and translation require an internet connection.

For example:

```text
Google speech recognition request failed:
recognition connection failed:
[Errno -3] Temporary failure in name resolution
```

usually indicates a DNS or network problem rather than a subtitle-processing problem.

Silero VAD itself can run locally, but Google Speech Recognition and Google GTX translation require network connectivity.

## Project Structure

```text
veyra/
├── cli/
├── core/
│   ├── audio_transcriber.py
│   ├── language.py
│   ├── subtitle_formatter.py
│   ├── subtitle_translator.py
│   └── subtitle_writer.py
├── jobs/
├── services/
│   └── subtitle_service.py
├── main.py
├── requirements.txt
├── README.md
└── .gitignore
```

## Credits

Veyra was developed with help and inspiration from [**PyAutoSRT**](https://github.com/botbahlul/PyAutoSRT) by Bot Bahlul.

PyAutoSRT provided a useful reference for automatic speech recognition, subtitle generation, and translation workflows.

Veyra also uses **Silero VAD** for local voice activity detection.

Veyra is an independent project and is not affiliated with or endorsed by PyAutoSRT, Silero, or Google.

## License

## License

Veyra is released under the MIT License.

See the [LICENSE](LICENSE) file for the complete license text.