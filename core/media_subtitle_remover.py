import os
import sys
import time
import shlex
import subprocess


class MediaSubtitleRemover:
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

    def __init__(self, output_path=None, progress_callback=None, error_messages_callback=None):
        self.output_path = output_path
        self.progress_callback = progress_callback
        self.error_messages_callback = error_messages_callback

    def __call__(self, media_filepath):
        if "\\" in media_filepath:
            media_filepath = media_filepath.replace("\\", "/")

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
            ffmpeg_command = [
                                'ffmpeg',
                                '-hide_banner',
                                '-loglevel', 'error',
                                '-v', 'error',
                                '-y',
                                '-i', media_filepath,
                                '-c', 'copy',
                                '-sn',
                                '-progress', '-', '-nostats',
                                self.output_path
                             ]

            media_file_display_name = os.path.basename(media_filepath).split('/')[-1]
            info = f"Removing subtitles streams from '{media_file_display_name}'"
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

