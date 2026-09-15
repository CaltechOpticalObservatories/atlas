# Standard Library Imports
from dataclasses import dataclass

# Third-Party Library Imports
import numpy as np


@dataclass(frozen=True)
class FrameStatistics:
    """
    Summary of one frame's pixel values, in detector counts.

    Computed from the raw array rather than the rendered pixmap, so the numbers
    describe the data and do not move when the display scale changes.
    """
    pixels: int      # finite pixels the statistics describe
    blank: int       # non-finite pixels excluded from them
    minimum: float
    maximum: float
    mean: float
    median: float
    deviation: float

    @property
    def is_empty(self):
        """True when the frame held no finite pixel to summarise."""
        return self.pixels == 0


def compute_statistics(data):
    """
    Summarises a frame's pixel values.

    Args:
        data (numpy.ndarray): Raw frame data, of any shape.

    Returns:
        FrameStatistics: the summary. Every statistic is NaN when the frame
        carries no finite pixel at all.
    """
    values = np.asarray(data).ravel()

    # One cast up front, reused by every statistic. Computing these straight
    # off integer data makes numpy promote separately in each call, which
    # dominates the cost on a large frame. float32 also byte-swaps the
    # big-endian arrays FITS specifies into native order.
    values = values.astype(np.float32, copy=False)

    total = int(values.size)

    # Blank pixels are NaN/inf in floating-point FITS data, and a single one
    # would otherwise make every statistic NaN.
    finite = np.isfinite(values)
    if not finite.all():
        values = values[finite]

    if values.size == 0:
        nan = float("nan")
        return FrameStatistics(pixels=0, blank=total, minimum=nan, maximum=nan,
                               mean=nan, median=nan, deviation=nan)

    return FrameStatistics(
        pixels=int(values.size),
        blank=total - int(values.size),
        minimum=float(values.min()),
        maximum=float(values.max()),
        mean=float(values.mean()),
        # The dominant cost by an order of magnitude on a large frame: median
        # partitions a copy, where the others are single passes.
        median=float(np.median(values)),
        deviation=float(values.std()),
    )
