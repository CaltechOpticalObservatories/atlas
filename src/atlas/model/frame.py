# Standard Library Imports
import itertools
import os

from .zoom import ZOOM_FIT, clamp_zoom


class Frame:
    """
    One loaded image, following the frame concept from SAOImage DS9.

    A frame owns its data, header and rendered pixmap. Display state that is
    per-image rather than per-window (zoom, scale, colormap) belongs here too
    as those features arrive, so tiled frames can be zoomed and scaled
    independently of each other.
    """

    _ids = itertools.count(1)

    def __init__(self, data, header, file_name=""):
        self.number = next(Frame._ids)
        self.data = data
        self.header = header
        self.file_name = file_name
        self.pixmap = None
        self.scale = "linear"
        self.zoom = ZOOM_FIT
        self.center = None

    def set_zoom(self, factor):
        """
        Zooms to a factor relative to the fit.

        Returns:
            bool: True when the frame's view actually changed, so a caller
            can avoid repainting for a zoom that was already at the limit.
        """
        factor = clamp_zoom(factor)
        if factor == self.zoom:
            return False
        self.zoom = factor
        return True

    @property
    def label(self):
        """Short caption for this frame."""
        if self.file_name:
            return os.path.basename(self.file_name)
        return f"Frame {self.number}"

    @property
    def shape(self):
        """Shape of the frame's data, or None when it holds no image."""
        return None if self.data is None else self.data.shape

    def __repr__(self):
        return f"<Frame {self.number} {self.label} {self.shape}>"
