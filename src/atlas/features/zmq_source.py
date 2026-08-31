# Standard Library Imports
import threading

# Third-Party Library Imports
from PyQt5.QtWidgets import QAction, QInputDialog
from PyQt5.QtCore import QObject, pyqtSignal

from .registry import Tool, register


class ZmqReceiver(QObject):
    """
    Receives file names on a background thread.

    Nothing here touches the frame list or any widget directly: the file name
    is handed over with a signal, which Qt queues onto the GUI thread. Mutating
    the frame list from the receiver thread would race with the UI.
    """

    file_received = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.thread = None
        self._stop = threading.Event()

    def start(self, address):
        """Starts listening, if not already running."""
        if self.thread is not None and self.thread.is_alive():
            return False

        self._stop.clear()
        self.thread = threading.Thread(target=self.receive, args=(address,), daemon=True)
        self.thread.start()
        return True

    def stop(self):
        """Asks the receiver thread to shut down."""
        self._stop.set()
        if self.thread is not None:
            self.thread.join(timeout=2.0)
            self.thread = None

    def receive(self, address):
        """Thread body: poll the socket and forward every file name."""
        # Imported here so atlas still runs when pyzmq is absent and this
        # feature is switched off.
        import zmq  # pylint: disable=import-outside-toplevel

        context = zmq.Context()
        socket = context.socket(getattr(zmq, self.settings.socket_type))

        try:
            if self.settings.bind:
                socket.bind(address)
            else:
                socket.connect(address)

            # A SUB socket receives nothing until it subscribes.
            if self.settings.socket_type == "SUB":
                socket.setsockopt_string(zmq.SUBSCRIBE, self.settings.topic)

            # Poll rather than block forever, so the thread can be stopped.
            while not self._stop.is_set():
                if socket.poll(timeout=200) == 0:
                    continue
                self.file_received.emit(socket.recv_string())

        except Exception as error:  # pragma: no cover - network failure path
            self.failed.emit(str(error))
        finally:
            socket.close()
            context.term()


@register("zmq")
class ZmqTool(Tool):
    """Connects to a ZMQ endpoint that publishes FITS file names."""

    def __init__(self, window, settings):
        super().__init__(window, settings)
        self.receiver = None
        self.connect_action = None
        self.disconnect_action = None

    def build(self):
        self.receiver = ZmqReceiver(self.settings)
        self.receiver.file_received.connect(self.on_file)
        self.receiver.failed.connect(
            lambda message: self.window.show_message(f"ZMQ error: {message}"))

        self.connect_action = QAction("Connect to ZMQ…", self.window)
        self.connect_action.triggered.connect(self.connect_to_zmq)
        self.window.tools_menu.addAction(self.connect_action)

        self.disconnect_action = QAction("Disconnect from ZMQ", self.window)
        self.disconnect_action.triggered.connect(self.disconnect_from_zmq)
        self.disconnect_action.setEnabled(False)
        self.window.tools_menu.addAction(self.disconnect_action)

    def connect_to_zmq(self):
        """Asks for an endpoint, defaulting to the configured one, and listens."""
        address, accepted = QInputDialog.getText(
            self.window, "Connect to ZMQ", "ZMQ address:", text=self.settings.address)
        if not accepted or not address:
            return

        if self.receiver.start(address):
            self.connect_action.setEnabled(False)
            self.disconnect_action.setEnabled(True)
            self.window.show_message(f"Listening on {address}")
        else:
            self.window.show_message("Already connected.")

    def disconnect_from_zmq(self):
        """Stops listening."""
        self.receiver.stop()
        self.connect_action.setEnabled(True)
        self.disconnect_action.setEnabled(False)
        self.window.show_message("Disconnected from ZMQ.")

    def on_file(self, file_name):
        """Loads a file announced over ZMQ. Runs on the GUI thread."""
        self.view_model.load_file(file_name)
