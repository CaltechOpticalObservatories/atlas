# Standard Library Imports
import math

# A frame's zoom is a factor on top of the fit: 1.0 shows the whole image in
# whatever space the tile has, 2.0 shows half of it at twice the size.
ZOOM_FIT = 1.0
ZOOM_MIN = 1.0 / 64.0
ZOOM_MAX = 512.0
ZOOM_STEP = 2.0
WHEEL_STEP = 1.2


def clamp_zoom(factor):
    """Holds a zoom factor inside the range the viewer will render."""
    return min(ZOOM_MAX, max(ZOOM_MIN, float(factor)))


def fit_scale(label_size, source_size):
    """
    Screen pixels per data pixel when the whole image is fitted to a tile.

    Args:
        label_size (tuple): (width, height) of the image label.
        source_size (tuple): (width, height) of the frame's pixmap.

    Returns:
        float: the scale factor, or 0.0 when either size is degenerate, which
        is what a tile mid-layout has.
    """
    label_width, label_height = label_size
    source_width, source_height = source_size
    if min(label_width, label_height, source_width, source_height) <= 0:
        return 0.0
    return min(label_width / source_width, label_height / source_height)


def _span(available, scale, limit):
    """
    How many data pixels `available` screen pixels hold, at most `limit`.
    """
    if scale <= 0:
        return limit
    return max(1, min(limit, math.ceil(available / scale - 1e-6)))


def visible_region(label_size, source_size, zoom=ZOOM_FIT, center=None):
    """
    The part of a frame's pixmap a tile should draw, and how big to draw it.

    Args:
        label_size (tuple): (width, height) of the image label.
        source_size (tuple): (width, height) of the frame's pixmap.
        zoom (float): factor on top of the fit, 1.0 being the whole image.
        center (tuple): (x, y) in source pixels to centre the view on, or None
            for the middle of the image.

    Returns:
        tuple: (x, y, width, height, scale), the source rectangle to draw.
    """
    fit = fit_scale(label_size, source_size)
    if fit <= 0:
        return None

    zoom = clamp_zoom(zoom)
    scale = fit * zoom
    source_width, source_height = source_size
    width = _span(label_size[0], scale, source_width)
    height = _span(label_size[1], scale, source_height)

    centre_x = source_width / 2 if center is None else center[0]
    centre_y = source_height / 2 if center is None else center[1]
    x = max(0, min(source_width - width, round(centre_x - width / 2)))
    y = max(0, min(source_height - height, round(centre_y - height / 2)))
    return (x, y, width, height, scale)


def anchored_center(point, center, ratio):
    """
    The view centre that keeps `point` where it is while the zoom changes.

    Args:
        point (tuple): (x, y) in source pixels, the anchor to hold still.
        center (tuple): (x, y) in source pixels, the current view centre.
        ratio (float): how much the scale is about to be multiplied by.

    Returns:
        tuple: the new (x, y) view centre.
    """
    if ratio <= 0:
        return center
    return (point[0] - (point[0] - center[0]) / ratio,
            point[1] - (point[1] - center[1]) / ratio)
