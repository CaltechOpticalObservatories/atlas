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
import os
import struct
import threading
import time
from types import SimpleNamespace

# Third-Party Library Imports
import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication

from atlas.config.schema import AtlasConfig, ShmConfig
from atlas.features import shm_reader
from atlas.features.shm_source import ShmReceiver
from atlas.viewmodel.frame_viewmodel import FrameViewModel

DISPLAY_FPS_CAP = 15.0
RUN_SECONDS = 1.5
MAX_TRAILING_PULLS = 5

SEGMENT = "ci-synthetic"
WIDTH = HEIGHT = 8
PRODUCER_HZ = 60


def create_segment(directory, width=WIDTH, height=HEIGHT):
    """
    Writes an empty segment file, the way ImageStreamIO_createIm does.
    """
    path = os.path.join(directory, f"{SEGMENT}.im.shm")
    imdatamemsize = width * height * 2  # uint16

    buffer = bytearray(shm_reader._METADATA_SIZE + imdatamemsize + 8)
    struct.pack_into("<I", buffer, shm_reader._OFFSET_NAXIS, 2)
    struct.pack_into("<III", buffer, shm_reader._OFFSET_SIZE, width, height, 0)
    struct.pack_into("<B", buffer, shm_reader._OFFSET_DATATYPE, 3)  # uint16
    struct.pack_into("<Q", buffer, shm_reader._OFFSET_CNT0, 0)
    struct.pack_into("<H", buffer, shm_reader._OFFSET_NBKW, 0)
    struct.pack_into("<Q", buffer, shm_reader._OFFSET_IMDATAMEMSIZE, imdatamemsize)

    if os.path.exists(path):
        os.unlink(path)
    with open(path, "wb") as segment_file:
        segment_file.write(buffer)
    return path


def write_frame(path, number, width=WIDTH, height=HEIGHT):
    """Producer side: fill the data area, then bump cnt0, as camerad does."""
    with open(path, "r+b") as segment_file:
        segment_file.seek(shm_reader._METADATA_SIZE)
        segment_file.write(np.full((height, width), number % 256, np.uint16).tobytes())
        segment_file.seek(shm_reader._OFFSET_CNT0)
        segment_file.write(struct.pack("<Q", number))


@pytest.fixture
def producer():
    """Runs a 60 Hz writer against a segment path, and always stops it."""
    threads = []

    def start(path):
        stop = threading.Event()

        def run():
            number = 1
            while not stop.is_set():
                write_frame(path, number)
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

    def wait_for_frame(_image, timeout):  # pylint: disable=unused-argument
        counter["n"] += 1
        data = np.full((4, 4), counter["n"] % 256, dtype=np.uint16)
        return shm_reader.ShmFrame(data=data, keywords={"FRAMENO": counter["n"]})

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(shm_reader, "attach", lambda _name, _dir="": "fake-handle")
        patch.setattr(shm_reader, "segment_path", lambda _image: "fake-path")
        patch.setattr(shm_reader, "segment_replaced", lambda _image: False)
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
