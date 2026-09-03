# Standard Library Imports
import os

# Third-Party Library Imports
from astropy.io import fits
from PyQt5.QtCore import pyqtSignal, QObject
from PyQt5.QtGui import QPixmap

from atlas.model.fits_model import FITSModel
from atlas.model.frame import Frame

# FITS files are conventionally named with any of these extensions.
FITS_EXTENSIONS = ('.fits', '.fit', '.fts', '.fits.gz', '.fit.gz', '.fts.gz', '.fz')


class FrameViewModel(QObject):
    """
    Holds every loaded frame and the current display mode.

    There is deliberately no "one image" versus "two images" mode: frames are a
    list, and the display mode decides how many of them are on screen. Loading
    an image always keeps it, whatever is currently being shown.
    """

    frames_changed = pyqtSignal()
    current_changed = pyqtSignal(int)
    display_mode_changed = pyqtSignal(str)
    message = pyqtSignal(str)

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.fits_model = FITSModel()
        self.frames = []
        self.current_index = -1
        self.display_mode = config.display.mode
        self._live_frame = None  # updated in place, see update_live_frame()

    def load_file(self, file_name):
        """
        Loads a FITS file into a new frame.

        Returns:
            Frame: the frame that was created, or None if the file could not
            be displayed.
        """
        try:
            data, header = self.fits_model.load_fits_image(file_name)
        except Exception as error:  # astropy raises a wide variety here
            self.message.emit(f"Could not read {os.path.basename(file_name)}: {error}")
            return None

        if data is None:
            self.message.emit(f"{os.path.basename(file_name)} contains no image data.")
            return None

        frame = Frame(data, header, file_name)
        frame.pixmap = self.render(data)
        if frame.pixmap is None:
            return None

        self.frames.append(frame)
        self.current_index = len(self.frames) - 1
        self.frames_changed.emit()
        self.current_changed.emit(self.current_index)
        return frame

    def update_live_frame(self, data, keywords):
        """Updates the live frame in place instead of appending a new one."""
        pixmap = self.render(data)
        if pixmap is None:
            return

        header = fits.Header(keywords)  # header.py expects frame.header.cards

        if self._live_frame is not None and self._live_frame not in self.frames:
            self._live_frame = None  # user deleted it; treat as never created

        if self._live_frame is None:
            self._live_frame = Frame(data, header)
            self._live_frame.pixmap = pixmap
            self.frames.append(self._live_frame)
            self.current_index = len(self.frames) - 1
            self.frames_changed.emit()
            self.current_changed.emit(self.current_index)
        else:
            self._live_frame.data = data
            self._live_frame.header = header
            self._live_frame.pixmap = pixmap
            self.current_changed.emit(self.current_index)

    def load_files(self, file_names):
        """Loads several files, one frame each. Returns how many succeeded."""
        loaded = 0
        for file_name in file_names:
            if self.load_file(file_name) is not None:
                loaded += 1
        return loaded

    def load_directory(self, directory):
        """Loads every FITS file in a directory, oldest first."""
        if not directory:
            return 0

        paths = [os.path.join(directory, name) for name in os.listdir(directory)
                 if name.lower().endswith(FITS_EXTENSIONS)]
        if not paths:
            self.message.emit(f"No FITS files found in {directory}.")
            return 0

        paths.sort(key=os.path.getmtime)
        return self.load_files(paths)

    def render(self, data):
        """Renders raw FITS data to a display pixmap."""
        plane = self.select_display_plane(data)
        if plane is None:
            return None

        if plane.ndim == 3:
            q_image = self.fits_model.convert_to_qimage(plane)
        else:
            q_image = self.fits_model.convert_to_qimage(self.fits_model.normalize_image(plane))

        return QPixmap.fromImage(q_image)

    def select_display_plane(self, data):
        """
        Reduces FITS data to something displayable: a 2D array, or an
        (h, w, 3|4) uint8 array for colour data.
        """
        if data.ndim == 2:
            return data

        if data.ndim == 3:
            # A FITS cube is stored slowest-axis-first, (nplanes, h, w), not
            # (h, w, nplanes). Channel-last only applies to real colour data.
            if data.shape[-1] in (3, 4) and data.dtype.kind == 'u' and data.itemsize == 1:
                return data
            return data[0]

        self.message.emit(f"Unsupported image shape {data.shape}.")
        return None

    @property
    def current_frame(self):
        """The frame the user is currently on, or None when there are none."""
        if 0 <= self.current_index < len(self.frames):
            return self.frames[self.current_index]
        return None

    def visible_frames(self):
        """
        The frames the current display mode puts on screen: just the current
        one in single mode, all of them when tiling.
        """
        if self.display_mode == "tile":
            return list(self.frames)

        frame = self.current_frame
        return [frame] if frame is not None else []

    def set_current_index(self, index):
        """Selects a frame by position."""
        if not self.frames:
            return
        index = max(0, min(index, len(self.frames) - 1))
        if index != self.current_index:
            self.current_index = index
            self.current_changed.emit(index)

    def next_frame(self):
        """Moves to the next frame, wrapping around."""
        if self.frames:
            self.set_current_index((self.current_index + 1) % len(self.frames))

    def previous_frame(self):
        """Moves to the previous frame, wrapping around."""
        if self.frames:
            self.set_current_index((self.current_index - 1) % len(self.frames))

    def delete_current_frame(self):
        """Removes the current frame."""
        if not self.frames:
            return
        self.frames.pop(self.current_index)
        self.current_index = min(self.current_index, len(self.frames) - 1)
        self.frames_changed.emit()
        self.current_changed.emit(self.current_index)

    def delete_all_frames(self):
        """Removes every frame."""
        if not self.frames:
            return
        self.frames.clear()
        self.current_index = -1
        self.frames_changed.emit()
        self.current_changed.emit(self.current_index)

    def set_display_mode(self, mode):
        """Switches between single-frame and tiled display."""
        if mode == self.display_mode:
            return
        self.display_mode = mode
        self.display_mode_changed.emit(mode)
        self.frames_changed.emit()
