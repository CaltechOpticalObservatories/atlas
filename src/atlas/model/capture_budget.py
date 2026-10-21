"""
How many frames one capture may hold, from the memory free on this machine.

Every frame of a capture is held in memory until the file is written, so the
limit is what fits in a share of the memory free now, less what writing the
cube out needs on top of it.
"""

# Standard Library Imports
import os

# Third-Party Library Imports
import psutil

from atlas.model.fits_model import CUBE_WRITE_OVERHEAD_BYTES

_KEYWORD_SIZE = 128   # bytes of one ImageStreamIO keyword
_COUNTER_BYTES = 16   # a captured frame's cnt0, and whether its keywords came with it
# Where Linux keeps POSIX shared memory; absent on macOS, which bounds it otherwise
_SHARED_MEMORY_DIR = "/dev/shm"


def available_bytes():
    """Memory the system can hand out now without swapping."""
    return psutil.virtual_memory().available


def capture_bytes_per_frame(frame_bytes, nbkw):
    """
    What one captured frame costs: its pixels, a copy of the segment's
    keyword area taken with it, and its two counters.
    """
    return frame_bytes + nbkw * _KEYWORD_SIZE + _COUNTER_BYTES


def shared_memory_free():
    """
    Room left where shared memory lives, or None where no filesystem bounds it.

    On Linux a capture lives in /dev/shm, a tmpfs often capped at half the
    memory, and filling it past its size kills the process with SIGBUS rather
    than failing politely, so the space there has to be counted too.
    """
    try:
        stats = os.statvfs(_SHARED_MEMORY_DIR)
    except (AttributeError, OSError):
        return None
    return stats.f_bavail * stats.f_frsize


def max_capture_frames(frame_bytes, fraction, available=None):
    """
    The most frames of `frame_bytes` each a capture may keep.

    Args:
        frame_bytes (int): What one frame costs; see capture_bytes_per_frame.
        fraction (float): Share of the free memory a capture may use.
        available (int): Free memory, in bytes; measured now if None.

    Returns:
        int: At least 1, since a single frame is always saved from the screen
        rather than captured.
    """
    if available is None:
        available = available_bytes()
    room = available * fraction - CUBE_WRITE_OVERHEAD_BYTES
    shared = shared_memory_free()
    if shared is not None:
        room = min(room, shared * fraction)
    return max(1, int(room // frame_bytes))
