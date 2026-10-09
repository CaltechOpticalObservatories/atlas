# Standard Library Imports
import time

# Third-Party Library Imports
from PyQt5.QtWidgets import QDockWidget, QGridLayout, QLabel, QSizePolicy, QWidget
from PyQt5.QtCore import Qt, QTimer

from atlas.model.statistics import compute_statistics, format_centroid, format_count
from .registry import Tool, register

# Panel rows, in the order they are shown: title -> FrameStatistics attribute.
ROWS = (
    ("Mean", "mean"),
    ("Median", "median"),
    ("Std dev", "deviation"),
    ("Variance", "variance"),
    ("Min", "minimum"),
    ("Max", "maximum"),
)
# Rows formatted specially, after the counts: title -> key into the columns.
EXTRA_ROWS = (
    ("Centroid", "centroid"),
    ("Pixels", "pixels"),
    ("Blank", "blank"),
)
REGION_HINT = "Shift+drag on the image to define a region."
# Every figure cell is at least this wide, so the panel does not resize, and
# shove the image beside it, each time a figure gains a digit. It holds a
# centroid on any frame under 10k pixels across, or a 16-bit detector's
# largest possible variance; only a figure wider still grows the panel.
WIDEST_FIGURE = "(0000.00, 0000.00)"


@register("statistics")
class StatisticsTool(Tool):
    """
    A dock panel summarising the current frame's pixel values, beside those of
    its region of interest when it has one.

    The statistics come from the raw data, so they are unaffected by the
    frame's display scale. Recomputing them is not free: the median alone costs
    an order of magnitude more than the rest, so a live stream updates them at
    settings.update_hz rather than on every displayed frame.
    """

    def __init__(self, window, settings):
        super().__init__(window, settings)
        self.dock = None
        self.caption = None
        self.values = {}         # the frame column: key -> QLabel
        self.region_values = {}  # the region column, keyed the same way
        self.region_caption = None
        self.timer = None
        self.frame = None
        self.last_computed = 0.0
        self.pending = False

    def build(self):
        panel = QWidget()
        layout = QGridLayout(panel)
        layout.setAlignment(Qt.AlignTop)
        # Centroids fill their cells, and would otherwise run into each other.
        layout.setHorizontalSpacing(12)

        # Neither caption may size the panel: a long file name is clipped,
        # with the whole of it in the tooltip, rather than widening the dock.
        self.caption = self.caption_label("No frame selected.")
        font = self.caption.font()
        font.setBold(True)
        self.caption.setFont(font)
        layout.addWidget(self.caption, 0, 0, 1, 3)

        for column, heading in ((1, "Frame"), (2, "Region")):
            label = QLabel(heading)
            label.setFont(font)
            layout.addWidget(label, 1, column, Qt.AlignRight)

        for row, (title, key) in enumerate(ROWS + EXTRA_ROWS, start=2):
            layout.addWidget(QLabel(f"{title}:"), row, 0, Qt.AlignRight)
            for column, values in ((1, self.values), (2, self.region_values)):
                value = QLabel("—")
                value.setFont(self.monospace_font(value))
                value.setMinimumWidth(
                    value.fontMetrics().horizontalAdvance(WIDEST_FIGURE))
                # Right-aligned, so units line up with units as figures change.
                value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                # The whole point of the panel is numbers worth copying elsewhere.
                value.setTextInteractionFlags(Qt.TextSelectableByMouse)
                layout.addWidget(value, row, column)
                values[key] = value

        # The last row, so this one may wrap: there is nothing below to push.
        self.region_caption = self.caption_label(REGION_HINT)
        self.region_caption.setWordWrap(True)
        layout.addWidget(self.region_caption, len(ROWS + EXTRA_ROWS) + 2, 0, 1, 3)

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
        self.view_model.region_changed.connect(self.on_region_changed)
        self.dock.visibilityChanged.connect(self.on_visibility)
        self.recompute()

    @staticmethod
    def caption_label(text):
        """A label that takes whatever width the panel has, never setting it."""
        label = QLabel(text)
        label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        return label

    @staticmethod
    def set_caption(label, text):
        """Captions a label, with the whole text in its tooltip in case it is clipped."""
        label.setText(text)
        label.setToolTip(text)

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

    def on_region_changed(self):
        """
        Summarises a newly drawn region at once.

        Only the region column is recomputed: the frame's figures, and the
        median that dominates their cost, have not changed.
        """
        if self.dock is None or not self.dock.isVisible():
            self.pending = True
            return
        self.show_region(self.view_model.current_frame)

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
        self.show_region(frame)
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

        self.set_caption(self.caption, frame.label)
        self.fill_column(self.values, statistics)

    def show_region(self, frame):
        """Recomputes and shows the statistics of a frame's region."""
        region = None if frame is None else frame.region
        if region is None:
            self.clear_column(self.region_values)
            self.set_caption(self.region_caption, REGION_HINT)
            return

        plane = self.view_model.select_display_plane(frame.data)
        clipped = None if plane is None else region.clip(plane.shape)
        if clipped is None:
            # A live stream can shrink the frame out from under its region.
            self.clear_column(self.region_values)
            self.set_caption(self.region_caption,
                             f"Region data{region.text} is off the frame.")
            return

        self.set_caption(self.region_caption,
                         f"Region: data{clipped.text}, {clipped.width} × {clipped.height}")
        # An all-blank region still says so: its figures dash, its count does not.
        self.fill_column(self.region_values,
                         compute_statistics(clipped.cut(plane), (clipped.x0, clipped.y0)))

    @staticmethod
    def fill_column(values, statistics):
        """Fills one column of the panel with a summary."""
        for _, attribute in ROWS:
            values[attribute].setText(format_count(getattr(statistics, attribute)))
        values["centroid"].setText(format_centroid(statistics))

        values["pixels"].setText(f"{statistics.pixels:,}")
        values["blank"].setText(f"{statistics.blank:,}")

    @staticmethod
    def clear_column(values):
        """Blanks one column of the panel."""
        for value in values.values():
            value.setText("—")

    def clear(self, message):
        """Blanks the frame's figures, explaining why in the caption."""
        self.set_caption(self.caption, message)
        self.clear_column(self.values)
