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
import os
import struct
import threading
import time
from types import SimpleNamespace

# Third-Party Library Imports
import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication

from astropy.io import fits

from atlas.config.schema import AtlasConfig, SaveConfig, ShmConfig, ToolsConfig
from atlas.features import shm_reader
from atlas.features.shm_source import ShmReceiver, stack_frames
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
        return shm_reader.ShmFrame(data=data, keywords={"FRAMENO": counter["n"]},
                                   cnt0=counter["n"])

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


# Saving several frames at once: kept on the reader thread, written as a cube.

NOW = datetime(2026, 10, 12, 19, 6, 37, tzinfo=timezone.utc)


def shm_frame(value, cnt0=None, shape=(4, 4), **keywords):
    """One ShmFrame filled with `value`."""
    return shm_reader.ShmFrame(data=np.full(shape, value, dtype=np.uint16),
                               keywords=keywords, cnt0=cnt0)


def test_stack_keeps_every_frame_and_its_own_keywords():
    """One header for the cube, but each frame's keywords survive in the table."""
    frames = [shm_frame(n, cnt0=n, FRAMENO=n, MODE="CDS") for n in (5, 6, 7)]

    cube, header, table, skipped = stack_frames(frames)

    assert cube.shape == (3, 4, 4)
    assert [plane[0, 0] for plane in cube] == [5, 6, 7]
    assert header["FRAMENO"] == 5 and header["NSKIPPED"] == 0
    assert table is not None
    assert list(table.columns["CNT0"]) == [5, 6, 7]
    assert list(table.columns["FRAMENO"]) == [5, 6, 7]
    assert skipped == 0


def test_stack_counts_frames_the_reader_missed():
    """A jump in cnt0 means frames went by unread; the file has to say so."""
    _, header, _, skipped = stack_frames([shm_frame(0, cnt0=n) for n in (10, 11, 14, 15)])
    assert skipped == 2
    assert header["NSKIPPED"] == 2


def test_stack_without_cnt0_does_not_guess():
    """Frames that carry no counter cannot say whether any were missed."""
    _, header, table, skipped = stack_frames([shm_frame(n, FRAMENO=n) for n in (1, 2)])
    assert skipped is None
    assert "NSKIPPED" not in header
    assert table.colnames == ["FRAMENO"]


def test_stack_refuses_frames_of_different_sizes():
    """A segment recreated at another size cannot be stacked into one cube."""
    with pytest.raises(ValueError, match="size changed"):
        stack_frames([shm_frame(0), shm_frame(0, shape=(8, 8))])


def test_receiver_captures_the_frames_it_reads(qapp, tmp_path, producer, receiver_for):
    """Against a real segment, the capture is every frame read, in order."""
    path = create_segment(str(tmp_path))
    producer(path)
    receiver = receiver_for()
    captured = []
    receiver.captured.connect(captured.append)

    receiver.start()
    assert wait_until(lambda: receiver.slot.take() is not None)
    assert receiver.capture(10, NOW)
    assert not receiver.capture(10, NOW), "a second capture must wait for the first"

    assert wait_until(lambda: captured), "the capture never filled"
    assert len(captured) == 1
    counters = [frame.cnt0 for frame in captured[0].frames]
    assert len(counters) == 10
    assert counters == sorted(set(counters)), "frames repeated or out of order"
    assert receiver.capture_progress() is None


@pytest.fixture
def live_window(make_window, fake_producer, tmp_path):
    """
    A window with shared memory and the save button on, reading the fake
    producer, and saving under tmp_path rather than /tmp/data.
    """
    # pylint: disable=unused-argument  # fake_producer is needed for its patching
    config = AtlasConfig(save=SaveConfig(directory=str(tmp_path)), tools=ToolsConfig(
        save_button=True, shm=ShmConfig(enabled=True, segment_name=SEGMENT)))
    window, view_model = make_window(config)
    yield window, view_model, window.tools["shm"], window.tools["save_button"]
    window.tools["shm"].shutdown()


def saved_files(tmp_path):
    """Every FITS file a test has saved."""
    return sorted(tmp_path.rglob("*.fits"))


def test_frames_box_only_with_shared_memory(make_window):
    """Without a stream there is nothing to take several frames from."""
    window, _ = make_window(AtlasConfig(tools=ToolsConfig(save_button=True)))
    assert window.tools["save_button"].count is None


def test_save_button_saves_a_cube_of_the_next_frames(live_window, tmp_path):
    """The whole feature: Frames 5, Save, and one file holds five frames."""
    window, _, shm, button = live_window
    shm.connect_to_shm()
    assert wait_until(window.save_action.isEnabled), "no frame arrived"

    button.count.setValue(5)
    window.save_action.trigger()

    assert wait_until(lambda: saved_files(tmp_path)), "the cube was never written"
    (saved,) = saved_files(tmp_path)
    cube, frames = fits.getdata(saved, "PRIMARY"), fits.getdata(saved, "FRAMES")
    assert cube.shape == (5, 4, 4)
    numbers = list(frames["FRAMENO"])
    assert numbers == list(range(numbers[0], numbers[0] + 5)), \
        "a capture should be consecutive frames, not what the display let through"
    # Each plane is the frame its table row describes.
    assert [plane[0, 0] for plane in cube] == [n % 256 for n in numbers]
    assert window.statusBar().currentMessage() == f"Saved {saved}"


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
    button.count.setValue(5)

    window.save_action.trigger()

    assert window.statusBar().currentMessage().startswith("Connect to shared memory")
    assert not saved_files(tmp_path)


def test_disconnecting_cancels_a_capture(live_window, tmp_path):
    """Half a cube is not written, and the user is told it was dropped."""
    window, _, shm, _ = live_window
    shm.connect_to_shm()
    assert shm.receiver.capture(10 ** 9, NOW)

    shm.disconnect_from_shm()

    assert "cancelled" in window.statusBar().currentMessage()
    assert shm.receiver.capture_progress() is None
    assert not saved_files(tmp_path)
