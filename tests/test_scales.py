"""
Per-frame log/linear intensity scales.

Covers the three seams the feature spans: the scaling maths in fits_model, the
per-frame state and re-render in the view model (including the Scale menu that
tracks it), and the histogram's own count-axis toggle.
"""

# pytest injects fixtures as arguments of the same name.
# pylint: disable=redefined-outer-name

# Third-Party Library Imports
import numpy as np
import pytest
from astropy.io import fits

from atlas.config.schema import AtlasConfig, ShmConfig, ToolsConfig
from atlas.features import shm_reader
from atlas.model.fits_model import FITSModel, LOG_SOFTENING, SCALES
from atlas.view.histogram import LOG_COUNT_FLOOR, Histogram

DEGENERATE = {
    "constant": np.full((4, 4), 7.0, dtype=np.float32),
    "all blank": np.full((4, 4), np.nan, dtype=np.float32),
    "mixed blank": np.array([[np.nan, 1.0], [np.inf, 5.0]], dtype=np.float32),
    "zeros": np.zeros((4, 4), dtype=np.uint16),
}


@pytest.fixture
def model():
    """The FITS model, whose normalize_image applies the scales."""
    return FITSModel()


@pytest.fixture
def viewer(make_window):
    """A window with the histogram available and no header panel."""
    return make_window(AtlasConfig(tools=ToolsConfig(header=False, histogram=True)))


@pytest.fixture
def two_frames(viewer, ramp, tmp_path):
    """A viewer with two ramp frames loaded, at different brightnesses."""
    window, view_model = viewer
    paths = []
    for name, multiplier in (("a.fits", 1), ("b.fits", 3)):
        path = tmp_path / name
        fits.PrimaryHDU((ramp * multiplier).astype(np.int32)).writeto(path)
        paths.append(str(path))

    assert view_model.load_files(paths) == 2, "both ramp files should load"
    return window, view_model


@pytest.mark.parametrize("scale", SCALES)
def test_every_scale_spans_the_display_range(model, ramp, scale):
    """Each scale anchors the frame's min and max to the full 0-255 range."""
    panel = model.normalize_image(ramp, scale)
    assert panel.dtype == np.uint8
    # Neither scale may clip a pixel the other one shows.
    assert (panel.min(), panel.max()) == (0, 255)


def test_log_brightens_without_ever_darkening(model, ramp):
    """Log lifts the faint end, and never renders a pixel darker than linear."""
    linear = model.normalize_image(ramp, "linear")
    log = model.normalize_image(ramp, "log")

    assert (log >= linear).all()
    midpoint = ramp.size // 2
    assert log.ravel()[midpoint] > linear.ravel()[midpoint]


def test_log_matches_the_ds9_formula(model):
    """Log is DS9's log(a*x + 1) / log(a + 1) over values mapped to [0, 1]."""
    thirds = model.normalize_image(np.array([[0.0, 0.5, 1.0]], dtype=np.float32), "log")
    expected = 255.0 * np.log1p(LOG_SOFTENING * 0.5) / np.log1p(LOG_SOFTENING)
    assert abs(int(thirds[0, 1]) - round(expected)) <= 1


def test_default_scale_is_linear(model, ramp):
    """Callers predating the argument must keep getting a linear render."""
    assert (model.normalize_image(ramp) == model.normalize_image(ramp, "linear")).all()


def test_unknown_scale_is_rejected(model, ramp):
    """An unrecognised scale raises rather than silently rendering linear."""
    with pytest.raises(ValueError, match="sqrt"):
        model.normalize_image(ramp, "sqrt")


@pytest.mark.parametrize("scale", SCALES)
@pytest.mark.parametrize("name", sorted(DEGENERATE))
def test_degenerate_data_still_renders(model, scale, name):
    """Constant and all-blank frames survive every scale rather than raising."""
    data = DEGENERATE[name]
    panel = model.normalize_image(data, scale)
    assert panel.dtype == np.uint8
    assert panel.shape == data.shape


def test_scale_menu_is_disabled_without_a_frame(viewer):
    """With nothing loaded there is nothing to scale, and nothing to claim."""
    window, _ = viewer
    assert not window.scale_menu.isEnabled()
    assert not any(action.isChecked() for action in window.scale_actions.values())


def test_frames_start_linear(two_frames):
    """A newly loaded frame renders linear, and the menu says so."""
    window, view_model = two_frames
    assert window.scale_menu.isEnabled()
    assert window.scale_actions["linear"].isChecked()
    assert all(frame.scale == "linear" for frame in view_model.frames)


def test_scale_is_per_frame(two_frames):
    """Changing one frame's scale leaves every other frame alone."""
    window, view_model = two_frames
    first, second = view_model.frames
    linear_render = second.pixmap.toImage()

    window.scale_actions["log"].trigger()

    assert second.scale == "log"
    assert second.pixmap.toImage() != linear_render, "the pixmap was not re-rendered"
    # This is what lets a log and a linear view sit side by side when tiling.
    assert first.scale == "linear"


def test_menu_follows_the_current_frame(two_frames):
    """Moving between frames re-ticks the menu to match."""
    window, view_model = two_frames
    window.scale_actions["log"].trigger()

    view_model.previous_frame()
    assert window.scale_actions["linear"].isChecked()
    view_model.next_frame()
    assert window.scale_actions["log"].isChecked()


def test_round_trip_is_lossless(two_frames):
    """Log and back leaves both the pixmap and the raw counts unchanged."""
    window, view_model = two_frames
    frame = view_model.frames[1]
    linear_render = frame.pixmap.toImage()
    raw = frame.data.copy()

    window.scale_actions["log"].trigger()
    window.scale_actions["linear"].trigger()

    assert (frame.data == raw).all(), "re-scaling must not touch the raw data"
    assert frame.pixmap.toImage() == linear_render


def test_rejected_scale_reaches_the_status_bar(two_frames):
    """An unknown scale is reported rather than raising out of the view model."""
    _, view_model = two_frames
    messages = []
    view_model.message.connect(messages.append)

    view_model.set_current_scale("bogus")

    assert messages and "bogus" in messages[0]
    assert view_model.current_frame.scale == "linear", \
        "a rejected scale must not be recorded"


def test_live_frame_keeps_its_scale(viewer, ramp):
    """A live frame's chosen scale survives the next arriving image."""
    _, view_model = viewer
    view_model.update_live_frame(ramp.astype(np.int32), {})
    live = view_model.current_frame
    view_model.set_current_scale("log")

    arriving = (ramp * 2).astype(np.int32)
    view_model.update_live_frame(arriving, {})

    assert view_model.current_frame is live, "the live frame should update in place"
    assert len(view_model.frames) == 1, "the live view must not grow the list"
    # The recorded scale is not proof of what was drawn, so compare the pixmap
    # against an independent render: a frame rendered linear but still labelled
    # log would otherwise pass.
    assert live.pixmap.toImage() == view_model.render(arriving, "log").toImage()
    assert live.pixmap.toImage() != view_model.render(arriving, "linear").toImage()


def test_live_stream_keeps_its_scale(make_window, ramp):
    """
    The scale survives the real SHM handoff, frame after frame.

    Drives ShmTool.on_frame through the receiver's own signal, so a live view
    re-rendered on the wrong scale somewhere in the feature layer is caught
    too. No segment is attached: emitting frame_received is exactly what the
    reader thread does once it has a frame.
    """
    window, view_model = make_window(AtlasConfig(tools=ToolsConfig(
        header=False, histogram=False,
        shm=ShmConfig(enabled=True, segment_name="ci-synthetic"))))
    tool = window.tools["shm"]

    def arrive(multiplier):
        data = (ramp * multiplier).astype(np.uint16)
        tool.receiver.slot.put(
            shm_reader.ShmFrame(data=data, keywords={"FRAMENO": multiplier}))
        tool.show_latest_frame()
        return data

    arrive(1)
    live = view_model.current_frame
    assert live is not None and live.scale == "linear"

    view_model.set_current_scale("log")
    assert window.scale_actions["log"].isChecked(), \
        "set_current_scale should re-sync the menu even when not driven from it"

    for multiplier in range(2, 8):
        data = arrive(multiplier)
        assert len(view_model.frames) == 1
        assert view_model.current_frame is live
        assert live.scale == "log", f"frame {multiplier} reset the chosen scale"
        assert live.pixmap.toImage() == view_model.render(data, "log").toImage(), \
            f"frame {multiplier} was not rendered on the live frame's scale"
        assert live.pixmap.toImage() != view_model.render(data, "linear").toImage()

    # Switching back mid-stream must take effect on the next arrival.
    view_model.set_current_scale("linear")
    data = arrive(8)
    assert live.pixmap.toImage() == view_model.render(data, "linear").toImage()


@pytest.fixture
def histogram(viewer, ramp):
    """A histogram dialog over a ramp and an all-blank frame."""
    window, _ = viewer
    blank = np.full((4, 4), np.nan, dtype=np.float32)
    dialog = Histogram([("ramp", ramp), ("blank", blank)], window)
    yield dialog
    dialog.close()


def test_count_axis_toggles(histogram):
    """The count axis goes log and, crucially, comes back."""
    assert histogram.axis.get_yscale() == "linear"

    histogram.log_counts.setChecked(True)
    assert histogram.axis.get_yscale() == "log"

    histogram.log_counts.setChecked(False)
    assert histogram.axis.get_yscale() == "linear", \
        "a cleared axis kept its log scale after the box was unticked"


def test_log_axis_survives_a_redraw(histogram):
    """Changing frame or bin count must not disturb the axis."""
    histogram.log_counts.setChecked(True)

    # The blank frame takes the no-finite-pixels path, and the slider extremes
    # are the narrowest and widest binning the dialog allows.
    histogram.show_next()
    histogram.slider.setValue(histogram.slider.maximum())
    histogram.show_previous()
    histogram.slider.setValue(histogram.slider.minimum())

    assert histogram.axis.get_yscale() == "log"


def test_log_bars_reach_their_own_count(histogram, ramp):
    """
    On a log axis the bars still reach exactly their own count.

    A log axis has no zero baseline, so bars are drawn from a floor just below
    a count of 1; their heights must be measured from that floor rather than
    from zero, or every bar overshoots by the floor.
    """
    histogram.log_counts.setChecked(True)
    histogram.slider.setValue(16)

    patches = list(histogram.axis.patches)
    assert patches, "no bars were drawn"
    assert all(patch.get_y() == LOG_COUNT_FLOOR for patch in patches), \
        "log bars must start at the floor, not at zero, which a log axis cannot show"

    values = ramp.ravel()
    counts, _ = np.histogram(values, bins=histogram.slider.value(),
                             range=(float(values.min()), float(values.max())))
    tops = sorted(patch.get_y() + patch.get_height() for patch in patches)
    expected = sorted(float(max(count, LOG_COUNT_FLOOR)) for count in counts)
    assert np.allclose(tops, expected)
