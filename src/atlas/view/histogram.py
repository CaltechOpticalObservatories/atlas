# Third-Party Library Imports
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QSlider, QLabel,
                             QPushButton, QCheckBox)
from PyQt5.QtCore import Qt

# Counts of 0 have no place on a log axis, and a bar chart drawn from a zero
# baseline has none either. The axis therefore starts just below a count of 1,
# the smallest count a bin can actually hold.
LOG_COUNT_FLOOR = 0.5


class Histogram(QDialog):
    """
    Histograms of pixel intensities, one frame at a time.

    Takes raw image arrays rather than pixmaps: a pixmap is 8-bit and device
    dependent, so its histogram would describe the rendering rather than the
    data.
    """

    def __init__(self, entries, parent=None):
        """
        Args:
            entries (list): (label, numpy array) pairs, one per frame.
            parent (QWidget): Parent window.
        """
        super().__init__(parent)
        self.entries = entries
        self.current_index = 0

        self.setWindowTitle("Pixel Histogram")
        self.resize(720, 540)

        layout = QVBoxLayout()
        self.setLayout(layout)

        self.figure, self.axis = plt.subplots(figsize=(8, 6))
        self.canvas = FigureCanvas(self.figure)
        layout.addWidget(self.canvas)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(1)
        self.slider.setMaximum(512)
        self.slider.setValue(128)
        self.slider.setTickPosition(QSlider.TicksBelow)
        self.slider.setTickInterval(32)
        self.slider.valueChanged.connect(self.update_histogram)
        layout.addWidget(self.slider)

        self.bin_label = QLabel()
        layout.addWidget(self.bin_label)

        # Pixel histograms are usually dominated by one sky/bias peak, so the
        # faint tail is invisible on a linear count axis.
        self.log_counts = QCheckBox("Log count axis")
        self.log_counts.toggled.connect(self.update_histogram)
        layout.addWidget(self.log_counts)

        navigation = QHBoxLayout()
        self.previous_button = QPushButton("Previous")
        self.next_button = QPushButton("Next")
        self.previous_button.clicked.connect(self.show_previous)
        self.next_button.clicked.connect(self.show_next)
        navigation.addWidget(self.previous_button)
        navigation.addWidget(self.next_button)
        layout.addLayout(navigation)

        self.update_histogram()

    def closeEvent(self, event):  # pylint: disable=invalid-name
        """Qt override: release the figure so repeated openings do not leak."""
        plt.close(self.figure)
        super().closeEvent(event)

    def update_histogram(self, *_):
        """Redraws the histogram for the current frame, bin count and axis scale."""
        # clear() resets the axis scale to linear along with everything else
        self.axis.clear()

        label, data = self.entries[self.current_index]
        values = np.asarray(data).ravel()

        # Blank pixels are stored as NaN in floating-point FITS data and would
        # otherwise propagate into the range.
        values = values[np.isfinite(values)]
        if values.size == 0:
            self.axis.set_title(f"{label}: no finite pixels")
            self.canvas.draw()
            return

        bin_count = self.slider.value()
        low, high = float(values.min()), float(values.max())
        if high <= low:
            # np.histogram rejects a zero-width range.
            high = low + 1.0

        counts, edges = np.histogram(values, bins=bin_count, range=(low, high))

        log_counts = self.log_counts.isChecked()
        if log_counts:
            # Heights are measured from the floor rather than from 0, so a bar
            # still reaches exactly its own count.
            bottom = LOG_COUNT_FLOOR
            heights = np.maximum(counts, LOG_COUNT_FLOOR) - LOG_COUNT_FLOOR
        else:
            bottom, heights = 0, counts

        self.axis.bar(edges[:-1], heights, width=np.diff(edges),
                      align="edge", color="#4a90d9", bottom=bottom)
        self.axis.set_title(f"{label}  ({self.current_index + 1} of {len(self.entries)})")
        self.axis.set_xlabel("Pixel value")
        self.axis.set_ylabel("Count (log)" if log_counts else "Count")
        if log_counts:
            self.axis.set_yscale("log")
            self.axis.set_ylim(bottom=LOG_COUNT_FLOOR,
                               top=max(float(counts.max()), 1.0) * 1.5)
        self.axis.grid(True, alpha=0.3)

        self.bin_label.setText(
            f"Bins: {bin_count}    range: {low:g} to {high:g}    pixels: {values.size:,}")

        self.previous_button.setEnabled(self.current_index > 0)
        self.next_button.setEnabled(self.current_index < len(self.entries) - 1)
        self.canvas.draw()

    def show_previous(self):
        """Shows the previous frame's histogram."""
        if self.current_index > 0:
            self.current_index -= 1
            self.update_histogram()

    def show_next(self):
        """Shows the next frame's histogram."""
        if self.current_index < len(self.entries) - 1:
            self.current_index += 1
            self.update_histogram()
