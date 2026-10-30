"""
Reads an ImageStreamIO shared-memory segment directly (mmap + struct),
without ImageStreamIOWrap, which needs a from-source pybind11/cmake build
and fails entirely on macOS (sem_timedwait isn't implemented on Darwin).
See plans/ATLAS-SHM-VIEWER-PLAN.md design decision D6 for the reasoning,
and how the offsets below were obtained (a real sizeof/offsetof probe
against an installed ImageStreamIO, not hand-computed). The circular buffer
offsets came from the same probe, against ImageStreamIO 2.00.

A segment holds one live frame, which the producer overwrites in place, and,
when created with CBsize > 0, a circular buffer of the last CBsize frames.
Only the ring lets a reader fall behind for a moment without losing frames,
so frames are read from it whenever the segment has one.
"""

# Standard Library Imports
import mmap
import os
import struct
import time
from dataclasses import dataclass, field
from typing import Optional

# Third-Party Library Imports
import numpy as np

# IMAGE_METADATA layout (ImageStruct.h)
_METADATA_SIZE = 384
_OFFSET_NAXIS = 112
_OFFSET_SIZE = 116          # uint32_t[3]
_OFFSET_DATATYPE = 136
_OFFSET_CNT0 = 264
_OFFSET_NBKW = 290
_OFFSET_CBSIZE = 292        # uint32_t
_OFFSET_CBINDEX = 296       # uint32_t
_OFFSET_IMDATAMEMSIZE = 312

# IMAGE_KEYWORD layout
_KEYWORD_SIZE = 128
_KW_OFFSET_NAME = 0
_KW_NAME_LEN = 16
_KW_OFFSET_TYPE = 16
_KW_OFFSET_VALUE = 24
_KW_VALUE_LEN = 16
_KW_OFFSET_CNT = 40         # uint64_t, bumped at each write of the keyword

# ImageStreamIO datatype codes (ImageStruct.h _DATATYPE_*)
_DATATYPE_TO_NUMPY = {
    1: np.uint8, 2: np.int8, 3: np.uint16, 4: np.int16,
    5: np.uint32, 6: np.int32, 7: np.uint64, 8: np.int64,
    9: np.float32, 10: np.float64,
}

# For readers that copy straight out of the mapping
OFFSET_CNT0 = _OFFSET_CNT0
KEYWORD_SIZE = _KEYWORD_SIZE

_POLL_INTERVAL = 0.001  # seconds between cnt0 checks while waiting
# A ring of one is only ever the slot being written, so it holds nothing.
_MIN_RING = 2


@dataclass
class ShmFrame:
    """One frame read from an ImageStreamIO segment."""
    data: np.ndarray
    keywords: dict = field(default_factory=dict)
    # The segment's frame counter for this image; a jump of more than one
    # between frames means the reader missed some in between.
    cnt0: Optional[int] = None


@dataclass
class SegmentInfo:
    """What an attached segment holds, fixed for the segment's whole life."""
    shape: tuple  # (height, width)
    dtype: np.dtype
    # Frames the producer's circular buffer keeps; 0 when it keeps none.
    ring: int = 0

    @property
    def frame_bytes(self):
        """Bytes of pixel data in one frame."""
        return self.shape[0] * self.shape[1] * self.dtype.itemsize


@dataclass
class _Handle:  # pylint: disable=too-many-instance-attributes  # plain record
    """An attached segment: its mmap, file descriptor, and data offsets."""
    mm: mmap.mmap
    fd: int
    data_offset: int
    path: str
    ident: tuple
    info: SegmentInfo
    imdatamemsize: int
    ring_offset: int = 0
    nbkw: int = 0

    @property
    def kw_offset(self):
        """Where the keyword area starts."""
        return self.data_offset + _round_up_8(self.imdatamemsize)


def _round_up_8(value):
    return (value + 7) & ~7


def _resolve_dir(shm_dir):
    """Mirrors ImageStreamIO_shmdirname's fallback chain."""
    for candidate in (shm_dir, os.environ.get("MILK_SHM_DIR"), "/milk/shm", "/tmp"):
        if candidate and os.path.isdir(candidate):
            return candidate
    raise RuntimeError("no usable ImageStreamIO shared-memory directory found")


def attach(segment_name, shm_dir=""):
    """Attaches to an existing ImageStreamIO segment; returns an opaque handle."""
    directory = _resolve_dir(shm_dir)
    return attach_path(os.path.join(directory, f"{segment_name}.im.shm"))


def attach_path(path):
    """Attaches to the segment file at `path`; returns an opaque handle."""
    segment_name = os.path.basename(path).removesuffix(".im.shm")
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError as error:
        raise RuntimeError(f'could not open segment "{segment_name}": {error}') from error

    try:
        info = os.fstat(fd)
        if info.st_size < _METADATA_SIZE:
            raise RuntimeError(f'segment "{segment_name}" is smaller than a valid header')
        mm = mmap.mmap(fd, info.st_size, prot=mmap.PROT_READ)
    except Exception:
        os.close(fd)
        raise

    try:
        handle = _describe(mm, fd, path, (info.st_dev, info.st_ino), info.st_size)
    except Exception:
        mm.close()
        os.close(fd)
        raise
    if handle is None:
        mm.close()
        os.close(fd)
        raise RuntimeError(f'segment "{segment_name}" is not set up yet')
    return handle


def _describe(mm, fd, path, ident, file_size):
    """A handle for a mapped segment, or None if its producer has not filled in the header."""
    width, height, _ = struct.unpack_from("<III", mm, _OFFSET_SIZE)
    (datatype,) = struct.unpack_from("<B", mm, _OFFSET_DATATYPE)
    (imdatamemsize,) = struct.unpack_from("<Q", mm, _OFFSET_IMDATAMEMSIZE)
    (ring,) = struct.unpack_from("<I", mm, _OFFSET_CBSIZE)
    (nbkw,) = struct.unpack_from("<H", mm, _OFFSET_NBKW)

    dtype = _DATATYPE_TO_NUMPY.get(datatype)
    if dtype is None:
        if datatype == 0:
            return None
        raise RuntimeError(f"unsupported ImageStreamIO datatype {datatype}")
    dtype = np.dtype(dtype)
    if not width or not height or imdatamemsize < width * height * dtype.itemsize:
        return None

    data_offset = _round_up_8(_METADATA_SIZE)
    # The ring is the last thing ImageStreamIO_image_sizing lays out, and the
    # file is exactly as long as everything laid out, so it ends the file.
    # Counting back from the end avoids sizeof(sem_t) and friends, which
    # differ between platforms.
    ring_offset = file_size - _round_up_8(imdatamemsize * ring)
    if ring < _MIN_RING or ring_offset < data_offset + _round_up_8(imdatamemsize):
        ring, ring_offset = 0, 0
    elif not _ring_follows_cnt0(mm, ring):
        # Some other writer moves cnt0 without the ring, so a frame's number
        # no longer says which slot holds it.
        ring, ring_offset = 0, 0

    return _Handle(mm=mm, fd=fd, data_offset=data_offset, path=path, ident=ident,
                   info=SegmentInfo(shape=(height, width), dtype=dtype, ring=ring),
                   imdatamemsize=imdatamemsize, ring_offset=ring_offset, nbkw=nbkw)


def _ring_follows_cnt0(mm, ring):
    """
    True when frame cnt0 sits in ring slot cnt0 % CBsize.

    ImageStreamIO_createIm zeroes both cnt0 and CBindex, and every
    ImageStreamIO_UpdateIm advances both by one, so this holds for any
    producer that publishes only through UpdateIm, as camerad does. CBindex
    moves just before cnt0, so it may be caught one ahead.
    """
    for _ in range(3):
        cnt0 = _read_cnt0(mm)
        (index,) = struct.unpack_from("<I", mm, _OFFSET_CBINDEX)
        if _read_cnt0(mm) != cnt0:
            continue  # a frame landed mid-read; look again
        return index in (cnt0 % ring, (cnt0 + 1) % ring)
    return False


def segment_path(handle):
    """The file this handle is mapped to."""
    return handle.path


def segment_info(handle):
    """The SegmentInfo of the segment this handle is mapped to."""
    return handle.info


def segment_replaced(handle):
    """
    True once the segment file has been unlinked or recreated since attaching.

    ImageStreamIO_createIm unlinks and recreates <name>.im.shm, so a producer
    restart leaves an existing handle mapped to an orphaned inode.
    """
    try:
        info = os.stat(handle.path)
    except OSError:
        return True
    return (info.st_dev, info.st_ino) != handle.ident


def _read_cnt0(mm):
    (cnt0,) = struct.unpack_from("<Q", mm, _OFFSET_CNT0)
    return cnt0


def frame_count(handle):
    """cnt0: the number of the newest frame the producer has finished."""
    return _read_cnt0(handle.mm)


def _read_keywords(buffer, kw_offset, nbkw):
    """
    The keywords in `buffer` from `kw_offset`, and each one's write counter.

    `buffer` is the segment's mapping, or a copy of its keyword area.
    """
    keywords = {}
    counts = []
    for i in range(nbkw):
        base = kw_offset + i * _KEYWORD_SIZE
        name_raw = buffer[base + _KW_OFFSET_NAME: base + _KW_OFFSET_NAME + _KW_NAME_LEN]
        name = bytes(name_raw).split(b"\x00", 1)[0].decode("ascii", "replace")
        if not name:
            break

        type_char = chr(buffer[base + _KW_OFFSET_TYPE])
        if type_char == "L":
            (value,) = struct.unpack_from("<q", buffer, base + _KW_OFFSET_VALUE)
        elif type_char == "D":
            (value,) = struct.unpack_from("<d", buffer, base + _KW_OFFSET_VALUE)
        elif type_char == "S":
            raw = buffer[base + _KW_OFFSET_VALUE: base + _KW_OFFSET_VALUE + _KW_VALUE_LEN]
            value = bytes(raw).split(b"\x00", 1)[0].decode("ascii", "replace")
        else:
            continue

        keywords[name] = value
        counts.append(struct.unpack_from("<Q", buffer, base + _KW_OFFSET_CNT)[0])
    return keywords, tuple(counts)


def read_keywords(handle):
    """
    The keywords on the segment now.

    They belong to the live frame, not to any slot of the ring, and the
    producer rewrites them before publishing the next frame, so they describe
    frame cnt0 only until the next one starts.
    """
    return _read_keywords(handle.mm, handle.kw_offset, handle.nbkw)[0]


def keyword_count(handle):
    """How many keywords the segment has room for."""
    return handle.nbkw


def keyword_area(handle):
    """(offset, size) of the segment's keyword area, for copying it whole."""
    return handle.kw_offset, handle.nbkw * _KEYWORD_SIZE


def decode_keywords(block, nbkw):
    """
    The keywords in a copy of a segment's keyword area, and the write counter
    of each one, in the order they appear.

    ImageStreamIO bumps a keyword's counter at every write, so comparing the
    counters says whether a copy holds the keywords of the frame it was taken
    with or of a later one.
    """
    return _read_keywords(block, 0, nbkw)


def _copy(handle, offset, out):
    """One frame's pixels at `offset`, copied into `out`, or a new array if None."""
    info = handle.info
    source = np.frombuffer(handle.mm, dtype=info.dtype, count=info.shape[0] * info.shape[1],
                           offset=offset).reshape(info.shape)
    try:
        if out is None:
            return source.copy()
        np.copyto(out, source)
        return out
    finally:
        # A view left alive anywhere, a traceback included, stops close()
        # unmapping the segment.
        del source


def _read_frame(handle, attempts=3):
    """
    The live frame, read again if the producer finished another meanwhile.

    Only a best effort against tearing: the producer copies the next frame in
    before cnt0 moves, so a copy overlapping that start goes unseen. A
    segment with a ring is read from the ring instead, where it cannot.
    """
    for _ in range(attempts):
        cnt0 = _read_cnt0(handle.mm)
        data = _copy(handle, handle.data_offset, None)
        keywords = read_keywords(handle)
        if _read_cnt0(handle.mm) == cnt0:
            break
    return ShmFrame(data=data, keywords=keywords, cnt0=cnt0)


def oldest_in_ring(handle, newest):
    """
    The number of the oldest frame still safe to read from the ring, given
    that `newest` is the newest frame published.

    The producer's next UpdateIm is already free to overwrite the slot after
    the newest, so only CBsize - 1 frames are held for sure.
    """
    return newest - handle.info.ring + 2


def read_ring(handle, number, out=None):
    """
    Frame `number` (its cnt0) out of the ring, into `out` if given.

    Returns:
        numpy.ndarray: the frame, or None when the producer has overwritten
        it, or might have during the copy. A frame is never returned torn.
    """
    if number < oldest_in_ring(handle, _read_cnt0(handle.mm)):
        return None
    slot = number % handle.info.ring
    data = _copy(handle, handle.ring_offset + slot * handle.imdatamemsize, out)
    # Checked again afterwards: a producer that lapped the slot during the
    # copy leaves no trace in the pixels themselves.
    if number < oldest_in_ring(handle, _read_cnt0(handle.mm)):
        return None
    return data


def wait_for_frame(handle, timeout, after=None, poll=None):
    """
    The live frame, once there is one newer than frame `after`; None on timeout.

    `after` is the cnt0 of the last frame the caller has. A frame that landed
    since then is returned straight away, rather than becoming the new
    baseline and being lost. None waits for the next frame to land. `poll` is
    the seconds between looks at cnt0, 0 to spin; None for the default.
    """
    if poll is None:
        poll = _POLL_INTERVAL
    if after is None:
        after = _read_cnt0(handle.mm)
    deadline = time.monotonic() + timeout
    while _read_cnt0(handle.mm) == after:
        if time.monotonic() >= deadline:
            return None
        time.sleep(poll)
    return _read_frame(handle)


def close(handle):
    """Detaches from the segment."""
    try:
        handle.mm.close()
    finally:
        os.close(handle.fd)
