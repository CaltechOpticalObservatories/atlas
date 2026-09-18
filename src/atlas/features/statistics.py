# Standard Library Imports
import time

# Third-Party Library Imports
from PyQt5.QtWidgets import QDockWidget, QFormLayout, QLabel, QWidget
from PyQt5.QtCore import Qt, QTimer

from atlas.model.statistics import compute_statistics, format_count
from .registry import Tool, register

# Panel rows, in the order they are shown: title -> FrameStatistics attribute.
ROWS = (
    ("Mean", "mean"),
    ("Median", "median"),
    ("Std dev", "deviation"),
    ("Min", "minimum"),
    ("Max", "maximum"),
)


@register("statistics")
class StatisticsTool(Tool):
    """
    A dock panel summarising the current frame's pixel values.

    The statistics come from the raw data, so they are unaffected by the
    frame's display scale. Recomputing them is not free: the median alone costs
    an order of magnitude more than the rest, so a live stream updates them at
    settings.update_hz rather than on every displayed frame.
    """

    def __init__(self, window, settings):
        super().__init__(window, settings)
        self.dock = None
        self.caption = None
        self.values = {}
        self.pixel_label = None
        self.timer = None
        self.frame = None
        self.last_computed = 0.0
        self.pending = False

    def build(self):
        panel = QWidget()
        layout = QFormLayout(panel)
        layout.setLabelAlignment(Qt.AlignRight)

        self.caption = QLabel("No frame selected.")
        font = self.caption.font()
        font.setBold(True)
        self.caption.setFont(font)
        layout.addRow(self.caption)

        for title, attribute in ROWS:
            value = QLabel("—")
            value.setFont(self.monospace_font(value))
            # The whole point of the panel is numbers worth copying elsewhere.
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            layout.addRow(f"{title}:", value)
            self.values[attribute] = value

        self.pixel_label = QLabel("—")
        self.pixel_label.setFont(self.monospace_font(self.pixel_label))
        layout.addRow("Pixels:", self.pixel_label)

        self.dock = QDockWidget("Statistics", self.window)
        self.dock.setWidget(panel)
        self.dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.window.addDockWidget(Qt.RightDockWidgetArea, self.dock)

        self.window.view_menu.addSeparator()
        self.window.view_menu.addAction(self.dock.toggleViewAction())

        # Trailing-edge throttle: a burst of live frames still ends with the
        # newest one's numbers on screen, just later rather than every frame.
        self.timer = QTimer(self.window)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.recompute)

        self.view_model.current_changed.connect(self.request_refresh)
        self.view_model.frames_changed.connect(self.request_refresh)
        self.dock.visibilityChanged.connect(self.on_visibility)
        self.recompute()

    @staticmethod
    def monospace_font(widget):
        """A fixed-width font, so the figures line up column-wise."""
        font = widget.font()
        font.setFamily("Menlo")
        font.setStyleHint(font.Monospace)
        return font

    def shutdown(self):
        """Stops the pending recompute so the process is not held open."""
        if self.timer is not None:
            self.timer.stop()

    def on_visibility(self, visible):
        """Catches up on anything missed while the panel was hidden."""
        if visible and self.pending:
            self.recompute()

    def request_refresh(self, *_):
        """
        Asks for a refresh, subject to the throttle.

        Switching frames by hand recomputes at once, because a stale panel
        beside a newly selected frame reads as a bug. Only repeated updates to
        the same frame, which is what a live stream produces, are rate limited.
        """
        if self.dock is None or not self.dock.isVisible():
            self.pending = True
            return

        frame = self.view_model.current_frame
        if frame is not self.frame:
            self.recompute()
            return

        interval = 1.0 / self.settings.update_hz
        remaining = interval - (time.monotonic() - self.last_computed)
        if remaining <= 0:
            self.recompute()
        elif not self.timer.isActive():
            self.timer.start(int(remaining * 1000))

    def recompute(self):
        """Recomputes and shows the current frame's statistics."""
        self.timer.stop()
        self.last_computed = time.monotonic()
        self.pending = False

        frame = self.view_model.current_frame
        self.frame = frame
        if frame is None:
            self.clear("No frame selected.")
            return

        plane = self.view_model.select_display_plane(frame.data)
        if plane is None:
            self.clear(f"{frame.label}: nothing to summarise")
            return

        statistics = compute_statistics(plane)
        if statistics.is_empty:
            self.clear(f"{frame.label}: no finite pixels")
            return

        self.caption.setText(frame.label)
        for _, attribute in ROWS:
            self.values[attribute].setText(
                format_count(getattr(statistics, attribute)))

        pixels = f"{statistics.pixels:,}"
        if statistics.blank:
            pixels += f"  ({statistics.blank:,} blank)"
        self.pixel_label.setText(pixels)

    def clear(self, message):
        """Blanks the figures, explaining why in the caption."""
        self.caption.setText(message)
        for value in self.values.values():
            value.setText("—")
        self.pixel_label.setText("—")
