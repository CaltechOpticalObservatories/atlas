"""
The frame statistics panel.

Covers the arithmetic against numpy's own nan-aware functions, the formatting,
the config bounds, and the panel's throttle. The throttle is the part with real
behaviour: a live stream must not recompute on every frame, but must still end
up showing the newest frame's numbers.
"""

# pytest injects fixtures as arguments of the same name.
# pylint: disable=redefined-outer-name

# Standard Library Imports
import math
import time

# Third-Party Library Imports
import numpy as np
import pytest

from atlas.config.schema import (AtlasConfig, ConfigError, StatisticsConfig,
                                 ToolsConfig, from_dict)
from atlas.features import statistics as statistics_tool
from atlas.features.statistics import format_count
from atlas.model.frame import Frame
from atlas.model.statistics import compute_statistics

# Fast enough to keep the suite short, slow enough that a burst is throttled.
UPDATE_HZ = 10.0


@pytest.fixture
def noisy():
    """A normal field with one NaN and one inf blank pixel."""
    data = np.random.default_rng(1).normal(500, 50, (128, 128)).astype(np.float32)
    data[0, 0] = np.nan
    data[1, 1] = np.inf
    return data


@pytest.fixture
def panel(make_window):
    """A shown window with the statistics panel enabled."""
    config = AtlasConfig(tools=ToolsConfig(
        header=False,
        statistics=StatisticsConfig(enabled=True, update_hz=UPDATE_HZ)))
    # Shown, because the panel skips work while hidden and a dock is not
    # visible until its window is.
    window, view_model = make_window(config, show=True)
    return window.tools["statistics"], view_model


@pytest.fixture
def count_computations(monkeypatch):
    """
    Counts real statistics computations, however they were triggered.

    Patching the module-level name catches work started by the throttle timer,
    which patching the tool's method would miss.
    """
    calls = {"n": 0}
    real = statistics_tool.compute_statistics

    def counted(data):
        calls["n"] += 1
        return real(data)

    monkeypatch.setattr(statistics_tool, "compute_statistics", counted)
    return calls


@pytest.mark.parametrize("attribute,reference", [
    ("mean", np.nanmean),
    ("median", np.nanmedian),
    ("deviation", np.nanstd),
    ("minimum", np.nanmin),
    ("maximum", np.nanmax),
])
def test_statistics_match_numpy(noisy, attribute, reference):
    """Every statistic matches numpy's nan-aware equivalent."""
    finite = noisy[np.isfinite(noisy)]
    ours = getattr(compute_statistics(noisy), attribute)
    assert np.isclose(ours, reference(finite), rtol=1e-5)


def test_blank_pixels_are_excluded_and_counted(noisy):
    """A single NaN would otherwise make every statistic NaN."""
    stats = compute_statistics(noisy)
    assert stats.pixels == noisy.size - 2
    assert stats.blank == 2
    assert not stats.is_empty


def test_big_endian_integers_are_read_correctly():
    """FITS is big-endian by specification, so this is the on-disk case."""
    stats = compute_statistics(np.arange(100, dtype=">i4").reshape(10, 10))
    assert (stats.minimum, stats.maximum) == (0, 99)
    assert np.isclose(stats.mean, 49.5)
    assert np.isclose(stats.median, 49.5)


def test_constant_frame_has_no_deviation():
    """A flat frame is a legitimate input, not a degenerate one."""
    stats = compute_statistics(np.full((8, 8), 7, dtype=np.uint16))
    assert stats.deviation == 0.0
    assert stats.minimum == stats.maximum == 7.0


def test_all_blank_frame_reports_empty():
    """Every statistic is NaN, not a misleading zero."""
    stats = compute_statistics(np.full((4, 4), np.nan, dtype=np.float32))
    assert stats.is_empty
    assert (stats.pixels, stats.blank) == (0, 16)
    assert all(math.isnan(value) for value in
               (stats.mean, stats.median, stats.deviation,
                stats.minimum, stats.maximum))


@pytest.mark.parametrize("value,expected", [
    (59983.0, "59,983"),   # integral counts should not show decimals
    (-12.0, "-12"),
    (499.6053, "499.605"),
    (float("nan"), "—"),   # NaN must not render as a number
])
def test_counts_format_without_inventing_precision(value, expected):
    """Counts read as counts, and blanks read as blank."""
    assert format_count(value) == expected


@pytest.mark.parametrize("bad", [0, -1, 61, "fast", True])
def test_bad_update_hz_is_rejected(bad):
    """update_hz is validated up front rather than misused later."""
    with pytest.raises(ConfigError, match="update_hz"):
        StatisticsConfig(enabled=True, update_hz=bad).validate("tools.statistics")


def test_boolean_shorthand_enables_the_tool():
    """`statistics: true` works, as it does for every other tool section."""
    config = from_dict({"tools": {"statistics": True}})
    assert config.tools.statistics.enabled is True
    assert "statistics" in config.tools.enabled_names()


def test_panel_reports_the_current_frame(panel, qapp, noisy):
    """The figures reach the panel, blanks included."""
    tool, view_model = panel
    assert tool.caption.text() == "No frame selected."

    view_model.update_live_frame(noisy, {})
    qapp.processEvents()

    expected = compute_statistics(noisy)
    assert tool.values["mean"].text() == format_count(expected.mean)
    assert "blank" in tool.pixel_label.text()


def test_statistics_ignore_the_display_scale(panel, qapp, noisy):
    """They describe detector counts, so the rendering is irrelevant."""
    tool, view_model = panel
    view_model.update_live_frame(noisy, {})
    qapp.processEvents()
    before = {name: label.text() for name, label in tool.values.items()}

    view_model.set_current_scale("log")
    tool.recompute()

    after = {name: label.text() for name, label in tool.values.items()}
    assert before == after


def test_live_stream_is_throttled(panel, qapp, count_computations):
    """A burst of live frames must not mean a recompute per frame."""
    tool, view_model = panel
    base = np.random.default_rng(2).normal(500, 50, (128, 128)).astype(np.float32)
    view_model.update_live_frame(base, {})
    qapp.processEvents()
    count_computations["n"] = 0

    burst = 20
    for offset in range(burst):
        view_model.update_live_frame(base + offset, {})
        qapp.processEvents()

    assert count_computations["n"] < burst, "the throttle did nothing"

    # Trailing edge: the newest frame's numbers must still arrive.
    expected = format_count(compute_statistics(base + burst - 1).mean)
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and tool.values["mean"].text() != expected:
        qapp.processEvents()
        time.sleep(0.01)
    assert tool.values["mean"].text() == expected, "the newest frame never landed"


def test_changing_frame_recomputes_immediately(panel, qapp, count_computations):
    """A stale panel beside a newly selected frame would read as a bug."""
    tool, view_model = panel
    view_model.update_live_frame(
        np.full((32, 32), 100.0, dtype=np.float32), {})
    qapp.processEvents()
    count_computations["n"] = 0

    other = np.full((32, 32), 9000.0, dtype=np.float32)
    frame = Frame(other, None, "second.fits")
    frame.pixmap = view_model.render(other)
    view_model.frames.append(frame)
    view_model.set_current_index(len(view_model.frames) - 1)
    qapp.processEvents()

    assert count_computations["n"] == 1, "switching frames should not wait for the throttle"
    assert tool.caption.text() == "second.fits"


def test_hidden_panel_skips_work_and_catches_up(panel, qapp, count_computations):
    """A hidden panel costs nothing, but must not show stale figures later."""
    tool, view_model = panel
    tool.dock.hide()
    qapp.processEvents()
    count_computations["n"] = 0

    view_model.update_live_frame(np.full((64, 64), 1234.0, dtype=np.float32), {})
    qapp.processEvents()
    assert count_computations["n"] == 0, "a hidden panel should not compute"
    assert tool.pending, "the skipped refresh should be remembered"

    tool.dock.show()
    qapp.processEvents()
    assert count_computations["n"] == 1, "showing the panel should catch up once"
    assert tool.values["mean"].text() == format_count(1234.0)
