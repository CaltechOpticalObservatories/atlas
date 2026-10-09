# Third-Party Library Imports
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QSizePolicy
from PyQt5.QtCore import Qt, pyqtSignal, QEvent, QRect, QSize
from PyQt5.QtGui import QColor, QPainter, QPen, QPixmap

from atlas.model.pixel import locate_pixel
from atlas.model.region import Region, region_on_screen
from atlas.model.zoom import WHEEL_STEP, anchored_center, visible_region

# DS9's default region colour: it stays visible on any grey level.
REGION_COLOUR = QColor("#00ff00")


class FrameWidget(QWidget):
    """
    Shows one frame: a caption above an aspect-preserving image.

    The image is always redrawn from the frame's original pixmap rather than
    from the previously scaled one, so repeated resizing does not compound
    quality loss, and zooming in never enlarges an already-shrunken copy.
    """

    clicked = pyqtSignal()
    # (frame, column, row) for the pixel under the cursor, or None when the
    # cursor is on this tile but not on a pixel of it.
    hovered = pyqtSignal(object)
    # A Region the user has just finished drawing, or None for a shift-click
    # that drew nothing, which clears the frame's region.
    region_drawn = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.frame = None
        self.is_current = False
        self.region = None
        self.drag = None  # where a pan was last seen
        self.scaled = None  # the drawn crop, before the region goes on it
        self.anchor = None  # the pixel a region drag began on
        self.sketch = None  # the Region being dragged out, not yet committed
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
        self.image.installEventFilter(self)

        layout.addWidget(self.caption)
        layout.addWidget(self.image)
        self.apply_border()

    def set_frame(self, frame):
        """Binds this widget to a frame, or clears it when given None."""
        self.frame = frame
        if frame is None:
            self.caption.setText("")
            self.image.setPixmap(QPixmap())
            self.region = None
            self.scaled = None
            self.anchor = self.sketch = None
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
        """
        Draws whatever the frame's zoom and pan currently select.
        """
        self.region = None
        self.scaled = None
        if self.frame is None or self.frame.pixmap is None:
            return

        source = self.frame.pixmap
        region = visible_region((self.image.width(), self.image.height()),
                                (source.width(), source.height()),
                                self.frame.zoom, self.frame.center)
        if region is None:
            return

        x, y, width, height, scale = region
        self.region = region
        self.frame.center = (x + width / 2, y + height / 2)

        # Nearest neighbour as soon as a data pixel covers more than a screen pixel
        mode = Qt.FastTransformation if scale >= 1 else Qt.SmoothTransformation
        self.scaled = source.copy(QRect(x, y, width, height)).scaled(
            QSize(round(width * scale), round(height * scale)),
            Qt.KeepAspectRatio, mode)
        self.draw_overlay()

    def draw_overlay(self):
        """
        Puts the frame's region, or the one being dragged out, on the image.

        Drawn onto a copy of the scaled crop rather than into it, so a region
        moving under the mouse costs a copy per move rather than a rescale.
        """
        if self.scaled is None:
            return

        box = self.sketch or self.frame.region
        if box is None:
            self.image.setPixmap(self.scaled)
            return

        # self.region is the part of the frame on screen, not the box
        pixmap = self.scaled.copy()
        left, top, width, height = region_on_screen(
            box, self.region[:4], (pixmap.width(), pixmap.height()))
        painter = QPainter(pixmap)
        # Dashed until the drag ends, so a box still being drawn reads as such.
        pen = QPen(REGION_COLOUR, 0, Qt.DashLine if self.sketch else Qt.SolidLine)
        painter.setPen(pen)
        painter.drawRect(QRect(left, top, width, height).adjusted(0, 0, -1, -1))
        painter.end()
        self.image.setPixmap(pixmap)

    def display_scale(self):
        """Screen pixels per data pixel as drawn, or 0 when nothing is drawn."""
        return 0.0 if self.region is None else self.region[4]

    def zoom_by(self, ratio, anchor=None):
        """Zooms this tile by a ratio, holding a data pixel still if given one."""
        if self.frame is None:
            return

        before = self.frame.zoom
        if not self.frame.set_zoom(before * ratio):
            return  # already as far in or out as the viewer will go

        if anchor is not None and self.frame.center is not None:
            self.frame.center = anchored_center(anchor, self.frame.center,
                                                self.frame.zoom / before)
        self.rescale()

    def pan_by(self, dx, dy):
        """
        Moves the view by a distance in screen pixels, dragging the image with it.

        Returns:
            bool: True when the view moved, which it does not when the whole
            frame is already on screen and there is nowhere to go.
        """
        scale = self.display_scale()
        if scale <= 0 or self.frame.center is None:
            return False
        _, _, width, height, _ = self.region
        if (width, height) == (self.frame.pixmap.width(), self.frame.pixmap.height()):
            return False

        self.frame.center = (self.frame.center[0] - dx / scale,
                             self.frame.center[1] - dy / scale)
        self.rescale()
        return True

    def resizeEvent(self, event):  # pylint: disable=invalid-name
        """Qt override: keep the image fitted as the widget changes size."""
        super().resizeEvent(event)
        self.rescale()

    def pixel_at(self, position, clamp=False):
        """
        The data index under a point in this widget's coordinates.

        Args:
            position (QPoint): the point, in this widget's coordinates.
            clamp (bool): report the nearest pixel on the image for a point
                beside it, rather than None.

        Returns:
            tuple: (column, row), 0-based, or None when the point is not on
            the image.
        """
        if self.frame is None or self.region is None:
            return None

        displayed = self.image.pixmap()
        if displayed is None or displayed.isNull():
            return None

        # The pixmap was rendered from the display plane
        x, y, width, height, _ = self.region
        point = self.image.mapFrom(self, position)
        return locate_pixel((point.x(), point.y()),
                            (self.image.width(), self.image.height()),
                            (displayed.width(), displayed.height()),
                            (width, height), (x, y), clamp=clamp)

    def mousePressEvent(self, event):  # pylint: disable=invalid-name
        """
        Qt override: clicking a frame makes it current, and begins a pan, or
        with Shift held, a region.
        """
        super().mousePressEvent(event)
        self.drag = self.anchor = self.sketch = None
        if event.button() == Qt.LeftButton:
            if event.modifiers() & Qt.ShiftModifier:
                # A region has to start on a pixel; it may then run off the edge.
                self.anchor = self.pixel_at(event.pos())
            else:
                self.drag = event.pos()
        self.clicked.emit()

    def mouseReleaseEvent(self, event):  # pylint: disable=invalid-name
        """Qt override: a pan or region drag lasts as long as the button is held."""
        super().mouseReleaseEvent(event)
        self.drag = None
        if self.anchor is None:
            return

        # A shift-click that never left its pixel drew nothing, and clears.
        region = self.sketch
        if region is not None and region.width == region.height == 1:
            region = None
        self.anchor = self.sketch = None
        self.draw_overlay()
        self.region_drawn.emit(region)

    def mouseMoveEvent(self, event):  # pylint: disable=invalid-name
        """
        Qt override: drag to pan or draw, and report the pixel under the cursor.

        The child labels ignore mouse moves, so Qt propagates them here with
        the position already translated into this widget's coordinates. That is
        also how clicks on the image reach mousePressEvent above.
        """
        super().mouseMoveEvent(event)
        if self.drag is not None and event.buttons() & Qt.LeftButton:
            delta = event.pos() - self.drag
            if self.pan_by(delta.x(), delta.y()):
                self.drag = event.pos()
        elif self.anchor is not None and event.buttons() & Qt.LeftButton:
            corner = self.pixel_at(event.pos(), clamp=True)
            if corner is not None:
                self.sketch = Region.from_corners(self.anchor, corner)
                self.draw_overlay()

        index = self.pixel_at(event.pos())
        self.hovered.emit(None if index is None else (self.frame, *index))

    def eventFilter(self, source, event):  # pylint: disable=invalid-name
        """
        Qt override: a wheel turned over the image zooms about the cursor.
        """
        notches = 0 if event.type() != QEvent.Wheel else event.angleDelta().y() / 120.0
        if source is self.image and notches and self.frame is not None:
            position = self.image.mapTo(self, event.pos())
            self.zoom_by(WHEEL_STEP ** notches, self.pixel_at(position))
            event.accept()
            return True
        return super().eventFilter(source, event)

    def leaveEvent(self, event):  # pylint: disable=invalid-name
        """Qt override: the cursor is off this tile, so it is on no pixel."""
        super().leaveEvent(event)
        self.drag = None
        self.hovered.emit(None)
