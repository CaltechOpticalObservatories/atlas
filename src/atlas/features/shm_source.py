# Standard Library Imports
import threading

# Third-Party Library Imports
from PyQt5.QtWidgets import QAction
from PyQt5.QtCore import QObject, pyqtSignal

from .registry import Tool, register
from .latest_frame_slot import LatestFrameSlot
from . import shm_reader


class ShmReceiver(QObject):
    """
    Reads frames from an ImageStreamIO segment on a background thread.

    Mirrors ZmqReceiver's thread + signal handoff (nothing here touches the
    frame list or any widget directly). Arrival can run at the detector's
    full rate (60 Hz expected); a LatestFrameSlot caps how often
    frame_received actually fires, so a slow GUI can't be driven faster than
    settings.display_fps_cap regardless of arrival rate.
    """

    frame_received = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.thread = None
        self._stop = threading.Event()

    def start(self):
        """Starts reading, if not already running."""
        if self.thread is not None and self.thread.is_alive():
            return False

        self._stop.clear()
        self.thread = threading.Thread(target=self.receive, daemon=True)
        self.thread.start()
        return True

    def stop(self):
        """Asks the reader thread to shut down."""
        self._stop.set()
        if self.thread is not None:
            self.thread.join(timeout=2.0)
            self.thread = None

    def receive(self):
        """Thread body: wait for new frames and forward them at a bounded rate."""
        try:
            image = shm_reader.attach(self.settings.segment_name, self.settings.shm_dir)
        except Exception as error:  # pragma: no cover - segment unavailable path
            self.failed.emit(str(error))
            return

        slot = LatestFrameSlot(min_interval=1.0 / self.settings.display_fps_cap)

        try:
            while not self._stop.is_set():
                # 0.2s timeout so the loop still notices _stop being set.
                frame = shm_reader.wait_for_frame(image, timeout=0.2)
                if frame is None:
                    continue

                slot.put(frame)
                ready = slot.take()
                if ready is not None:
                    self.frame_received.emit(ready)

        except Exception as error:  # pragma: no cover - segment read failure path
            self.failed.emit(str(error))
        finally:
            shm_reader.close(image)


@register("shm")
class ShmTool(Tool):
    """Live-displays frames arriving on an ImageStreamIO shared-memory segment."""

    def __init__(self, window, settings):
        super().__init__(window, settings)
        self.receiver = None
        self.connect_action = None
        self.disconnect_action = None

    def build(self):
        self.receiver = ShmReceiver(self.settings)
        self.receiver.frame_received.connect(self.on_frame)
        self.receiver.failed.connect(
            lambda message: self.window.show_message(f"SHM error: {message}"))

        self.connect_action = QAction(f"Connect to {self.settings.segment_name}", self.window)
        self.connect_action.triggered.connect(self.connect_to_shm)
        self.window.tools_menu.addAction(self.connect_action)

        self.disconnect_action = QAction("Disconnect from SHM", self.window)
        self.disconnect_action.triggered.connect(self.disconnect_from_shm)
        self.disconnect_action.setEnabled(False)
        self.window.tools_menu.addAction(self.disconnect_action)

    def connect_to_shm(self):
        """Starts reading from the configured segment."""
        if self.receiver.start():
            self.connect_action.setEnabled(False)
            self.disconnect_action.setEnabled(True)
            self.window.show_message(f'Reading "{self.settings.segment_name}"')
        else:
            self.window.show_message("Already connected.")

    def disconnect_from_shm(self):
        """Stops reading."""
        self.receiver.stop()
        self.connect_action.setEnabled(True)
        self.disconnect_action.setEnabled(False)
        self.window.show_message("Disconnected from SHM.")

    def on_frame(self, frame):
        """Handles a new frame. Runs on the GUI thread."""
        self.view_model.update_live_frame(frame.data, frame.keywords)
