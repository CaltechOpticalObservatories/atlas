"""
The shm_source live-view plumbing, without a real ImageStreamIO segment.

Monkeypatches shm_reader's seam with a synthetic producer running far past the
expected 60 Hz and asserts the throttle/display pipeline holds: a fast producer
must not queue a backlog, grow the frame list, or drive the GUI faster than the
configured display cap.
"""

# pytest injects fixtures as arguments of the same name.
# pylint: disable=redefined-outer-name

# Standard Library Imports
import time
from types import SimpleNamespace

# Third-Party Library Imports
import numpy as np
import pytest

from atlas.config.schema import AtlasConfig, ShmConfig
from atlas.features import shm_reader
from atlas.features.shm_source import ShmReceiver
from atlas.viewmodel.frame_viewmodel import FrameViewModel

DISPLAY_FPS_CAP = 15.0
RUN_SECONDS = 1.5


@pytest.fixture(scope="module")
def fake_producer():
    """
    Replaces shm_reader's seam with a producer emitting as fast as it can.

    Module scope, so the timed run below happens once for the whole module
    rather than per test; that rules out the function-scoped `monkeypatch`
    fixture, hence the explicit context.
    """
    counter = {"n": 0}

    def attach(_segment_name, _shm_dir=""):
        return "fake-handle"

    def wait_for_frame(_image, timeout):  # pylint: disable=unused-argument
        counter["n"] += 1
        data = np.full((4, 4), counter["n"] % 256, dtype=np.uint16)
        return shm_reader.ShmFrame(data=data, keywords={"FRAMENO": counter["n"]})

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(shm_reader, "attach", attach)
        patch.setattr(shm_reader, "wait_for_frame", wait_for_frame)
        patch.setattr(shm_reader, "close", lambda _image: None)
        yield counter


@pytest.fixture(scope="module")
def run(qapp, fake_producer):
    """
    Runs a started receiver for RUN_SECONDS and reports what happened.

    The reader thread is always stopped, so it cannot outlive the module.
    """
    settings = ShmConfig(enabled=True, segment_name="ci-synthetic",
                         display_fps_cap=DISPLAY_FPS_CAP)
    view_model = FrameViewModel(AtlasConfig())
    receiver = ShmReceiver(settings)

    emitted = {"n": 0}
    frames_changed = {"n": 0}
    failures = []

    receiver.frame_received.connect(
        lambda frame: view_model.update_live_frame(frame.data, frame.keywords))
    receiver.frame_received.connect(
        lambda _frame: emitted.__setitem__("n", emitted["n"] + 1))
    receiver.failed.connect(failures.append)
    view_model.frames_changed.connect(
        lambda: frames_changed.__setitem__("n", frames_changed["n"] + 1))

    assert receiver.start(), "the receiver should start"
    try:
        deadline = time.monotonic() + RUN_SECONDS
        while time.monotonic() < deadline:
            qapp.processEvents()
            time.sleep(0.005)
    finally:
        receiver.stop()

    return SimpleNamespace(receiver=receiver, view_model=view_model,
                           arrivals=fake_producer["n"], emitted=emitted["n"],
                           frames_changed=frames_changed["n"], failures=failures)


def test_stop_joins_the_reader_thread(run):
    """A left-running thread would keep the process alive after the window closes."""
    assert run.receiver.thread is None


def test_receiver_reports_no_failures(run):
    """The synthetic producer exercises the happy path end to end."""
    assert not run.failures


def test_producer_outruns_the_display_cap(run):
    """The premise of the test: arrivals far exceed what is displayed."""
    assert run.arrivals > 1000


def test_live_view_does_not_grow_the_frame_list(run):
    """Thousands of arrivals must still be one frame, updated in place."""
    assert len(run.view_model.frames) == 1
    assert run.frames_changed == 1, "frames_changed should only fire once, on creation"


def test_emission_rate_honours_the_display_cap(run):
    """
    Roughly RUN_SECONDS * DISPLAY_FPS_CAP emissions, not the arrival count.

    Generous slack: CI runners are noisy, and the point is the order of
    magnitude, not the exact count.
    """
    expected = RUN_SECONDS * DISPLAY_FPS_CAP
    assert 0.5 * expected <= run.emitted <= 2 * expected, (
        f"expected ~{expected:.0f} emissions at {DISPLAY_FPS_CAP} Hz over "
        f"{RUN_SECONDS}s, got {run.emitted}")
