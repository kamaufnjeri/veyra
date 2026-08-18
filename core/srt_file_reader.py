from datetime import datetime


class SRTFileReader:
    def __init__(self, error_messages_callback=None):
        self.error_messages_callback = error_messages_callback
        self.timed_subtitles = []

    def __call__(self, srt_file_path):
        try:
            """
            Read SRT formatted subtitles file and return subtitles as list of tuples
            """
            with open(srt_file_path, 'r') as srt_file:
                lines = srt_file.readlines()
                # Split the subtitles file into subtitles blocks
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
                        self.timed_subtitles.append(((start_time_total_seconds, end_time_total_seconds), subtitles))
                return self.timed_subtitles

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
