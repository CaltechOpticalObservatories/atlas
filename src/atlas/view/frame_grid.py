# Standard Library Imports
import math

# Third-Party Library Imports
from PyQt5.QtWidgets import QWidget, QGridLayout, QLabel
from PyQt5.QtCore import Qt, pyqtSignal

from atlas.model.pixel import PixelReadout, read_pixel
from .frame_widget import FrameWidget


class FrameGrid(QWidget):
    """
    Lays out whichever frames the display mode makes visible.

    Frame widgets are pooled and rebound rather than recreated on every change,
    so switching frames does not flicker or lose scroll state.
    """

    # A PixelReadout for the pixel under the cursor, or None when there is
    # none. Emitted for whichever tile is hovered, not just the current frame.
    pixel_hovered = pyqtSignal(object)

    def __init__(self, view_model, parent=None):
        super().__init__(parent)
        self.view_model = view_model
        self.widgets = []
        self.hover = None  # last (frame, column, row) a tile reported

        self.grid = QGridLayout()
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.grid)

        self.placeholder = QLabel("No image loaded.\n\nFile → Open Image…")
        self.placeholder.setAlignment(Qt.AlignCenter)
        self.placeholder.setStyleSheet("color: #888;")
        self.grid.addWidget(self.placeholder, 0, 0)

        self.view_model.frames_changed.connect(self.refresh)
        self.view_model.current_changed.connect(self.refresh)
        self.view_model.display_mode_changed.connect(self.refresh)
        # Re-read rather than clear: under a live stream the cursor is usually
        # still, and watching one pixel's counts change is the point of resting
        # it there. A frame that has gone away is dropped by report_pixel.
        self.view_model.frames_changed.connect(self.report_pixel)
        self.view_model.current_changed.connect(self.report_pixel)

    def column_count(self, frame_count):
        """
        Chooses the number of tile columns.

        Falls back to a roughly square grid when the configuration does not
        pin a column count.
        """
        configured = self.view_model.config.display.tile_columns
        if configured:
            return max(1, min(configured, frame_count))
        return max(1, math.ceil(math.sqrt(frame_count)))

    def widget_for(self, index):
        """Returns the pooled frame widget at `index`, creating it if needed."""
        while len(self.widgets) <= index:
            widget = FrameWidget(self)
            position = len(self.widgets)
            widget.clicked.connect(lambda pos=position: self.select(pos))
            widget.hovered.connect(self.on_hover)
            self.widgets.append(widget)
        return self.widgets[index]

    def select(self, position):
        """Makes the frame at a grid position current."""
        visible = self.view_model.visible_frames()
        if position < len(visible):
            frame = visible[position]
            if frame in self.view_model.frames:
                self.view_model.set_current_index(self.view_model.frames.index(frame))

    def on_hover(self, position):
        """Records the pixel a tile reports under the cursor, and reports it on."""
        self.hover = position
        self.report_pixel()

    def report_pixel(self, *_):
        """
        Emits the value of the hovered pixel, reading it afresh each time.

        The index is kept rather than the value, so this is also what a frame
        arriving under a stationary cursor goes through.
        """
        readout = self.current_readout()
        if readout is None:
            self.hover = None
        self.pixel_hovered.emit(readout)

    def current_readout(self):
        """The hovered pixel as a PixelReadout, or None if there is no longer one."""
        if self.hover is None:
            return None

        frame, column, row = self.hover
        # Tiling can be switched off under the cursor, leaving a hovered frame
        # that is no longer on screen; deleting it leaves one that is gone.
        if frame not in self.view_model.visible_frames():
            return None

        plane = self.view_model.select_display_plane(frame.data)
        if plane is None:
            return None

        value = read_pixel(plane, column, row)
        if value is None:
            return None
        return PixelReadout(frame.label, column, row, value)

    def refresh(self):
        """Rebuilds the grid for the frames that should currently be visible."""
        visible = self.view_model.visible_frames()

        self.placeholder.setVisible(not visible)
        if not visible:
            for widget in self.widgets:
                widget.setParent(None)
                widget.hide()
            self.widgets.clear()
            return

        columns = self.column_count(len(visible))
        current = self.view_model.current_frame

        for position, frame in enumerate(visible):
            widget = self.widget_for(position)
            widget.set_frame(frame)
            widget.set_current(frame is current and len(visible) > 1)
            if self.grid.indexOf(widget) == -1:
                self.grid.addWidget(widget, position // columns, position % columns)
            else:
                self.grid.removeWidget(widget)
                self.grid.addWidget(widget, position // columns, position % columns)
            widget.show()

        # Retire any pooled widgets beyond the current frame count.
        for widget in self.widgets[len(visible):]:
            self.grid.removeWidget(widget)
            widget.setParent(None)
            widget.hide()
        del self.widgets[len(visible):]

        # Even column and row weights so tiles share the space equally.
        for column in range(self.grid.columnCount()):
            self.grid.setColumnStretch(column, 1 if column < columns else 0)
        rows = math.ceil(len(visible) / columns)
        for row in range(self.grid.rowCount()):
            self.grid.setRowStretch(row, 1 if row < rows else 0)
