"""
Test to check for per-frame log/linear intensity scales.

Covers the three seams the feature spans: the scaling maths in fits_model, the
per-frame state and re-render in the view model (including the Scale menu that
tracks it), and the histogram's own count-axis toggle.
"""

import os
import sys
import tempfile

import matplotlib
matplotlib.use("Agg")  # CI has no display, and importing Histogram imports pyplot

# The backend has to be chosen before anything pulls in pyplot, which the atlas
# imports below do, so those imports cannot come first.
# pylint: disable=wrong-import-position
import numpy as np
from astropy.io import fits
from PyQt5.QtWidgets import QApplication

from atlas.config.schema import AtlasConfig, ShmConfig, ToolsConfig
from atlas.features import shm_reader
from atlas.model.fits_model import FITSModel, SCALES, LOG_SOFTENING
from atlas.view.histogram import Histogram, LOG_COUNT_FLOOR
from atlas.view.main_window import AtlasWindow
from atlas.viewmodel.frame_viewmodel import FrameViewModel

# A ramp spans the whole display range evenly, so the effect of a scale on it
# is arithmetic rather than a matter of taste.
RAMP = np.linspace(0, 1000, 256, dtype=np.float32).reshape(16, 16)


def check_scale_maths():
    """The scales map a ramp as documented, and log lifts the faint end."""
    model = FITSModel()
    linear = model.normalize_image(RAMP, "linear")
    log = model.normalize_image(RAMP, "log")

    for name, panel in (("linear", linear), ("log", log)):
        assert panel.dtype == np.uint8, f"{name} must render 8-bit, got {panel.dtype}"
        # Both scales anchor the frame's own min and max to the display range,
        # so neither one clips a pixel the other shows.
        assert (panel.min(), panel.max()) == (0, 255), \
            f"{name} should span 0-255, got {panel.min()}-{panel.max()}"

    assert (log >= linear).all(), "log must never render a pixel darker than linear"
    midpoint = RAMP.size // 2
    assert log.ravel()[midpoint] > linear.ravel()[midpoint], \
        "log must brighten mid-range pixels"

    # DS9's log is log(a*x + 1) / log(a + 1) over values already in [0, 1].
    thirds = model.normalize_image(np.array([[0.0, 0.5, 1.0]], dtype=np.float32), "log")
    expected = 255.0 * np.log1p(LOG_SOFTENING * 0.5) / np.log1p(LOG_SOFTENING)
    assert abs(int(thirds[0, 1]) - round(expected)) <= 1, \
        f"log at the half-way point should be ~{expected:.0f}, got {thirds[0, 1]}"

    # Callers that predate the argument must keep getting a linear render.
    assert (model.normalize_image(RAMP) == linear).all(), "default scale must be linear"

    try:
        model.normalize_image(RAMP, "sqrt")
    except ValueError:
        pass
    else:
        raise AssertionError("an unknown scale must be rejected, not rendered linear")

    print(f"OK: ramp midpoint renders {linear.ravel()[midpoint]} linear, "
          f"{log.ravel()[midpoint]} log")


def check_degenerate_data():
    """Blank and constant frames survive every scale rather than raising."""
    model = FITSModel()
    cases = {
        "constant": np.full((4, 4), 7.0, dtype=np.float32),
        "all blank": np.full((4, 4), np.nan, dtype=np.float32),
        "mixed blank": np.array([[np.nan, 1.0], [np.inf, 5.0]], dtype=np.float32),
        "zeros": np.zeros((4, 4), dtype=np.uint16),
    }
    for scale in SCALES:
        for name, data in cases.items():
            panel = model.normalize_image(data, scale)
            assert panel.dtype == np.uint8, f"{name} on {scale}: got {panel.dtype}"
            assert panel.shape == data.shape, f"{name} on {scale}: shape changed"

    print(f"OK: constant and blank frames render on all of {', '.join(SCALES)}")


def write_ramp(directory, name, multiplier):
    """Writes a ramp to a FITS file and returns its path."""
    path = os.path.join(directory, name)
    fits.PrimaryHDU((RAMP * multiplier).astype(np.int32)).writeto(path, overwrite=True)
    return path


def check_per_frame_scale(window, view_model, directory):
    """The scale belongs to the frame, and the menu follows the current one."""
    assert not window.scale_menu.isEnabled(), \
        "with no frame loaded there is nothing to scale"
    assert not any(action.isChecked() for action in window.scale_actions.values()), \
        "the menu must not claim a scale when no frame is loaded"

    loaded = view_model.load_files([write_ramp(directory, "a.fits", 1),
                                   write_ramp(directory, "b.fits", 3)])
    assert loaded == 2, f"expected 2 frames, loaded {loaded}"
    assert window.scale_menu.isEnabled()
    assert window.scale_actions["linear"].isChecked(), "frames must start linear"

    first, second = view_model.frames
    linear_render = second.pixmap.toImage()
    raw = second.data.copy()

    window.scale_actions["log"].trigger()
    assert second.scale == "log"
    assert second.pixmap.toImage() != linear_render, "the pixmap was not re-rendered"
    assert window.scale_actions["log"].isChecked()
    assert not window.scale_actions["linear"].isChecked()

    # Per-frame, not per-window: the other frame is untouched, which is what
    # lets a log and a linear view sit side by side in tile mode.
    assert first.scale == "linear", "changing one frame's scale changed another's"

    view_model.previous_frame()
    assert window.scale_actions["linear"].isChecked(), \
        "the menu must follow the current frame's scale"
    view_model.next_frame()
    assert window.scale_actions["log"].isChecked()

    # Only the pixmap is derived; the detector counts must come back unchanged.
    window.scale_actions["linear"].trigger()
    assert (second.data == raw).all(), "re-scaling must not touch the raw data"
    assert second.pixmap.toImage() == linear_render, \
        "a log/linear round trip must be lossless"

    messages = []
    view_model.message.connect(messages.append)
    view_model.set_current_scale("bogus")
    assert messages and "bogus" in messages[0], \
        f"an unknown scale should reach the status bar, got {messages}"
    assert second.scale == "linear", "a rejected scale must not be recorded"

    print("OK: scales are per-frame, lossless, and tracked by the View menu")


def check_live_frame_keeps_scale(view_model):
    """A live frame's chosen scale survives the next arriving image."""
    view_model.update_live_frame(RAMP.astype(np.int32), {})
    live = view_model.current_frame
    frame_count = len(view_model.frames)

    view_model.set_current_scale("log")
    assert live.scale == "log"

    arriving = (RAMP * 2).astype(np.int32)
    view_model.update_live_frame(arriving, {})
    assert view_model.current_frame is live, "the live frame should update in place"
    assert len(view_model.frames) == frame_count, "the live view must not grow the list"
    assert live.scale == "log", \
        "an arriving frame reset the scale the user chose for the live view"

    # The recorded scale is not proof of what was drawn: check the new pixmap
    # against an independent render, or a frame rendered linear while still
    # labelled log would pass.
    assert live.pixmap.toImage() == view_model.render(arriving, "log").toImage(), \
        "the arriving frame was not rendered on the live frame's own scale"
    assert live.pixmap.toImage() != view_model.render(arriving, "linear").toImage(), \
        "the arriving frame was rendered linear despite a log live frame"

    print("OK: the live view keeps its scale across incoming frames")


def check_live_stream_keeps_scale():
    """
    The scale survives the real SHM handoff, frame after frame.

    check_live_frame_keeps_scale covers the view model's own seam; this drives
    ShmTool.on_frame through the receiver's actual signal, so a live view that
    re-rendered on the wrong scale somewhere in the feature layer is caught
    too. No segment is attached: emitting frame_received is exactly what the
    reader thread does once it has one.
    """
    config = AtlasConfig(tools=ToolsConfig(
        header=False, histogram=False,
        shm=ShmConfig(enabled=True, segment_name="ci-synthetic")))
    view_model = FrameViewModel(config)
    window = AtlasWindow(view_model, config)
    tool = window.tools["shm"]

    def arrive(multiplier):
        """Emits one synthetic frame the way the reader thread would."""
        data = (RAMP * multiplier).astype(np.uint16)
        tool.receiver.frame_received.emit(
            shm_reader.ShmFrame(data=data, keywords={"FRAMENO": multiplier}))
        return data

    arrive(1)
    live = view_model.current_frame
    assert live is not None, "the first arriving frame should create the live view"
    assert len(view_model.frames) == 1
    assert live.scale == "linear"

    view_model.set_current_scale("log")
    assert window.scale_actions["log"].isChecked(), \
        "set_current_scale should re-sync the menu even when not driven from it"

    # A stream, not a single update: the scale has to hold for every arrival.
    for multiplier in range(2, 8):
        data = arrive(multiplier)
        assert len(view_model.frames) == 1, "the live view must not grow the frame list"
        assert view_model.current_frame is live, "the live frame should update in place"
        assert live.scale == "log", f"frame {multiplier} reset the chosen scale"
        assert live.pixmap.toImage() == view_model.render(data, "log").toImage(), \
            f"frame {multiplier} was not rendered on the live frame's scale"
        assert live.pixmap.toImage() != view_model.render(data, "linear").toImage(), \
            f"frame {multiplier} was rendered linear despite a log live view"

    # And switching back mid-stream must take effect on the next arrival.
    view_model.set_current_scale("linear")
    data = arrive(8)
    assert live.pixmap.toImage() == view_model.render(data, "linear").toImage(), \
        "switching back to linear did not take effect on the next frame"

    window.close()
    print("OK: a live SHM stream keeps the scale across arriving frames")


def check_histogram_axis(window):
    """The histogram's count axis toggles, and resets when switched off."""
    blank = np.full((4, 4), np.nan, dtype=np.float32)
    dialog = Histogram([("ramp", RAMP), ("blank", blank)], window)

    assert dialog.axis.get_yscale() == "linear", "the count axis starts linear"
    dialog.log_counts.setChecked(True)
    assert dialog.axis.get_yscale() == "log"
    dialog.log_counts.setChecked(False)
    assert dialog.axis.get_yscale() == "linear", \
        "a cleared axis kept its log scale after the box was unticked"

    # Redrawing for a different frame or bin count must not disturb the axis.
    # The blank frame takes the no-finite-pixels path, and the slider extremes
    # are the narrowest and widest binning the dialog allows.
    dialog.log_counts.setChecked(True)
    dialog.show_next()
    dialog.slider.setValue(dialog.slider.maximum())
    dialog.show_previous()
    dialog.slider.setValue(dialog.slider.minimum())
    assert dialog.axis.get_yscale() == "log", "the log axis did not survive a redraw"

    check_log_bar_geometry(dialog)
    dialog.close()
    print("OK: the histogram count axis toggles between log and linear")


def check_log_bar_geometry(dialog):
    """
    On a log axis the bars still reach exactly their own count.

    A log axis has no zero baseline, so the bars are drawn from a floor just
    below a count of 1; their heights have to be measured from that floor
    rather than from zero, or every bar overshoots by the floor.
    """
    dialog.log_counts.setChecked(True)
    dialog.slider.setValue(16)

    patches = list(dialog.axis.patches)
    assert patches, "no bars were drawn"
    assert all(patch.get_y() == LOG_COUNT_FLOOR for patch in patches), \
        "log bars must start at the floor, not at zero, which a log axis cannot show"

    values = RAMP.ravel()
    counts, _ = np.histogram(values, bins=dialog.slider.value(),
                             range=(float(values.min()), float(values.max())))
    tops = sorted(patch.get_y() + patch.get_height() for patch in patches)
    expected = sorted(float(max(count, LOG_COUNT_FLOOR)) for count in counts)
    assert np.allclose(tops, expected), \
        f"bar tops {tops[:4]}... should match the bin counts {expected[:4]}..."


def main():
    """Runs every scale check; raises AssertionError on failure."""
    check_scale_maths()
    check_degenerate_data()

    app = QApplication(sys.argv)
    config = AtlasConfig(tools=ToolsConfig(header=False, histogram=True))
    view_model = FrameViewModel(config)
    window = AtlasWindow(view_model, config)

    with tempfile.TemporaryDirectory() as directory:
        check_per_frame_scale(window, view_model, directory)

    check_live_frame_keeps_scale(view_model)
    check_live_stream_keeps_scale()
    check_histogram_axis(window)

    window.close()
    app.processEvents()
    print("\nOK: log/linear scales hold across the model, view model and histogram")


if __name__ == "__main__":
    main()
