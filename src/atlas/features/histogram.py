# Third-Party Library Imports
from PyQt5.QtWidgets import QAction

from atlas.view.histogram import Histogram
from .registry import Tool, register


@register("histogram")
class HistogramTool(Tool):
    """Opens a histogram window for the frames currently on screen."""

    def __init__(self, window, settings):
        super().__init__(window, settings)
        self.dialog = None

    def build(self):
        action = QAction("Histogram…", self.window)
        action.triggered.connect(self.show_histogram)
        self.window.tools_menu.addAction(action)

    def show_histogram(self):
        """Shows histograms of the visible frames' raw data."""
        frames = self.view_model.visible_frames()
        entries = []
        for frame in frames:
            plane = self.view_model.select_display_plane(frame.data)
            if plane is not None:
                entries.append((frame.label, plane))

        if not entries:
            self.window.show_message("No image loaded to histogram.")
            return

        # Held on the tool: a local would be garbage-collected immediately and
        # the window would never appear.
        self.dialog = Histogram(entries, self.window)
        self.dialog.show()
        self.dialog.raise_()
