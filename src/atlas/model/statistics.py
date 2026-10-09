# Standard Library Imports
import math
from dataclasses import dataclass

# Third-Party Library Imports
import numpy as np


@dataclass(frozen=True)
class FrameStatistics:  # pylint: disable=too-many-instance-attributes
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
    variance: float
    # Flux-weighted centroid, in the same 0-based (column, row) indices as the
    # hover readout. NaN when nothing rises above the median.
    centroid_x: float = float("nan")
    centroid_y: float = float("nan")

    @property
    def is_empty(self):
        """True when the frame held no finite pixel to summarise."""
        return self.pixels == 0


def flux_centroid(plane, background):
    """
    The flux-weighted centroid of a 2D plane.

    Each pixel is weighted by its counts above `background`, and pixels below
    it count for nothing. Weighting by raw counts instead would let the bias
    and sky in every pixel of the box drag the centroid towards the box's
    middle, which on a detector with a bias of thousands of counts leaves it
    barely moving off the middle at all.

    Args:
        plane (numpy.ndarray): 2D float data; non-finite pixels are ignored.
        background (float): the level to measure flux from.

    Returns:
        tuple: (x, y) in 0-based indices into `plane`, or (NaN, NaN) when no
        pixel rises above the background.
    """
    weights = plane - background
    weights[~np.isfinite(weights)] = 0
    np.maximum(weights, 0, out=weights)

    # Summed in float64: float32 accumulates visible error over a full frame.
    columns = weights.sum(axis=0, dtype=np.float64)
    rows = weights.sum(axis=1, dtype=np.float64)
    total = columns.sum()
    if not total > 0:
        nan = float("nan")
        return (nan, nan)
    return (float(columns @ np.arange(columns.size) / total),
            float(rows @ np.arange(rows.size) / total))


def compute_statistics(data, origin=(0, 0)):
    """
    Summarises a frame's pixel values.

    Args:
        data (numpy.ndarray): Raw frame data, of any shape.
        origin (tuple): (x, y) of data[0, 0] in the frame, so the centroid of
            a region cut out of a frame is reported in the frame's indices.

    Returns:
        FrameStatistics: the summary. Every statistic is NaN when the frame
        carries no finite pixel at all, and the centroid is NaN unless the
        data is a 2D plane.
    """
    # One cast up front, reused by every statistic. Computing these straight
    # off integer data makes numpy promote separately in each call, which
    # dominates the cost on a large frame. float32 also byte-swaps the
    # big-endian arrays FITS specifies into native order.
    array = np.asarray(data).astype(np.float32, copy=False)
    values = array.ravel()

    total = int(values.size)

    # Blank pixels are NaN/inf in floating-point FITS data, and a single one
    # would otherwise make every statistic NaN.
    finite = np.isfinite(values)
    if not finite.all():
        values = values[finite]

    if values.size == 0:
        nan = float("nan")
        return FrameStatistics(pixels=0, blank=total, minimum=nan, maximum=nan,
                               mean=nan, median=nan, deviation=nan, variance=nan)

    # The dominant cost by an order of magnitude on a large frame: median
    # partitions a copy, where the others are single passes.
    median = float(np.median(values))
    variance = float(values.var())

    centroid = (float("nan"), float("nan"))
    if array.ndim == 2:
        x, y = flux_centroid(array, median)
        centroid = (x + origin[0], y + origin[1])

    return FrameStatistics(
        pixels=int(values.size),
        blank=total - int(values.size),
        minimum=float(values.min()),
        maximum=float(values.max()),
        mean=float(values.mean()),
        median=median,
        deviation=math.sqrt(variance),
        variance=variance,
        centroid_x=centroid[0],
        centroid_y=centroid[1],
    )


def format_count(value):
    """Formats a pixel value for display, without inventing precision."""
    if math.isnan(value):
        return "—"
    if float(value).is_integer():
        # Detector counts are integers; 59983.000 would just be noise.
        return f"{int(value):,}"
    return f"{value:,.3f}"


def format_centroid(statistics):
    """Formats a centroid as an (x, y) index pair, or a dash when it has none."""
    if math.isnan(statistics.centroid_x):
        return "—"
    return f"({statistics.centroid_x:.2f}, {statistics.centroid_y:.2f})"
