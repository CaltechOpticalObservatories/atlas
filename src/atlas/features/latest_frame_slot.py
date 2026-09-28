# Standard Library Imports
import threading


class LatestFrameSlot:
    """
    Thread-safe hand-off point between a fast producer and a slower consumer.

    put() always overwrites, so a producer running far ahead of the consumer
    (e.g. a 60 Hz frame source) never queues a backlog: at most one frame is
    pending at any time, and it is always the newest one.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._pending = None

    def put(self, value):
        """Producer side: overwrite whatever is pending."""
        with self._lock:
            self._pending = value

    def take(self):
        """Consumer side: the newest value, or None if nothing new arrived."""
        with self._lock:
            value, self._pending = self._pending, None
            return value
