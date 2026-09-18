# Standard Library Imports
from dataclasses import dataclass
from typing import Any

# Third-Party Library Imports
import numpy as np

from .statistics import format_count


@dataclass(frozen=True)
class PixelReadout:
    """
    One pixel of one frame, as the status bar should report it.

    The indices are 0-based array indices, so ``(x, y)`` is ``data[y, x]``.
    That is deliberately numpy's convention and not DS9's 1-based one: the
    numbers are most useful when they can be pasted straight into whatever
    the user is inspecting the frame with.
    """
    label: str      # the frame it came from, which only matters when tiling
    x: int          # column index
    y: int          # row index
    value: Any      # a count, or one sample per channel for colour data

    @property
    def text(self):
        """The pixel's value, formatted for display."""
        if isinstance(self.value, tuple):
            return ", ".join(str(sample) for sample in self.value)
        return format_count(self.value)


def locate_pixel(point, label_size, displayed_size, source_size):
    """
    Maps a point on a frame's image label to an index into its data.

    Two things stand between the two coordinate systems: the pixmap is scaled
    to fit the label, and whatever space is left over is split evenly either
    side of it by the label's centre alignment. Both have to be undone.

    Args:
        point (tuple): (x, y) in the image label's own coordinates.
        label_size (tuple): (width, height) of the image label.
        displayed_size (tuple): (width, height) of the scaled pixmap.
        source_size (tuple): (width, height) of the unscaled pixmap, which is
            also the width and height of the data being displayed.

    Returns:
        tuple: (column, row), 0-based, or None when the point is not on the
        image. Everything outside the pixmap is a miss, including the label's
        own letterboxing, which belongs to no pixel.
    """
    displayed_width, displayed_height = displayed_size
    source_width, source_height = source_size
    if min(displayed_width, displayed_height, source_width, source_height) <= 0:
        return None

    # A QLabel centres its pixmap, so half the unused space precedes it.
    x = point[0] - (label_size[0] - displayed_width) // 2
    y = point[1] - (label_size[1] - displayed_height) // 2
    if not (0 <= x < displayed_width and 0 <= y < displayed_height):
        return None

    return (x * source_width // displayed_width,
            y * source_height // displayed_height)


def read_pixel(plane, column, row):
    """
    Reads one pixel out of a display plane.

    Args:
        plane (numpy.ndarray): The 2D plane, or (h, w, channels) colour data,
            that is actually on screen.
        column (int): 0-based column index.
        row (int): 0-based row index.

    Returns:
        The value as a plain Python number, a tuple of samples for colour data,
        or None when the index is outside the array. A live stream can replace
        the data under a stationary cursor, so an index that was in bounds when
        the mouse last moved need not still be.
    """
    height, width = plane.shape[:2]
    if not (0 <= column < width and 0 <= row < height):
        return None

    value = np.asarray(plane[row, column])
    if value.ndim:
        return tuple(value.tolist())
    return value.item()
