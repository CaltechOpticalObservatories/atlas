"""
Covers the arithmetic against numpy's own nan-aware functions, the formatting,
the config bounds, and the panel's throttle. A live stream must not recompute on every frame, 
but must still end up showing the newest frame's numbers.
"""

import math
import sys
import time

import numpy as np
from PyQt5.QtWidgets import QApplication

from atlas.config.schema import (AtlasConfig, ConfigError, StatisticsConfig,
                                 ToolsConfig, from_dict)
from atlas.features import statistics as statistics_tool
from atlas.features.statistics import format_count
from atlas.model.frame import Frame
from atlas.model.statistics import compute_statistics
from atlas.view.main_window import AtlasWindow
from atlas.viewmodel.frame_viewmodel import FrameViewModel

# Fast enough to keep the check short, slow enough that a burst is throttled.
UPDATE_HZ = 10.0


def check_arithmetic():
    """Every statistic matches numpy's nan-aware equivalent."""
    data = np.random.default_rng(1).normal(500, 50, (256, 256)).astype(np.float32)
    data[0, 0] = np.nan  # a blank pixel, as floating-point FITS data carries
    data[1, 1] = np.inf

    stats = compute_statistics(data)
    for name, ours, theirs in (
            ("mean", stats.mean, np.nanmean(data[np.isfinite(data)])),
            ("median", stats.median, np.nanmedian(data[np.isfinite(data)])),
            ("std", stats.deviation, np.nanstd(data[np.isfinite(data)])),
            ("min", stats.minimum, np.nanmin(data[np.isfinite(data)])),
            ("max", stats.maximum, np.nanmax(data[np.isfinite(data)]))):
        assert np.isclose(ours, theirs, rtol=1e-5), \
            f"{name}: {ours} != numpy's {theirs}"

    assert stats.pixels == data.size - 2, \
        f"two non-finite pixels should be excluded, got {stats.pixels} of {data.size}"
    assert stats.blank == 2, f"expected 2 blank pixels, got {stats.blank}"
    assert not stats.is_empty

    print("OK: statistics match numpy, blanks excluded")


def check_data_types():
    """Integer and big-endian FITS arrays are summarised, not rejected."""
    # FITS is big-endian by specification, so this is the common on-disk case.
    counts = np.arange(100, dtype=">i4").reshape(10, 10)
    stats = compute_statistics(counts)
    assert stats.minimum == 0 and stats.maximum == 99, \
        f"big-endian ints mis-read: {stats.minimum} to {stats.maximum}"
    assert np.isclose(stats.mean, 49.5) and np.isclose(stats.median, 49.5)

    constant = compute_statistics(np.full((8, 8), 7, dtype=np.uint16))
    assert constant.deviation == 0.0, "a constant frame has zero deviation"
    assert constant.minimum == constant.maximum == 7.0

    blank = compute_statistics(np.full((4, 4), np.nan, dtype=np.float32))
    assert blank.is_empty, "an all-blank frame should report as empty"
    assert blank.pixels == 0 and blank.blank == 16
    assert all(math.isnan(value) for value in  # NaN, not a misleading zero
               (blank.mean, blank.median, blank.deviation,
                blank.minimum, blank.maximum))

    print("OK: integer, big-endian, constant and all-blank frames handled")


def check_formatting():
    """Counts are shown without inventing or losing precision."""
    assert format_count(59983.0) == "59,983", "integral counts should not show decimals"
    assert format_count(-12.0) == "-12"
    assert format_count(499.6053) == "499.605"
    assert format_count(float("nan")) == "—", "NaN must not render as a number"
    print("OK: counts format as expected")


def check_config_bounds():
    """update_hz is validated rather than accepted and misused later."""
    StatisticsConfig(enabled=True, update_hz=2.0).validate("tools.statistics")

    for bad in (0, -1, 61, "fast", True):
        try:
            StatisticsConfig(enabled=True, update_hz=bad).validate("tools.statistics")
        except ConfigError:
            continue
        raise AssertionError(f"update_hz={bad!r} should have been rejected")

    # The bare-boolean shorthand every other tool section accepts.
    config = from_dict({"tools": {"statistics": True}})
    assert config.tools.statistics.enabled is True
    assert "statistics" in config.tools.enabled_names()

    print("OK: update_hz is validated and the boolean shorthand works")


def build_window(update_hz=UPDATE_HZ):
    """A shown window with the statistics panel enabled."""
    config = AtlasConfig(tools=ToolsConfig(
        header=False, statistics=StatisticsConfig(enabled=True, update_hz=update_hz)))
    view_model = FrameViewModel(config)
    window = AtlasWindow(view_model, config)
    # The panel skips work while hidden, and a dock is not visible until its
    # window is, so an unshown window would never refresh at all.
    window.show()
    return window, view_model, window.tools["statistics"]


def check_panel_contents(app):
    """The panel fills in for a frame, and ignores the display scale."""
    window, view_model, tool = build_window()
    app.processEvents()
    assert tool.dock.isVisible(), "the dock should be visible once the window is"
    assert tool.caption.text() == "No frame selected."

    data = np.random.default_rng(1).normal(500, 50, (128, 128)).astype(np.float32)
    data[0, 0] = np.nan
    view_model.update_live_frame(data, {})
    app.processEvents()

    stats = compute_statistics(data)
    assert tool.values["mean"].text() == format_count(stats.mean), \
        f"panel shows {tool.values['mean'].text()}, expected {format_count(stats.mean)}"
    assert "blank" in tool.pixel_label.text(), \
        f"the blank pixel should be reported, got {tool.pixel_label.text()!r}"

    # Statistics describe detector counts, so the display scale is irrelevant.
    before = {name: label.text() for name, label in tool.values.items()}
    view_model.set_current_scale("log")
    tool.recompute()
    after = {name: label.text() for name, label in tool.values.items()}
    assert before == after, f"the scale moved the statistics: {before} -> {after}"

    window.close()
    print("OK: the panel reports a frame and is unaffected by the display scale")


def check_throttle(app):
    """A live stream is rate limited, but still lands the newest numbers."""
    window, view_model, tool = build_window()
    app.processEvents()

    # Counting the real computation catches work triggered by any route,
    # including the timer, which patching the method would miss.
    calls = {"n": 0}
    real = statistics_tool.compute_statistics

    def counted(data):
        calls["n"] += 1
        return real(data)

    statistics_tool.compute_statistics = counted
    try:
        base = np.random.default_rng(2).normal(500, 50, (128, 128)).astype(np.float32)
        view_model.update_live_frame(base, {})
        app.processEvents()
        calls["n"] = 0

        burst = 20
        for offset in range(burst):
            view_model.update_live_frame(base + offset, {})
            app.processEvents()
        during = calls["n"]
        assert during < burst, \
            f"{burst} live frames caused {during} recomputes; the throttle did nothing"

        # Trailing edge: the last frame's numbers must still arrive.
        deadline = time.monotonic() + 2.0
        expected = format_count(compute_statistics(base + burst - 1).mean)
        while time.monotonic() < deadline and tool.values["mean"].text() != expected:
            app.processEvents()
            time.sleep(0.01)
        assert tool.values["mean"].text() == expected, \
            f"the newest frame never landed: {tool.values['mean'].text()} != {expected}"

        # Navigating by hand must not wait for the throttle.
        calls["n"] = 0
        other = np.full((32, 32), 9000.0, dtype=np.float32)
        frame = Frame(other, None, "second.fits")
        frame.pixmap = view_model.render(other)
        view_model.frames.append(frame)
        view_model.set_current_index(len(view_model.frames) - 1)
        app.processEvents()
        assert calls["n"] == 1, \
            f"switching frames should recompute at once, got {calls['n']} recomputes"
        assert tool.caption.text() == "second.fits"
    finally:
        statistics_tool.compute_statistics = real
        window.close()

    print(f"OK: a {burst}-frame burst caused {during} recompute(s), "
          "and frame changes are immediate")


def check_hidden_panel_skips_work(app):
    """A hidden panel costs nothing, and catches up when shown."""
    window, view_model, tool = build_window()
    app.processEvents()

    calls = {"n": 0}
    real = statistics_tool.compute_statistics

    def counted(data):
        calls["n"] += 1
        return real(data)

    statistics_tool.compute_statistics = counted
    try:
        tool.dock.hide()
        app.processEvents()
        calls["n"] = 0

        data = np.full((64, 64), 1234.0, dtype=np.float32)
        view_model.update_live_frame(data, {})
        app.processEvents()
        assert calls["n"] == 0, \
            f"a hidden panel should not compute, got {calls['n']} recomputes"
        assert tool.pending, "the skipped refresh should be remembered"

        tool.dock.show()
        app.processEvents()
        assert calls["n"] == 1, \
            f"showing the panel should catch up once, got {calls['n']} recomputes"
        assert tool.values["mean"].text() == format_count(1234.0)
    finally:
        statistics_tool.compute_statistics = real
        window.close()

    print("OK: a hidden panel skips the work and catches up when shown")


def main():
    """Runs every statistics check; raises AssertionError on failure."""
    check_arithmetic()
    check_data_types()
    check_formatting()
    check_config_bounds()

    app = QApplication(sys.argv)
    check_panel_contents(app)
    check_throttle(app)
    check_hidden_panel_skips_work(app)
    app.processEvents()

    print("\nOK: frame statistics are correct, formatted, and throttled on a stream")


if __name__ == "__main__":
    main()
