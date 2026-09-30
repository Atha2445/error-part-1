import os
import logging
import threading
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import time
from typing import Callable, Optional

VIDEO_EXTENSIONS = (".mp4", ".avi", ".mkv")


class VideoHandler(FileSystemEventHandler):
    def __init__(self, callback):
        self.callback = callback

    def on_created(self, event):
        if event.is_directory:
            return
        if not event.src_path.lower().endswith(VIDEO_EXTENSIONS):
            return

        self.callback(event.src_path)


class WatchdogService:
    """Monitors a folder for new video files and starts analysis automatically.

    Callbacks (all optional):
        on_detected(video_path)            – a new video file was seen
        on_progress(video_path, stage, pct) – live progress from the analysis
        on_complete(video_path, verdict)    – analysis finished
        on_error(video_path, error)         – analysis failed
    Processing is serialized (one file at a time) so the shared VLM model is
    never used concurrently.
    """

    def __init__(self, watch_path: str, video_service: 'VideoService',
                 output_path: str = "./outputs",
                 on_detected: Optional[Callable[[str], None]] = None,
                 on_progress: Optional[Callable[[str, str, int], None]] = None,
                 on_complete: Optional[Callable[[str, dict], None]] = None,
                 on_error: Optional[Callable[[str, str], None]] = None):
        self.watch_path = watch_path
        self.output_path = output_path
        self.video_service = video_service
        self.on_detected = on_detected
        self.on_progress = on_progress
        self.on_complete = on_complete
        self.on_error = on_error
        self.observer = None
        self.handler = VideoHandler(self._process_video)
        self._processing_lock = threading.Lock()
        os.makedirs(self.output_path, exist_ok=True)
        os.makedirs(self.watch_path, exist_ok=True)

    def _process_video(self, video_path: str):
        logging.info("New video detected: %s", video_path)
        if self.on_detected:
            self.on_detected(video_path)

        def progress_cb(stage: str, progress: int):
            if self.on_progress:
                self.on_progress(video_path, stage, progress)

        # Wait for the file to finish copying before opening it
        self._wait_until_file_is_ready(video_path)

        video_name = os.path.basename(video_path)
        out_path = os.path.join(self.output_path, f"processed_{video_name}")

        with self._processing_lock:
            logging.info("Starting processing for %s", video_path)
            try:
                verdict = self.video_service.process_video(
                    video_path,
                    output_path=out_path,
                    progress_callback=progress_cb,
                )
                if verdict is None:
                    msg = f"Could not open video: {video_path}"
                    logging.error(msg)
                    if self.on_error:
                        self.on_error(video_path, msg)
                    return
                verdict["video_id"] = os.path.basename(out_path)
                verdict["original_filename"] = video_name
                verdict["source"] = "auto-scan"
                logging.info("Processing complete: %s", verdict.get("risk_level", ""))
                if self.on_complete:
                    self.on_complete(video_path, verdict)
            except Exception as e:
                logging.exception("Processing failed for %s: %s", video_path, e)
                if self.on_error:
                    self.on_error(video_path, str(e))

    def _wait_until_file_is_ready(self, file_path, check_interval=1):
        last_size = -1
        while True:
            try:
                current_size = os.path.getsize(file_path)
                if current_size == last_size and current_size > 0:
                    return
                last_size = current_size
                time.sleep(check_interval)
            except FileNotFoundError:
                time.sleep(check_interval)

    def start(self):
        if self.observer and self.observer.is_alive():
            return
        self.observer = Observer()
        self.observer.schedule(self.handler, self.watch_path, recursive=False)
        self.observer.start()
        logging.info("Watching folder: %s", self.watch_path)

    def stop(self):
        if self.observer:
            self.observer.stop()
            self.observer.join()
            logging.info("Watchdog stopped")

    def update_directory(self, new_path: str):
        self.stop()
        self.watch_path = os.path.abspath(os.path.expanduser(os.path.expandvars(new_path.strip())))
        os.makedirs(self.watch_path, exist_ok=True)
        self.start()
        logging.info("Watchdog directory updated to: %s", self.watch_path)
