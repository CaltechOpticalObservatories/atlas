"""
Shared fixtures for the atlas suite.

The Qt platform and the matplotlib backend are settled here, at import time:
both have to be chosen before anything constructs a QApplication or imports
pyplot, and the modules under test do both.
"""

# The platform and backend set below must be settled before anything imports
# pyplot or constructs a QApplication, so those imports cannot come first.
# pytest also injects fixtures as arguments of the same name.
# pylint: disable=wrong-import-position, redefined-outer-name

# Standard Library Imports
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Third-Party Library Imports
import matplotlib

matplotlib.use("Agg")

import numpy as np
import pytest
from PyQt5.QtWidgets import QApplication

from atlas.view.main_window import AtlasWindow
from atlas.viewmodel.frame_viewmodel import FrameViewModel


@pytest.fixture(scope="session")
def qapp():
    """
    The one QApplication for the whole session.

    Qt permits a single instance per process, so this cannot be per-test.
    """
    app = QApplication.instance() or QApplication([])
    yield app
    app.processEvents()


@pytest.fixture
def ramp():
    """
    A 16x16 ramp from 0 to 1000.

    A ramp covers the display range evenly, so what a scale does to it is
    arithmetic rather than a matter of taste. Built per test, so one test
    cannot leave a mutated array for the next.
    """
    return np.linspace(0, 1000, 256, dtype=np.float32).reshape(16, 16)


@pytest.fixture
def make_window(qapp):
    """
    Builds a window and view model for a config, and closes it afterwards.

    Pass ``show=True`` for anything that depends on widget visibility: a dock
    is not visible until its window is, and panels that skip work while hidden
    would otherwise never run at all.
    """
    created = []

    def build(config, show=False):
        view_model = FrameViewModel(config)
        window = AtlasWindow(view_model, config)
        if show:
            window.show()
            qapp.processEvents()
        created.append(window)
        return window, view_model

    yield build

    for window in created:
        window.close()
    qapp.processEvents()
