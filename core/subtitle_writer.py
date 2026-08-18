from __future__ import annotations

import os
from typing import List, Tuple, Union, Optional
from core.subtitle_formatter import SubtitleFormatter

import os
from typing import Optional, Callable, Any

class SubtitleWriter:

    def __init__(self, error_callback: Optional[Callable[[Any], None]] = None):
        self.error_callback = error_callback

    def write(self, filepath: str, content: str) -> Optional[str]:
        try:
            saved_filepath = os.path.abspath(filepath)
            parent_directory = os.path.dirname(saved_filepath)

            os.makedirs(parent_directory, exist_ok=True)

            with open(saved_filepath, "w", encoding="utf-8", newline="") as file:
                file.write(content)

            return saved_filepath

        except KeyboardInterrupt:
            self._error("Cancelling task execution")
            return None

        except Exception as exc:
            self._error(exc)
            return None

    def _error(self, error: Any) -> None:
        if self.error_callback:
            self.error_callback(error)
        else:
            print(error)

# class SubtitleWriter:

#     def __init__(
#         self,
#         regions: List[Union[Tuple[float, float], List[float]]],
#         transcripts: List[str],
#         format: str = "srt",
#         error_messages_callback=None,
#     ):
#         self.regions = regions
#         self.transcripts = transcripts
#         self.format = format.lower()
#         self.error_messages_callback = error_messages_callback

#         # Zip regions and non-empty transcripts into timed pairs
#         self.timed_subtitles = [
#             (region, transcript)
#             for region, transcript in zip(self.regions, self.transcripts)
#             if transcript and str(transcript).strip()
#         ]

#     def get_timed_subtitles(self):
#         return self.timed_subtitles

#     def write(
#         self,
#         declared_subtitle_filepath: str,
#         padding_before: float = 0.0,
#         padding_after: float = 0.0,
#     ) -> Optional[str]:
#         try:
#             formatter = SubtitleFormatter(
#                 self.format,
#                 error_messages_callback=self.error_messages_callback,
#             )

#             formatted_subtitles = formatter(
#                 self.timed_subtitles,
#                 padding_before=padding_before,
#                 padding_after=padding_after,
#             )

#             if formatted_subtitles is None:
#                 raise RuntimeError("Failed to format subtitles.")

#             saved_subtitle_filepath = declared_subtitle_filepath
#             subtitle_file_base, subtitle_file_ext = os.path.splitext(
#                 saved_subtitle_filepath
#             )

#             if not subtitle_file_ext:
#                 saved_subtitle_filepath = f"{subtitle_file_base}.{self.format}"

#             parent_directory = os.path.dirname(
#                 os.path.abspath(saved_subtitle_filepath)
#             )

#             os.makedirs(parent_directory, exist_ok=True)

#             with open(
#                 saved_subtitle_filepath,
#                 "w",
#                 encoding="utf-8",
#                 newline="",
#             ) as file:
#                 file.write(formatted_subtitles)

#             return saved_subtitle_filepath

#         except KeyboardInterrupt:
#             self._error("Cancelling all tasks")
#             return None

#         except Exception as exc:
#             self._error(exc)
#             return None

#     def _error(self, error):
#         if self.error_messages_callback:
#             self.error_messages_callback(error)
#         else:
#             print(error)

# from __future__ import annotations

# import os

# from core.subtitle_formatter import (
#     SubtitleFormatter,
# )


# class SubtitleWriter:

#     def __init__(
#         self,
#         regions,
#         transcripts,
#         format,
#         error_messages_callback=None,
#     ):

#         self.regions = regions
#         self.transcripts = transcripts
#         self.format = format.lower()

#         self.error_messages_callback = (
#             error_messages_callback
#         )

#         self.timed_subtitles = [
#             (region, transcript)
#             for region, transcript in zip(
#                 self.regions,
#                 self.transcripts,
#             )
#             if transcript
#         ]

#     # ----------------------------------------------------------
#     # Get subtitles
#     # ----------------------------------------------------------

#     def get_timed_subtitles(self):

#         return self.timed_subtitles

#     # ----------------------------------------------------------
#     # Write subtitle file
#     # ----------------------------------------------------------

#     def write(
#         self,
#         declared_subtitle_filepath: str,
#     ):

#         try:

#             formatter = SubtitleFormatter(
#                 self.format,
#                 error_messages_callback=(
#                     self.error_messages_callback
#                 ),
#             )

#             formatted_subtitles = formatter(
#                 self.timed_subtitles
#             )

#             if formatted_subtitles is None:
#                 raise RuntimeError(
#                     "Failed to format subtitles."
#                 )

#             saved_subtitle_filepath = (
#                 declared_subtitle_filepath
#             )

#             subtitle_file_base, subtitle_file_ext = (
#                 os.path.splitext(
#                     saved_subtitle_filepath
#                 )
#             )

#             if not subtitle_file_ext:

#                 saved_subtitle_filepath = (
#                     f"{subtitle_file_base}."
#                     f"{self.format}"
#                 )

#             parent_directory = os.path.dirname(
#                 os.path.abspath(
#                     saved_subtitle_filepath
#                 )
#             )

#             os.makedirs(
#                 parent_directory,
#                 exist_ok=True,
#             )

#             with open(
#                 saved_subtitle_filepath,
#                 "w",
#                 encoding="utf-8",
#                 newline="",
#             ) as file:

#                 file.write(
#                     formatted_subtitles
#                 )

#             return saved_subtitle_filepath

#         except KeyboardInterrupt:

#             self._error(
#                 "Cancelling all tasks"
#             )

#             return None

#         except Exception as exc:

#             self._error(exc)

#             return None

#     # ----------------------------------------------------------
#     # Error
#     # ----------------------------------------------------------

#     def _error(self, error):

#         if self.error_messages_callback:
#             self.error_messages_callback(error)
#         else:
#             print(error)