class SubtitleSyncJobProcessor:

    def __init__(
        self,
        progress_callback=None,
        error_callback=None,
    ):
        self.progress_callback = progress_callback
        self.error_callback = error_callback
        self.cancelled = False

    def cancel(self):
        self.cancelled = True

    def check_cancelled(self):
        if self.cancelled:
            raise JobCancelled(
                "Subtitle synchronization cancelled."
            )

    def process(
        self,
        subtitle_filepath,
        output_filepath,
        operation="offset",
        **kwargs,
    ):
        self.check_cancelled()

        service = SubtitleSyncService(
            progress_callback=self.progress_callback,
            error_callback=self.error_callback,
        )

        if operation == "offset":
            result = service.sync_offset(
                subtitle_filepath,
                output_filepath,
                kwargs["offset"],
                kwargs.get("video_duration"),
            )

        elif operation == "two_points":
            result = service.sync_two_points(
                subtitle_filepath,
                output_filepath,
                kwargs["subtitle_point_1"],
                kwargs["video_point_1"],
                kwargs["subtitle_point_2"],
                kwargs["video_point_2"],
                kwargs.get("video_duration"),
            )

        elif operation == "points":
            result = service.sync_points(
                subtitle_filepath,
                output_filepath,
                kwargs["points"],
                kwargs.get("video_duration"),
            )

        elif operation == "start_end":
            result = service.sync_start_end(
                subtitle_filepath,
                output_filepath,
                kwargs["video_duration"],
            )

        else:
            raise ValueError(
                f"Invalid synchronization operation: {operation}"
            )

        self.check_cancelled()

        return result