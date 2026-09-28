# Standard Library Imports
import threading

# Third-Party Library Imports
from PyQt5.QtWidgets import QAction, QDialog, QLabel, QSlider, QVBoxLayout
from PyQt5.QtCore import QObject, Qt, QTimer, pyqtSignal

from .registry import Tool, register
from .latest_frame_slot import LatestFrameSlot
from . import shm_reader

_MIN_DISPLAY_HZ = 1
_MAX_DISPLAY_HZ = 120
_ATTACH_RETRY_SECONDS = 1.0


class ShmReceiver(QObject):
    """
    Reads frames from an ImageStreamIO segment on a background thread.
    """

    attached = pyqtSignal(str)
    detached = pyqtSignal(str)

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.thread = None
        self.slot = LatestFrameSlot()
        self._stop = threading.Event()
        self._failure_reported = False

    def start(self):
        """
        Starts reading, if not already running.

        True means the reader thread started, not that a segment was found:
        attaching happens on that thread and is retried until it succeeds, so
        callers must wait for `attached` before claiming to be reading.
        """
        if self.thread is not None and self.thread.is_alive():
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
        self.connect_action = None
        self.disconnect_action = None

    def build(self):
        self.receiver = ShmReceiver(self.settings)
        self.receiver.attached.connect(self.on_attached)
        self.receiver.detached.connect(self.on_detached)

        self.timer = QTimer(self.window)
        self.timer.setInterval(self.interval_ms(self.settings.display_fps_cap))
        self.timer.timeout.connect(self.show_latest_frame)

        # A permanent widget rather than a status message: "connected but
        # receiving nothing" is exactly the state that has to stay on screen,
        # since otherwise it looks the same as a detector sitting idle.
        self.status = QLabel()
        self.window.statusBar().addPermanentWidget(self.status)
        self.status.setText("SHM: disconnected")

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
        self.status.setText(f"SHM: connecting to {self.settings.segment_name}…")

    def disconnect_from_shm(self):
        """Stops reading."""
        self.timer.stop()
        self.receiver.stop()
        self.connect_action.setEnabled(True)
        self.disconnect_action.setEnabled(False)
        self.status.setText("SHM: disconnected")
        self.window.show_message("Disconnected from SHM.")

    def shutdown(self):
        """Stops the reader thread so the app can actually exit."""
        self.timer.stop()
        self.receiver.stop()

    def on_attached(self, path):
        """The reader thread is on a live segment now. Runs on the GUI thread."""
        self.status.setText(f"SHM: reading {self.settings.segment_name}")
        self.window.show_message(f"Reading {path}")

    def on_detached(self, reason):
        """
        The reader thread has no usable segment. Runs on the GUI thread.
        """
        self.status.setText(f"SHM: not reading {self.settings.segment_name}")
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
        frame = self.receiver.slot.take()
        if frame is None:
            return
        self.view_model.update_live_frame(frame.data, frame.keywords)
