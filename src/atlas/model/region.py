# Standard Library Imports
from dataclasses import dataclass


@dataclass(frozen=True)
class Region:
    """
    A box of data pixels on one frame.

    The bounds are 0-based and half-open, numpy's convention like the hover
    readout's, so the region is exactly ``data[y0:y1, x0:x1]`` and its width is
    ``x1 - x0``.
    """
    x0: int
    y0: int
    x1: int
    y1: int

    @classmethod
    def from_corners(cls, first, second):
        """
        The box spanning two corner pixels, both of them included.

        Args:
            first (tuple): (column, row) where the drag began.
            second (tuple): (column, row) where it is now, which may lie
                above or to the left of `first`.
        """
        return cls(min(first[0], second[0]), min(first[1], second[1]),
                   max(first[0], second[0]) + 1, max(first[1], second[1]) + 1)

    @property
    def width(self):
        """Columns covered."""
        return self.x1 - self.x0

    @property
    def height(self):
        """Rows covered."""
        return self.y1 - self.y0

    def clip(self, shape):
        """
        The part of this region inside an array of the given shape.

        A live stream can replace a frame with a smaller one under a region
        drawn on the last, so a region is not guaranteed to fit its data.

        Returns:
            Region: the overlap, or None when there is none.
        """
        height, width = shape[:2]
        clipped = Region(max(0, self.x0), max(0, self.y0),
                         min(width, self.x1), min(height, self.y1))
        if clipped.width <= 0 or clipped.height <= 0:
            return None
        return clipped

    def cut(self, plane):
        """The region's pixels out of a plane, without copying them."""
        return plane[self.y0:self.y1, self.x0:self.x1]

    @property
    def text(self):
        """The region as the numpy slice that selects it."""
        return f"[{self.y0}:{self.y1}, {self.x0}:{self.x1}]"


def region_on_screen(region, view, displayed_size):
    """
    Where a region falls on a tile's scaled image.

    Args:
        region (Region): the box, in data pixels.
        view (tuple): (x, y, width, height), the part of the frame being
            drawn, as returned by zoom.visible_region().
        displayed_size (tuple): (width, height) of the scaled pixmap.

    Returns:
        tuple: (left, top, width, height) in the scaled pixmap's pixels. It
        may extend past the pixmap when the region is partly out of view, and
        is never less than one pixel across, so a region smaller than a screen
        pixel is still drawn.
    """
    x, y, width, height = view
    x_scale = displayed_size[0] / width
    y_scale = displayed_size[1] / height
    left = round((region.x0 - x) * x_scale)
    top = round((region.y0 - y) * y_scale)
    right = round((region.x1 - x) * x_scale)
    bottom = round((region.y1 - y) * y_scale)
    return (left, top, max(1, right - left), max(1, bottom - top))
