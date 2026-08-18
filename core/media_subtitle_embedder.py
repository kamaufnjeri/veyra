import os
import sys
import time
import json
import shlex
import subprocess


class MediaSubtitleEmbedder:
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

    def __init__(self, subtitle_path=None, language=None, output_path=None, progress_callback=None, error_messages_callback=None):
        self.subtitle_path = subtitle_path
        self.language = language
        self.output_path = output_path
        self.progress_callback = progress_callback
        self.error_messages_callback = error_messages_callback

    def get_existing_subtitle_language(self, media_filepath):
        # Run ffprobe to get stream information
        if "\\" in media_filepath:
            media_filepath = media_filepath.replace("\\", "/")

        command = [
                    'ffprobe',
                    '-hide_banner',
                    '-v', 'error',
                    '-loglevel', 'error',
                    '-of', 'json',
                    '-show_entries',
                    'format:stream',
                    media_filepath
                  ]

        output = None
        if sys.platform == "win32":
            output = subprocess.run(command, stdin=open(os.devnull), stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            output = subprocess.run(command, stdin=open(os.devnull), stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)

        metadata = json.loads(output.stdout)
        streams = metadata['streams']

        # Find the subtitle stream with language metadata
        subtitle_languages = []
        for stream in streams:
            if stream['codec_type'] == 'subtitle' and 'tags' in stream and 'language' in stream['tags']:
                language = stream['tags']['language']
                subtitle_languages.append(language)

        return subtitle_languages

    def __call__(self, media_filepath):
        if "\\" in media_filepath:
            media_filepath = media_filepath.replace("\\", "/")

        if "\\" in self.subtitle_path:
            self.subtitle_path = self.subtitle_path.replace("\\", "/")

        if "\\" in self.output_path:
            self.output_path = self.output_path.replace("\\", "/")

        if not os.path.isfile(media_filepath):
            if self.error_messages_callback:
                self.error_messages_callback(f"The given file does not exist: '{media_filepath}'")
            else:
                print(f"The given file does not exist: '{media_filepath}'")
                raise Exception(f"Invalid file: '{media_filepath}'")

        if not self.ffprobe_check():
            if self.error_messages_callback:
                self.error_messages_callback("Cannot find ffprobe executable")
            else:
                print("Cannot find ffprobe executable")
                raise Exception("Dependency not found: ffprobe")

        if not self.ffmpeg_check():
            if self.error_messages_callback:
                self.error_messages_callback("Cannot find ffmpeg executable")
            else:
                print("Cannot find ffmpeg executable")
                raise Exception("Dependency not found: ffmpeg")

        try:
            existing_languages = self.get_existing_subtitle_language(media_filepath)
            if self.language in existing_languages:
                # THIS 'print' THINGS WILL MAKE progresbar screwed up!
                #msg = (f"'{self.language}' subtitle stream already existed in '{media_filepath}'")
                #if self.error_messages_callback:
                #    self.error_messages_callback(msg)
                #else:
                #    print(msg)
                return

            else:
                # Determine the next available subtitle index
                next_index = len(existing_languages)

                ffmpeg_command = [
                                    'ffmpeg',
                                    '-hide_banner',
                                    '-loglevel', 'error',
                                    '-v', 'error',
                                    '-y',
                                    '-i', media_filepath,
                                    '-sub_charenc', 'UTF-8',
                                    '-i', self.subtitle_path,
                                    '-c:v', 'copy',
                                    '-c:a', 'copy',
                                    '-scodec', 'mov_text',
                                    '-metadata:s:s:' + str(next_index), f'language={shlex.quote(self.language)}',
                                    '-map', '0',
                                    '-map', '1',
                                    '-progress', '-', '-nostats',
                                    self.output_path
                                 ]

                subtitle_file_display_name = os.path.basename(self.subtitle_path).split('/')[-1]
                media_file_display_name = os.path.basename(media_filepath).split('/')[-1]
                info = f"Embedding '{self.language}' subtitles file '{subtitle_file_display_name}' into '{media_file_display_name}'"
                start_time = time.time()

                ffprobe_command = [
                                    'ffprobe',
                                    '-hide_banner',
                                    '-v', 'error',
                                    '-loglevel', 'error',
                                    '-show_entries',
                                    'format=duration',
                                    '-of', 'default=noprint_wrappers=1:nokey=1',
                                    media_filepath
                                  ]

                ffprobe_process = None
                if sys.platform == "win32":
                    ffprobe_process = subprocess.check_output(ffprobe_command, stdin=open(os.devnull), universal_newlines=True, shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
                else:
                    ffprobe_process = subprocess.check_output(ffprobe_command, stdin=open(os.devnull), universal_newlines=True)

                total_duration = float(ffprobe_process.strip())

                process = None
                if sys.platform == "win32":
                    process = subprocess.Popen(ffmpeg_command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
                else:
                    process = subprocess.Popen(ffmpeg_command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

                while True:
                    if process.stdout is None:
                        continue

                    stderr_line = (process.stdout.readline().decode("utf-8", errors="replace").strip())
 
                    if stderr_line == '' and process.poll() is not None:
                        break

                    if "out_time=" in stderr_line:
                        time_str = stderr_line.split('time=')[1].split()[0]
                        current_duration = sum(float(x) * 1000 * 60 ** i for i, x in enumerate(reversed(time_str.split(":"))))

                        if current_duration>0 and current_duration<=total_duration*1000:
                            percentage = int(current_duration*100/(int(float(total_duration))*1000))
                            if self.progress_callback and percentage <= 100:
                                self.progress_callback(info, media_file_display_name, percentage, start_time)

                if os.path.isfile(self.output_path):
                    return self.output_path
                else:
                    return None

                if os.path.isfile(self.output_path):
                    return self.output_path
                else:
                    return None

        except KeyboardInterrupt:
            if self.error_messages_callback:
                self.error_messages_callback("Cancelling all tasks")
            else:
                print("Cancelling all tasks")
            return

        except Exception as e:
            if self.error_messages_callback:
                self.error_messages_callback(e)
            else:
                print(e)
            return
