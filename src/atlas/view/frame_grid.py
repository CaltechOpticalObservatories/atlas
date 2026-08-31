# Standard Library Imports
import math

# Third-Party Library Imports
from PyQt5.QtWidgets import QWidget, QGridLayout, QLabel
from PyQt5.QtCore import Qt

from .frame_widget import FrameWidget


class FrameGrid(QWidget):
    """
    Lays out whichever frames the display mode makes visible.

    Frame widgets are pooled and rebound rather than recreated on every change,
    so switching frames does not flicker or lose scroll state.
    """

    def __init__(self, view_model, parent=None):
        super().__init__(parent)
        self.view_model = view_model
        self.widgets = []

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
            self.widgets.append(widget)
        return self.widgets[index]

    def select(self, position):
        """Makes the frame at a grid position current."""
        visible = self.view_model.visible_frames()
        if position < len(visible):
            frame = visible[position]
            if frame in self.view_model.frames:
                self.view_model.set_current_index(self.view_model.frames.index(frame))

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
