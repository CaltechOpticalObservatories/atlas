"""
CI check for the shm_source live-view plumbing, without a real ImageStreamIO
segment: monkeypatches shm_reader's seam with a synthetic producer running
far past the expected 60 Hz, and asserts the throttle/display pipeline holds.

Not a pytest suite (atlas has none yet) -- a standalone script, run directly,
matching how camera-interface's own CI drives its integration checks.
"""

import sys
import time

from PyQt5.QtWidgets import QApplication

import numpy as np

from atlas.features import shm_reader
from atlas.features.shm_source import ShmReceiver
from atlas.config.schema import AtlasConfig, ShmConfig
from atlas.viewmodel.frame_viewmodel import FrameViewModel

DISPLAY_FPS_CAP = 15.0
RUN_SECONDS = 1.5


def install_fake_producer():
    """Replaces shm_reader's seam with a producer emitting as fast as possible."""
    counter = {"n": 0}

    def fake_attach(_segment_name, _shm_dir=""):
        return "fake-handle"

    def fake_wait_for_frame(_image, timeout):  # pylint: disable=unused-argument
        counter["n"] += 1
        data = np.full((4, 4), counter["n"] % 256, dtype=np.uint16)
        return shm_reader.ShmFrame(data=data, keywords={"FRAMENO": counter["n"]})

    def fake_close(_image):
        pass

    shm_reader.attach = fake_attach
    shm_reader.wait_for_frame = fake_wait_for_frame
    shm_reader.close = fake_close
    return counter


def main():
    """Runs the synthetic throttle check; raises AssertionError on failure."""
    app = QApplication(sys.argv)
    counter = install_fake_producer()

    settings = ShmConfig(enabled=True, segment_name="ci-synthetic",
                          display_fps_cap=DISPLAY_FPS_CAP)
    view_model = FrameViewModel(AtlasConfig())
    receiver = ShmReceiver(settings)
    receiver.frame_received.connect(lambda f: view_model.update_live_frame(f.data, f.keywords))

    failures = []
    receiver.failed.connect(failures.append)

    frames_changed_count = {"n": 0}
    view_model.frames_changed.connect(
        lambda: frames_changed_count.__setitem__("n", frames_changed_count["n"] + 1))

    emitted = {"n": 0}
    receiver.frame_received.connect(lambda _f: emitted.__setitem__("n", emitted["n"] + 1))

    assert receiver.start()

    deadline = time.monotonic() + RUN_SECONDS
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)

    receiver.stop()
    assert receiver.thread is None, "stop() should join and clear the thread"

    print(f"synthetic arrivals: {counter['n']}")
    print(f"frames emitted to GUI thread: {emitted['n']}")
    print(f"view_model.frames length: {len(view_model.frames)}")
    print(f"failures: {failures}")

    assert not failures, f"receiver reported failures: {failures}"
    assert counter["n"] > 1000, "producer should have run far faster than the display cap"
    assert len(view_model.frames) == 1, "live view must not grow the frame list"
    assert frames_changed_count["n"] == 1, "frames_changed should only fire once, on creation"

    # Allow generous slack (CI runners are noisy): expect roughly
    # RUN_SECONDS * DISPLAY_FPS_CAP emissions, not the raw arrival count.
    expected = RUN_SECONDS * DISPLAY_FPS_CAP
    assert 0.5 * expected <= emitted["n"] <= 2 * expected, (
        f"expected ~{expected:.0f} emissions at {DISPLAY_FPS_CAP} Hz over "
        f"{RUN_SECONDS}s, got {emitted['n']}")

    print("OK: shm_source throttles a fast synthetic producer without growing "
          "the frame list")


if __name__ == "__main__":
    main()
