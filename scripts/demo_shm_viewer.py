"""
Manual demo: launches the real atlas UI with a live view fed by a synthetic
ImageStreamIO producer (an orbiting bright spot), since a real segment needs
a Linux environment ImageStreamIOWrap can build on (see
plans/ATLAS-SHM-VIEWER-PLAN.md). Run directly, not via pytest.

Usage:
    python scripts/demo_shm_viewer.py [fits_file]

Optionally pass a FITS file to load alongside the live view (tile mode),
e.g. one written by a real camerad + emulator run.
"""

import math
import sys
import time

from PyQt5.QtWidgets import QApplication
import numpy as np

from atlas.features import shm_reader
from atlas.config.schema import AtlasConfig
from atlas.viewmodel.frame_viewmodel import FrameViewModel
from atlas.view.main_window import AtlasWindow

SIZE = 256


def install_synthetic_producer():
    """Replaces shm_reader's seam with an orbiting-spot frame generator."""
    counter = {"n": 0}
    yy, xx = np.mgrid[0:SIZE, 0:SIZE]
    gradient = ((xx + yy) / (2 * SIZE) * 120).astype(np.uint16)

    def fake_attach(_segment_name, _shm_dir=""):
        return "fake-handle"

    def fake_wait_for_frame(_image, _timeout):
        counter["n"] += 1
        time.sleep(1 / 60)  # simulate a 60 Hz producer
        t = counter["n"] * 0.05
        cx = SIZE / 2 + (SIZE / 3) * math.cos(t)
        cy = SIZE / 2 + (SIZE / 3) * math.sin(t)
        spot = np.exp(-(((xx - cx) ** 2 + (yy - cy) ** 2)) / (2 * 15 ** 2)) * 4000
        data = (gradient + spot).astype(np.uint16)
        return shm_reader.ShmFrame(data=data, keywords={"FRAMENO": counter["n"]})

    def fake_close(_image):
        pass

    shm_reader.attach = fake_attach
    shm_reader.wait_for_frame = fake_wait_for_frame
    shm_reader.close = fake_close


def main():
    """Launches atlas with the synthetic SHM feed connected."""
    install_synthetic_producer()

    config = AtlasConfig()
    config.tools.shm.enabled = True
    config.tools.shm.segment_name = "synthetic-demo"
    config.tools.header = True
    config.display.mode = "tile"

    app = QApplication(sys.argv[:1])
    view_model = FrameViewModel(config)
    window = AtlasWindow(view_model, config)
    window.resize(900, 550)
    window.show()

    if len(sys.argv) > 1:
        view_model.load_file(sys.argv[1])

    window.tools["shm"].connect_to_shm()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
