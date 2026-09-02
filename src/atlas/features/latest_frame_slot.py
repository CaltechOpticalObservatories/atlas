# Standard Library Imports
import threading
import time


class LatestFrameSlot:
    """
    Thread-safe hand-off point between a fast producer and a slower consumer.

    put() always overwrites, so a producer running far ahead of the consumer
    (e.g. a 60 Hz frame source) never queues a backlog -- at most one pending
    frame exists at any time. take() only returns a frame once at least
    min_interval seconds have passed since the last successful take, so a
    consumer that calls it on every arrival still can't be driven faster than
    the configured cap.
    """

    def __init__(self, min_interval=0.0):
        self.min_interval = min_interval
        self._lock = threading.Lock()
        self._pending = None
        self._last_take = 0.0

    def put(self, value):
        """Producer side: overwrite whatever is pending."""
        with self._lock:
            self._pending = value

    def take(self):
        """Consumer side: the latest value if one is due, else None."""
        now = time.monotonic()
        with self._lock:
            if self._pending is None or now - self._last_take < self.min_interval:
                return None
            value, self._pending = self._pending, None
            self._last_take = now
            return value
