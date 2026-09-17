"""
The hover pixel readout.
"""

# pytest injects fixtures as arguments of the same name.
# pylint: disable=redefined-outer-name

# Standard Library Imports
import math

# Third-Party Library Imports
import numpy as np
import pytest
from astropy.io import fits
from PyQt5.QtCore import QEvent, QPoint, Qt
from PyQt5.QtGui import QMouseEvent

from atlas.config.schema import AtlasConfig, DisplayConfig, ToolsConfig
from atlas.model.pixel import PixelReadout, locate_pixel, read_pixel

# Every pixel carries its own index: data[row, column] == row * 16 + column,
# so a readout that is off by a row or a column says so in the value too.
COUNTS = np.arange(256, dtype=np.int32).reshape(16, 16)


def test_an_exactly_fitting_image_maps_corner_to_corner():
    """With no letterboxing and no scaling the two coordinate systems agree."""
    fit = {"label_size": (16, 16), "displayed_size": (16, 16),
           "source_size": (16, 16)}
    assert locate_pixel((0, 0), **fit) == (0, 0)
    assert locate_pixel((15, 15), **fit) == (15, 15)
    assert locate_pixel((3, 11), **fit) == (3, 11)


def test_scaling_is_undone():
    """A pixel drawn ten screen pixels wide still reports one data index."""
    fit = {"label_size": (160, 160), "displayed_size": (160, 160),
           "source_size": (16, 16)}
    assert locate_pixel((0, 0), **fit) == (0, 0)
    assert locate_pixel((9, 9), **fit) == (0, 0), "still inside the first pixel"
    assert locate_pixel((10, 0), **fit) == (1, 0)
    assert locate_pixel((159, 159), **fit) == (15, 15)


def test_centre_alignment_is_undone():
    """
    The label centres the pixmap, so half the slack precedes the image.
    """
    # 100 wide pixmap in a 200 wide label: 50 either side.
    fit = {"label_size": (200, 100), "displayed_size": (100, 100),
           "source_size": (10, 10)}
    assert locate_pixel((50, 0), **fit) == (0, 0)
    assert locate_pixel((149, 99), **fit) == (9, 9)


@pytest.mark.parametrize("point", [(49, 0), (150, 0), (50, -1), (50, 100), (-5, -5)])
def test_letterboxing_belongs_to_no_pixel(point):
    """The empty space either side of the image must not report a pixel."""
    assert locate_pixel(point, label_size=(200, 100), displayed_size=(100, 100),
                        source_size=(10, 10)) is None


@pytest.mark.parametrize("displayed,source", [
    ((0, 100), (10, 10)),   # nothing drawn yet
    ((100, 0), (10, 10)),
    ((100, 100), (0, 10)),  # no data behind it
])
def test_degenerate_sizes_report_nothing(displayed, source):
    """A tile mid-layout has no geometry to invert, and must not divide by it."""
    assert locate_pixel((10, 10), label_size=(100, 100),
                        displayed_size=displayed, source_size=source) is None


def test_read_pixel_indexes_row_then_column():
    """(x, y) is data[y, x]; swapping them is the obvious way to get this wrong."""
    assert read_pixel(COUNTS, 3, 11) == 11 * 16 + 3


@pytest.mark.parametrize("column,row", [(-1, 0), (0, -1), (16, 0), (0, 16)])
def test_read_pixel_rejects_indices_off_the_array(column, row):
    """A live stream can shrink the data under a cursor that has not moved."""
    assert read_pixel(COUNTS, column, row) is None


def test_read_pixel_handles_big_endian_data():
    """FITS is big-endian by specification, so this is the on-disk case."""
    data = np.arange(9, dtype=">i4").reshape(3, 3)
    assert read_pixel(data, 2, 1) == 5


def test_read_pixel_returns_every_channel_of_colour_data():
    """Colour frames have no single count, so all the samples are reported."""
    colour = np.zeros((4, 4, 3), dtype=np.uint8)
    colour[1, 2] = (10, 20, 30)
    assert read_pixel(colour, 2, 1) == (10, 20, 30)


@pytest.mark.parametrize("value,expected", [
    (59983, "59,983"),
    (499.6053, "499.605"),
    (float("nan"), "—"),
    ((10, 20, 30), "10, 20, 30"),
])
def test_readout_formats_its_value(value, expected):
    """Counts read as counts, blanks read as blank, colour reads as channels."""
    assert PixelReadout("f.fits", 1, 2, value).text == expected


@pytest.fixture
def viewer(make_window, qapp):
    """
    A shown window with one frame of known counts on screen.

    Shown, because a tile has no size until its window does, and the geometry
    under test is exactly that size.
    """
    window, view_model = make_window(
        AtlasConfig(tools=ToolsConfig(header=False)), show=True)
    view_model.update_live_frame(COUNTS, {})
    qapp.processEvents()
    return window, view_model


def image_point(widget, column, row):
    """The centre of a data pixel, in the tile's image label coordinates."""
    displayed = widget.image.pixmap()
    source = widget.frame.pixmap
    return QPoint(
        (widget.image.width() - displayed.width()) // 2
        + int((column + 0.5) * displayed.width() / source.width()),
        (widget.image.height() - displayed.height()) // 2
        + int((row + 0.5) * displayed.height() / source.height()))


def hover(qapp, widget, point):
    """
    Moves the cursor to a point in a tile's image label.

    Delivered to the label rather than to the tile, because that is where a
    real cursor arrives: the readout depends on Qt propagating the move up to
    the tile, and on translating the position on the way.
    """
    event = QMouseEvent(QEvent.MouseMove, point,
                        Qt.NoButton, Qt.NoButton, Qt.NoModifier)
    qapp.notify(widget.image, event)
    qapp.processEvents()


def test_hovering_a_pixel_reports_its_index_and_count(viewer, qapp):
    """The readout is what the whole feature exists to produce."""
    window, _ = viewer
    widget = window.frame_grid.widgets[0]
    assert widget.image.pixmap() is not None, "nothing was drawn to hover over"

    for column, row in ((0, 0), (3, 11), (15, 15)):
        hover(qapp, widget, image_point(widget, column, row))
        assert window.pixel_readout.text() == \
            f"({column}, {row})  {row * 16 + column}", \
            f"wrong readout for data[{row}, {column}]"


def test_hovering_beside_the_image_reports_nothing(viewer, qapp):
    """
    The letterboxing around a tile's image belongs to no pixel.

    A square frame in a wide tile has empty space either side of it; the
    nearest pixel is not the pixel under the cursor.
    """
    window, _ = viewer
    widget = window.frame_grid.widgets[0]
    displayed = widget.image.pixmap()
    if displayed.width() >= widget.image.width():
        pytest.skip("this tile has no horizontal letterboxing to test")

    hover(qapp, widget, image_point(widget, 8, 8))
    assert window.pixel_readout.text(), "the readout was empty to begin with"

    hover(qapp, widget, QPoint(0, widget.image.height() // 2))
    assert window.pixel_readout.text() == ""


def test_leaving_the_tile_clears_the_readout(viewer, qapp):
    """A coordinate left standing after the cursor has gone would be a lie."""
    window, _ = viewer
    widget = window.frame_grid.widgets[0]
    hover(qapp, widget, image_point(widget, 4, 4))
    assert window.pixel_readout.text()

    qapp.notify(widget, QEvent(QEvent.Leave))
    qapp.processEvents()
    assert window.pixel_readout.text() == ""


def test_readout_follows_a_live_frame(viewer, qapp):
    """
    A frame arriving under a still cursor re-reads the same pixel.

    Resting on one pixel and watching its counts change is the reason the
    hovered index is kept rather than the hovered value.
    """
    window, view_model = viewer
    widget = window.frame_grid.widgets[0]
    hover(qapp, widget, image_point(widget, 3, 11))
    assert window.pixel_readout.text() == f"(3, 11)  {11 * 16 + 3}"

    view_model.update_live_frame(COUNTS + 1000, {})
    qapp.processEvents()

    assert window.pixel_readout.text() == f"(3, 11)  {11 * 16 + 3 + 1000:,}"


def test_readout_clears_when_the_frame_goes_away(viewer, qapp):
    """The pixel of a deleted frame is not a pixel of anything."""
    window, view_model = viewer
    widget = window.frame_grid.widgets[0]
    hover(qapp, widget, image_point(widget, 4, 4))
    assert window.pixel_readout.text()

    view_model.delete_all_frames()
    qapp.processEvents()

    assert window.pixel_readout.text() == ""
    assert window.frame_grid.hover is None, "a dead frame was still held"


def test_tiled_readout_names_the_frame_and_reads_its_own_data(
        make_window, qapp, tmp_path):
    """
    One status bar under several tiles has to say which one it means.

    Hovering the second tile must also read the second frame's counts, not the
    current frame's: the readout follows the cursor, not the selection.
    """
    window, view_model = make_window(
        AtlasConfig(display=DisplayConfig(mode="tile"),
                    tools=ToolsConfig(header=False)), show=True)

    paths = []
    for name, offset in (("a.fits", 0), ("b.fits", 1000)):
        path = tmp_path / name
        fits.PrimaryHDU(COUNTS + offset).writeto(path)
        paths.append(str(path))
    assert view_model.load_files(paths) == 2
    qapp.processEvents()

    for position, offset in enumerate((0, 1000)):
        widget = window.frame_grid.widgets[position]
        hover(qapp, widget, image_point(widget, 3, 11))
        expected = f"{widget.frame.label}  (3, 11)  {11 * 16 + 3 + offset:,}"
        assert window.pixel_readout.text() == expected


def test_untiling_drops_a_hover_on_a_frame_no_longer_shown(
        make_window, qapp, tmp_path):
    """
    Going back to a single frame can leave the cursor over a hidden tile.

    No move event follows, so the readout would otherwise keep reporting a
    frame that is no longer on screen.
    """
    window, view_model = make_window(
        AtlasConfig(display=DisplayConfig(mode="tile"),
                    tools=ToolsConfig(header=False)), show=True)

    paths = []
    for name in ("a.fits", "b.fits"):
        path = tmp_path / name
        fits.PrimaryHDU(COUNTS).writeto(path)
        paths.append(str(path))
    assert view_model.load_files(paths) == 2
    qapp.processEvents()

    # Hover the first tile, then select and un-tile down to the second frame.
    hover(qapp, window.frame_grid.widgets[0], image_point(
        window.frame_grid.widgets[0], 3, 11))
    assert window.pixel_readout.text()

    view_model.set_current_index(1)
    view_model.set_display_mode("single")
    qapp.processEvents()

    assert window.pixel_readout.text() == ""


def test_blank_pixels_read_as_blank(make_window, qapp):
    """A NaN pixel must not be shown as a number."""
    window, view_model = make_window(
        AtlasConfig(tools=ToolsConfig(header=False)), show=True)
    data = np.full((8, 8), 5.0, dtype=np.float32)
    data[2, 3] = np.nan
    view_model.update_live_frame(data, {})
    qapp.processEvents()

    widget = window.frame_grid.widgets[0]
    hover(qapp, widget, image_point(widget, 3, 2))

    assert window.pixel_readout.text() == "(3, 2)  —"
    assert math.isnan(read_pixel(data, 3, 2))


def test_a_downscaled_frame_stays_self_consistent(make_window, qapp):
    """
    On a frame larger than its tile the reported value must match the
    reported index.

    A detector frame is almost always shown smaller than it is, so several
    data rows share one screen row and no readout can name all of them. What
    it must never do is pair one pixel's coordinates with another's count.
    """
    window, view_model = make_window(
        AtlasConfig(tools=ToolsConfig(header=False)), show=True)
    # Distinct per pixel, so a mismatched row or column cannot coincide.
    data = np.arange(512 * 512, dtype=np.int32).reshape(512, 512)
    view_model.update_live_frame(data, {})
    qapp.processEvents()

    widget = window.frame_grid.widgets[0]
    displayed = widget.image.pixmap()
    assert displayed.width() < 512, "this tile is not downscaling anything"

    for column, row in ((0, 0), (170, 341), (341, 170), (511, 511)):
        hover(qapp, widget, image_point(widget, column, row))
        text = window.pixel_readout.text()
        assert text, f"no readout for data[{row}, {column}]"

        coordinates, value = text.split(")")
        got_column, got_row = (int(part) for part in coordinates.strip("(").split(","))
        assert value.strip() == f"{data[got_row, got_column]:,}", \
            f"{text} does not report the pixel it names"
