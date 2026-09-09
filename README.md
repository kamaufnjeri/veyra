# Veyra

Veyra is a local Python-based media application built around three separate tools:

- **Subtitle Generation** — generate and translate subtitles from video or audio.
- **Media Download** — download videos, playlists, audio, or subtitles using [`yt-dlp`](https://github.com/yt-dlp/yt-dlp).
- **Media Processing** — convert, cut, join, and burn subtitles into media.

## About

Veyra is an opinionated personal media project built around how I personally work with media.

It is **not designed to be a universal media-processing solution**. Instead, it focuses on the workflows, tools, and features that fit my needs and the way I prefer to manage and process media.

The goal is to keep Veyra **tailored, practical, and useful for my specific use cases**, rather than trying to support every possible media workflow.

Because of this, some design decisions may be highly specific to my preferences — and that's intentional.

---

# Features

## 1. Subtitle Generation

Veyra can generate subtitles from either a video file or WAV audio.

The subtitle-generation pipeline is divided into two main stages:

- **Speech region detection** — identifies portions of the audio that contain speech and provides timestamps.
- **Speech recognition** — converts the detected speech regions into text.

The overall workflow is:

```text
Video / WAV Audio
       ↓
Speech Region Detection
       ↓
Speech Recognition
       ↓
SRT Subtitles
       ↓
Optional Translation
```

### Speech Region Detection

Veyra supports two methods for detecting speech regions and generating their timestamps:

- **[Silero VAD](https://github.com/snakers4/silero-vad)** — detects regions of the audio that contain speech and provides timestamps for those regions.
- **Fixed segments** — divides the audio into fixed 10-second segments and uses those segments as the regions to process.

These methods are used for **speech detection and timing**, not for converting speech into text.

### Speech Recognition

After speech regions have been identified, Veyra uses **Google Speech Recognition** through the [`SpeechRecognition`](https://pypi.org/project/SpeechRecognition/) Python package to convert the audio from those regions into text.

The resulting text and timestamps are then used to generate an SRT subtitle file.

Veyra is therefore focused on **subtitle generation**, rather than being a general-purpose transcription application.

### Subtitle Generation Workflow

```text
Video / WAV
    ↓
┌───────────────────────────┐
│ Silero VAD                │
│           OR              │
│ Fixed 10-second segments  │
└─────────────┬─────────────┘
              ↓
Detected Speech Regions
       + Timestamps
              ↓
Google Speech Recognition
              ↓
       Recognized Text
              ↓
         SRT Subtitle
              ↓
     Optional Translation
              ↓
       Translated SRT
```

Generated subtitles can be saved as SRT files and optionally translated into a chosen language.

Existing subtitle files can also be reused and translated without generating them again.

Translation includes caching and retry handling to avoid unnecessary repeated requests where possible.

---

## 2. Media Download

Veyra includes a separate media downloader based on [`yt-dlp`](https://github.com/yt-dlp/yt-dlp).

You can provide a URL and download supported media in different ways, including:

- Single videos
- Playlists
- Audio
- Subtitles
- Other media supported by `yt-dlp`

For example:

```text
URL
 ↓
yt-dlp
 ↓
Video / Playlist / Audio / Subtitles
```

The exact websites, formats, qualities, and download options depend on the current capabilities of `yt-dlp`.

Websites can change their systems, authentication requirements, or anti-bot measures, which can cause downloads to stop working until `yt-dlp` is updated or compatibility is restored.

> **Note:** Users are responsible for ensuring that downloaded media is used in accordance with applicable laws, copyright requirements, and website terms.

---

## 3. Media Processing

Media processing is a separate part of Veyra and does not require the subtitle-generation or download features.

Veyra uses **[FFmpeg](https://ffmpeg.org/)** and **FFprobe** for media operations such as:

- Convert media
- Cut videos into parts
- Join videos
- Burn subtitles
- Inspect media information

### Conversion

Veyra can convert between supported media formats.

Examples:

```text
MKV → MP4
MOV → MP4
MP4 → MKV
```

Depending on the operation, streams may be copied without re-encoding or re-encoded when necessary.

### Cutting

Videos can be divided into parts using options such as:

- Duration
- Number of parts
- Start/end times
- Timestamps

For example:

```text
Video
  ↓
Part 1
Part 2
Part 3
Part 4
```

### Joining

Multiple compatible video files can be joined into a single file:

```text
Part 1
Part 2
Part 3
  ↓
Complete Video
```

The files should have compatible media properties for reliable joining.

### Burning Subtitles

Veyra can permanently burn an SRT subtitle file into a video.

```text
Video + SRT
     ↓
   FFmpeg
     ↓
Video with subtitles
```

Burned subtitles become part of the video image and cannot be disabled during playback.

Subtitle appearance can be configured using options such as:

- Font
- Font size
- Font color

---

# FFmpeg and FFprobe

[FFmpeg](https://ffmpeg.org/) and FFprobe are required for Veyra's media-processing features.

## Ubuntu / Debian

Install FFmpeg with:

```bash
sudo apt update
sudo apt install ffmpeg
```

Verify the installation:

```bash
ffmpeg -version
ffprobe -version
```

## Windows / macOS

Install an appropriate FFmpeg distribution and ensure both `ffmpeg` and `ffprobe` are available in the system `PATH`.

See the official [FFmpeg download page](https://ffmpeg.org/download.html) for available options.

---

# Installation

## 1. Clone the Repository

```bash
git clone <repository-url>
cd veyra
```

## 2. Create a Virtual Environment

```bash
python3 -m venv .venv
```

## 3. Activate the Virtual Environment

### Linux / macOS

```bash
source .venv/bin/activate
```

### Windows

```powershell
.venv\Scripts\activate
```

## 4. Install Python Dependencies

```bash
pip install -r requirements.txt
```

> **Important:** FFmpeg and FFprobe must also be installed separately.

---

# Running Veyra

Veyra can be started using either `main.py` or `dev.py`.

## Run Normally

```bash
python main.py
```

## Run the Development Version

```bash
python dev.py
```

On systems where `python3` is required:

```bash
python3 main.py
```

or:

```bash
python3 dev.py
```

---

# Requirements

Veyra's main Python dependencies include:

| Package | Purpose |
|---|---|
| [`PySide6`](https://pypi.org/project/PySide6/) | Graphical user interface |
| [`pysubs2`](https://pypi.org/project/pysubs2/) | Subtitle manipulation |
| [`pysrt`](https://pypi.org/project/pysrt/) | SRT subtitle handling |
| [`srt`](https://pypi.org/project/srt/) | SRT subtitle parsing and generation |
| [`silero-vad`](https://github.com/snakers4/silero-vad) | Speech region detection and voice activity detection |
| [`SpeechRecognition`](https://pypi.org/project/SpeechRecognition/) | Interface for speech recognition |
| [`srtranslator`](https://pypi.org/project/srtranslator/) | Subtitle translation |
| [`torch`](https://pypi.org/project/torch/) | Required by the Silero VAD pipeline |
| [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) | Media downloading |

Python standard-library modules such as `re`, `signal`, and `threading` do not need to be installed separately.

---

# External Requirements

Veyra also requires:

- **[FFmpeg](https://ffmpeg.org/)**
- **FFprobe**
- An available speech-recognition service supported by the configured [`SpeechRecognition`](https://pypi.org/project/SpeechRecognition/) setup

---

# Subtitle Generation Architecture

The subtitle-generation system separates **speech detection** from **speech recognition**.

```text
                  ┌─────────────────┐
                  │   Video / WAV   │
                  └────────┬────────┘
                           ↓
                ┌──────────────────────┐
                │ Speech Region        │
                │ Detection            │
                └──────────┬───────────┘
                           │
                 ┌─────────┴─────────┐
                 ↓                   ↓
          ┌──────────────┐    ┌───────────────┐
          │  Silero VAD  │    │ Fixed 10-sec  │
          │              │    │   Segments    │
          └──────┬───────┘    └───────┬───────┘
                 │                    │
                 └─────────┬──────────┘
                           ↓
                 Speech Regions +
                    Timestamps
                           ↓
                ┌──────────────────────┐
                │ Google Speech        │
                │ Recognition          │
                └──────────┬───────────┘
                           ↓
                     Recognized Text
                           ↓
                    ┌─────────────┐
                    │ SRT Subtitle│
                    └──────┬──────┘
                           ↓
                    Optional Translation
                           ↓
                   Translated SRT
```

This separation allows Veyra to use different methods for determining where speech occurs while keeping speech-to-text as a separate step.

---

# Limitations

Veyra is designed around a specific personal workflow and does not guarantee compatibility with every:

- Website
- Media format
- Codec
- Language
- Audio source
- Subtitle format
- External service

Subtitle quality depends on factors such as:

- Audio quality
- Language
- Background noise
- Number of speakers
- Speech-recognition service
- Accuracy of the detected speech regions

Google Speech Recognition and other external services may also have availability, request, network, or usage limitations.

External services and websites can change independently of Veyra.

---

# Credits

Veyra was developed with help and inspiration from [PyAutoSRT](https://github.com/botbahlul/PyAutoSRT) by [Bot Bahlul](https://github.com/botbahlul).

PyAutoSRT provided a useful reference for automatic speech recognition, subtitle generation, and subtitle translation workflows.

Veyra also uses:

- [Silero VAD](https://github.com/snakers4/silero-vad) for speech region detection
- [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) for media downloading
- [FFmpeg](https://ffmpeg.org/) / FFprobe for media processing
- [`SpeechRecognition`](https://pypi.org/project/SpeechRecognition/) for speech-recognition integration

Veyra is an independent project and is not affiliated with or endorsed by PyAutoSRT, Silero, `yt-dlp`, Google, or FFmpeg.

---

# References

- [PyAutoSRT — GitHub](https://github.com/botbahlul/PyAutoSRT)
- [Bot Bahlul — GitHub](https://github.com/botbahlul)
- [Silero VAD — GitHub](https://github.com/snakers4/silero-vad)
- [yt-dlp — GitHub](https://github.com/yt-dlp/yt-dlp)
- [SpeechRecognition — PyPI](https://pypi.org/project/SpeechRecognition/)
- [PySide6 — PyPI](https://pypi.org/project/PySide6/)
- [pysubs2 — PyPI](https://pypi.org/project/pysubs2/)
- [pysrt — PyPI](https://pypi.org/project/pysrt/)
- [srt — PyPI](https://pypi.org/project/srt/)
- [srtranslator — PyPI](https://pypi.org/project/srtranslator/)
- [PyTorch — PyPI](https://pypi.org/project/torch/)
- [FFmpeg — Official Website](https://ffmpeg.org/)

---

# License

Veyra is released under the **MIT License**.

See the [`LICENSE`](LICENSE) file for the complete license text.
