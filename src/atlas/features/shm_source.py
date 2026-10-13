# Standard Library Imports
from dataclasses import dataclass, field
from datetime import datetime, timezone
import threading

# Third-Party Library Imports
from astropy.io import fits
from astropy.table import Table
import numpy as np
from PyQt5.QtWidgets import QAction, QDialog, QLabel, QSlider, QVBoxLayout
from PyQt5.QtCore import QObject, Qt, QTimer, pyqtSignal

from atlas.model import saving
from .registry import Tool, register
from .latest_frame_slot import LatestFrameSlot
from . import shm_reader

_MIN_DISPLAY_HZ = 1
_MAX_DISPLAY_HZ = 120
_ATTACH_RETRY_SECONDS = 1.0


@dataclass
class Capture:
    """A request, made at `when`, to keep the next `count` frames read."""
    count: int
    when: datetime
    frames: list = field(default_factory=list)


def stack_frames(frames):
    """
    Turns captured frames into one FITS cube, ready for saving.

    The header is the first frame's keywords. Every frame has its own, so they
    also go in a table with one row per frame, alongside each frame's cnt0.

    Returns:
        tuple: (cube, header, table, skipped). The cube is (nframes, height,
        width); `table` is None when there is nothing per frame to record;
        `skipped` counts frames the reader missed between the first and last,
        going by cnt0, or is None when the frames carry no cnt0.

    Raises:
        ValueError: when the frames are not all one shape and type, as when
        the segment was recreated at another size partway through.
    """
    first = frames[0]
    if any(f.data.shape != first.data.shape or f.data.dtype != first.data.dtype
           for f in frames):
        raise ValueError("the frame size changed partway through")
    cube = np.stack([f.data for f in frames])

    header = fits.Header(first.keywords)
    columns = {}
    skipped = None
    counters = [f.cnt0 for f in frames]
    if None not in counters:
        skipped = sum(b - a - 1 for a, b in zip(counters, counters[1:]) if b > a + 1)
        header["NSKIPPED"] = (skipped, "frames missed between those saved")
        columns["CNT0"] = counters
    # Only keywords every frame has can make a full column.
    for name in first.keywords:
        if all(name in f.keywords for f in frames):
            columns[name] = [f.keywords[name] for f in frames]

    table = Table(columns) if columns else None
    return cube, header, table, skipped


class ShmReceiver(QObject):
    """
    Reads frames from an ImageStreamIO segment on a background thread.
    """

    attached = pyqtSignal(str)
    detached = pyqtSignal(str)
    captured = pyqtSignal(object)  # a finished Capture

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.thread = None
        self.slot = LatestFrameSlot()
        self._stop = threading.Event()
        self._failure_reported = False
        self._capture = None
        self._capture_lock = threading.Lock()

    @property
    def running(self):
        """True while the reader thread is up, attached or still trying."""
        return self.thread is not None and self.thread.is_alive()

    def capture(self, count, when):
        """
        Asks the reader thread to keep the next `count` frames it reads.

        Kept on the reader thread rather than from the display, which only
        sees the frames the display rate lets through: these are every frame
        the reader gets. `captured` is emitted with the Capture once full.

        Returns:
            bool: False if a capture is already under way.
        """
        with self._capture_lock:
            if self._capture is not None:
                return False
            self._capture = Capture(count, when)
            return True

    def cancel_capture(self):
        """Abandons any capture under way, returning it, or None if there was none."""
        with self._capture_lock:
            capture, self._capture = self._capture, None
        return capture

    def capture_progress(self):
        """(frames kept, frames asked for) for a capture under way, or None."""
        with self._capture_lock:
            if self._capture is None:
                return None
            return len(self._capture.frames), self._capture.count

    def collect(self, frame):
        """Reader thread: adds a frame to any capture under way."""
        with self._capture_lock:
            capture = self._capture
            if capture is None:
                return
            capture.frames.append(frame)
            if len(capture.frames) < capture.count:
                return
            self._capture = None
        self.captured.emit(capture)

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
        """
        Thread body: wait for new frames and forward them at a bounded rate.
        """
        image = None
        try:
            while not self._stop.is_set():
                if image is None:
                    image = self.attach()
                    if image is None:
                        # Wait out the retry interval, but stay interruptible
                        self._stop.wait(_ATTACH_RETRY_SECONDS)
                    continue

                try:
                    # 0.2s timeout so the loop still notices _stop being set
                    frame = shm_reader.wait_for_frame(image, timeout=0.2)
                except Exception as error:  # pragma: no cover - segment read failure path
                    self.detach(image, str(error))
                    image = None
                    continue

                if frame is None:
                    if shm_reader.segment_replaced(image):
                        self.detach(image, "segment was replaced, re-attaching")
                        image = None
                    continue

                self.slot.put(frame)
                self.collect(frame)
        finally:
            if image is not None:
                shm_reader.close(image)

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
        self.attached.emit(shm_reader.segment_path(image))
        return image

    def detach(self, image, reason):
        """Closes a handle that is no longer usable, and reports why."""
        shm_reader.close(image)
        self._failure_reported = False
        self.detached.emit(reason)


@register("shm")
class ShmTool(Tool):
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
        self.timer = None
        self.status = None
        self.status_text = ""
        self.connect_action = None
        self.disconnect_action = None

    def build(self):
        self.receiver = ShmReceiver(self.settings)
        self.receiver.attached.connect(self.on_attached)
        self.receiver.detached.connect(self.on_detached)
        self.receiver.captured.connect(self.on_captured)

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

        rate_action = QAction("Set display rate…", self.window)
        rate_action.triggered.connect(self.set_display_rate)
        menu.addAction(rate_action)

    def set_status(self, text):
        """Sets the status line, which a capture under way adds its progress to."""
        self.status_text = text
        self.show_capture_progress()

    def show_capture_progress(self):
        """Shows how far a capture has got, on the GUI thread at timer pace."""
        progress = self.receiver.capture_progress()
        text = self.status_text
        if progress is not None:
            text = f"{text} — saving frame {progress[0]} of {progress[1]}"
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

        self.timer.start()
        self.connect_action.setEnabled(False)
        self.disconnect_action.setEnabled(True)
        self.set_status(f"SHM: connecting to {self.settings.segment_name}…")

    def disconnect_from_shm(self):
        """Stops reading, abandoning any capture that has not finished."""
        self.timer.stop()
        self.receiver.stop()
        capture = self.receiver.cancel_capture()
        self.connect_action.setEnabled(True)
        self.disconnect_action.setEnabled(False)
        self.set_status("SHM: disconnected")
        if capture is None:
            self.window.show_message("Disconnected from SHM.")
        else:
            self.window.show_message(
                f"Disconnected from SHM. Saving {capture.count} frames was cancelled "
                f"after {len(capture.frames)}; nothing was written.")

    def shutdown(self):
        """Stops the reader thread so the app can actually exit."""
        self.timer.stop()
        self.receiver.stop()
        self.receiver.cancel_capture()

    def save_next_frames(self, count):
        """
        Saves the next `count` frames off the stream as one FITS cube, at
        <save directory>/<date>/<date>_<time>.fits for the moment this was
        asked.
        """
        if not self.receiver.running:
            self.window.show_message("Connect to shared memory to save several frames.")
            return

        when = datetime.now(timezone.utc)
        try:
            # Checked now rather than once the frames are in, so a directory
            # that cannot be made does not cost a whole capture.
            saving.day_directory(self.window.save_directory, when)
        except OSError as error:
            self.window.show_message(f"Could not save: {error}")
            return

        if not self.receiver.capture(count, when):
            self.window.show_message("Already saving frames; wait for that to finish.")
            return
        self.show_capture_progress()

    def on_captured(self, capture):
        """A capture is full: writes it out. Runs on the GUI thread."""
        self.show_capture_progress()
        try:
            cube, header, table, skipped = stack_frames(capture.frames)
            file_name = saving.next_save_path(self.window.save_directory, capture.when)
        except (ValueError, OSError) as error:
            self.window.show_message(f"Could not save {capture.count} frames: {error}")
            return

        if self.view_model.save_image(file_name, cube, header, table) and skipped:
            self.window.show_message(
                f"Saved {file_name}, but {skipped} frames arrived too fast to keep "
                f"and are missing from it.")

    def on_attached(self, path):
        """The reader thread is on a live segment now. Runs on the GUI thread."""
        self.set_status(f"SHM: reading {self.settings.segment_name}")
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
