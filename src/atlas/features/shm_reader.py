"""
Reads an ImageStreamIO shared-memory segment directly (mmap + struct),
without ImageStreamIOWrap, which needs a from-source pybind11/cmake build
and fails entirely on macOS (sem_timedwait isn't implemented on Darwin).
See plans/ATLAS-SHM-VIEWER-PLAN.md design decision D6 for the reasoning,
and how the offsets below were obtained (a real sizeof/offsetof probe
against an installed ImageStreamIO, not hand-computed).
"""

# Standard Library Imports
import mmap
import os
import struct
import time
from dataclasses import dataclass, field

# Third-Party Library Imports
import numpy as np

# IMAGE_METADATA layout (ImageStruct.h)
_METADATA_SIZE = 384
_OFFSET_NAXIS = 112
_OFFSET_SIZE = 116          # uint32_t[3]
_OFFSET_DATATYPE = 136
_OFFSET_CNT0 = 264
_OFFSET_NBKW = 290
_OFFSET_IMDATAMEMSIZE = 312

# IMAGE_KEYWORD layout
_KEYWORD_SIZE = 128
_KW_OFFSET_NAME = 0
_KW_NAME_LEN = 16
_KW_OFFSET_TYPE = 16
_KW_OFFSET_VALUE = 24
_KW_VALUE_LEN = 16

# ImageStreamIO datatype codes (ImageStruct.h _DATATYPE_*)
_DATATYPE_TO_NUMPY = {
    1: np.uint8, 2: np.int8, 3: np.uint16, 4: np.int16,
    5: np.uint32, 6: np.int32, 7: np.uint64, 8: np.int64,
    9: np.float32, 10: np.float64,
}

_POLL_INTERVAL = 0.002  # seconds between cnt0 checks while waiting


@dataclass
class ShmFrame:
    """One frame read from an ImageStreamIO segment."""
    data: np.ndarray
    keywords: dict = field(default_factory=dict)


@dataclass
class _Handle:
    """An attached segment: its mmap, file descriptor, and data offset."""
    mm: mmap.mmap
    fd: int
    data_offset: int


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
    path = os.path.join(directory, f"{segment_name}.im.shm")

    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError as error:
        raise RuntimeError(f'could not open segment "{segment_name}": {error}') from error

    try:
        size = os.fstat(fd).st_size
        if size < _METADATA_SIZE:
            raise RuntimeError(f'segment "{segment_name}" is smaller than a valid header')
        mm = mmap.mmap(fd, size, prot=mmap.PROT_READ)
    except Exception:
        os.close(fd)
        raise

    return _Handle(mm=mm, fd=fd, data_offset=_round_up_8(_METADATA_SIZE))


def _read_cnt0(mm):
    (cnt0,) = struct.unpack_from("<Q", mm, _OFFSET_CNT0)
    return cnt0


def _read_keywords(mm, kw_offset, nbkw):
    keywords = {}
    for i in range(nbkw):
        base = kw_offset + i * _KEYWORD_SIZE
        name_raw = mm[base + _KW_OFFSET_NAME: base + _KW_OFFSET_NAME + _KW_NAME_LEN]
        name = name_raw.split(b"\x00", 1)[0].decode("ascii", "replace")
        if not name:
            break

        type_char = chr(mm[base + _KW_OFFSET_TYPE])
        if type_char == "L":
            (value,) = struct.unpack_from("<q", mm, base + _KW_OFFSET_VALUE)
        elif type_char == "D":
            (value,) = struct.unpack_from("<d", mm, base + _KW_OFFSET_VALUE)
        elif type_char == "S":
            raw = mm[base + _KW_OFFSET_VALUE: base + _KW_OFFSET_VALUE + _KW_VALUE_LEN]
            value = raw.split(b"\x00", 1)[0].decode("ascii", "replace")
        else:
            continue

        keywords[name] = value
    return keywords


def _read_frame(mm, data_offset):
    width, height, _ = struct.unpack_from("<III", mm, _OFFSET_SIZE)
    (datatype,) = struct.unpack_from("<B", mm, _OFFSET_DATATYPE)
    (nbkw,) = struct.unpack_from("<H", mm, _OFFSET_NBKW)
    (imdatamemsize,) = struct.unpack_from("<Q", mm, _OFFSET_IMDATAMEMSIZE)

    dtype = _DATATYPE_TO_NUMPY.get(datatype)
    if dtype is None:
        raise RuntimeError(f"unsupported ImageStreamIO datatype {datatype}")

    raw = mm[data_offset: data_offset + imdatamemsize]
    data = np.frombuffer(raw, dtype=dtype)[: width * height].reshape(height, width).copy()

    kw_offset = data_offset + _round_up_8(imdatamemsize)
    keywords = _read_keywords(mm, kw_offset, nbkw)
    return ShmFrame(data=data, keywords=keywords)


def wait_for_frame(handle, timeout):
    """Polls cnt0 for a new frame; returns None on timeout."""
    start_cnt0 = _read_cnt0(handle.mm)
    deadline = time.monotonic() + timeout
    while _read_cnt0(handle.mm) == start_cnt0:
        if time.monotonic() >= deadline:
            return None
        time.sleep(_POLL_INTERVAL)
    return _read_frame(handle.mm, handle.data_offset)


def close(handle):
    """Detaches from the segment."""
    handle.mm.close()
    os.close(handle.fd)
