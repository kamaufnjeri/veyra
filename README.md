# Veyra

Veyra is a local Python-based media and subtitle application built around the way I personally work with video, audio, subtitles, and downloaded media.

It combines **media downloading, subtitle generation, subtitle translation, and media processing** into one application.

Veyra is intentionally opinionated. It was built to suit my own workflow, preferences, and the type of media work I personally do. It is not intended to be a universal media-processing solution, and some operations may require adjustments depending on the media, operating system, codecs, external services, or other factors.

---

## What Veyra Does

Veyra is designed to handle a media workflow from downloading or loading a video through subtitle generation, translation, and final media processing.

A typical workflow can look like this:

```text
Download media
      ↓
Prepare / extract audio
      ↓
Detect speech
      ↓
Transcribe speech
      ↓
Generate subtitles
      ↓
Translate subtitles
      ↓
Cut / join / convert / burn subtitles
      ↓
Finished media
```

Veyra can:

- Download videos and other media from supported websites using **yt-dlp**
- Work with locally stored video and audio files
- Extract and convert audio using **FFmpeg**
- Generate subtitles from video or audio
- Use **Silero VAD** for voice activity detection
- Process audio using fixed segments, with **10-second segments** as the default
- Transcribe speech as part of the subtitle-generation process
- Generate timestamped **SRT subtitles**
- Translate existing or generated subtitles
- Reuse existing subtitle files
- Cache translations to avoid unnecessary repeated translation requests
- Convert video and audio between supported formats
- Cut videos into segments
- Join multiple media files
- Burn subtitles permanently into videos
- Inspect media information using **FFprobe**
- Report processing progress and errors

---

## Downloading Media

Veyra can download media from supported websites using **yt-dlp**.

This allows the subtitle-generation and media-processing workflow to start with an online video rather than a file that is already stored locally.

For example:

```text
YouTube / Dailymotion / Other supported website
                    ↓
                  yt-dlp
                    ↓
              Downloaded media
                    ↓
                  Veyra
```

Examples of websites that may be supported include:

- YouTube
- Dailymotion
- Vimeo
- Many other websites supported by yt-dlp

The exact websites, formats, qualities, and download methods available depend on the current capabilities of yt-dlp and the individual website.

Websites can change their video delivery systems, authentication requirements, anti-bot systems, APIs, or other technical details. As a result, downloading from a particular website may stop working until yt-dlp is updated or the website becomes compatible again.

Veyra does not control the websites being downloaded from.

Users are responsible for ensuring that downloading and using media complies with applicable website terms, copyright laws, and other applicable laws.

---

## Subtitle Generation

Subtitle generation is one of the main purposes of Veyra.

Veyra takes video or audio, detects the parts containing speech, transcribes that speech, and uses the resulting text and timing information to create subtitles.

The general workflow is:

```text
Video / Audio
      ↓
FFmpeg
      ↓
Audio preparation
      ↓
Silero VAD
      ↓
Speech segments
      ↓
Speech Recognition
      ↓
Recognized speech
      ↓
Timestamps
      ↓
SRT subtitles
```

The **speech-recognition step exists specifically to generate the text used for subtitles**.

Veyra is therefore not intended to be a general-purpose transcription application. Transcription is part of the subtitle-generation pipeline.

---

## Voice Activity Detection

Veyra uses **Silero VAD (Voice Activity Detection)** to identify portions of audio that contain speech.

The purpose of the VAD stage is to help determine where speech occurs before the audio is sent through the speech-recognition process.

The workflow is approximately:

```text
Audio
  ↓
Silero VAD
  ↓
Speech detected
  ↓
Speech segments
  ↓
Speech recognition
  ↓
Subtitle text
```

Silero VAD runs locally and does not itself require an internet connection.

It helps Veyra distinguish speech-containing portions of audio from silence and other non-speech portions.

---

## Fixed Audio Segments

Veyra uses fixed processing segments as part of its subtitle-generation workflow.

The default processing segment size is:

```text
10 seconds
```

Conceptually, the audio is processed in sections such as:

```text
00:00 ── 00:10
00:10 ── 00:20
00:20 ── 00:30
00:30 ── 00:40
...
```

Silero VAD is used as part of the speech-detection process within this workflow.

The 10-second segmentation approach was chosen because it fits the way Veyra was designed to process speech for subtitle generation.

It is an opinionated design choice and may not be ideal for every type of content.

Different media can produce different results, including:

- Movies
- TV shows
- Interviews
- Podcasts
- Lectures
- Tutorials
- Music
- Multiple speakers
- Background conversations
- Very short dialogue
- Long uninterrupted speech

Subtitle timing and segmentation can therefore vary depending on the content.

---

## Audio Preparation

Before speech recognition, Veyra can use **FFmpeg** to prepare the audio.

Depending on the processing workflow, audio may be extracted from a video and converted into a suitable format such as WAV.

For example:

```text
Video
  ↓
FFmpeg
  ↓
WAV audio
  ↓
Silero VAD
  ↓
Speech Recognition
  ↓
Subtitle generation
```

Preparing the audio into a predictable format helps the speech-recognition component process the input consistently.

FFmpeg is also used by Veyra for other media operations such as conversion, cutting, joining, and subtitle burning.

---

## Speech Recognition for Subtitle Generation

After Veyra identifies speech segments, those segments are passed to the speech-recognition component.

The resulting recognized text is then used to create subtitles.

The workflow is:

```text
Video / Audio
      ↓
Audio extraction
      ↓
Silero VAD
      ↓
Speech segments
      ↓
Speech Recognition
      ↓
Recognized text
      ↓
Timing information
      ↓
SRT subtitle generation
```

For example:

```text
Audio:
"Welcome to the video."

        ↓

Speech Recognition:

"Welcome to the video."

        ↓

Subtitle:

1
00:00:02,100 --> 00:00:05,200
Welcome to the video.
```

The purpose of the speech-recognition stage in Veyra is therefore to turn spoken audio into the text and timing information required for subtitle generation.

---

## SRT Subtitle Output

Veyra generates timestamped subtitles, primarily in SRT format.

A typical SRT file looks like:

```text
1
00:00:02,100 --> 00:00:05,200
Welcome to the video.

2
00:00:05,500 --> 00:00:08,700
Today we are going to discuss this topic.
```

The timestamps are generated from the subtitle-generation and speech-processing workflow.

These subtitles can then be:

- Used as external subtitle files
- Translated into other languages
- Burned permanently into video
- Reused for future processing

---

## Existing Subtitles

Veyra checks for existing subtitle files where possible before performing expensive processing.

For example, if a video already has:

```text
movie.en.srt
```

Veyra can reuse that subtitle rather than transcribing the video again.

This can save:

- Processing time
- Speech-recognition requests
- Network usage
- Translation requests

Translated subtitles can also be reused.

For example:

```text
movie.en.srt
movie.sw.srt
```

If the requested subtitle already exists, Veyra can avoid repeating work that has already been completed.

---

## Subtitle Translation

Veyra can translate generated or existing subtitles into another language.

The general workflow is:

```text
Source SRT
    ↓
Translation Cache
    ↓
Translation Service
    ↓
Translated Text
    ↓
Translated SRT
```

For example:

```text
English subtitles
       ↓
    Translation
       ↓
Swahili subtitles
```

The translation system is designed with several reliability features, including:

- Translation caching
- Retry handling
- Request timeouts
- Persistent HTTP connections
- HTTPX fallback
- Empty-text handling
- Progress reporting
- Error reporting

Translation caching is particularly useful when the same subtitle text is processed more than once.

Instead of repeatedly requesting the same translation, Veyra can reuse the cached result.

Translation still depends on the availability of the external translation service and normally requires an internet connection.

---

## Media Processing

Veyra is not only a subtitle generator.

After subtitles have been generated, Veyra provides media-processing operations that can be used to prepare the final video.

The main media-processing operations include:

```text
Convert
Cut
Join
Burn Subtitles
Inspect
```

These operations rely primarily on **FFmpeg** and **FFprobe**.

---

## Media Conversion

Veyra can convert media between supported formats.

For example:

```text
MKV
 ↓
MP4
```

or:

```text
MOV
 ↓
MP4
```

or:

```text
MP4
 ↓
MKV
```

Depending on the selected options, compatible streams may be copied without re-encoding, or the media may be re-encoded.

Conversion may involve settings such as:

- Video codec
- Audio codec
- Video quality
- CRF
- Encoding preset
- Audio bitrate
- Pixel format
- Faststart
- Subtitle handling
- Metadata handling
- Overwrite behavior

Stream copying can be significantly faster because the existing audio and video streams do not need to be encoded again.

Re-encoding is required when the existing streams are not compatible with the desired output or when the user wants to change properties such as codec, quality, resolution, or other encoding parameters.

---

## Cutting Videos

Veyra can cut media into separate segments.

Depending on the available operation, this can include:

- Duration-based cutting
- Number-of-parts cutting
- Timestamp-based cutting
- Start/end cutting

For example, a one-hour video could be split into 10-minute sections:

```text
One-hour video
      ↓
 ┌─────────────┐
 │   Part 1    │
 ├─────────────┤
 │   Part 2    │
 ├─────────────┤
 │   Part 3    │
 ├─────────────┤
 │   Part 4    │
 ├─────────────┤
 │   Part 5    │
 └─────────────┘
```

Timestamp-based cutting can also be used to define specific boundaries.

For example:

```text
00:00:00
00:05:00
00:12:30
00:20:00
```

can be used to create segments around those timestamps.

Cutting accuracy can depend on how FFmpeg performs the operation.

Stream-copy cuts may depend on keyframes, while more accurate cuts may require re-encoding.

---

## Joining Videos

Veyra can join multiple compatible media files into a single output.

For example:

```text
episode-part-1.mp4
episode-part-2.mp4
episode-part-3.mp4
          ↓
        Veyra
          ↓
episode-complete.mp4
```

The order of the input files matters.

Joining works best when the source files have compatible properties, such as:

- Video codec
- Resolution
- Frame rate
- Audio codec
- Audio properties
- Container
- Stream layout

Files with significantly different properties may require additional processing or conversion before they can be joined correctly.

---

## Burning Subtitles

Veyra can permanently burn subtitles into a video.

Burning subtitles means that the subtitle text becomes part of the visible video image.

The process is approximately:

```text
Video + SRT
     ↓
    FFmpeg
     ↓
Video with permanent subtitles
```

Unlike a normal subtitle track, burned subtitles cannot simply be turned off during playback.

Veyra provides subtitle styling options such as:

- Font
- Font size
- Font color

Common system fonts can be used for subtitle rendering, depending on the operating system and available font configuration.

Burning subtitles normally requires video re-encoding because FFmpeg has to render the subtitle text onto every relevant video frame.

As a result, subtitle burning can take considerably longer than simply adding or copying a subtitle stream.

---

## Media Inspection

Veyra can inspect media files using **FFprobe**.

This can be useful for understanding what is actually contained inside a video or audio file before processing it.

Information can include:

- Duration
- Container format
- Video streams
- Audio streams
- Subtitle streams
- Video codec
- Audio codec
- Resolution
- Frame rate
- Bitrate
- Metadata
- Other information provided by FFprobe

This can help identify why a particular media operation may or may not work as expected.

---

## FFmpeg and FFprobe

Veyra relies heavily on **FFmpeg** and **FFprobe**.

They are used for operations such as:

```text
Extract audio
Convert audio
Convert video
Cut media
Join media
Burn subtitles
Inspect media
```

FFmpeg is therefore an important dependency for Veyra.

### Ubuntu / Debian

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

On Windows and macOS, install an appropriate FFmpeg distribution for the operating system and make sure both `ffmpeg` and `ffprobe` are available to Veyra.

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

Activate it on Linux/macOS:

```bash
source .venv/bin/activate
```

On Windows:

```powershell
.venv\Scripts\activate
```

Install the Python dependencies:

```bash
pip install -r requirements.txt
```

Make sure FFmpeg and FFprobe are also installed and available on the system.

---

## Typical Veyra Workflow

A complete Veyra workflow can look like this:

```text
Online Video
     ↓
yt-dlp
     ↓
Downloaded Video
     ↓
FFmpeg
     ↓
Prepared Audio
     ↓
Silero VAD
     ↓
Speech Segments
     ↓
Speech Recognition
     ↓
SRT Subtitle Generation
     ↓
Subtitle Translation
     ↓
Translated SRT
     ↓
FFmpeg Media Processing
     ↓
Cut / Join / Convert / Burn
     ↓
Finished Video
```

Alternatively, Veyra can start with an existing local media file:

```text
Local Video
     ↓
Audio Preparation
     ↓
Silero VAD
     ↓
Speech Recognition
     ↓
Subtitle Generation
     ↓
Translation
     ↓
Media Processing
     ↓
Finished Media
```

The goal is to provide a practical workflow for downloading, processing, subtitling, translating, and preparing media without having to use a separate application for every step.

---

## Network Requirements

Not every part of Veyra requires an internet connection.

The following components can operate locally:

```text
Silero VAD
FFmpeg
FFprobe
Local media processing
```

However, other parts of the workflow may require internet access:

```text
Media Downloading
        ↓
      Internet

Speech Recognition
        ↓
      Internet

Subtitle Translation
        ↓
      Internet
```

Therefore, the network requirement depends on which Veyra feature is being used.

For example:

```text
Temporary failure in name resolution
```

usually indicates a DNS or network problem.

It does not necessarily mean that Veyra's subtitle or media-processing code is broken.

---

## Errors and Limitations

Veyra was built primarily around my own workflow and preferences.

Because of that, it should be considered a practical personal tool rather than a system that guarantees compatibility with every possible media file, website, codec, language, subtitle format, or external service.

Errors can occur for many reasons.

Possible causes include:

- Corrupt media files
- Unsupported codecs
- Missing FFmpeg components
- Missing fonts
- Invalid subtitle files
- Unusual media containers
- Unsupported audio layouts
- Variable frame rates
- Unsupported websites
- Changes to websites
- Network failures
- DNS failures
- Translation service failures
- Speech-recognition failures
- Poor-quality audio
- Background noise
- Multiple speakers
- Overlapping speech
- Unusual accents
- Unsupported or poorly recognized languages
- Very large files
- Insufficient disk space
- File-permission problems
- Operating-system differences
- Changes in third-party Python libraries
- Changes in external APIs or services

For example, speech recognition may fail even when the video itself is perfectly valid.

A video can play normally but still contain audio that is difficult for the recognition service to understand.

Similarly, a subtitle translation request may fail because of a temporary network or service problem even though the original SRT file is completely valid.

---

## External Services Can Change

Some parts of Veyra depend on software, websites, or services that are outside the control of the project.

Examples include:

- Websites supported by yt-dlp
- Speech-recognition services
- Translation services
- External APIs
- Python libraries
- FFmpeg behavior and supported codecs

These services can change independently of Veyra.

For example, a website may change its download system, or a remote service may change its API behavior.

When this happens, a previously working feature may begin producing errors without any changes to the Veyra code itself.

Updating dependencies or modifying the relevant part of Veyra may then be necessary.

---

## Subtitle Quality

Automatic subtitle generation is not guaranteed to be perfect.

The quality of generated subtitles depends on several factors, including:

- Audio quality
- Background noise
- Speaker clarity
- Speaker accents
- Language
- Speaking speed
- Multiple speakers
- Overlapping speech
- Music or sound effects
- Microphone quality
- Speech-recognition service accuracy

For this reason, generated subtitles may sometimes require manual correction.

Veyra is intended to make subtitle generation faster and easier, not to guarantee perfectly edited subtitles for every video.

---

## Why Veyra Was Built This Way

Veyra was built to solve the media-processing tasks that I personally work with repeatedly.

The application is therefore based on practical preferences rather than an attempt to implement every possible media feature.

Some of the choices made in Veyra include:

- **yt-dlp** for downloading media
- **FFmpeg** for audio and video processing
- **FFprobe** for media inspection
- **Silero VAD** for local voice activity detection
- Fixed processing segments, with **10 seconds** as the default
- Speech recognition for generating subtitle text
- **SRT** as the primary subtitle format
- Subtitle translation with caching and retry handling
- FFmpeg-based subtitle burning
- Media cutting
- Media joining
- Media conversion
- Media inspection

These choices reflect the workflow the application was designed around.

They may not be the best choices for every user, every operating system, or every type of media.

If your workflow is different, you may need to modify the application or its processing settings.

---

## Credits

Veyra was developed with help and inspiration from **PyAutoSRT** by Bot Bahlul.

PyAutoSRT provided a useful reference for automatic speech recognition, subtitle generation, and translation workflows.

Veyra also uses **Silero VAD** for local voice activity detection and **yt-dlp** for media downloading.

Veyra is an independent project and is not affiliated with or endorsed by PyAutoSRT, Silero, yt-dlp, or Google.

---

## License

Veyra is released under the MIT License.

See the `LICENSE` file for the complete license text.
