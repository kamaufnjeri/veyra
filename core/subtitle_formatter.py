from __future__ import annotations

import json
from typing import List, Tuple, Union, Optional


class SubtitleFormatter:

    supported_formats = [
        "srt",
        "vtt",
        "json",
        "raw",
    ]

    def __init__(
        self,
        format_type: str,
        error_messages_callback=None,
    ):
        self.format_type = format_type.lower()
        self.error_messages_callback = error_messages_callback

        if self.format_type not in self.supported_formats:
            raise ValueError(f"Unsupported subtitle format: {self.format_type}")

        

    def __call__(
        self,
        subtitles: List[Union[Tuple[Tuple[float, float], str], Tuple[float, float, str]]],
        padding_before: float = 0.0,
        padding_after: float = 0.0,
    ) -> Optional[str]:
        try:
            # Standardize input format into tuples of ((start, end), text)
            normalized_subtitles = self._normalize_subtitles(subtitles)

            if self.format_type == "srt":
                return self.srt_formatter(
                    normalized_subtitles, padding_before, padding_after
                )

            if self.format_type == "vtt":
                return self.vtt_formatter(
                    normalized_subtitles, padding_before, padding_after
                )

            if self.format_type == "json":
                return self.json_formatter(normalized_subtitles)

            if self.format_type == "raw":
                return self.raw_formatter(normalized_subtitles)

            raise ValueError(f"Unsupported format type: {self.format_type}")

        except KeyboardInterrupt:
            self._error("Cancelling all tasks")
            return None

        except Exception as exc:
            self._error(exc)
            return None

    def format(
        self,
        regions,
        transcripts,
        padding_before: float = 0.0,
        padding_after: float = 0.0,
    ) -> Optional[str]:
        """
        Compatibility method used by SubtitleService.

        Converts regions + transcripts into the structure
        expected by __call__().
        """
        subtitles = [
            (region, transcript)
            for region, transcript in zip(regions, transcripts)
            if transcript and str(transcript).strip()
        ]

        return self(
            subtitles,
            padding_before=padding_before,
            padding_after=padding_after,
        )
    # ----------------------------------------------------------
    # Formatters
    # ----------------------------------------------------------

    def srt_formatter(
        self,
        subtitles: List[Tuple[Tuple[float, float], str]],
        padding_before: float = 0.0,
        padding_after: float = 0.0,
    ) -> str:
        blocks = []
        for index, ((start, end), text) in enumerate(subtitles, start=1):
            start_sec = max(0.0, start - padding_before)
            end_sec = max(start_sec, end + padding_after)

            start_tc = self._format_timecode(start_sec, decimal_marker=",")
            end_tc = self._format_timecode(end_sec, decimal_marker=",")

            blocks.append(f"{index}\n{start_tc} --> {end_tc}\n{str(text).strip()}\n")

        return "\n".join(blocks)

    def vtt_formatter(
        self,
        subtitles: List[Tuple[Tuple[float, float], str]],
        padding_before: float = 0.0,
        padding_after: float = 0.0,
    ) -> str:
        blocks = ["WEBVTT\n"]
        for index, ((start, end), text) in enumerate(subtitles, start=1):
            start_sec = max(0.0, start - padding_before)
            end_sec = max(start_sec, end + padding_after)

            # WebVTT uses period '.' as millisecond separator
            start_tc = self._format_timecode(start_sec, decimal_marker=".")
            end_tc = self._format_timecode(end_sec, decimal_marker=".")

            blocks.append(f"{index}\n{start_tc} --> {end_tc}\n{str(text).strip()}\n")

        return "\n".join(blocks)

    def json_formatter(
        self,
        subtitles: List[Tuple[Tuple[float, float], str]],
    ) -> str:
        subtitle_dicts = [
            {
                "start": start,
                "end": end,
                "content": str(text),
            }
            for (start, end), text in subtitles
        ]
        return json.dumps(subtitle_dicts, ensure_ascii=False, indent=2)

    def raw_formatter(
        self,
        subtitles: List[Tuple[Tuple[float, float], str]],
    ) -> str:
        return " ".join(str(text).strip() for _range, text in subtitles if text)

    # ----------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------

    @staticmethod
    def _format_timecode(seconds: float, decimal_marker: str = ",") -> str:
        """Formattings seconds into HH:MM:SS,mmm or HH:MM:SS.mmm timecodes."""
        millisec = int(round((seconds % 1) * 1000))
        total_sec = int(seconds)
        hours = total_sec // 3600
        minutes = (total_sec % 3600) // 60
        secs = total_sec % 60
        return f"{hours:02d}:{minutes:02d}:{secs:02d}{decimal_marker}{millisec:03d}"

    @staticmethod
    def _normalize_subtitles(
        subtitles: List[Union[Tuple[Tuple[float, float], str], Tuple[float, float, str]]]
    ) -> List[Tuple[Tuple[float, float], str]]:
        """Normalizes both ((start, end), text) and (start, end, text) inputs."""
        normalized = []
        for item in subtitles:
            if len(item) == 2 and isinstance(item[0], (tuple, list)):
                normalized.append(((float(item[0][0]), float(item[0][1])), item[1]))
            elif len(item) == 3:
                normalized.append(((float(item[0]), float(item[1])), item[2]))
        return normalized

    def _error(self, error):
        if self.error_messages_callback:
            self.error_messages_callback(error)
        else:
            print(error)


# from __future__ import annotations

# import json

# import pysrt


# class SubtitleFormatter:

#     supported_formats = [
#         "srt",
#         "vtt",
#         "json",
#         "raw",
#     ]

#     def __init__(
#         self,
#         format_type: str,
#         error_messages_callback=None,
#     ):

#         self.format_type = (
#             format_type.lower()
#         )

#         self.error_messages_callback = (
#             error_messages_callback
#         )

#         if (
#             self.format_type
#             not in self.supported_formats
#         ):
#             raise ValueError(
#                 f"Unsupported subtitle format: "
#                 f"{self.format_type}"
#             )

#     def __call__(
#         self,
#         subtitles,
#         padding_before: float = 0,
#         padding_after: float = 0,
#     ):

#         try:

#             if self.format_type == "srt":

#                 return self.srt_formatter(
#                     subtitles,
#                     padding_before,
#                     padding_after,
#                 )

#             if self.format_type == "vtt":

#                 return self.vtt_formatter(
#                     subtitles,
#                     padding_before,
#                     padding_after,
#                 )

#             if self.format_type == "json":

#                 return self.json_formatter(
#                     subtitles
#                 )

#             if self.format_type == "raw":

#                 return self.raw_formatter(
#                     subtitles
#                 )

#             raise ValueError(
#                 f"Unsupported format type: "
#                 f"{self.format_type}"
#             )

#         except KeyboardInterrupt:

#             self._error(
#                 "Cancelling all tasks"
#             )

#             return None

#         except Exception as exc:

#             self._error(exc)

#             return None

#     # ----------------------------------------------------------
#     # SRT
#     # ----------------------------------------------------------

#     def srt_formatter(
#         self,
#         subtitles,
#         padding_before=0,
#         padding_after=0,
#     ):

#         sub_rip_file = (
#             pysrt.SubRipFile()
#         )

#         for index, (
#             (start, end),
#             text,
#         ) in enumerate(
#             subtitles,
#             start=1,
#         ):

#             item = pysrt.SubRipItem()

#             item.index = index

#             item.text = str(text)

#             start_ms = max(
#                 0,
#                 int(
#                     (start - padding_before)
#                     * 1000
#                 ),
#             )

#             end_ms = max(
#                 start_ms,
#                 int(
#                     (end + padding_after)
#                     * 1000
#                 ),
#             )

#             item.start = (
#                 pysrt.SubRipTime.from_ordinal(
#                     start_ms
#                 )
#             )

#             item.end = (
#                 pysrt.SubRipTime.from_ordinal(
#                     end_ms
#                 )
#             )

#             sub_rip_file.append(item)

#         return str(
#             sub_rip_file
#         )

#     # ----------------------------------------------------------
#     # VTT
#     # ----------------------------------------------------------

#     def vtt_formatter(
#         self,
#         subtitles,
#         padding_before=0,
#         padding_after=0,
#     ):

#         srt_text = self.srt_formatter(
#             subtitles,
#             padding_before,
#             padding_after,
#         )

#         return (
#             "WEBVTT\n\n"
#             + srt_text.replace(
#                 ",",
#                 ".",
#             )
#         )

#     # ----------------------------------------------------------
#     # JSON
#     # ----------------------------------------------------------

#     def json_formatter(
#         self,
#         subtitles,
#     ):

#         subtitle_dicts = [
#             {
#                 "start": start,
#                 "end": end,
#                 "content": text,
#             }
#             for (
#                 (start, end),
#                 text,
#             ) in subtitles
#         ]

#         return json.dumps(
#             subtitle_dicts,
#             ensure_ascii=False,
#             indent=2,
#         )

#     # ----------------------------------------------------------
#     # RAW
#     # ----------------------------------------------------------

#     def raw_formatter(
#         self,
#         subtitles,
#     ):

#         return " ".join(
#             str(text)
#             for (
#                 _range,
#                 text,
#             ) in subtitles
#         )

#     # ----------------------------------------------------------
#     # Error
#     # ----------------------------------------------------------

#     def _error(self, error):

#         if self.error_messages_callback:
#             self.error_messages_callback(error)
#         else:
#             print(error)