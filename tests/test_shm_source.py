"""
The shm_source live-view plumbing, without a real ImageStreamIO segment.

Monkeypatches shm_reader's seam with a synthetic producer running far past the
expected 60 Hz and asserts the throttle/display pipeline holds: a fast producer
must not queue a backlog, grow the frame list, or drive the GUI faster than the
configured display cap.
"""

# pytest injects fixtures as arguments of the same name, and some are taken
# purely for their side effect: `qapp` has to exist for the receiver's
# cross-thread state signals to be deliverable at all. The segment writer below
# uses shm_reader's own layout constants rather than a second copy of the
# offsets, which would be free to drift from the ones actually being read.
# pylint: disable=redefined-outer-name, protected-access, unused-argument

# Standard Library Imports
from datetime import datetime, timezone
from multiprocessing import shared_memory
import os
import struct
import threading
import time
from types import SimpleNamespace

# Third-Party Library Imports
import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication, QFileDialog

from astropy.io import fits

from atlas.config.schema import AtlasConfig, ConfigError, SaveConfig, ShmConfig, ToolsConfig
from atlas.features import shm_capture, shm_reader
from atlas.features.shm_source import ShmReceiver, capture_table
from atlas.model import capture_budget
from atlas.model.fits_model import CUBE_WRITE_OVERHEAD_BYTES
from atlas.viewmodel.frame_viewmodel import FrameViewModel

DISPLAY_FPS_CAP = 15.0
RUN_SECONDS = 1.5
MAX_TRAILING_PULLS = 5

SEGMENT = "ci-synthetic"
WIDTH = HEIGHT = 8
PRODUCER_HZ = 60


# Stands in for everything ImageStreamIO lays out between the keywords and the
# ring (semaphores, PIDs, proc traces), whose size the reader must not depend on.
SEGMENT_FILLER = 1000


def create_segment(directory, width=WIDTH, height=HEIGHT, ring=0):
    """
    Writes an empty segment file, the way ImageStreamIO_createIm does, with one
    keyword, FRAMENO, and a ring of `ring` frames at the end when above 0.
    """
    path = os.path.join(directory, f"{SEGMENT}.im.shm")
    imdatamemsize = width * height * 2  # uint16

    buffer = bytearray(shm_reader._METADATA_SIZE + imdatamemsize + shm_reader._KEYWORD_SIZE
                       + (SEGMENT_FILLER + imdatamemsize * ring if ring else 0))
    struct.pack_into("<I", buffer, shm_reader._OFFSET_NAXIS, 2)
    struct.pack_into("<III", buffer, shm_reader._OFFSET_SIZE, width, height, 0)
    struct.pack_into("<B", buffer, shm_reader._OFFSET_DATATYPE, 3)  # uint16
    struct.pack_into("<Q", buffer, shm_reader._OFFSET_CNT0, 0)
    struct.pack_into("<H", buffer, shm_reader._OFFSET_NBKW, 1)
    struct.pack_into("<I", buffer, shm_reader._OFFSET_CBSIZE, ring)
    struct.pack_into("<I", buffer, shm_reader._OFFSET_CBINDEX, 0)
    struct.pack_into("<Q", buffer, shm_reader._OFFSET_IMDATAMEMSIZE, imdatamemsize)
    keyword = keyword_offset(width, height)
    buffer[keyword:keyword + len(b"FRAMENO")] = b"FRAMENO"
    buffer[keyword + shm_reader._KW_OFFSET_TYPE] = ord("L")

    if os.path.exists(path):
        os.unlink(path)
    with open(path, "wb") as segment_file:
        segment_file.write(buffer)
    return path


def keyword_offset(width=WIDTH, height=HEIGHT):
    """Where a segment's one keyword starts."""
    return shm_reader._METADATA_SIZE + shm_reader._round_up_8(width * height * 2)


def frame_value(number):
    """What every pixel of frame `number` holds, so a frame says which it is."""
    return number % 65536


# The producer's own frame numbers, deliberately unrelated to cnt0, so a test
# can tell a FRAMENO read from the segment from one worked out from cnt0
FRAMENO_BASE = 7_000_000


def write_frame(path, number, ring=0, publish=True, width=WIDTH, height=HEIGHT):
    # pylint: disable=too-many-arguments, too-many-positional-arguments
    """
    Producer side, as an ImageStreamIO writer does: fill the live frame and
    rewrite its keyword, bumping the keyword's write counter; then what
    ImageStreamIO_UpdateIm does: copy it into the next ring slot, advance
    CBindex, and only then bump cnt0. With `publish` False it stops short of
    advancing CBindex and cnt0, so a test can publish several at once.
    """
    pixels = np.full((height, width), frame_value(number), np.uint16).tobytes()
    keyword = keyword_offset(width, height)
    with open(path, "r+b") as segment_file:
        segment_file.seek(shm_reader._METADATA_SIZE)
        segment_file.write(pixels)
        segment_file.seek(keyword + shm_reader._KW_OFFSET_CNT)
        (count,) = struct.unpack("<Q", segment_file.read(8))
        segment_file.seek(keyword + shm_reader._KW_OFFSET_VALUE)
        segment_file.write(struct.pack("<q", FRAMENO_BASE + number))
        segment_file.seek(keyword + shm_reader._KW_OFFSET_CNT)
        segment_file.write(struct.pack("<Q", count + 1))
        if ring:
            ring_offset = os.path.getsize(path) - len(pixels) * ring
            segment_file.seek(ring_offset + (number % ring) * len(pixels))
            segment_file.write(pixels)
    if publish:
        publish_frame(path, number, ring)


def publish_frame(path, number, ring=0):
    """Advances CBindex and cnt0 to frame `number`, as the end of UpdateIm does."""
    with open(path, "r+b") as segment_file:
        if ring:
            segment_file.seek(shm_reader._OFFSET_CBINDEX)
            segment_file.write(struct.pack("<I", number % ring))
        segment_file.seek(shm_reader._OFFSET_CNT0)
        segment_file.write(struct.pack("<Q", number))


@pytest.fixture
def producer():
    """Runs a 60 Hz writer against a segment path, and always stops it."""
    threads = []

    def start(path, ring=0):
        stop = threading.Event()

        def run():
            number = 1
            while not stop.is_set():
                write_frame(path, number, ring=ring)
                number += 1
                time.sleep(1 / PRODUCER_HZ)

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        threads.append((stop, thread))
        return stop

    yield start

    for stop, thread in threads:
        stop.set()
        thread.join(timeout=2.0)


@pytest.fixture
def receiver_for(tmp_path):
    """Builds a receiver on a temp shm dir, and always stops its thread."""
    built = []

    def build():
        settings = ShmConfig(enabled=True, segment_name=SEGMENT,
                             shm_dir=str(tmp_path), display_fps_cap=DISPLAY_FPS_CAP)
        receiver = ShmReceiver(settings)
        built.append(receiver)
        return receiver

    yield build

    for receiver in built:
        receiver.stop()


def wait_until(predicate, timeout=5.0):
    """
    True once predicate holds, False if it never does within timeout.
    """
    app = QApplication.instance()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if app is not None:
            app.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_segment_replaced_spots_a_recreated_file(tmp_path):
    """The stale mapping stays readable, so only the inode gives it away."""
    path = create_segment(str(tmp_path))
    handle = shm_reader.attach(SEGMENT, str(tmp_path))
    try:
        assert not shm_reader.segment_replaced(handle)
        create_segment(str(tmp_path))  # camerad restarts
        assert shm_reader.segment_replaced(handle)
    finally:
        shm_reader.close(handle)
    assert os.path.exists(path)


def test_segment_replaced_spots_a_deleted_file(tmp_path):
    """A removed segment is not one we can keep reading either."""
    path = create_segment(str(tmp_path))
    handle = shm_reader.attach(SEGMENT, str(tmp_path))
    try:
        os.unlink(path)
        assert shm_reader.segment_replaced(handle)
    finally:
        shm_reader.close(handle)


def test_receiver_reattaches_after_the_producer_restarts(
        qapp, tmp_path, producer, receiver_for):
    path = create_segment(str(tmp_path))
    producer(path)

    receiver = receiver_for()
    receiver.start()
    assert wait_until(lambda: receiver.slot.take() is not None), "no frames before the restart"

    create_segment(str(tmp_path))  # camerad restarts: new inode, cnt0 back to 0
    producer(path)

    assert wait_until(lambda: receiver.slot.take() is not None), \
        "the receiver stayed on the orphaned inode instead of re-attaching"


def test_receiver_waits_for_a_segment_that_does_not_exist_yet(
        qapp, tmp_path, producer, receiver_for):
    """Connecting before camerad starts must recover on its own, not die."""
    receiver = receiver_for()
    detached = []
    receiver.detached.connect(detached.append)

    receiver.start()
    assert wait_until(lambda: receiver.thread.is_alive() and detached), \
        "a missing segment should be reported, not swallowed"
    assert receiver.thread.is_alive(), "the reader thread should keep retrying"

    path = create_segment(str(tmp_path))  # camerad finally starts
    producer(path)

    assert wait_until(lambda: receiver.slot.take() is not None), \
        "the receiver never picked up the segment once it appeared"


def test_a_missing_segment_is_reported_once_not_every_retry(qapp, tmp_path, receiver_for):
    """Retrying every second must not turn the status line into a strobe."""
    assert not os.listdir(tmp_path)
    receiver = receiver_for()
    detached = []
    receiver.detached.connect(detached.append)

    receiver.start()
    assert wait_until(lambda: detached)
    time.sleep(1.5)  # long enough for several retries
    assert len(detached) == 1, f"expected one report, got {detached}"


@pytest.fixture
def fake_producer():
    counter = {"n": 0}

    def wait_for_frame(_image, timeout, **_):  # pylint: disable=unused-argument
        counter["n"] += 1
        data = np.full((4, 4), counter["n"] % 256, dtype=np.uint16)
        return shm_reader.ShmFrame(data=data, keywords={"FRAMENO": counter["n"]},
                                   cnt0=counter["n"])

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(shm_reader, "attach", lambda _name, _dir="": "fake-handle")
        patch.setattr(shm_reader, "segment_path", lambda _image: "fake-path")
        patch.setattr(shm_reader, "segment_replaced", lambda _image: False)
        patch.setattr(shm_reader, "segment_info",
                      lambda _image: shm_reader.SegmentInfo((4, 4), np.dtype(np.uint16)))
        patch.setattr(shm_reader, "keyword_count", lambda _image: 0)
        patch.setattr(shm_reader, "wait_for_frame", wait_for_frame)
        patch.setattr(shm_reader, "close", lambda _image: None)
        yield counter


@pytest.fixture
def slow_gui_run(qapp, fake_producer):
    """
    Runs a fast producer against a consumer too slow to keep up with it.
    """
    settings = ShmConfig(enabled=True, segment_name=SEGMENT,
                         display_fps_cap=DISPLAY_FPS_CAP)
    view_model = FrameViewModel(AtlasConfig())
    receiver = ShmReceiver(settings)

    displayed = []
    render_cost = 2.0 / DISPLAY_FPS_CAP  # twice as slow as the cap asks for

    def pull():
        frame = receiver.slot.take()
        if frame is None:
            return
        time.sleep(render_cost)
        view_model.update_live_frame(frame.data, frame.keywords)
        displayed.append(frame.keywords["FRAMENO"])

    assert receiver.start(), "the receiver should start"
    try:
        deadline = time.monotonic() + RUN_SECONDS
        while time.monotonic() < deadline:
            pull()
            qapp.processEvents()
        produced_when_stopped = fake_producer["n"]
        displayed_when_stopped = len(displayed)
    finally:
        receiver.stop()

    # The producer is gone. Whatever a real GUI would still draw is drawn now.
    trailing = 0
    while trailing < MAX_TRAILING_PULLS:
        before = len(displayed)
        pull()
        qapp.processEvents()
        if len(displayed) == before:
            break
        trailing += 1

    return SimpleNamespace(view_model=view_model, receiver=receiver,
                           arrivals=fake_producer["n"], displayed=displayed,
                           produced_when_stopped=produced_when_stopped,
                           displayed_when_stopped=displayed_when_stopped,
                           trailing=trailing)


def test_producer_outruns_the_display(slow_gui_run):
    assert slow_gui_run.arrivals > 1000
    assert len(slow_gui_run.displayed) < slow_gui_run.arrivals / 10


def test_nothing_trails_after_the_producer_stops(slow_gui_run):
    assert slow_gui_run.trailing <= 1, (
        f"at least {slow_gui_run.trailing} frames still displayed after the "
        f"producer stopped; at most the one pending frame should remain")


def test_the_gui_always_gets_the_newest_frame(slow_gui_run):
    displayed = slow_gui_run.displayed
    assert displayed == sorted(displayed), "frames should never go backwards"
    # Each displayed frame cost render_cost, during which the producer ran on,
    # so consecutive displays must be far apart rather than consecutive.
    gaps = [b - a for a, b in zip(displayed, displayed[1:])]
    assert gaps and min(gaps) > 1, (
        "consecutive FRAMENOs mean the consumer is walking a queue, not "
        f"taking the latest: {displayed[:10]}")


def test_live_view_does_not_grow_the_frame_list(slow_gui_run):
    assert len(slow_gui_run.view_model.frames) == 1


def test_stop_joins_the_reader_thread(slow_gui_run):
    assert slow_gui_run.receiver.thread is None


def test_stop_drops_the_pending_frame(slow_gui_run):
    """Reconnecting should not open on an image from the previous session."""
    assert slow_gui_run.receiver.slot.take() is None


# Saving several frames at once: kept by the capture worker, written as a cube.

NOW = datetime(2026, 10, 12, 19, 6, 37, tzinfo=timezone.utc)


def test_table_keeps_every_frame_and_its_own_keywords():
    """One header for the cube, but each frame's keywords survive in the table."""
    header, table, skipped, missing = capture_table(
        [5, 6, 7], [{"FRAMENO": n, "MODE": "CDS"} for n in (5, 6, 7)])

    assert header["FRAMENO"] == 5 and header["NSKIPPED"] == 0
    assert "NKWMISS" not in header and missing == 0
    assert table is not None
    assert list(table.columns["CNT0"]) == [5, 6, 7]
    assert list(table.columns["FRAMENO"]) == [5, 6, 7]
    assert skipped == 0


def test_table_counts_frames_the_reader_missed():
    """A jump in cnt0 means frames went by unread; the file has to say so."""
    header, _, skipped, _ = capture_table([10, 11, 14, 15], [{}] * 4)
    assert skipped == 2
    assert header["NSKIPPED"] == 2


def test_table_without_cnt0_does_not_guess():
    """Frames that carry no counter cannot say whether any were missed."""
    header, table, skipped, _ = capture_table([None, None], [{"FRAMENO": 1}, {"FRAMENO": 2}])
    assert skipped is None
    assert "NSKIPPED" not in header
    assert table.colnames == ["FRAMENO"]


def test_frames_read_without_keywords_are_masked_not_invented():
    """
    A frame whose keywords could not be shown to be its own has them masked;
    borrowing a neighbour's would put a wrong FRAMENO against it.
    """
    header, table, _, missing = capture_table([1, 2, 3], [None, {"FRAMENO": 2}, None])

    assert header["FRAMENO"] == 2, "the header comes from the first frame that has keywords"
    assert header["NKWMISS"] == 2 and missing == 2
    assert list(table.columns["FRAMENO"].mask) == [True, False, True]
    assert table.columns["FRAMENO"][1] == 2


# Reading the ring directly, frame by frame, with no thread to time.

RING = 8


@pytest.fixture
def ring_segment(tmp_path):
    """A segment with an 8-frame ring, and a handle on it."""
    path = create_segment(str(tmp_path), ring=RING)
    handle = shm_reader.attach(SEGMENT, str(tmp_path))
    yield path, handle
    shm_reader.close(handle)


def test_ring_frames_are_read_by_number(ring_segment):
    """Frame n sits in slot n % CBsize, so asking by number finds it."""
    path, handle = ring_segment
    for number in range(1, 6):
        write_frame(path, number, ring=RING)

    assert shm_reader.segment_info(handle).ring == RING
    for number in range(1, 6):
        assert shm_reader.read_ring(handle, number)[0, 0] == frame_value(number)


def test_ring_reads_into_the_array_given(ring_segment):
    """A capture's cube is filled in place, with no copy in between."""
    path, handle = ring_segment
    write_frame(path, 1, ring=RING)
    plane = np.zeros((HEIGHT, WIDTH), np.uint16)

    assert shm_reader.read_ring(handle, 1, out=plane) is plane
    assert plane[0, 0] == frame_value(1)


def test_an_overwritten_frame_is_refused_not_returned(ring_segment):
    """
    Once the producer has come round the ring, the slot holds a later frame;
    so does the slot it may be writing next.
    """
    path, handle = ring_segment
    for number in range(1, 21):
        write_frame(path, number, ring=RING)

    oldest = shm_reader.oldest_in_ring(handle, 20)
    assert oldest == 20 - RING + 2
    assert shm_reader.read_ring(handle, oldest - 1) is None
    assert shm_reader.read_ring(handle, oldest)[0, 0] == frame_value(oldest)


def test_a_ring_out_of_step_with_cnt0_is_not_trusted(tmp_path):
    """Frame numbers only find their slots if cnt0 and CBindex move together."""
    path = create_segment(str(tmp_path), ring=RING)
    with open(path, "r+b") as segment_file:
        segment_file.seek(shm_reader._OFFSET_CBINDEX)
        segment_file.write(struct.pack("<I", 5))  # cnt0 is still 0
    handle = shm_reader.attach(SEGMENT, str(tmp_path))
    try:
        assert shm_reader.segment_info(handle).ring == 0
    finally:
        shm_reader.close(handle)


def test_a_frame_that_landed_meanwhile_is_not_lost(tmp_path):
    """
    Without a ring, a frame published while the last was being handled must
    be returned at once, not taken as the new baseline and waited past.
    """
    path = create_segment(str(tmp_path))
    handle = shm_reader.attach(SEGMENT, str(tmp_path))
    try:
        write_frame(path, 1)
        write_frame(path, 2)  # lands while the caller is busy with frame 1

        frame = shm_reader.wait_for_frame(handle, timeout=0.05, after=1)

        assert frame is not None and frame.cnt0 == 2
    finally:
        shm_reader.close(handle)


def test_the_display_is_only_copied_a_frame_once_it_took_the_last(
        qapp, ring_segment, receiver_for):
    """At kHz rates, copying every frame for a 15 Hz display is wasted work."""
    path, handle = ring_segment
    receiver = receiver_for()
    receiver.info = shm_reader.segment_info(handle)
    write_frame(path, 1, ring=RING)
    receiver.read_from_ring(handle)
    write_frame(path, 2, ring=RING)
    receiver.read_from_ring(handle)

    frame = receiver.slot.take()
    assert frame.cnt0 == 1, "frame 1 was still waiting, so frame 2 was not copied"
    assert frame.keywords == {"FRAMENO": FRAMENO_BASE + 1}
    write_frame(path, 3, ring=RING)
    receiver.read_from_ring(handle)
    assert receiver.slot.take().cnt0 == 3


# The capture worker's loop, run here on a thread against frames published by
# hand, so each test decides exactly what the worker finds when it looks.

class WorkerRun:  # pylint: disable=too-many-instance-attributes
    """capture_frames running on a thread, with buffers standing in for shared memory."""

    def __init__(self, handle, count):
        info = shm_reader.segment_info(handle)
        self.handle, self.count, self.info = handle, count, info
        self.cube = bytearray(count * info.frame_bytes)
        self.keywords = bytearray(count * handle.nbkw * shm_reader.KEYWORD_SIZE)
        self.counters = bytearray(count * 16)
        self.progress = SimpleNamespace(value=0)
        self.cancel = threading.Event()
        self.result = None
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()
        time.sleep(0.05)  # let it read the cnt0 it starts from

    def run(self):
        """Thread body."""
        buffers = [memoryview(buffer) for buffer in (self.cube, self.keywords, self.counters)]
        self.result = shm_capture.capture_frames(self.handle, self.count, *buffers,
                                                 self.progress, self.cancel)

    def wait_for(self, kept):
        """Waits until the worker has kept `kept` frames."""
        assert wait_until(lambda: self.progress.value >= kept, timeout=2.0), \
            f"kept {self.progress.value}, expected {kept}"

    def finish(self):
        """The worker's (kept, error), and the capture as the GUI would see it."""
        self.thread.join(timeout=5.0)
        assert not self.thread.is_alive(), "the worker never finished"
        kept, error = self.result
        capture = SimpleNamespace(
            kept=kept, nbkw=self.handle.nbkw,
            counters=np.frombuffer(self.counters, np.uint64).reshape(-1, 2)[:kept],
            cube=np.frombuffer(self.cube, self.info.dtype).reshape(-1, *self.info.shape)[:kept])
        size = self.handle.nbkw * shm_reader.KEYWORD_SIZE
        capture.keyword_block = lambda i: bytes(self.keywords[i * size:(i + 1) * size])
        return kept, error, capture


def numbers_of(capture):
    """The cnt0 of every frame a capture kept."""
    return capture.counters[:, 0].tolist()


def test_the_worker_keeps_every_frame_with_its_own_keywords(ring_segment):
    """A worker that sees every frame published keeps each with its keywords."""
    path, handle = ring_segment
    run = WorkerRun(handle, 5)
    for number in range(1, 6):
        write_frame(path, number, ring=RING)
        run.wait_for(number)

    kept, error, capture = run.finish()

    assert (kept, error) == (5, None)
    assert numbers_of(capture) == [1, 2, 3, 4, 5]
    assert [plane[0, 0] for plane in capture.cube] == [frame_value(n) for n in range(1, 6)]
    keywords = shm_capture.frame_keywords(capture)
    assert [frame["FRAMENO"] for frame in keywords] == [FRAMENO_BASE + n for n in range(1, 6)]


def test_the_worker_catches_up_from_the_ring(ring_segment):
    """
    Frames published while the worker was held up are still in the ring; only
    the newest of them can still have its keywords.
    """
    path, handle = ring_segment
    run = WorkerRun(handle, 5)
    write_frame(path, 1, ring=RING)
    run.wait_for(1)
    for number in range(2, 6):
        write_frame(path, number, ring=RING, publish=False)
    publish_frame(path, 5, RING)  # as if four landed while it looked away

    kept, error, capture = run.finish()

    assert (kept, error) == (5, None)
    assert numbers_of(capture) == [1, 2, 3, 4, 5]
    assert [plane[0, 0] for plane in capture.cube] == [frame_value(n) for n in range(1, 6)]
    keywords = shm_capture.frame_keywords(capture)
    assert [frame is not None for frame in keywords] == [True, False, False, False, True]
    assert keywords[4]["FRAMENO"] == FRAMENO_BASE + 5


def test_frames_the_ring_no_longer_holds_are_a_gap_not_a_guess(ring_segment):
    """Held up longer than the ring lasts, the worker loses frames, and cnt0 shows which."""
    path, handle = ring_segment
    run = WorkerRun(handle, 4)
    write_frame(path, 1, ring=RING)
    run.wait_for(1)
    newest = 1 + 2 * RING
    for number in range(2, newest + 1):
        write_frame(path, number, ring=RING, publish=False)
    publish_frame(path, newest, RING)

    kept, _, capture = run.finish()

    oldest = newest - RING + 2  # see test_an_overwritten_frame_is_refused_not_returned
    assert kept == 4
    assert numbers_of(capture) == [1, oldest, oldest + 1, oldest + 2]
    assert [plane[0, 0] for plane in capture.cube] == [frame_value(n) for n in numbers_of(capture)]


def test_the_worker_reads_a_segment_without_a_ring_too(tmp_path):
    """With no ring there is only the live frame, copied the moment it lands."""
    path = create_segment(str(tmp_path))
    handle = shm_reader.attach(SEGMENT, str(tmp_path))
    try:
        run = WorkerRun(handle, 3)
        for number in range(1, 4):
            write_frame(path, number)
            run.wait_for(number)
        kept, error, capture = run.finish()
    finally:
        shm_reader.close(handle)

    assert (kept, error) == (3, None)
    assert numbers_of(capture) == [1, 2, 3]
    assert [frame["FRAMENO"] for frame in shm_capture.frame_keywords(capture)] == \
        [FRAMENO_BASE + n for n in (1, 2, 3)]


def test_the_worker_stops_when_the_segment_is_recreated(ring_segment):
    """cnt0 going backwards means a new segment, whose frames are not these."""
    path, handle = ring_segment
    run = WorkerRun(handle, 5)
    write_frame(path, 1, ring=RING)
    run.wait_for(1)
    publish_frame(path, 0, RING)

    kept, error, _ = run.finish()

    assert kept == 1
    assert "recreated" in error


def test_the_worker_can_be_cancelled_while_waiting(ring_segment):
    """A stream gone quiet must not hold a disconnect up."""
    _, handle = ring_segment
    run = WorkerRun(handle, 5)
    run.cancel.set()

    kept, error, _ = run.finish()

    assert (kept, error) == (0, shm_capture.CANCELLED)


def keyword_copies(*frames):
    """
    A finished capture whose frames had their keywords copied as given: each
    (cnt0, FRAMENO, write counter), or a bare cnt0 for a frame copied without.
    """
    blocks, counters = [], []
    for frame in frames:
        block = bytearray(shm_reader.KEYWORD_SIZE)
        if isinstance(frame, int):
            counters.append((frame, 0))
        else:
            number, frameno, count = frame
            block[:7] = b"FRAMENO"
            block[shm_reader._KW_OFFSET_TYPE] = ord("L")
            struct.pack_into("<q", block, shm_reader._KW_OFFSET_VALUE, frameno)
            struct.pack_into("<Q", block, shm_reader._KW_OFFSET_CNT, count)
            counters.append((number, 1))
        blocks.append(bytes(block))
    return SimpleNamespace(kept=len(frames), nbkw=1, keyword_block=blocks.__getitem__,
                           counters=np.array(counters, np.uint64))


def test_keywords_copied_after_the_next_frames_went_in_are_refused():
    """
    The producer writes a frame's keywords before publishing it, so a copy
    taken late can hold the next frame's. Its write counter gives it away:
    one ahead of where every other frame's stands.
    """
    capture = keyword_copies((10, 110, 500), (11, 111, 501), (12, 113, 503), (13, 113, 503))

    keywords = shm_capture.frame_keywords(capture)

    assert [None if frame is None else frame["FRAMENO"] for frame in keywords] == \
        [110, 111, None, 113]


def test_frames_copied_without_keywords_have_none():
    """A frame caught up on from the ring had no keywords to copy."""
    capture = keyword_copies((10, 110, 500), 11, (12, 112, 502))
    assert shm_capture.frame_keywords(capture)[1] is None


def test_a_producer_that_never_bumps_the_counters_is_taken_at_its_word():
    """Counters that never move cannot tell copies apart, so none is refused."""
    capture = keyword_copies((10, 110, 0), (11, 111, 0), (12, 112, 0))
    assert [frame["FRAMENO"] for frame in shm_capture.frame_keywords(capture)] == [110, 111, 112]


# How many frames a capture may hold.

MB = 2 ** 20


@pytest.fixture
def no_shared_memory_filesystem(monkeypatch):
    """Takes /dev/shm out of the sums, so a test means the same on Linux and macOS."""
    monkeypatch.setattr(capture_budget, "shared_memory_free", lambda: None)


def test_the_limit_is_a_share_of_free_memory_over_the_frame_size(no_shared_memory_filesystem):
    """Writing the cube out needs a little on top, which comes off first."""
    available = 4096 * MB
    expected = (available // 2 - CUBE_WRITE_OVERHEAD_BYTES) // MB
    assert capture_budget.max_capture_frames(MB, 0.5, available=available) == expected


def test_the_limit_never_drops_below_one_frame(no_shared_memory_filesystem):
    """One frame is saved from the screen, so it is always allowed."""
    assert capture_budget.max_capture_frames(MB, 0.5, available=MB) == 1


def test_a_small_dev_shm_caps_the_limit_too(monkeypatch):
    """Overfilling /dev/shm is a SIGBUS, not an error, so plenty of memory is not enough."""
    monkeypatch.setattr(capture_budget, "shared_memory_free", lambda: 100 * MB)
    assert capture_budget.max_capture_frames(MB, 0.5, available=64_000 * MB) == 50


def test_each_frame_costs_its_keywords_and_counters_as_well():
    """The keyword copy and counters are held in memory beside the pixels."""
    assert capture_budget.capture_bytes_per_frame(1000, 3) == 1000 + 3 * 128 + 16


@pytest.mark.parametrize("fraction", [0, -0.5, 0.95, True, "half"])
def test_capture_memory_fraction_must_leave_some_memory(fraction):
    """All the memory free would leave nothing for the display or anything else."""
    with pytest.raises(ConfigError, match="capture_memory_fraction"):
        ShmConfig(capture_memory_fraction=fraction).validate("tools.shm")


# The whole feature, through the window, against a real segment: the capture
# worker is a process of its own, which no monkeypatching here can reach.

LIVE_RING = 8
# What one 8x8 uint16 frame of the test segment costs a capture
FRAME_COST = capture_budget.capture_bytes_per_frame(WIDTH * HEIGHT * 2, 1)


@pytest.fixture
def live_window(make_window, producer, tmp_path, no_shared_memory_filesystem):
    """
    A window with shared memory and the save button on, reading a segment a
    60 Hz producer is writing, and saving under tmp_path rather than /tmp/data.
    """
    shm_dir = tmp_path / "shm"
    shm_dir.mkdir()
    producer(create_segment(str(shm_dir), ring=LIVE_RING), ring=LIVE_RING)
    config = AtlasConfig(save=SaveConfig(directory=str(tmp_path / "data")), tools=ToolsConfig(
        save_button=True, shm=ShmConfig(enabled=True, segment_name=SEGMENT,
                                        shm_dir=str(shm_dir))))
    window, view_model = make_window(config)
    yield window, view_model, window.tools["shm"], window.tools["save_button"]
    window.tools["shm"].shutdown()


def saved_files(tmp_path):
    """Every FITS file a test has saved."""
    return sorted((tmp_path / "data").rglob("*.fits"))


def wait_for_save(window, shm, tmp_path):
    """The one file a save wrote, once it is completely written."""
    assert wait_until(lambda: saved_files(tmp_path) and shm.pending is None
                      and not shm.writer.busy
                      and window.statusBar().currentMessage().startswith("Saved"),
                      timeout=15.0), "the cube was never written"
    (saved,) = saved_files(tmp_path)
    return saved


def test_frames_box_only_with_shared_memory(make_window):
    """Without a stream there is nothing to take several frames from."""
    window, _ = make_window(AtlasConfig(tools=ToolsConfig(save_button=True)))
    assert window.tools["save_button"].count is None


def test_save_button_saves_a_cube_of_the_next_frames(live_window, tmp_path):
    """Frames 5, Save, and one file holds five frames, each with its own keywords."""
    window, _, shm, button = live_window
    shm.connect_to_shm()
    assert wait_until(window.save_action.isEnabled), "no frame arrived"

    button.count.setValue(5)
    window.save_action.trigger()

    saved = wait_for_save(window, shm, tmp_path)
    cube, header = fits.getdata(saved, "PRIMARY", header=True)
    frames = fits.getdata(saved, "FRAMES")
    assert cube.shape == (5, HEIGHT, WIDTH)
    numbers = list(frames["CNT0"])
    assert numbers == list(range(numbers[0], numbers[0] + 5)), \
        "a capture should be consecutive frames, not what the display let through"
    assert list(frames["FRAMENO"]) == [FRAMENO_BASE + n for n in numbers]
    assert header["NSKIPPED"] == 0 and "NKWMISS" not in header
    # Each plane is the frame its table row describes.
    assert [plane[0, 0] for plane in cube] == [frame_value(n) for n in numbers]
    assert window.statusBar().currentMessage() == f"Saved {saved}"


def test_a_capture_gives_its_shared_memory_back(live_window, tmp_path, monkeypatch):
    """Left behind, a capture's memory would stay taken until the next reboot."""
    window, _, shm, button = live_window
    made = []
    allocate = shm_capture.Capture.allocate

    def recording_allocate(*args):
        made.append(allocate(*args))
        return made[-1]

    monkeypatch.setattr(shm_capture.Capture, "allocate", recording_allocate)
    shm.connect_to_shm()
    assert wait_until(window.save_action.isEnabled)
    button.count.setValue(3)
    window.save_action.trigger()
    wait_for_save(window, shm, tmp_path)

    for block in (made[0].cube_memory, made[0].keyword_memory, made[0].counter_memory):
        with pytest.raises(FileNotFoundError):
            shared_memory.SharedMemory(block.name)


def test_one_frame_still_saves_the_frame_on_screen(live_window, tmp_path):
    """The Frames box at 1 leaves saving exactly as it was."""
    window, view_model, shm, _ = live_window
    shm.connect_to_shm()
    assert wait_until(window.save_action.isEnabled)
    shm.disconnect_from_shm()  # hold the frame still

    window.save_action.trigger()

    (saved,) = saved_files(tmp_path)
    assert np.array_equal(fits.getdata(saved), view_model.current_frame.data)


def test_several_frames_need_a_connection(live_window, tmp_path):
    """Asking before connecting is a message, not a capture that never ends."""
    window, view_model, _, button = live_window
    view_model.update_live_frame(np.zeros((4, 4), np.uint16), {})
    button.set_frame_limit(10, "as left by an earlier connection")
    button.count.setValue(5)

    window.save_action.trigger()

    assert window.statusBar().currentMessage().startswith("Connect to shared memory")
    assert not saved_files(tmp_path)


def test_disconnecting_cancels_a_capture(live_window, tmp_path):
    """Half a cube is not written, and the user is told it was dropped."""
    window, _, shm, button = live_window
    shm.connect_to_shm()
    assert wait_until(lambda: button.count.maximum() > 1000)
    button.count.setValue(1000)  # 17 s at 60 Hz
    window.save_action.trigger()
    capture = shm.pending
    assert wait_until(lambda: shm.capture_progress()[0] > 0, timeout=10.0)

    shm.disconnect_from_shm()

    assert "cancelled" in window.statusBar().currentMessage()
    assert shm.capture_progress() is None
    with pytest.raises(FileNotFoundError):
        shared_memory.SharedMemory(capture.cube_memory.name)
    assert not saved_files(tmp_path)


def test_frames_box_stops_at_what_fits_in_memory(live_window, monkeypatch):
    """The limit is unknown until a segment says how big its frames are."""
    _, _, shm, button = live_window
    # A share of 0.5 of this leaves room for 2000 frames once writing has
    # what it needs.
    monkeypatch.setattr(capture_budget, "available_bytes",
                        lambda: 2 * (CUBE_WRITE_OVERHEAD_BYTES + 2000 * FRAME_COST))
    assert button.count.maximum() == 1

    shm.connect_to_shm()
    assert wait_until(lambda: button.count.maximum() > 1), "the limit never followed the segment"

    assert button.count.maximum() == 2000
    assert "2,000 frames of 8×8 uint16" in button.count.toolTip()


def test_a_save_that_no_longer_fits_is_refused(live_window, tmp_path, monkeypatch):
    """Free memory is looked at again on Save, not trusted from when the segment was found."""
    window, _, shm, button = live_window
    shm.connect_to_shm()
    assert wait_until(lambda: button.count.maximum() > 100)
    button.count.setValue(100)

    monkeypatch.setattr(capture_budget, "available_bytes",
                        lambda: 2 * (CUBE_WRITE_OVERHEAD_BYTES + 50 * FRAME_COST))
    window.save_action.trigger()

    assert window.statusBar().currentMessage() == \
        "Only 50 frames fit in memory now; save 50 or fewer."
    assert shm.capture_progress() is None
    assert button.count.maximum() == 50


def test_a_capture_is_written_off_the_gui_thread(live_window, tmp_path, monkeypatch):
    """A cube of gigabytes going to disk must not freeze the window."""
    window, view_model, shm, button = live_window
    threads = []
    save_image = view_model.save_image

    def recording_save(*args):
        threads.append(threading.current_thread())
        return save_image(*args)

    monkeypatch.setattr(view_model, "save_image", recording_save)
    shm.connect_to_shm()
    assert wait_until(window.save_action.isEnabled)
    button.count.setValue(3)
    window.save_action.trigger()

    wait_for_save(window, shm, tmp_path)
    assert threads[0] is not threading.main_thread()


def test_a_new_save_waits_for_the_last_write(live_window, monkeypatch):
    """Two cubes in memory at once would be twice the budget."""
    window, _, shm, button = live_window
    shm.connect_to_shm()
    assert wait_until(lambda: button.count.maximum() > 1)
    monkeypatch.setattr(shm.writer, "file_name", "/somewhere/still_writing.fits")

    button.count.setValue(3)
    window.save_action.trigger()

    assert window.statusBar().currentMessage() == \
        "Already saving frames; wait for that to finish."
    assert shm.capture_progress() is None


def test_segment_directory_can_be_changed_from_the_menu(live_window, tmp_path, monkeypatch):
    """Tools → Shared Memory → Set Segment Directory… is where Connect looks next."""
    _, _, shm, _ = live_window
    empty = tmp_path / "empty"
    empty.mkdir()
    shm.settings.shm_dir = str(empty)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *_: str(tmp_path / "shm"))

    shm.directory_action.trigger()
    shm.connect_to_shm()

    assert wait_until(lambda: shm.receiver.info is not None)
    assert shm.receiver.path == str(tmp_path / "shm" / f"{SEGMENT}.im.shm")


def test_cancelling_the_segment_directory_picker_keeps_it(live_window, tmp_path, monkeypatch):
    """An empty answer from the picker means the user backed out."""
    _, _, shm, _ = live_window
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *_: "")

    shm.directory_action.trigger()

    assert shm.settings.shm_dir == str(tmp_path / "shm")


def test_segment_directory_is_fixed_while_connected(live_window):
    """The reader has already settled on a directory, so the menu says so."""
    _, _, shm, _ = live_window

    shm.connect_to_shm()
    assert not shm.directory_action.isEnabled()
    shm.disconnect_from_shm()
    assert shm.directory_action.isEnabled()
