import os
import sys
import json
import subprocess
from datetime import datetime



class SubtitleStreamParser:
    def which(self, program):
        def is_exe(file_path):
            return os.path.isfile(file_path) and os.access(file_path, os.X_OK)
        fpath, _ = os.path.split(program)
        if fpath:
            if is_exe(program):
                return program
        else:
            for path in os.environ["PATH"].split(os.pathsep):
                path = path.strip('"')
                exe_file = os.path.join(path, program)
                if is_exe(exe_file):
                    return exe_file
        return None

    def ffprobe_check(self):
        if self.which("ffprobe"):
            return "ffprobe"
        if self.which("ffprobe.exe"):
            return "ffprobe.exe"
        return None

    def ffmpeg_check(self):
        if self.which("ffmpeg"):
            return "ffmpeg"
        if self.which("ffmpeg.exe"):
            return "ffmpeg.exe"
        return None

    def __init__(self, error_messages_callback=None):
        self.error_messages_callback = error_messages_callback
        self._indexes = []
        self._languages = []
        self._timed_subtitles = []
        self._number_of_streams = 0

    def get_subtitle_streams(self, media_filepath):
        ffprobe_cmd = [
                        'ffprobe',
                        '-hide_banner',
                        '-v', 'error',
                        '-loglevel', 'error',
                        '-print_format', 'json',
                        '-show_entries', 'stream=index:stream_tags=language',
                        '-select_streams', 's',
                        media_filepath
                      ]

        try:
            result = None
            if sys.platform == "win32":
                result = subprocess.run(ffprobe_cmd, stdin=open(os.devnull), capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                result = subprocess.run(ffprobe_cmd, stdin=open(os.devnull), capture_output=True, text=True)

            output = result.stdout

            streams = json.loads(output)['streams']

            subtitle_streams = []
            empty_stream_exists = False

            for index, stream in enumerate(streams, start=1):
                language = stream['tags'].get('language')
                subtitle_streams.append({'index': index, 'language': language})

                # Check if 'No subtitles' stream exists
                if language == 'No subtitles':
                    empty_stream_exists = True

            # Append 'No subtitles' stream if it exists
            if not empty_stream_exists:
                subtitle_streams.append({'index': len(streams) + 1, 'language': 'No subtitles'})

            return subtitle_streams

        except FileNotFoundError:
            if self.error_messages_callback:
                msg = 'ffprobe not found. Make sure it is installed and added to the system PATH.'
                self.error_messages_callback(msg)
            else:
                print(msg)
            return None

        except Exception as e:
            if self.error_messages_callback:
                self.error_messages_callback(e)
            else:
                print(e)
            return None

    def get_timed_subtitles(self, media_filepath, subtitle_stream_index):
        ffmpeg_cmd = [
                        'ffmpeg',
                        '-hide_banner',
                        '-loglevel', 'error',
                        '-v', 'error',
                        '-i', media_filepath,
                        '-map', f'0:s:{subtitle_stream_index-1}',
                        '-f', 'srt',
                        '-'
                     ]

        try:
            result = None
            if sys.platform == "win32":
                result = subprocess.run(ffmpeg_cmd, stdin=open(os.devnull), capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                result = subprocess.run(ffmpeg_cmd, stdin=open(os.devnull), capture_output=True, text=True)

            output = result.stdout

            timed_subtitles = []
            subtitle_streams_data_with_timed_subtitles = []
            lines = output.strip().split('\n')
            #print(lines)
            subtitles = []
            subtitles = None
            subtitle_blocks = []
            block = []
            for line in lines:
                if line.strip() == '':
                    subtitle_blocks.append(block)
                    block = []
                else:
                    block.append(line.strip())
            subtitle_blocks.append(block)

            # Parse each subtitles block and store as tuple in timed_subtitles list
            for block in subtitle_blocks:
                if block:
                    # Extract start and end times from subtitles block
                    start_time_str, end_time_str = block[1].split(' --> ')
                    time_format = '%H:%M:%S,%f'
                    start_time_time_delta = datetime.strptime(start_time_str, time_format) - datetime.strptime('00:00:00,000', time_format)
                    start_time_total_seconds = start_time_time_delta.total_seconds()
                    end_time_time_delta = datetime.strptime(end_time_str, time_format) - datetime.strptime('00:00:00,000', time_format)
                    end_time_total_seconds = end_time_time_delta.total_seconds()
                    # Extract subtitles text from subtitles block
                    subtitles = ' '.join(block[2:])
                    timed_subtitles.append(((start_time_total_seconds, end_time_total_seconds), subtitles))
            return timed_subtitles

        except FileNotFoundError:
            if self.error_messages_callback:
                msg = 'ffmpeg not found. Make sure it is installed and added to the system PATH.'
                self.error_messages_callback(msg)
            else:
                print(msg)
            return None

        except Exception as e:
            if self.error_messages_callback:
                self.error_messages_callback(e)
            else:
                print(e)
            return None

    def number_of_streams(self):
        return self._number_of_streams

    def indexes(self):
        return self._indexes

    def languages(self):
        return self._languages

    def timed_subtitles(self):
        return self._timed_subtitles

    def index_of_language(self, language):
        for i in range(self.number_of_streams()):
            if self.languages()[i] == language:
                return i+1
            return

    def language_of_index(self, index):
        return self.languages()[index-1]

    def timed_subtitles_of_index(self, index):
        return self.timed_subtitles()[index-1]

    def timed_subtitles_of_language(self, language):
        for i in range(self.number_of_streams()):
            if self.languages()[i] == language:
                return self.timed_subtitles()[i]

    def __call__(self, media_filepath):
        if "\\" in media_filepath:
            media_filepath = media_filepath.replace("\\", "/")

        if not self.ffprobe_check():
            if self.error_messages_callback:
                self.error_messages_callback("Cannot find ffprobe executable")
            else:
                print("Cannot find ffprobe executable")
                raise Exception("Dependency not found: ffprobe")

        subtitle_streams = self.get_subtitle_streams(media_filepath)
        subtitle_streams_data = []
        if subtitle_streams:
            for subtitle_stream in subtitle_streams:
                subtitle_stream_index = subtitle_stream['index']
                subtitle_stream_language = subtitle_stream['language']
                #print(f"Stream Index: {subtitle_stream_index}, Language: {subtitle_stream_language}")
                subtitle_streams_data.append((subtitle_stream_index, subtitle_stream_language))

        subtitle_streams_data_with_timed_subtitles = []

        for subtitle_stream_index in range(len(subtitle_streams)):
            index, language = subtitle_streams_data[subtitle_stream_index]
            self._indexes.append(index)
            self._languages.append(language)
            self._timed_subtitles.append(self.get_timed_subtitles(media_filepath, subtitle_stream_index+1))
            subtitle_streams_data_with_timed_subtitles.append((index, language, self.get_timed_subtitles(media_filepath, subtitle_stream_index+1)))

        self._number_of_streams = len(subtitle_streams_data_with_timed_subtitles)

        return subtitle_streams_data_with_timed_subtitles

