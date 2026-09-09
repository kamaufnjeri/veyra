from __future__ import annotations

from pathlib import Path

from .ffmpeg import FFmpeg
from .models import BurnResult, BurnerSettings


class SubtitleBurner:
    """
    Burns subtitles permanently into a video.

    Notes:
    - Subtitle burning always requires video re-encoding.
    - Audio is copied when possible to reduce processing time.
    - CPU encoding is deliberately limited to reduce system load.
    - ASS/SSA styling is preserved unless the user explicitly
      provides style overrides.
    """

    def __init__(
        self,
        *,
        ffmpeg="ffmpeg",
        ffprobe="ffprobe",
        progress_callback=None,
        cancellation_callback=None,
    ):
        self.ff = FFmpeg(
            ffmpeg=ffmpeg,
            ffprobe=ffprobe,
            progress_callback=progress_callback,
            cancellation_callback=cancellation_callback,
        )

    # ========================================================
    # BURN
    # ========================================================

    def burn(
        self,
        video: str | Path,
        subtitle: str | Path,
        output: str | Path,
        settings: BurnerSettings | None = None,
    ) -> BurnResult:

        settings = settings or BurnerSettings()
        settings.validate()

        video = Path(video)
        subtitle = Path(subtitle)
        output = Path(output)

        # ----------------------------------------------------
        # VALIDATE INPUTS
        # ----------------------------------------------------

        self.ff.validate_input(video)
        self.ff.validate_input(subtitle)

        self.ff.validate_output(
            video,
            output,
            settings.overwrite,
        )

        # ----------------------------------------------------
        # DURATION
        # ----------------------------------------------------

        duration = self.ff.duration(video)

        # ----------------------------------------------------
        # TEMPORARY OUTPUT
        # ----------------------------------------------------

        temp = self.ff.temporary_path(
            output.suffix or ".mp4"
        )

        # ----------------------------------------------------
        # SUBTITLE FILTER
        # ----------------------------------------------------

        subtitle_filter = self._subtitle_filter(
            subtitle,
            settings,
        )

        # ----------------------------------------------------
        # BASE COMMAND
        # ----------------------------------------------------

        command = [
            self.ff.ffmpeg,

            "-hide_banner",
            "-y",
            "-nostdin",

            # Input
            "-i",
            str(video),

            # Burn subtitles
            "-vf",
            subtitle_filter,

            # Video stream
            "-map",
            "0:v:0?",

            # Audio streams, if present
            "-map",
            "0:a?",
        ]

        # ----------------------------------------------------
        # VIDEO
        #
        # Burning subtitles requires video encoding.
        #
        # We deliberately limit the number of CPU threads.
        # This prevents FFmpeg from consuming the entire CPU
        # and making the application/system appear frozen.
        # ----------------------------------------------------

        command += [
            "-c:v",
            settings.video_codec,

            "-preset",
            settings.preset,

            "-crf",
            str(settings.crf),

            "-pix_fmt",
            settings.pixel_format,

            # Keep CPU usage under control.
            "-threads",
            "2",
        ]

        # ----------------------------------------------------
        # AUDIO
        # ----------------------------------------------------

        if settings.audio_mode == "fast_copy":
            command += [
                "-c:a",
                "copy",
            ]
        else:
            command += [
                "-c:a",
                settings.audio_codec,

                "-b:a",
                settings.audio_bitrate,
            ]

        # ----------------------------------------------------
        # FASTSTART
        # ----------------------------------------------------

        if (
            settings.faststart
            and output.suffix.lower()
            in {".mp4", ".m4v", ".mov"}
        ):
            command += [
                "-movflags",
                "+faststart",
            ]

        # ----------------------------------------------------
        # OUTPUT
        # ----------------------------------------------------

        command.append(str(temp))

        # ----------------------------------------------------
        # RUN
        # ----------------------------------------------------

        try:
            self.ff.run(
                command,
                message="Burning subtitles",
                duration=duration,
            )

            # ------------------------------------------------
            # ATOMIC REPLACE
            # ------------------------------------------------

            self.ff.atomic_replace(
                temp,
                output,
            )

            return BurnResult(
                source=video,
                subtitle=subtitle,
                output=output,
                duration=duration,
            )

        finally:
            self.ff.cleanup()

    # ========================================================
    # SUBTITLE FILTER
    # ========================================================

    @staticmethod
    def _subtitle_filter(
        subtitle: Path,
        settings: BurnerSettings,
    ) -> str:
        """
        Build the FFmpeg subtitles filter.

        ASS/SSA files normally contain their own styling.
        We preserve that styling unless the user has selected
        explicit font/size/color overrides.

        SRT/VTT/etc. can also receive force_style options.
        """

        path = SubtitleBurner._escape_filter_path(
            subtitle
        )

        options: list[str] = []

        # ----------------------------------------------------
        # FONT
        # ----------------------------------------------------

        if settings.subtitle_font:
            font = str(settings.subtitle_font)

            # Escape characters that could interfere with
            # FFmpeg's filter parser.
            font = (
                font
                .replace("\\", r"\\")
                .replace(",", r"\,")
                .replace("'", r"\'")
            )

            options.append(
                f"FontName={font}"
            )

        # ----------------------------------------------------
        # FONT SIZE
        # ----------------------------------------------------

        if settings.subtitle_font_size:
            options.append(
                f"FontSize={settings.subtitle_font_size}"
            )

        # ----------------------------------------------------
        # COLOR
        # ----------------------------------------------------

        if settings.subtitle_color:
            ass_color = SubtitleBurner._to_ass_color(
                settings.subtitle_color
            )

            options.append(
                f"PrimaryColour={ass_color}"
            )

        # ----------------------------------------------------
        # BUILD FILTER
        # ----------------------------------------------------

        if options:
            force_style = ",".join(options)

            return (
                f"subtitles='{path}':"
                f"force_style='{force_style}'"
            )

        return f"subtitles='{path}'"

    # ========================================================
    # PATH ESCAPING
    # ========================================================

    @staticmethod
    def _escape_filter_path(
        subtitle: Path,
    ) -> str:
        """
        Escape a subtitle path for FFmpeg's filter parser.

        This is particularly important on Windows where paths
        commonly contain drive letters such as C:\\.
        """

        path = str(subtitle.resolve())

        path = path.replace("\\", "/")

        # FFmpeg filter syntax treats ':' specially.
        path = path.replace(":", r"\:")

        # Protect single quotes.
        path = path.replace("'", r"\'")

        return path

    # ========================================================
    # COLOR CONVERSION
    # ========================================================

    @staticmethod
    def _to_ass_color(
        color: str,
    ) -> str:
        """
        Convert common user-facing colors into ASS/SSA color
        notation.

        ASS uses:
            &HAABBGGRR

        The AA component is kept at 00 (opaque).
        """

        value = str(color).strip().lower()

        # ----------------------------------------------------
        # Common named colors
        # ----------------------------------------------------

        named_colors = {
            "white": "FFFFFF",
            "black": "000000",
            "red": "FF0000",
            "green": "00FF00",
            "blue": "0000FF",
            "yellow": "FFFF00",
            "cyan": "00FFFF",
            "magenta": "FF00FF",
            "orange": "FFA500",
            "purple": "800080",
            "gray": "808080",
            "grey": "808080",
        }

        if value in named_colors:
            value = named_colors[value]

        # ----------------------------------------------------
        # #RRGGBB
        # ----------------------------------------------------

        elif value.startswith("#"):
            value = value[1:]

        # ----------------------------------------------------
        # RRGGBB
        # ----------------------------------------------------

        elif len(value) == 6:
            value = value

        # ----------------------------------------------------
        # Already ASS format
        # ----------------------------------------------------

        elif value.startswith("&h"):
            return value.upper()

        # ----------------------------------------------------
        # Invalid color
        # ----------------------------------------------------

        else:
            # Fall back to white rather than generating an
            # invalid FFmpeg filter.
            value = "FFFFFF"

        # ----------------------------------------------------
        # Validate RGB
        # ----------------------------------------------------

        if len(value) != 6:
            value = "FFFFFF"

        try:
            int(value, 16)
        except ValueError:
            value = "FFFFFF"

        # ----------------------------------------------------
        # RRGGBB -> BBGGRR
        # ----------------------------------------------------

        red = value[0:2]
        green = value[2:4]
        blue = value[4:6]

        return (
            f"&H00{blue}{green}{red}".upper()
        )