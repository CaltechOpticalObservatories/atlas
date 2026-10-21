"""
Captures frames off an ImageStreamIO segment in a process of its own.

A frame's keywords last only until the producer starts on the next frame, under
a millisecond at kHz rates, and its pixels only as long as the segment's ring
holds them. A thread in the GUI process cannot keep those deadlines: it shares
the interpreter lock with Qt, which holds it for milliseconds at a time while
drawing. A process has an interpreter to itself, so during a capture it can
watch cnt0 continuously and copy each frame the moment it is published.

The GUI process allocates the capture's buffers in shared memory and sends the
worker their names; the worker fills them and reports how many frames it kept.
Nothing is decided in the worker beyond what was copied when: whether a frame's
keywords really are its own is worked out afterwards (see frame_keywords).
"""

# Standard Library Imports
from collections import Counter
from dataclasses import dataclass
import gc
import multiprocessing
from multiprocessing import shared_memory
import struct
import threading
import time

# Third-Party Library Imports
import numpy as np
from PyQt5.QtCore import QObject, pyqtSignal

from . import shm_reader

# Spins between looks at things that cost more than reading cnt0
_SPINS_PER_CHECK = 4096
# How long without a frame before checking the segment was not replaced
_IDLE_CHECK_SECONDS = 0.2
_CNT0 = struct.Struct("<Q")
# Per frame: its cnt0, and 1 if the keyword area was copied while it was the
# newest frame, else 0
_COUNTERS = 2

CANCELLED = "cancelled"


def _buffer_size(nbytes):
    """SharedMemory refuses a size of 0, as for a segment with no keywords."""
    return max(1, nbytes)


@dataclass
class Capture:  # pylint: disable=too-many-instance-attributes
    """
    A request, made at `when`, to keep the next `count` frames, and the shared
    memory they go into.

    The cube is allocated whole at the start, and each frame is copied
    straight into its plane, so the capture never needs memory twice over.
    """
    count: int
    when: object  # datetime
    info: shm_reader.SegmentInfo
    nbkw: int
    path: str
    cube_memory: shared_memory.SharedMemory
    keyword_memory: shared_memory.SharedMemory
    counter_memory: shared_memory.SharedMemory
    kept: int = 0
    error: str = None

    @classmethod
    def allocate(cls, count, when, info, nbkw, path):
        """
        Makes the shared memory for a capture.

        Raises:
            OSError: when the system cannot provide it.
        """
        blocks = []
        try:
            for nbytes in (count * info.frame_bytes,
                           count * nbkw * shm_reader.KEYWORD_SIZE,
                           count * _COUNTERS * 8):
                blocks.append(shared_memory.SharedMemory(create=True,
                                                         size=_buffer_size(nbytes)))
        except (OSError, ValueError) as error:
            for block in blocks:
                block.close()
                block.unlink()
            raise OSError(f"could not set aside memory for {count} frames: {error}") from error
        return cls(count, when, info, nbkw, path,
                   cube_memory=blocks[0], keyword_memory=blocks[1], counter_memory=blocks[2])

    def request(self):
        """What the worker needs to fill this capture."""
        return {"path": self.path, "count": self.count,
                "shape": self.info.shape, "dtype": self.info.dtype.str, "ring": self.info.ring,
                "nbkw": self.nbkw, "cube": self.cube_memory.name,
                "keywords": self.keyword_memory.name, "counters": self.counter_memory.name}

    @property
    def cube(self):
        """The frames kept, as a (kept, height, width) view of the shared memory."""
        return np.ndarray((self.count, *self.info.shape), self.info.dtype,
                          buffer=self.cube_memory.buf)[:self.kept]

    @property
    def counters(self):
        """(kept, 2): each kept frame's cnt0, and whether its keywords were copied with it."""
        return np.ndarray((self.count, _COUNTERS), np.uint64,
                          buffer=self.counter_memory.buf)[:self.kept]

    def keyword_block(self, index):
        """The copy of the keyword area taken with kept frame `index`."""
        size = self.nbkw * shm_reader.KEYWORD_SIZE
        # Copied out: a view left alive would stop release() unmapping.
        return bytes(self.keyword_memory.buf[index * size:(index + 1) * size])

    def release(self):
        """Gives the shared memory back. Every view of it must be gone by now."""
        for block in (self.cube_memory, self.keyword_memory, self.counter_memory):
            try:
                block.close()
            except BufferError:  # pragma: no cover - a view outlived the write
                pass  # unmapped once that view goes; unlinking frees it then
            try:
                block.unlink()
            except FileNotFoundError:  # pragma: no cover - already gone
                pass


def frame_keywords(capture):
    """
    Each kept frame's keywords, or None where they cannot be shown to be its own.

    A copy taken while a frame was the newest can still hold the next frame's
    keywords: the producer writes those before it publishes that frame. Each
    keyword's write counter tells the two apart. A producer that writes every
    keyword once per frame keeps counter minus cnt0 the same from frame to
    frame, so a copy whose difference is not the usual one was taken after
    the next frame's keywords went in. A producer that never bumps the
    counters cannot be checked this way, and its copies are taken at their word.
    """
    counters = capture.counters.tolist()
    decoded = [None] * capture.kept
    counts = {}
    for index, (_, copied) in enumerate(counters):
        if copied:
            decoded[index], counts[index] = shm_reader.decode_keywords(
                capture.keyword_block(index), capture.nbkw)

    if len(set(counts.values())) > 1:  # the producer does bump them
        offsets = {index: tuple(count - counters[index][0] for count in frame_counts)
                   for index, frame_counts in counts.items()}
        usual, _ = Counter(offsets.values()).most_common(1)[0]
        for index, offset in offsets.items():
            if offset != usual:
                decoded[index] = None
    return decoded


class CaptureProcess(QObject):
    """
    The capture worker, seen from the GUI process.

    Spawning re-imports the main script in the worker, so a script that
    builds an atlas window itself needs the usual `if __name__ == "__main__"`
    guard; the atlas command and the demo script have one.
    """

    # (Capture, kept, error): a capture has ended, error None if it filled
    ended = pyqtSignal(object, int, object)

    def __init__(self):
        super().__init__()
        # Spawned rather than forked: a forked copy of a Qt process is unsafe.
        context = multiprocessing.get_context("spawn")
        # One-way pipes, receiving end first: requests go to the worker,
        # results come back.
        requests, self._requests = context.Pipe(duplex=False)
        self._results, results = context.Pipe(duplex=False)
        self.progress = context.RawValue("Q", 0)
        self.cancel = context.Event()
        self.process = context.Process(target=serve, name="atlas-capture", daemon=True,
                                       args=(requests, results, self.progress, self.cancel))
        self.process.start()
        # The worker's ends belong to it now.
        requests.close()
        results.close()
        self.capture = None
        self._waiter = None

    @property
    def busy(self):
        """True while a capture is under way."""
        return self.capture is not None

    def start(self, capture):
        """Starts filling `capture`; `ended` follows once it is full or given up."""
        self.cancel.clear()
        self.progress.value = 0
        self.capture = capture
        self._requests.send(capture.request())
        self._waiter = threading.Thread(target=self._wait, args=(capture,), daemon=True)
        self._waiter.start()

    def _wait(self, capture):
        try:
            kept, error = self._results.recv()
        except (EOFError, OSError):
            kept, error = 0, "the capture process stopped"
        self.capture = None
        self.ended.emit(capture, kept, error)

    def stop(self):
        """Ends any capture under way, and the worker with it."""
        self.cancel.set()
        try:
            self._requests.send(None)
        except OSError:  # pragma: no cover - the worker has already gone
            pass
        self.process.join(timeout=2.0)
        if self.process.is_alive():  # pragma: no cover - a worker that will not stop
            self.process.terminate()
            self.process.join(timeout=1.0)
        if self._waiter is not None:
            self._waiter.join(timeout=2.0)


def serve(requests, results, progress, cancel):
    """Worker process body: fills one capture at a time until told to stop."""
    while True:
        try:
            request = requests.recv()
        except EOFError:
            return
        if request is None:
            return
        results.send(run(request, progress, cancel))


def run(request, progress, cancel):
    """Fills the capture `request` describes. Returns (kept, error)."""
    # Anything going wrong is reported back rather than ending the worker.
    # pylint: disable=broad-exception-caught
    try:
        handle = shm_reader.attach_path(request["path"])
    except Exception as error:
        return 0, f"could not open the segment: {error}"
    blocks = []
    try:
        for name in ("cube", "keywords", "counters"):
            blocks.append(shared_memory.SharedMemory(request[name]))
        info = shm_reader.segment_info(handle)
        if (info.shape != tuple(request["shape"]) or info.dtype.str != request["dtype"]
                or info.ring != request["ring"] or handle.nbkw != request["nbkw"]):
            return 0, "the frame size changed before the capture began"
        return capture_frames(handle, request["count"], *(block.buf for block in blocks),
                              progress, cancel)
    except Exception as error:
        return progress.value, f"the capture failed: {error}"
    finally:
        for block in blocks:
            block.close()
        shm_reader.close(handle)


def capture_frames(handle, count, cube, keywords, counters, progress, cancel):
    """
    Copies the next `count` frames published into the buffers, keeping time.

    Spins on cnt0 rather than sleeping: a sleep can last longer than a frame.
    When cnt0 moves, the keyword area is copied first, since it is the next
    thing the producer overwrites; then every frame since the last one that
    the ring still holds, oldest first; then cnt0 is read again, and any copy
    the producer may have lapped meanwhile is dropped, so a lost frame shows
    as a gap in cnt0 and a torn one is never kept.

    Returns:
        tuple: (frames kept, None if all were, or why the capture stopped short).
    """
    # One loop, inline on purpose: every call per frame is time the producer
    # does not give.
    # pylint: disable=too-many-arguments, too-many-positional-arguments, too-many-locals
    # pylint: disable=too-many-branches, too-many-statements, too-many-nested-blocks
    mm = handle.mm
    info = shm_reader.segment_info(handle)
    ring = info.ring
    frame_bytes = info.frame_bytes
    kw_offset, kw_size = shm_reader.keyword_area(handle)
    cnt0_offset = shm_reader.OFFSET_CNT0
    read = _CNT0.unpack_from
    segment = memoryview(mm)
    numbers = counters.cast("Q")
    scratch = bytearray(kw_size)

    gc.disable()
    try:
        last = read(mm, cnt0_offset)[0]
        kept = 0
        spins = 0
        idle_since = time.monotonic()
        while kept < count:
            newest = read(mm, cnt0_offset)[0]
            if newest == last:
                spins += 1
                if spins % _SPINS_PER_CHECK == 0:
                    if cancel.is_set():
                        return kept, CANCELLED
                    now = time.monotonic()
                    if now - idle_since >= _IDLE_CHECK_SECONDS:
                        idle_since = now
                        if shm_reader.segment_replaced(handle):
                            return kept, "the segment was recreated partway through"
                continue
            if newest < last:
                return kept, "the segment was recreated partway through"
            if cancel.is_set():  # a microsecond or so, against a frame period
                return kept, CANCELLED

            scratch[:] = segment[kw_offset:kw_offset + kw_size]
            keywords_fresh = read(mm, cnt0_offset)[0] == newest

            if ring:
                first = max(last + 1, shm_reader.oldest_in_ring(handle, newest))
            else:
                first = newest  # the live frame is all there is
            for number in range(first, newest + 1):
                if kept == count:
                    break
                if ring:
                    source = handle.ring_offset + (number % ring) * handle.imdatamemsize
                else:
                    source = handle.data_offset
                cube[kept * frame_bytes:(kept + 1) * frame_bytes] = \
                    segment[source:source + frame_bytes]
                now_newest = read(mm, cnt0_offset)[0]
                if (number < shm_reader.oldest_in_ring(handle, now_newest) if ring
                        else now_newest != number):
                    continue  # overwritten while being copied
                with_keywords = number == newest and keywords_fresh
                if with_keywords:
                    keywords[kept * kw_size:(kept + 1) * kw_size] = scratch
                numbers[kept * _COUNTERS] = number
                numbers[kept * _COUNTERS + 1] = int(with_keywords)
                kept += 1
                progress.value = kept
            last = newest
            idle_since = time.monotonic()
        return kept, None
    finally:
        gc.enable()
        numbers.release()
        segment.release()
