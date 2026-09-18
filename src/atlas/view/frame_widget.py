# Third-Party Library Imports
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QSizePolicy
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap

from atlas.model.pixel import locate_pixel


class FrameWidget(QWidget):
    """
    Shows one frame: a caption above an aspect-preserving image.

    The image is always rescaled from the frame's original pixmap rather than
    from the previously scaled one, so repeated resizing does not compound
    quality loss.
    """

    clicked = pyqtSignal()
    # (frame, column, row) for the pixel under the cursor, or None when the
    # cursor is on this tile but not on a pixel of it.
    hovered = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.frame = None
        self.is_current = False
        # Without tracking, Qt only delivers moves while a button is held, and
        # a readout that needs a drag to update is not a hover readout.
        self.setMouseTracking(True)

        layout = QVBoxLayout()
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        self.setLayout(layout)

        self.caption = QLabel()
        self.caption.setMouseTracking(True)
        self.caption.setAlignment(Qt.AlignCenter)
        self.caption.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        font = self.caption.font()
        font.setBold(True)
        self.caption.setFont(font)

        self.image = QLabel()
        self.image.setAlignment(Qt.AlignCenter)
        self.image.setMinimumSize(1, 1)
        # Ignored, not Expanding: a QLabel reports its pixmap size as its
        # sizeHint, so a large image would otherwise drive the layout and let
        # one frame squeeze its neighbours out of the grid.
        self.image.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.image.setMouseTracking(True)

        layout.addWidget(self.caption)
        layout.addWidget(self.image)
        self.apply_border()

    def set_frame(self, frame):
        """Binds this widget to a frame, or clears it when given None."""
        self.frame = frame
        if frame is None:
            self.caption.setText("")
            self.image.setPixmap(QPixmap())
            return

        self.caption.setText(frame.label)
        self.rescale()

    def set_current(self, is_current):
        """Marks this frame as the current one."""
        if is_current != self.is_current:
            self.is_current = is_current
            self.apply_border()

    def apply_border(self):
        """Draws a highlight around the current frame."""
        colour = "#4a90d9" if self.is_current else "transparent"
        self.setStyleSheet(f"QWidget {{ border: 2px solid {colour}; }}"
                           "QLabel { border: none; }")

    def rescale(self):
        """Fits the frame's pixmap to the space currently available."""
        if self.frame is None or self.frame.pixmap is None:
            return

        target = self.image.size()
        if target.width() <= 0 or target.height() <= 0:
            return

        self.image.setPixmap(self.frame.pixmap.scaled(
            target, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def resizeEvent(self, event):  # pylint: disable=invalid-name
        """Qt override: keep the image fitted as the widget changes size."""
        super().resizeEvent(event)
        self.rescale()

    def pixel_at(self, position):
        """
        The data index under a point in this widget's coordinates.

        Returns:
            tuple: (column, row), 0-based, or None when the point is not on
            the image.
        """
        if self.frame is None or self.frame.pixmap is None:
            return None

        displayed = self.image.pixmap()
        if displayed is None or displayed.isNull():
            return None

        # The unscaled pixmap was rendered from the display plane, so its size
        # is the shape of the data the index has to land in.
        point = self.image.mapFrom(self, position)
        return locate_pixel((point.x(), point.y()),
                            (self.image.width(), self.image.height()),
                            (displayed.width(), displayed.height()),
                            (self.frame.pixmap.width(), self.frame.pixmap.height()))

    def mousePressEvent(self, event):  # pylint: disable=invalid-name
        """Qt override: clicking a frame makes it current."""
        super().mousePressEvent(event)
        self.clicked.emit()

    def mouseMoveEvent(self, event):  # pylint: disable=invalid-name
        """
        Qt override: report the pixel under the cursor as it moves.

        The child labels ignore mouse moves, so Qt propagates them here with
        the position already translated into this widget's coordinates. That is
        also how clicks on the image reach mousePressEvent above.
        """
        super().mouseMoveEvent(event)
        index = self.pixel_at(event.pos())
        self.hovered.emit(None if index is None else (self.frame, *index))

    def leaveEvent(self, event):  # pylint: disable=invalid-name
        """Qt override: the cursor is off this tile, so it is on no pixel."""
        super().leaveEvent(event)
        self.hovered.emit(None)
