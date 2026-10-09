"""
Region statistics: a box drawn on a frame, and the panel's summary of it.

The centroid is the part most worth pinning down. It is weighted by flux above
the region's median, and a test on a star sitting on a large bias is what shows
why: weighted by raw counts it would barely leave the middle of the box.
"""

# pytest injects fixtures as arguments of the same name.
# pylint: disable=redefined-outer-name

# Standard Library Imports
import math

# Third-Party Library Imports
import numpy as np
import pytest
from PyQt5.QtCore import QEvent, QPoint, Qt
from PyQt5.QtGui import QColor, QMouseEvent

from atlas.config.schema import AtlasConfig, StatisticsConfig, ToolsConfig
from atlas.model.pixel import locate_pixel
from atlas.model.region import Region, region_on_screen
from atlas.model.statistics import compute_statistics, flux_centroid, format_count
from atlas.view.frame_widget import REGION_COLOUR

# Every pixel carries its own index: data[row, column] == row * 16 + column.
COUNTS = np.arange(256, dtype=np.int32).reshape(16, 16)


def star(shape, x, y, sigma=1.5, bias=1000.0):
    """A Gaussian star of 5000 counts peak centred on (x, y), on a flat bias."""
    rows, columns = np.indices(shape)
    return (bias + 5000.0 * np.exp(
        -((columns - x) ** 2 + (rows - y) ** 2) / (2 * sigma ** 2))).astype(np.float32)


def test_corners_make_a_box_whichever_way_the_drag_went():
    """Dragging up and to the left is as good as down and to the right."""
    assert Region.from_corners((5, 9), (2, 3)) == Region(2, 3, 6, 10)
    assert Region.from_corners((2, 3), (5, 9)) == Region(2, 3, 6, 10)


def test_both_corner_pixels_are_inside_the_box():
    """The pixel the drag ended on is part of the region, not one past it."""
    region = Region.from_corners((2, 3), (5, 9))
    assert (region.width, region.height) == (4, 7)
    assert region.cut(COUNTS)[-1, -1] == COUNTS[9, 5]


def test_cut_is_the_numpy_slice_the_text_names():
    """The region's text is meant to be pasted straight into numpy."""
    region = Region(2, 3, 6, 10)
    assert region.text == "[3:10, 2:6]"
    assert np.array_equal(region.cut(COUNTS), COUNTS[3:10, 2:6])


def test_clip_keeps_the_part_on_the_frame():
    """A frame that shrinks under a region still has the overlap summarised."""
    assert Region(10, 12, 40, 40).clip((16, 16)) == Region(10, 12, 16, 16)
    assert Region(20, 20, 30, 30).clip((16, 16)) is None


def test_region_on_screen_follows_the_scale_and_the_crop():
    """Ten screen pixels per data pixel, counted from the drawn crop's corner."""
    region = Region(2, 3, 5, 7)
    assert region_on_screen(region, (0, 0, 16, 16), (160, 160)) == (20, 30, 30, 40)
    assert region_on_screen(region, (2, 2, 8, 8), (80, 80)) == (0, 10, 30, 40)


def test_a_region_smaller_than_a_screen_pixel_is_still_drawn():
    """On a downscaled frame a small box must not vanish into nothing."""
    assert region_on_screen(Region(100, 100, 101, 101),
                            (0, 0, 2048, 2048), (512, 512))[2:] == (1, 1)


def test_clamped_locate_pins_a_point_off_the_image_to_its_edge():
    """A drag that runs off the image keeps the region at the image's edge."""
    fit = {"label_size": (200, 100), "displayed_size": (100, 100),
           "source_size": (10, 10)}
    assert locate_pixel((0, -20), **fit) is None
    assert locate_pixel((0, -20), **fit, clamp=True) == (0, 0)
    assert locate_pixel((199, 150), **fit, clamp=True) == (9, 9)


def test_variance_matches_numpy():
    """Variance is reported beside the deviation it squares."""
    data = np.random.default_rng(3).normal(500, 50, (64, 64)).astype(np.float32)
    data[0, 0] = np.nan
    stats = compute_statistics(data)
    assert np.isclose(stats.variance, np.nanvar(data), rtol=1e-5)
    assert np.isclose(stats.deviation ** 2, stats.variance, rtol=1e-6)


def test_centroid_of_a_single_hot_pixel_is_that_pixel():
    """The simplest source there is, and its index in (x, y) order."""
    data = np.full((16, 16), 100.0, dtype=np.float32)
    data[11, 3] = 900.0
    stats = compute_statistics(data)
    assert (stats.centroid_x, stats.centroid_y) == (3.0, 11.0)


def test_centroid_finds_a_star_between_pixels():
    """
    A star off the pixel grid is located to well under a pixel.

    Not exactly: the noise peaks above the median carry a little weight too,
    and they pull towards the middle of the box, a few hundredths of a pixel
    here. A tighter box pulls less.
    """
    data = star((32, 32), 13.3, 17.8)
    data += np.random.default_rng(4).normal(0, 5, data.shape).astype(np.float32)
    stats = compute_statistics(data)
    assert stats.centroid_x == pytest.approx(13.3, abs=0.1)
    assert stats.centroid_y == pytest.approx(17.8, abs=0.1)


def test_centroid_is_not_dragged_to_the_middle_by_the_bias():
    """
    A bias of thousands of counts in every pixel outweighs the star.

    This is the reason for subtracting the median: weighted by raw counts the
    centroid of a star near a box's corner lands most of the way to the middle.
    """
    data = star((32, 32), 6.0, 6.0, bias=30000.0)
    raw = (np.indices(data.shape)[1] * data).sum() / data.sum()
    assert raw > 12, "this bias was not large enough to show the problem"
    assert compute_statistics(data).centroid_x == pytest.approx(6.0, abs=0.01)


def test_region_centroid_is_reported_in_frame_indices():
    """A centroid read off the panel indexes the frame, not the cut-out."""
    data = star((64, 64), 40.0, 25.0)
    region = Region(30, 15, 50, 35)
    stats = compute_statistics(region.cut(data), (region.x0, region.y0))
    assert stats.centroid_x == pytest.approx(40.0, abs=0.01)
    assert stats.centroid_y == pytest.approx(25.0, abs=0.01)


def test_flat_data_has_no_centroid():
    """Nothing rises above the median, so there is nothing to locate."""
    assert all(math.isnan(v) for v in flux_centroid(
        np.full((8, 8), 7.0, dtype=np.float32), 7.0))


def test_blank_pixels_do_not_poison_the_centroid():
    """One NaN would otherwise make the weighted sums NaN."""
    data = star((32, 32), 10.0, 20.0)
    data[0, 0] = np.nan
    data[31, 31] = np.inf
    stats = compute_statistics(data)
    assert stats.centroid_x == pytest.approx(10.0, abs=0.01)
    assert stats.centroid_y == pytest.approx(20.0, abs=0.01)


def test_colour_data_has_no_centroid():
    """There is no single flux to weight by across three channels."""
    assert math.isnan(compute_statistics(
        np.zeros((4, 4, 3), dtype=np.uint8)).centroid_x)


@pytest.fixture
def viewer(make_window, qapp):
    """A shown window with the statistics panel and one frame of data."""
    def build(data):
        config = AtlasConfig(tools=ToolsConfig(
            header=False, statistics=StatisticsConfig(enabled=True)))
        window, view_model = make_window(config, show=True)
        view_model.update_live_frame(data, {})
        qapp.processEvents()
        return window, view_model, window.frame_grid.widgets[0]

    return build


def image_point(widget, column, row):
    """The centre of a data pixel, in the tile's image label coordinates."""
    displayed = widget.image.pixmap()
    x, y, width, height, _ = widget.region
    return QPoint(
        (widget.image.width() - displayed.width()) // 2
        + int((column - x + 0.5) * displayed.width() / width),
        (widget.image.height() - displayed.height()) // 2
        + int((row - y + 0.5) * displayed.height() / height))


def drag(qapp, widget, start, end, modifiers=Qt.ShiftModifier):
    """
    Presses, drags and releases the left button across a tile's image.

    `start` and `end` are (column, row) data pixels, or a QPoint for a point
    that is on no pixel. Pixels are mapped to the screen as each event is sent,
    because the panel filling in can resize the tile mid-drag.

    Delivered to the image label, where a real mouse arrives, so this also
    covers Qt propagating each event up to the tile.
    """
    events = (
        (QEvent.MouseButtonPress, start, Qt.LeftButton, Qt.LeftButton),
        (QEvent.MouseMove, end, Qt.NoButton, Qt.LeftButton),
        (QEvent.MouseButtonRelease, end, Qt.LeftButton, Qt.NoButton),
    )
    for kind, where, button, buttons in events:
        point = where if isinstance(where, QPoint) else image_point(widget, *where)
        qapp.notify(widget.image, QMouseEvent(kind, point, button, buttons, modifiers))
        qapp.processEvents()


def green_pixels(widget):
    """How many pixels of the tile's drawn image are the region colour."""
    image = widget.image.pixmap().toImage()
    return sum(QColor(image.pixel(x, y)) == REGION_COLOUR
               for y in range(image.height()) for x in range(image.width()))


def test_shift_drag_defines_a_region_and_summarises_it(viewer, qapp):
    """The whole feature: draw a box, get its statistics beside the frame's."""
    window, view_model, widget = viewer(COUNTS)
    tool = window.tools["statistics"]
    assert tool.values["mean"].text() == format_count(COUNTS.mean())
    assert tool.region_values["mean"].text() == "—"

    drag(qapp, widget, (2, 3), (5, 9))

    region = view_model.current_frame.region
    assert region == Region(2, 3, 6, 10)
    expected = compute_statistics(COUNTS[3:10, 2:6], (2, 3))
    for key in ("mean", "variance", "minimum", "maximum"):
        assert tool.region_values[key].text() == format_count(getattr(expected, key))
    assert tool.region_values["minimum"].text() == str(COUNTS[3, 2])
    assert tool.region_values["maximum"].text() == str(COUNTS[9, 5])
    assert tool.region_values["pixels"].text() == "28"
    assert "data[3:10, 2:6]" in tool.region_caption.text()
    assert tool.values["mean"].text() == format_count(COUNTS.mean()), \
        "the frame's own figures should still be beside the region's"


def test_the_panel_reports_a_stars_centroid(viewer, qapp):
    """Boxing a star reads its position off the panel, in frame indices."""
    window, _, widget = viewer(star((32, 32), 20.0, 9.0, sigma=1.0))
    drag(qapp, widget, (14, 3), (26, 15))
    assert window.tools["statistics"].region_values["centroid"].text() == "(20.00, 9.00)"


def test_a_plain_drag_still_pans(viewer, qapp):
    """Shift is what makes a drag draw; without it the frame moves as before."""
    _, view_model, widget = viewer(COUNTS)
    view_model.set_current_zoom(4.0)
    qapp.processEvents()
    before = view_model.current_frame.center

    drag(qapp, widget, (8, 8), (6, 6),
         modifiers=Qt.NoModifier)

    assert view_model.current_frame.region is None
    assert view_model.current_frame.center != before


def test_the_region_is_drawn_over_the_image_but_not_into_it(viewer, qapp):
    """
    The box goes on the displayed copy only.

    The frame's own pixmap is what every redraw starts from, so a box painted
    into it would survive being cleared.
    """
    _, view_model, widget = viewer(COUNTS)
    rendered = view_model.current_frame.pixmap.toImage()
    assert green_pixels(widget) == 0

    drag(qapp, widget, (2, 3), (5, 9))
    assert green_pixels(widget) > 0
    assert view_model.current_frame.pixmap.toImage() == rendered


def test_shift_click_clears_the_region(viewer, qapp):
    """A shift-click that never left its pixel draws nothing, and clears."""
    window, view_model, widget = viewer(COUNTS)
    drag(qapp, widget, (2, 3), (5, 9))
    assert view_model.current_frame.region is not None
    assert window.clear_region_action.isEnabled()

    drag(qapp, widget, (8, 8), (8, 8))

    assert view_model.current_frame.region is None
    assert green_pixels(widget) == 0
    assert window.tools["statistics"].region_values["mean"].text() == "—"
    assert not window.clear_region_action.isEnabled()


def test_clear_region_menu_action(viewer, qapp):
    """Frame → Clear Region removes the box and its figures."""
    window, view_model, widget = viewer(COUNTS)
    drag(qapp, widget, (2, 3), (5, 9))

    window.clear_region_action.trigger()
    qapp.processEvents()

    assert view_model.current_frame.region is None
    assert green_pixels(widget) == 0
    assert window.tools["statistics"].region_values["mean"].text() == "—"


def test_a_drag_off_the_image_stops_at_its_edge(viewer, qapp):
    """Overshooting the corner is the easy way to box to the edge of a frame."""
    _, view_model, widget = viewer(COUNTS)
    drag(qapp, widget, (10, 12),
         QPoint(widget.image.width() + 50, widget.image.height() + 50))
    assert view_model.current_frame.region == Region(10, 12, 16, 16)


def test_the_region_follows_a_live_stream(viewer, qapp):
    """The box stays put while the counts under it change."""
    window, view_model, widget = viewer(COUNTS)
    tool = window.tools["statistics"]
    drag(qapp, widget, (2, 3), (5, 9))

    view_model.update_live_frame(COUNTS + 1000, {})
    tool.recompute()

    assert view_model.current_frame.region == Region(2, 3, 6, 10)
    assert tool.region_values["minimum"].text() == format_count(COUNTS[3, 2] + 1000)


def test_a_region_left_off_a_shrunken_frame_says_so(viewer, qapp):
    """A smaller frame can arrive under a region; that is not an error."""
    window, view_model, widget = viewer(COUNTS)
    tool = window.tools["statistics"]
    drag(qapp, widget, (10, 12), (15, 15))

    view_model.update_live_frame(np.ones((8, 8), dtype=np.int32), {})
    tool.recompute()

    assert tool.region_values["mean"].text() == "—"
    assert "off the frame" in tool.region_caption.text()
