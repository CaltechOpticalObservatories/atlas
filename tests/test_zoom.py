"""
Zooming and panning a frame.
"""
# pylint: disable=redefined-outer-name

# Third-Party Library Imports
import numpy as np
import pytest
from PyQt5.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt5.QtGui import QColor, QMouseEvent, QWheelEvent

from atlas.config.schema import AtlasConfig, ConfigError, DisplayConfig, ToolsConfig

# Every pixel carries its own index
COUNTS = np.arange(256, dtype=np.int32).reshape(16, 16)


@pytest.fixture
def viewer(make_window, qapp):
    """
    Builds a shown window around one frame of data.

    Shown, because a tile has no size until its window does, and the geometry
    under test is exactly that size.
    """
    def build(data, config=None):
        window, view_model = make_window(
            config or AtlasConfig(tools=ToolsConfig(header=False)), show=True)
        view_model.update_live_frame(data, {})
        qapp.processEvents()
        return window, view_model, window.frame_grid.widgets[0]

    return build


def displayed_values(widget):
    """Every grey level in what the tile is currently drawing."""
    image = widget.image.pixmap().toImage()
    return {QColor(image.pixel(x, y)).red()
            for y in range(image.height()) for x in range(image.width())}


def image_point(widget, column, row):
    """The centre of a data pixel, in the tile's image label coordinates."""
    displayed = widget.image.pixmap()
    x, y, width, height, _ = widget.region
    return QPoint(
        (widget.image.width() - displayed.width()) // 2
        + int((column - x + 0.5) * displayed.width() / width),
        (widget.image.height() - displayed.height()) // 2
        + int((row - y + 0.5) * displayed.height() / height))


def send(qapp, widget, event):
    """Delivers an event to the image label, where a real one arrives."""
    qapp.notify(widget.image, event)
    qapp.processEvents()


def test_zooming_in_magnifies_without_correcting_the_image(viewer, qapp):
    """
    A zoom crops the render and enlarges the crop. It does nothing else.
    """
    data = (np.indices((32, 32)).sum(axis=0) % 2) * 1000
    data[0, 0] = 100000  # the outlier that sets the display range
    _, view_model, widget = viewer(data.astype(np.int32))
    rendered = widget.frame.pixmap

    widget.frame.center = (28, 28)
    view_model.set_current_zoom(8.0)
    qapp.processEvents()

    assert widget.frame.pixmap is rendered, "the frame was re-rendered"
    assert widget.display_scale() > 1, "this tile is not magnifying anything"
    assert 0 not in widget.region[:2], "the view did not move off the hot pixel"

    x, y, width, height, _ = widget.region
    crop = rendered.copy(x, y, width, height).toImage()
    assert displayed_values(widget) == {
        QColor(crop.pixel(i, j)).red()
        for j in range(crop.height()) for i in range(crop.width())}, \
        "the magnified region holds greys its part of the render does not"
    assert max(displayed_values(widget)) < 10, \
        "the dim region was restretched to its own range"
