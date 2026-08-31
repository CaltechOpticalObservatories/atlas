# Third-Party Library Imports
from PyQt5.QtWidgets import QAction
import numpy as np

from atlas.model.frame import Frame
from .registry import Tool, register


def extract_tap_halves(data, take_first_half, tap_width, num_taps):
    """
    Gathers one half of every tap from a tapped detector frame.

    Args:
        data (numpy.ndarray): The 2D frame to segment.
        take_first_half (bool): True for the signal half, False for the reset half.
        tap_width (int): Width of each tap segment.
        num_taps (int): Number of tap segments.

    Returns:
        numpy.ndarray: The gathered half-taps.

    Raises:
        ValueError: If the frame does not match the expected geometry.
    """
    if data.ndim != 2:
        raise ValueError(f"expected a 2D frame, got shape {data.shape}")

    height, width = data.shape
    half = tap_width // 2
    expected = tap_width * (num_taps + 1)

    if width != expected:
        raise ValueError(
            f"frame is {width} px wide but {num_taps} taps of {tap_width} px "
            f"needs {expected}")

    gathered = np.zeros((height, half * num_taps), dtype=data.dtype)
    for tap_index in range(num_taps):
        start = tap_index * tap_width
        tap = data[:, start:start + tap_width]
        part = tap[:, :half] if take_first_half else tap[:, half:]
        gathered[:, tap_index * half:(tap_index + 1) * half] = part

    return gathered


def subtract_taps(signal_data, reset_data, tap_width, num_taps):
    """
    Subtracts the signal half-taps of one frame from the reset half-taps of another.

    Returns:
        numpy.ndarray: The signed difference, in int64 so negatives survive.
    """
    signal = extract_tap_halves(signal_data, True, tap_width, num_taps)
    reset = extract_tap_halves(reset_data, False, tap_width, num_taps)

    if signal.shape != reset.shape:
        raise ValueError("signal and reset halves differ in shape")

    # The difference is genuinely signed; an unsigned accumulator would wrap
    # negatives around to full brightness.
    return reset.astype(np.int64) - signal.astype(np.int64)


@register("tap_subtraction")
class TapSubtractionTool(Tool):
    """
    Subtracts signal and reset taps of two frames into a new frame.

    This is specific to COO detector readout, which is why it stays off unless
    a configuration enables it.
    """

    def build(self):
        action = QAction("Subtract Signal/Reset Taps", self.window)
        action.setToolTip("Subtract the current frame's reset taps from the "
                          "previous frame's signal taps")
        action.triggered.connect(self.subtract)
        self.window.tools_menu.addAction(action)

    def subtract(self):
        """Runs the subtraction on the current frame and the one before it."""
        frames = self.view_model.frames
        if len(frames) < 2:
            self.window.show_message(
                "Tap subtraction needs two frames; open a second image first.")
            return

        # Operate on the current frame and its predecessor, so the user picks
        # the pair with Frame -> Next/Previous.
        index = max(self.view_model.current_index, 1)
        signal_frame, reset_frame = frames[index - 1], frames[index]

        try:
            result = subtract_taps(
                self.view_model.select_display_plane(signal_frame.data),
                self.view_model.select_display_plane(reset_frame.data),
                self.settings.tap_width, self.settings.num_taps)
        except ValueError as error:
            self.window.show_message(f"Tap subtraction failed: {error}")
            return

        # The result is just another frame; it needs no special pane.
        frame = Frame(result, reset_frame.header,
                      f"{signal_frame.label} - {reset_frame.label}")
        frame.pixmap = self.view_model.render(result)
        self.view_model.frames.append(frame)
        self.view_model.current_index = len(self.view_model.frames) - 1
        self.view_model.frames_changed.emit()
        self.view_model.current_changed.emit(self.view_model.current_index)

        self.window.show_message(
            f"Tap subtraction: range {result.min()} to {result.max()}")
