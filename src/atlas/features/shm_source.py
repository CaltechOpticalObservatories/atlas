# Standard Library Imports
from datetime import datetime, timezone
import os
import threading
import time

# Third-Party Library Imports
from astropy.io import fits
from astropy.table import MaskedColumn, Table
from PyQt5.QtWidgets import QAction, QDialog, QFileDialog, QLabel, QSlider, QVBoxLayout
from PyQt5.QtCore import QObject, Qt, QTimer, pyqtSignal

from atlas.model import capture_budget, saving
from .registry import Tool, register
from .latest_frame_slot import LatestFrameSlot
from . import shm_reader
from .shm_capture import CANCELLED, Capture, CaptureProcess, frame_keywords

_MIN_DISPLAY_HZ = 1
_MAX_DISPLAY_HZ = 120
_ATTACH_RETRY_SECONDS = 1.0
# How long without a frame before checking the segment was not replaced
_IDLE_CHECK_SECONDS = 0.2
# How often the display reader looks at a ring for a new frame
_RING_POLL_SECONDS = 0.001


def capture_table(numbers, keywords):
    """
    The header and per-frame table to save a capture's cube with.

    The header is the keywords of the first frame that has its own. Every
    frame has its own values, so they also go in a table with one row per
    frame, alongside each frame's cnt0. A frame saved without its keywords has
    them masked in the table, never borrowed from a neighbour, and NKWMISS
    counts such frames.

    Args:
        numbers (list): Each frame's cnt0, or None throughout when unknown.
        keywords (list): Each frame's keywords, or None where it has none.

    Returns:
        tuple: (header, table, skipped, missing). `table` is None when there is
        nothing per frame to record; `skipped` counts frames missed between the
        first and last, going by cnt0, or is None when the frames carry no
        cnt0; `missing` counts frames saved without keywords.
    """
    known = [frame for frame in keywords if frame is not None]
    first = known[0] if known else {}
    header = fits.Header(first)
    columns = {}
    skipped = None
    if None not in numbers:
        skipped = sum(b - a - 1 for a, b in zip(numbers, numbers[1:]) if b > a + 1)
        header["NSKIPPED"] = (skipped, "frames missed between those saved")
        columns["CNT0"] = numbers

    mask = [frame is None for frame in keywords]
    missing = sum(mask)
    if missing:
        header["NKWMISS"] = (missing, "frames saved without their own keywords")
    # Only keywords every frame that has any carries can make a full column.
    for name in first:
        if all(name in frame for frame in known):
            # A masked row still needs a value of the column's type under it.
            values = [first[name] if frame is None else frame[name] for frame in keywords]
            columns[name] = MaskedColumn(values, mask=mask) if missing else values

    table = Table(columns) if columns else None
    return header, table, skipped, missing


class ShmReceiver(QObject):  # pylint: disable=too-many-instance-attributes
    """
    Follows an ImageStreamIO segment on a background thread, for the display.

    Only the newest frame matters here, so the ones between are let go.
    Keeping every frame is the capture worker's job (see shm_capture), in a
    process of its own, where the GUI cannot hold it up.
    """

    attached = pyqtSignal(str)
    detached = pyqtSignal(str)

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.thread = None
        self.slot = LatestFrameSlot()
        # What the segment last attached to holds, and where it is; None before any
        self.info = None
        self.nbkw = 0
        self.path = None
        self._stop = threading.Event()
        self._failure_reported = False
        # Reader thread only: the number of the newest frame read
        self._last = None

    @property
    def running(self):
        """True while the reader thread is up, attached or still trying."""
        return self.thread is not None and self.thread.is_alive()

    def start(self):
        """
        Starts reading, if not already running.

        True means the reader thread started, not that a segment was found:
        attaching happens on that thread and is retried until it succeeds, so
        callers must wait for `attached` before claiming to be reading.
        """
        if self.running:
            return False

        self._stop.clear()
        self._failure_reported = False
        self.thread = threading.Thread(target=self.receive, daemon=True)
        self.thread.start()
        return True

    def stop(self):
        """Asks the reader thread to shut down."""
        self._stop.set()
        if self.thread is not None:
            self.thread.join(timeout=2.0)
            self.thread = None
        self.slot.take()  # drop any leftover frame, so a reconnect starts clean

    def receive(self):
        """Thread body: keep the newest frame waiting for the display."""
        image = None
        idle_since = time.monotonic()
        try:
            while not self._stop.is_set():
                if image is None:
                    image = self.attach()
                    if image is None:
                        # Wait out the retry interval, but stay interruptible
                        self._stop.wait(_ATTACH_RETRY_SECONDS)
                    continue

                try:
                    if self.info.ring:
                        arrived = self.read_from_ring(image)
                    else:
                        arrived = self.read_live(image)
                except Exception as error:  # pragma: no cover - segment read failure path
                    self.detach(image, str(error))
                    image = None
                    continue

                now = time.monotonic()
                if arrived:
                    idle_since = now
                    continue
                if now - idle_since >= _IDLE_CHECK_SECONDS:
                    idle_since = now
                    if shm_reader.segment_replaced(image):
                        self.detach(image, "segment was replaced, re-attaching")
                        image = None
                        continue
                if self.info.ring:
                    time.sleep(_RING_POLL_SECONDS)
        finally:
            if image is not None:
                shm_reader.close(image)

    def read_from_ring(self, image):
        """
        Notes the newest frame in the ring, and copies it if the display has
        taken the last one. True if there was a new one.
        """
        newest = shm_reader.frame_count(image)
        if newest == self._last:
            return False
        # Copied only when the display has taken the last one: at kHz rates
        # copying every frame for a 15 Hz display is most of the work. The
        # frame shown can then be up to one display tick old.
        if self.slot.empty():
            keywords = shm_reader.read_keywords(image)
            data = shm_reader.read_ring(image, newest)
            if data is not None:
                self.slot.put(shm_reader.ShmFrame(data=data, keywords=keywords, cnt0=newest))
        self._last = newest
        return True

    def read_live(self, image):
        """Waits for the live frame to move on, and reads it. True if it did."""
        frame = shm_reader.wait_for_frame(image, timeout=_IDLE_CHECK_SECONDS, after=self._last)
        if frame is None:
            return False
        self._last = frame.cnt0
        self.slot.put(frame)
        return True

    def attach(self):
        """Attaches to the configured segment, or returns None and says why."""
        try:
            image = shm_reader.attach(self.settings.segment_name, self.settings.shm_dir)
        except Exception as error:  # pragma: no cover - segment unavailable path
            # Retried every second, so only the first failure of a run is
            # reported: the status line should state the problem, not flicker.
            if not self._failure_reported:
                self._failure_reported = True
                self.detached.emit(str(error))
            return None

        self._failure_reported = False
        self._last = None
        self.info = shm_reader.segment_info(image)
        self.nbkw = shm_reader.keyword_count(image)
        self.path = shm_reader.segment_path(image)
        self.attached.emit(self.path)
        return image

    def detach(self, image, reason):
        """Closes a handle that is no longer usable, and reports why."""
        shm_reader.close(image)
        self._failure_reported = False
        self.detached.emit(reason)


class CaptureWriter(QObject):
    """
    Writes a finished capture out on a thread of its own, so a cube of
    gigabytes does not freeze the window while it goes to disk.

    One at a time: a new capture waits for the last write, so no more than one
    cube is ever in memory.
    """

    # file name, frames skipped, frames without keywords, written
    finished = pyqtSignal(str, object, int, bool)

    def __init__(self, view_model):
        super().__init__()
        self.view_model = view_model
        self.thread = None
        # The file being written, or None
        self.file_name = None

    @property
    def busy(self):
        """True while a capture is being written."""
        return self.file_name is not None

    def write(self, file_name, capture):
        """Starts writing a capture, giving its memory back after; `finished` says how it went."""
        self.file_name = file_name
        self.thread = threading.Thread(target=self.run, args=(file_name, capture), daemon=True)
        self.thread.start()

    def run(self, file_name, capture):
        """Writer thread: the save itself reports to the status bar."""
        try:
            numbers = capture.counters[:, 0].tolist()
            header, table, skipped, missing = capture_table(numbers, frame_keywords(capture))
            written = self.view_model.save_image(file_name, capture.cube, header, table)
        finally:
            capture.release()
            self.file_name = None
        self.finished.emit(file_name, skipped, missing, written)

    def wait(self):
        """Blocks until any write under way is done, so quitting loses nothing."""
        if self.thread is not None:
            self.thread.join()
            self.thread = None


@register("shm")
class ShmTool(Tool):  # pylint: disable=too-many-instance-attributes
    """
    Live-displays frames arriving on an ImageStreamIO shared-memory segment.

    The reader thread keeps only the newest frame in a slot; the timer here
    pulls from it at settings.display_fps_cap. Nothing reaches the display
    unless this timer asks for it, so a GUI that cannot keep up skips frames
    rather than falling behind.
    """

    def __init__(self, window, settings):
        super().__init__(window, settings)
        self.receiver = None
        self.writer = None
        # The capture worker while connected, and the capture it is filling
        self.capturer = None
        self.pending = None
        self.timer = None
        self.status = None
        self.status_text = ""
        self.connect_action = None
        self.disconnect_action = None
        self.directory_action = None

    def build(self):
        self.receiver = ShmReceiver(self.settings)
        self.receiver.attached.connect(self.on_attached)
        self.receiver.detached.connect(self.on_detached)
        self.writer = CaptureWriter(self.view_model)
        self.writer.finished.connect(self.on_written)

        self.timer = QTimer(self.window)
        self.timer.setInterval(self.interval_ms(self.settings.display_fps_cap))
        self.timer.timeout.connect(self.show_latest_frame)

        # A permanent widget rather than a status message: "connected but
        # receiving nothing" is exactly the state that has to stay on screen,
        # since otherwise it looks the same as a detector sitting idle.
        self.status = QLabel()
        self.window.statusBar().addPermanentWidget(self.status)
        self.set_status("SHM: disconnected")

        menu = self.window.tools_menu.addMenu("Shared Memory")

        self.connect_action = QAction(f"Connect to {self.settings.segment_name}", self.window)
        self.connect_action.triggered.connect(self.connect_to_shm)
        menu.addAction(self.connect_action)

        self.disconnect_action = QAction("Disconnect from SHM", self.window)
        self.disconnect_action.triggered.connect(self.disconnect_from_shm)
        self.disconnect_action.setEnabled(False)
        menu.addAction(self.disconnect_action)

        self.directory_action = QAction("Set Segment Directory…", self.window)
        self.directory_action.triggered.connect(self.choose_shm_directory)
        menu.addAction(self.directory_action)

        rate_action = QAction("Set display rate…", self.window)
        rate_action.triggered.connect(self.set_display_rate)
        menu.addAction(rate_action)

    def set_status(self, text):
        """Sets the status line, which a capture under way adds its progress to."""
        self.status_text = text
        self.show_capture_progress()

    def capture_progress(self):
        """(frames kept, frames asked for) for a capture under way, or None."""
        if self.pending is None:
            return None
        return self.capturer.progress.value, self.pending.count

    def show_capture_progress(self):
        """Shows how far a capture has got, on the GUI thread at timer pace."""
        progress = self.capture_progress()
        writing = self.writer.file_name
        text = self.status_text
        if progress is not None:
            text = f"{text} — saving frame {progress[0]} of {progress[1]}"
        elif writing is not None:
            text = f"{text} — writing {os.path.basename(writing)}…"
        if self.status.text() != text:
            self.status.setText(text)

    @staticmethod
    def interval_ms(hz):
        """Timer period for a display rate, floored at 1ms so Qt still idles."""
        return max(1, round(1000.0 / hz))

    def connect_to_shm(self):
        """Starts reading from the configured segment."""
        if not self.receiver.start():
            self.window.show_message("Already connected.")
            return

        # Started now, so it has settled in long before anyone presses Save.
        self.capturer = CaptureProcess()
        self.capturer.ended.connect(self.on_capture_ended)
        self.timer.start()
        self.connect_action.setEnabled(False)
        self.disconnect_action.setEnabled(True)
        self.directory_action.setEnabled(False)
        self.set_status(f"SHM: connecting to {self.settings.segment_name}…")

    def choose_shm_directory(self):
        """
        Picks the directory the segment is looked for in, for this session.

        Only while disconnected: the reader settles on a directory when it
        attaches, so changing it under a live connection would do nothing.
        """
        directory = QFileDialog.getExistingDirectory(
            self.window, "Segment Directory", self.settings.shm_dir)
        if directory:
            self.settings.shm_dir = directory
            self.window.show_message(
                f"Looking for {self.settings.segment_name} in {directory}")

    def stop_capturer(self):
        """Ends the capture worker, and gives back the memory of any capture it had."""
        if self.capturer is not None:
            self.capturer.stop()
            self.capturer = None
        if self.pending is not None:
            self.pending.release()
            self.pending = None

    def disconnect_from_shm(self):
        """Stops reading, abandoning any capture that has not finished."""
        progress = self.capture_progress()
        self.timer.stop()
        self.receiver.stop()
        self.stop_capturer()
        self.connect_action.setEnabled(True)
        self.disconnect_action.setEnabled(False)
        self.directory_action.setEnabled(True)
        self.set_status("SHM: disconnected")
        if progress is None:
            self.window.show_message("Disconnected from SHM.")
        else:
            self.window.show_message(
                f"Disconnected from SHM. Saving {progress[1]} frames was cancelled "
                f"after {progress[0]}; nothing was written.")

    def shutdown(self):
        """Stops the reader thread and worker so the app can actually exit."""
        self.timer.stop()
        self.receiver.stop()
        self.stop_capturer()
        # A capture already in has been paid for; quitting must not cut it short.
        self.writer.wait()

    def capture_limit(self):
        """The most frames of the attached segment a capture can hold now."""
        return capture_budget.max_capture_frames(
            capture_budget.capture_bytes_per_frame(self.receiver.info.frame_bytes,
                                                   self.receiver.nbkw),
            self.settings.capture_memory_fraction)

    def offer_capture_limit(self, limit):
        """Caps the save button's Frames box at what fits in memory, if it has one."""
        button = self.window.tools.get("save_button")
        if button is None:
            return
        info = self.receiver.info
        height, width = info.shape
        free_gb = capture_budget.available_bytes() / 2 ** 30
        button.set_frame_limit(limit, (
            f"Up to {limit:,} frames of {width}×{height} {info.dtype.name} "
            f"({info.frame_bytes / 2 ** 20:.2f} MB each): "
            f"{self.settings.capture_memory_fraction:.0%} of the {free_gb:.1f} GB free"))

    def save_next_frames(self, count):
        """
        Saves the next `count` frames off the stream as one FITS cube, at
        <save directory>/<date>/<date>_<time>.fits for the moment this was
        asked.
        """
        if not self.receiver.running:
            self.window.show_message("Connect to shared memory to save several frames.")
            return
        info = self.receiver.info
        if info is None:
            self.window.show_message(
                f"Still looking for {self.settings.segment_name}; "
                f"several frames can be saved once it is found.")
            return
        if self.pending is not None or self.writer.busy:
            self.window.show_message("Already saving frames; wait for that to finish.")
            return

        # Checked again now: the memory free when the segment was found may
        # since have gone to something else.
        limit = self.capture_limit()
        self.offer_capture_limit(limit)
        if count > limit:
            self.window.show_message(
                f"Only {limit:,} frames fit in memory now; save {limit:,} or fewer.")
            return

        when = datetime.now(timezone.utc)
        try:
            # Checked now rather than once the frames are in, so a directory
            # that cannot be made does not cost a whole capture.
            saving.day_directory(self.window.save_directory, when)
            capture = Capture.allocate(count, when, info, self.receiver.nbkw,
                                       self.receiver.path)
        except OSError as error:
            self.window.show_message(f"Could not save: {error}")
            return

        self.pending = capture
        self.capturer.start(capture)
        self.show_capture_progress()

    def on_capture_ended(self, capture, kept, error):
        """The worker has filled a capture, or given up on it. Runs on the GUI thread."""
        if capture is not self.pending:
            return  # disconnected meanwhile, and already given back
        self.pending = None
        capture.kept = kept
        if error is None:
            try:
                file_name = saving.next_save_path(self.window.save_directory, capture.when)
            except OSError as path_error:
                error = str(path_error)
            else:
                self.writer.write(file_name, capture)
        if error is not None:
            capture.release()
            if error != CANCELLED:
                self.window.show_message(f"Could not save {capture.count} frames: {error}")
        self.show_capture_progress()

    def on_written(self, file_name, skipped, missing, written):
        """A capture is on disk, or failed to be. Runs on the GUI thread."""
        self.show_capture_progress()
        if not written:
            return
        if skipped and missing:
            self.window.show_message(
                f"Saved {file_name}, but {skipped} frames arrived too fast to keep, and "
                f"{missing} of those saved have no keywords of their own.")
        elif skipped:
            self.window.show_message(
                f"Saved {file_name}, but {skipped} frames arrived too fast to keep "
                f"and are missing from it.")
        elif missing:
            self.window.show_message(
                f"Saved {file_name}, but {missing} frames in it have no keywords of their own.")

    def on_attached(self, path):
        """The reader thread is on a live segment now. Runs on the GUI thread."""
        self.set_status(f"SHM: reading {self.settings.segment_name}")
        self.offer_capture_limit(self.capture_limit())
        self.window.show_message(f"Reading {path}")

    def on_detached(self, reason):
        """
        The reader thread has no usable segment. Runs on the GUI thread.
        """
        self.set_status(f"SHM: not reading {self.settings.segment_name}")
        self.window.show_message(f"SHM: {reason}")

    def set_display_rate(self):
        """Opens a slider that live-tunes the display rate, independent of connection state."""
        current_hz = round(self.settings.display_fps_cap)

        dialog = QDialog(self.window)
        dialog.setWindowTitle("Display Rate")
        layout = QVBoxLayout(dialog)

        label = QLabel(f"{current_hz} Hz")
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)

        slider = QSlider(Qt.Horizontal)
        slider.setMinimum(_MIN_DISPLAY_HZ)
        slider.setMaximum(_MAX_DISPLAY_HZ)
        slider.setValue(current_hz)
        slider.valueChanged.connect(lambda hz: self.apply_display_rate(hz, label))
        layout.addWidget(slider)

        dialog.exec_()

    def apply_display_rate(self, hz, label):
        """Applies a new display rate live. setInterval restarts a running timer."""
        label.setText(f"{hz} Hz")
        self.settings.display_fps_cap = hz
        self.timer.setInterval(self.interval_ms(hz))

    def show_latest_frame(self):
        """Displays the newest frame, if one arrived since the last tick."""
        self.show_capture_progress()
        frame = self.receiver.slot.take()
        if frame is None:
            return
        self.view_model.update_live_frame(frame.data, frame.keywords)
