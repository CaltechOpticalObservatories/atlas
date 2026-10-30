"""
Manual demo: launches the real atlas UI with a live view fed by a synthetic
ImageStreamIO producer (an orbiting bright spot), since a real segment needs
a Linux environment ImageStreamIOWrap can build on (see
plans/ATLAS-SHM-VIEWER-PLAN.md). Run directly, not via pytest.

The producer writes a real segment file, laid out as ImageStreamIO lays one
out, in a temporary directory: multi-frame saves are taken by a separate
capture process, which can only read what is really there.

Usage:
    python scripts/demo_shm_viewer.py [--profile NAME] [fits_file]

Optionally pass a FITS file to load alongside the live view (tile mode),
e.g. one written by a real camerad + emulator run. --profile starts from a
bundled profile instead of the defaults, so its tools and layout can be tried
against the live feed; the feed itself is always switched on.
"""

# The producer writes the segment layout with shm_reader's own constants,
# rather than a second copy of the offsets free to drift from the ones read.
# pylint: disable=protected-access

import argparse
import math
import mmap
import os
import struct
import sys
import tempfile
import threading
import time

from PyQt5.QtWidgets import QApplication
import numpy as np

from atlas.features import shm_reader
from atlas.config.loader import available_profiles, load_config
from atlas.config.schema import AtlasConfig
from atlas.viewmodel.frame_viewmodel import FrameViewModel
from atlas.view.main_window import AtlasWindow

SIZE = 256
SEGMENT = "synthetic-demo"
RING = 16
PRODUCER_HZ = 60


def create_segment(directory):
    """Writes an empty uint16 segment with a ring and a FRAMENO keyword; returns its mapping."""
    frame_bytes = SIZE * SIZE * 2
    keyword = shm_reader._METADATA_SIZE + frame_bytes
    size = keyword + shm_reader._KEYWORD_SIZE + frame_bytes * RING
    buffer = bytearray(size)
    struct.pack_into("<I", buffer, shm_reader._OFFSET_NAXIS, 2)
    struct.pack_into("<III", buffer, shm_reader._OFFSET_SIZE, SIZE, SIZE, 0)
    struct.pack_into("<B", buffer, shm_reader._OFFSET_DATATYPE, 3)  # uint16
    struct.pack_into("<H", buffer, shm_reader._OFFSET_NBKW, 1)
    struct.pack_into("<I", buffer, shm_reader._OFFSET_CBSIZE, RING)
    struct.pack_into("<Q", buffer, shm_reader._OFFSET_IMDATAMEMSIZE, frame_bytes)
    buffer[keyword:keyword + 7] = b"FRAMENO"
    buffer[keyword + shm_reader._KW_OFFSET_TYPE] = ord("L")

    path = os.path.join(directory, f"{SEGMENT}.im.shm")
    with open(path, "wb") as segment_file:
        segment_file.write(buffer)
    with open(path, "r+b") as segment_file:
        return mmap.mmap(segment_file.fileno(), size)


def start_synthetic_producer(directory):
    """Publishes an orbiting spot at 60 Hz, as an ImageStreamIO writer does."""
    mm = create_segment(directory)
    frame_bytes = SIZE * SIZE * 2
    keyword = shm_reader._METADATA_SIZE + frame_bytes
    ring_offset = keyword + shm_reader._KEYWORD_SIZE
    # Single 8-byte stores, as C makes them; struct.pack_into zero-fills
    # first, which a reader can catch halfway.
    cnt0 = np.frombuffer(mm, np.uint64, 1, shm_reader._OFFSET_CNT0)
    cbindex = np.frombuffer(mm, np.uint32, 1, shm_reader._OFFSET_CBINDEX)
    frameno = np.frombuffer(mm, np.int64, 1, keyword + shm_reader._KW_OFFSET_VALUE)
    writes = np.frombuffer(mm, np.uint64, 1, keyword + shm_reader._KW_OFFSET_CNT)
    live = np.frombuffer(mm, np.uint16, SIZE * SIZE, shm_reader._METADATA_SIZE)
    yy, xx = np.mgrid[0:SIZE, 0:SIZE]
    gradient = ((xx + yy) / (2 * SIZE) * 120).astype(np.uint16)

    def run():
        number = 0
        while True:
            number += 1
            t = number * 0.05
            cx = SIZE / 2 + (SIZE / 3) * math.cos(t)
            cy = SIZE / 2 + (SIZE / 3) * math.sin(t)
            spot = np.exp(-(((xx - cx) ** 2 + (yy - cy) ** 2)) / (2 * 15 ** 2)) * 4000
            live[:] = (gradient + spot).astype(np.uint16).ravel()
            frameno[0] = number
            writes[0] += 1
            # What ImageStreamIO_UpdateIm does: next ring slot, CBindex, then cnt0
            slot = number % RING
            mm[ring_offset + slot * frame_bytes:ring_offset + (slot + 1) * frame_bytes] = \
                live.tobytes()
            cbindex[0] = slot
            cnt0[0] = number
            time.sleep(1 / PRODUCER_HZ)

    threading.Thread(target=run, daemon=True).start()


def main():
    """Launches atlas with the synthetic SHM feed connected."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("fits_file", nargs="?",
                        help="a FITS file to load beside the live view")
    parser.add_argument("-p", "--profile", choices=available_profiles(),
                        help="start from a bundled profile instead of the defaults")
    args = parser.parse_args()

    shm_dir = tempfile.mkdtemp(prefix="atlas-demo-")
    start_synthetic_producer(shm_dir)

    if args.profile:
        config = load_config(profile=args.profile)
    else:
        config = AtlasConfig()
        config.tools.header = True
        config.display.mode = "tile"
    config.tools.shm.enabled = True
    config.tools.shm.segment_name = SEGMENT
    config.tools.shm.shm_dir = shm_dir

    app = QApplication(sys.argv[:1])
    view_model = FrameViewModel(config)
    window = AtlasWindow(view_model, config)
    window.resize(900, 550)
    window.show()

    if args.fits_file:
        view_model.load_file(args.fits_file)

    window.tools["shm"].connect_to_shm()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
