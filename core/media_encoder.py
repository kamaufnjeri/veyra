from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from typing import Any, Callable, Dict, List, Optional


class MediaEncoder:
    """
    Intelligent MP4 processor.

    TARGET MP4
    ----------
    Video:
        H.264 / AVC1
        yuv420p

    Audio:
        AAC / MP4A

    SUBTITLES
    ----------
    Never copied.
    Never embedded.

    DECISION TREE
    -------------
    H264 + AAC + yuv420p + MP4
        -> NOTHING

    H264 + AAC + yuv420p + non-MP4
        -> REMUX ONLY

    H264 + AAC + wrong pixel format
        -> VIDEO ENCODE ONLY

    H264 + wrong audio
        -> COPY VIDEO
        -> ENCODE AUDIO

    wrong video + AAC
        -> ENCODE VIDEO
        -> COPY AUDIO

    wrong video + wrong audio
        -> ENCODE BOTH

    The goal is to avoid unnecessary encoding.
    """

    VIDEO_FORMATS = {
        "mp4",
        "mkv",
        "webm",
    }

    AUDIO_FORMATS = {
        "mp3",
        "m4a",
        "aac",
        "opus",
        "wav",
        "flac",
    }

    H264_CODECS = {
        "h264",
        "avc",
        "avc1",
    }

    AAC_CODECS = {
        "aac",
        "mp4a",
    }

    def __init__(
        self,
        progress_callback: Optional[Callable[..., None]] = None,
        error_callback: Optional[Callable[[Any], None]] = None,
        ffmpeg_path: Optional[str] = None,
        ffprobe_path: Optional[str] = None,
    ) -> None:

        self.progress_callback = progress_callback
        self.error_callback = error_callback

        self.ffmpeg_path = (
            ffmpeg_path
            or shutil.which("ffmpeg")
        )

        self.ffprobe_path = (
            ffprobe_path
            or shutil.which("ffprobe")
        )

        self._cancel_event = threading.Event()
        self._process: Optional[subprocess.Popen] = None

        self._duration = 0.0
        self._started_at = 0.0
        self._last_emit = 0.0

    # ==========================================================
    # PUBLIC
    # ==========================================================

    def encode(
        self,
        input_filepath: str,
        output_format: str = "mp4",
        force_reencode: Optional[bool] = None,
    ) -> Optional[str]:

        self.reset_cancel()
        self._require_ffmpeg()

        input_filepath = os.path.abspath(
            input_filepath
        )

        if not os.path.isfile(input_filepath):
            raise FileNotFoundError(
                input_filepath
            )

        output_format = str(
            output_format or ""
        ).strip().lower().lstrip(".")

        if output_format not in self.VIDEO_FORMATS:
            raise ValueError(
                f"Unsupported output format: {output_format}"
            )

        if output_format == "mp4":
            return self._prepare_mp4(
                input_filepath,
                force_reencode,
            )

        output_filepath = self._change_extension(
            input_filepath,
            output_format,
        )

        if (
            os.path.abspath(output_filepath)
            == os.path.abspath(input_filepath)
        ):
            return input_filepath

        if force_reencode is True:
            return self._encode_video(
                input_filepath,
                output_filepath,
                output_format,
            )

        # First attempt a stream copy.
        try:
            self._remux(
                input_filepath,
                output_filepath,
                output_format,
            )

            if os.path.isfile(output_filepath):
                self._safe_remove(input_filepath)
                return output_filepath

        except Exception:
            if self._cancel_event.is_set():
                raise

            self._safe_remove(output_filepath)

        # Only encode if remux isn't possible.
        return self._encode_video(
            input_filepath,
            output_filepath,
            output_format,
        )

    # ==========================================================
    # MP4 DECISION ENGINE
    # ==========================================================

    def _prepare_mp4(
        self,
        input_filepath: str,
        force_reencode: Optional[bool],
    ) -> Optional[str]:

        self._check_cancelled()

        info = self._probe(input_filepath)

        video_codec = self._normalize_codec(
            info.get("video_codec")
        )

        audio_codec = self._normalize_codec(
            info.get("audio_codec")
        )

        pixel_format = str(
            info.get("pixel_format", "")
            or ""
        ).strip().lower()

        duration = self._safe_float(
            info.get("duration"),
            0.0,
        )

        self._duration = duration

        extension = (
            os.path.splitext(input_filepath)[1]
            .lower()
        )

        output_filepath = (
            input_filepath
            if extension == ".mp4"
            else self._change_extension(
                input_filepath,
                "mp4",
            )
        )

        filename = os.path.basename(
            input_filepath
        )

        # ------------------------------------------------------
        # FORCE
        # ------------------------------------------------------

        if force_reencode is True:
            self._progress(
                "Encoding H.264/AAC",
                filename,
                0,
            )

            return self._encode_mp4(
                input_filepath,
                output_filepath,
            )

        # ------------------------------------------------------
        # PERFECT MP4
        #
        # ZERO FFMPEG.
        # ------------------------------------------------------

        if (
            extension == ".mp4"
            and video_codec in self.H264_CODECS
            and audio_codec in self.AAC_CODECS
            and pixel_format == "yuv420p"
        ):

            self._progress(
                "MP4 already compatible - no encoding",
                filename,
                100,
            )

            return input_filepath

        # ------------------------------------------------------
        # COMPATIBLE STREAMS, WRONG CONTAINER
        #
        # REMUX ONLY.
        # ------------------------------------------------------

        if (
            video_codec in self.H264_CODECS
            and audio_codec in self.AAC_CODECS
            and pixel_format == "yuv420p"
        ):

            self._progress(
                "Remuxing to MP4 - no re-encoding",
                filename,
                0,
            )

            self._remux_video_audio(
                input_filepath,
                output_filepath,
                copy_video=True,
                copy_audio=True,
            )

            self._safe_remove(
                input_filepath
            )

            self._progress(
                "MP4 ready - no re-encoding",
                os.path.basename(output_filepath),
                100,
            )

            return output_filepath

        # ------------------------------------------------------
        # H264 VIDEO + AAC AUDIO
        # WRONG PIXEL FORMAT
        #
        # Only video.
        # ------------------------------------------------------

        if (
            video_codec in self.H264_CODECS
            and audio_codec in self.AAC_CODECS
            and pixel_format != "yuv420p"
        ):

            self._progress(
                "Converting video pixel format only",
                filename,
                0,
            )

            self._encode_video_only(
                input_filepath,
                output_filepath,
                copy_audio=True,
            )

            self._safe_remove(
                input_filepath
            )

            self._progress(
                "MP4 ready - audio was not re-encoded",
                os.path.basename(output_filepath),
                100,
            )

            return output_filepath

        # ------------------------------------------------------
        # H264 VIDEO
        # WRONG AUDIO
        #
        # Copy video.
        # Encode audio.
        # ------------------------------------------------------

        if video_codec in self.H264_CODECS:

            self._progress(
                "H.264 detected - converting audio only",
                filename,
                0,
            )

            self._remux_video_audio(
                input_filepath,
                output_filepath,
                copy_video=True,
                copy_audio=False,
            )

            self._safe_remove(
                input_filepath
            )

            self._progress(
                "MP4 ready - video was not re-encoded",
                os.path.basename(output_filepath),
                100,
            )

            return output_filepath

        # ------------------------------------------------------
        # AAC AUDIO
        # WRONG VIDEO
        #
        # Copy audio.
        # Encode video.
        # ------------------------------------------------------

        if audio_codec in self.AAC_CODECS:

            self._progress(
                "AAC detected - converting video only",
                filename,
                0,
            )

            self._encode_video_only(
                input_filepath,
                output_filepath,
                copy_audio=True,
            )

            self._safe_remove(
                input_filepath
            )

            self._progress(
                "MP4 ready - audio was not re-encoded",
                os.path.basename(output_filepath),
                100,
            )

            return output_filepath

        # ------------------------------------------------------
        # BOTH WRONG
        #
        # Only here do we encode both.
        # ------------------------------------------------------

        self._progress(
            "Converting video to H.264 and audio to AAC",
            filename,
            0,
        )

        return self._encode_mp4(
            input_filepath,
            output_filepath,
        )

    # ==========================================================
    # REMUX / PARTIAL ENCODE
    # ==========================================================

    def _remux_video_audio(
        self,
        input_filepath: str,
        output_filepath: str,
        copy_video: bool,
        copy_audio: bool,
    ) -> None:

        temp_filepath = self._temp_path(
            output_filepath,
            "veyra",
        )

        command = [
            self.ffmpeg_path,
            "-y",
            "-i",
            input_filepath,

            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
        ]

        if copy_video:
            command += [
                "-c:v",
                "copy",
            ]
        else:
            command += [
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-crf",
                "23",
                "-pix_fmt",
                "yuv420p",
            ]

        if copy_audio:
            command += [
                "-c:a",
                "copy",
            ]
        else:
            command += [
                "-c:a",
                "aac",
                "-b:a",
                "160k",
            ]

        command += [
            "-sn",
            "-dn",
            "-movflags",
            "+faststart",
            "-progress",
            "pipe:1",
            "-nostats",
            temp_filepath,
        ]

        try:
            self._run(command)

            if not os.path.isfile(temp_filepath):
                raise RuntimeError(
                    "FFmpeg did not create the MP4."
                )

            self._safe_remove(
                output_filepath
            )

            os.replace(
                temp_filepath,
                output_filepath,
            )

        finally:
            self._safe_remove(
                temp_filepath
            )

    # ==========================================================
    # VIDEO ONLY
    # ==========================================================

    def _encode_video_only(
        self,
        input_filepath: str,
        output_filepath: str,
        copy_audio: bool = True,
    ) -> None:

        temp_filepath = self._temp_path(
            output_filepath,
            "veyra-video",
        )

        command = [
            self.ffmpeg_path,
            "-y",
            "-i",
            input_filepath,

            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",

            "-c:v",
            "libx264",

            # Fast encoding.
            "-preset",
            "ultrafast",

            "-crf",
            "23",

            "-pix_fmt",
            "yuv420p",
        ]

        if copy_audio:
            command += [
                "-c:a",
                "copy",
            ]
        else:
            command += [
                "-c:a",
                "aac",
                "-b:a",
                "160k",
            ]

        command += [
            "-sn",
            "-dn",
            "-movflags",
            "+faststart",
            "-progress",
            "pipe:1",
            "-nostats",
            temp_filepath,
        ]

        try:
            self._run(command)

            if not os.path.isfile(temp_filepath):
                raise RuntimeError(
                    "FFmpeg failed to encode the video."
                )

            self._safe_remove(
                output_filepath
            )

            os.replace(
                temp_filepath,
                output_filepath,
            )

        finally:
            self._safe_remove(
                temp_filepath
            )

    # ==========================================================
    # FULL MP4
    # ==========================================================

    def _encode_mp4(
        self,
        input_filepath: str,
        output_filepath: str,
    ) -> Optional[str]:

        temp_filepath = self._temp_path(
            output_filepath,
            "veyra-h264",
        )

        command = [
            self.ffmpeg_path,
            "-y",
            "-i",
            input_filepath,

            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",

            "-c:v",
            "libx264",

            "-preset",
            "ultrafast",

            "-crf",
            "23",

            "-pix_fmt",
            "yuv420p",

            "-c:a",
            "aac",

            "-b:a",
            "160k",

            "-sn",
            "-dn",

            "-movflags",
            "+faststart",

            "-progress",
            "pipe:1",
            "-nostats",

            temp_filepath,
        ]

        try:
            self._run(command)

            if not os.path.isfile(temp_filepath):
                raise RuntimeError(
                    "FFmpeg did not create the H.264 MP4."
                )

            self._safe_remove(
                output_filepath
            )

            os.replace(
                temp_filepath,
                output_filepath,
            )

            self._safe_remove(
                input_filepath
            )

            self._progress(
                "H.264/AAC MP4 complete",
                os.path.basename(output_filepath),
                100,
            )

            return output_filepath

        finally:
            self._safe_remove(
                temp_filepath
            )

    # ==========================================================
    # GENERIC ENCODE
    # ==========================================================

    def _encode_video(
        self,
        input_filepath: str,
        output_filepath: str,
        output_format: str,
    ) -> Optional[str]:

        self._duration = self._probe_duration(
            input_filepath
        )

        command = [
            self.ffmpeg_path,
            "-y",
            "-i",
            input_filepath,

            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",

            "-sn",
            "-dn",
        ]

        command += self._encoding_arguments(
            output_format
        )

        command += [
            "-progress",
            "pipe:1",
            "-nostats",
            output_filepath,
        ]

        self._progress(
            "Encoding media",
            os.path.basename(input_filepath),
            0,
        )

        self._run(command)

        if not os.path.isfile(output_filepath):
            raise RuntimeError(
                "FFmpeg output was not created."
            )

        self._safe_remove(
            input_filepath
        )

        self._progress(
            "Media encoding complete",
            os.path.basename(output_filepath),
            100,
        )

        return output_filepath

    # ==========================================================
    # REMUX
    # ==========================================================

    def _remux(
        self,
        input_filepath: str,
        output_filepath: str,
        output_format: str,
    ) -> None:

        command = [
            self.ffmpeg_path,
            "-y",
            "-i",
            input_filepath,

            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",

            "-c",
            "copy",

            "-sn",
            "-dn",
        ]

        if output_format == "mp4":
            command += [
                "-movflags",
                "+faststart",
            ]

        command += [
            "-progress",
            "pipe:1",
            "-nostats",
            output_filepath,
        ]

        self._run(command)

    # ==========================================================
    # PROBE
    # ==========================================================

    def _probe(
        self,
        filepath: str,
    ) -> Dict[str, Any]:

        if not self.ffprobe_path:
            return {}

        command = [
            self.ffprobe_path,

            "-v",
            "error",

            "-show_entries",
            (
                "format=duration:"
                "stream=codec_type,codec_name,pix_fmt"
            ),

            "-of",
            "json",

            filepath,
        ]

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
        except Exception:
            return {}

        if result.returncode != 0:
            return {}

        try:
            data = json.loads(
                result.stdout
            )
        except Exception:
            return {}

        video_codec = None
        audio_codec = None
        pixel_format = None

        for stream in data.get(
            "streams",
            [],
        ):

            if not isinstance(stream, dict):
                continue

            codec_type = stream.get(
                "codec_type"
            )

            if (
                codec_type == "video"
                and video_codec is None
            ):
                video_codec = stream.get(
                    "codec_name"
                )

                pixel_format = stream.get(
                    "pix_fmt"
                )

            elif (
                codec_type == "audio"
                and audio_codec is None
            ):
                audio_codec = stream.get(
                    "codec_name"
                )

        duration = self._safe_float(
            data.get("format", {}).get(
                "duration"
            ),
            0.0,
        )

        return {
            "video_codec": video_codec,
            "audio_codec": audio_codec,
            "pixel_format": pixel_format,
            "duration": duration,
        }

    def _probe_duration(
        self,
        filepath: str,
    ) -> float:

        return self._safe_float(
            self._probe(filepath).get("duration"),
            0.0,
        )

    # ==========================================================
    # AUDIO
    # ==========================================================

    def encode_audio(
        self,
        input_filepath: str,
        output_format: str = "mp3",
        bitrate: str = "320k",
    ) -> Optional[str]:

        self.reset_cancel()
        self._require_ffmpeg()

        input_filepath = os.path.abspath(
            input_filepath
        )

        if not os.path.isfile(input_filepath):
            raise FileNotFoundError(
                input_filepath
            )

        output_format = str(
            output_format
        ).strip().lower().lstrip(".")

        if output_format not in self.AUDIO_FORMATS:
            raise ValueError(
                f"Unsupported audio format: {output_format}"
            )

        output_filepath = (
            os.path.splitext(input_filepath)[0]
            + "."
            + output_format
        )

        self._duration = self._probe_duration(
            input_filepath
        )

        command = [
            self.ffmpeg_path,
            "-y",
            "-i",
            input_filepath,

            "-vn",

            "-b:a",
            str(bitrate),

            "-progress",
            "pipe:1",
            "-nostats",

            output_filepath,
        ]

        self._progress(
            "Encoding audio",
            os.path.basename(input_filepath),
            0,
        )

        self._run(command)

        if not os.path.isfile(output_filepath):
            raise RuntimeError(
                "Audio encoding failed."
            )

        self._safe_remove(
            input_filepath
        )

        self._progress(
            "Audio encoding complete",
            os.path.basename(output_filepath),
            100,
        )

        return output_filepath

    # ==========================================================
    # FFMPEG ARGUMENTS
    # ==========================================================

    @staticmethod
    def _encoding_arguments(
        output_format: str,
    ) -> List[str]:

        if output_format == "mp4":
            return [
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-crf",
                "23",
                "-pix_fmt",
                "yuv420p",

                "-c:a",
                "aac",
                "-b:a",
                "160k",

                "-movflags",
                "+faststart",
            ]

        if output_format == "webm":
            return [
                "-c:v",
                "libvpx-vp9",
                "-deadline",
                "realtime",
                "-cpu-used",
                "8",
                "-crf",
                "32",
                "-b:v",
                "0",

                "-c:a",
                "libopus",
                "-b:a",
                "128k",
            ]

        if output_format == "mkv":
            return [
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-crf",
                "23",
                "-pix_fmt",
                "yuv420p",

                "-c:a",
                "aac",
                "-b:a",
                "160k",
            ]

        raise ValueError(
            f"Unsupported format: {output_format}"
        )

    # ==========================================================
    # FFMPEG PROCESS
    # ==========================================================

    def _run(
        self,
        command: List[str],
    ) -> None:

        self._check_cancelled()

        self._started_at = time.monotonic()
        self._last_emit = 0.0

        process: Optional[subprocess.Popen] = None
        return_code = -1

        stderr_lines: List[str] = []

        try:

            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )

            self._process = process

            stderr_thread = threading.Thread(
                target=self._read_stderr,
                args=(
                    process,
                    stderr_lines,
                ),
                daemon=True,
            )

            stderr_thread.start()

            if process.stdout is not None:

                for raw_line in process.stdout:

                    self._check_cancelled()

                    line = raw_line.strip()

                    if (
                        not line
                        or "=" not in line
                    ):
                        continue

                    key, value = line.split(
                        "=",
                        1,
                    )

                    if key == "out_time_ms":
                        self._ffmpeg_progress(
                            value
                        )

            return_code = process.wait()

            stderr_thread.join(
                timeout=2
            )

        except FileNotFoundError as exc:

            raise RuntimeError(
                "FFmpeg was not found."
            ) from exc

        finally:

            self._process = None

        self._check_cancelled()

        if return_code != 0:

            error_text = "\n".join(
                stderr_lines
            ).strip()

            raise RuntimeError(
                "FFmpeg failed "
                f"(exit code {return_code}).\n"
                f"{error_text[-4000:]}"
            )

    @staticmethod
    def _read_stderr(
        process: subprocess.Popen,
        lines: List[str],
    ) -> None:

        if process.stderr is None:
            return

        try:
            for line in process.stderr:
                line = line.strip()

                if line:
                    lines.append(line)

        except Exception:
            pass

    # ==========================================================
    # FFMPEG PROGRESS
    # ==========================================================

    def _ffmpeg_progress(
        self,
        out_time_ms: str,
    ) -> None:

        try:
            seconds = (
                float(out_time_ms)
                / 1_000_000.0
            )
        except (
            TypeError,
            ValueError,
        ):
            return

        if self._duration <= 0:
            self._progress(
                "Processing media",
                "Media",
                0,
            )
            return

        percentage = int(
            seconds
            / self._duration
            * 100
        )

        percentage = max(
            0,
            min(
                99,
                percentage,
            ),
        )

        now = time.monotonic()

        if (
            now - self._last_emit
            < 0.20
        ):
            return

        self._last_emit = now

        elapsed = (
            now - self._started_at
        )

        speed = "--"
        eta = None

        if (
            seconds > 0
            and elapsed > 0
        ):

            ratio = (
                seconds / elapsed
            )

            speed = f"{ratio:.2f}x"

            if ratio > 0:
                eta = int(
                    max(
                        0,
                        self._duration - seconds,
                    )
                    / ratio
                )

        self._progress(
            "Processing media",
            "Media",
            percentage,
            None,
            speed,
            self._format_seconds(eta),
        )

    # ==========================================================
    # CANCEL
    # ==========================================================

    def cancel(self) -> None:

        self._cancel_event.set()

        process = self._process

        if process is not None:
            try:
                process.terminate()
            except Exception:
                pass

    def reset_cancel(self) -> None:
        self._cancel_event.clear()

    def _check_cancelled(self) -> None:

        if not self._cancel_event.is_set():
            return

        process = self._process

        if process is not None:
            try:
                process.kill()
            except Exception:
                pass

        raise RuntimeError(
            "Media operation cancelled."
        )

    # ==========================================================
    # VALIDATION
    # ==========================================================

    def _require_ffmpeg(self) -> None:

        if not self.ffmpeg_path:
            raise RuntimeError(
                "FFmpeg was not found. "
                "Install FFmpeg and make sure "
                "ffmpeg is available on PATH."
            )

    # ==========================================================
    # HELPERS
    # ==========================================================

    @staticmethod
    def _normalize_codec(
        codec: Any,
    ) -> str:

        value = str(
            codec or ""
        ).strip().lower()

        if value in {
            "avc",
            "avc1",
        }:
            return "h264"

        if value.startswith("mp4a"):
            return "aac"

        return value

    @staticmethod
    def _temp_path(
        output_filepath: str,
        suffix: str,
    ) -> str:

        base = os.path.splitext(
            output_filepath
        )[0]

        return (
            f"{base}.{suffix}.tmp.mp4"
        )

    @staticmethod
    def _safe_remove(
        filepath: str,
    ) -> None:

        try:
            if (
                filepath
                and os.path.isfile(filepath)
            ):
                os.remove(filepath)
        except OSError:
            pass

    @staticmethod
    def _change_extension(
        filepath: str,
        extension: str,
    ) -> str:

        return (
            os.path.splitext(filepath)[0]
            + "."
            + extension
        )

    @staticmethod
    def _safe_float(
        value: Any,
        default: float,
    ) -> float:

        try:
            return float(value)
        except (
            TypeError,
            ValueError,
        ):
            return default

    # ==========================================================
    # PROGRESS
    # ==========================================================

    def _progress(
        self,
        info: str,
        filename: str,
        percentage: int,
        downloaded: Any = None,
        speed: Any = None,
        eta: Any = None,
    ) -> None:

        if not self.progress_callback:
            return

        percentage = max(
            0,
            min(
                100,
                int(percentage),
            ),
        )

        try:
            self.progress_callback(
                info,
                filename,
                percentage,
                downloaded,
                speed,
                eta,
            )

        except TypeError:

            try:
                self.progress_callback(
                    info,
                    filename,
                    percentage,
                )
            except Exception:
                pass

        except Exception:
            pass

    # ==========================================================
    # FORMATTING
    # ==========================================================

    @staticmethod
    def _format_seconds(
        value: Any,
    ) -> str:

        if value is None:
            return "--:--"

        try:
            value = max(
                0,
                int(value),
            )
        except (
            TypeError,
            ValueError,
        ):
            return "--:--"

        hours, remainder = divmod(
            value,
            3600,
        )

        minutes, seconds = divmod(
            remainder,
            60,
        )

        if hours:
            return (
                f"{hours:02d}:"
                f"{minutes:02d}:"
                f"{seconds:02d}"
            )

        return (
            f"{minutes:02d}:"
            f"{seconds:02d}"
        )