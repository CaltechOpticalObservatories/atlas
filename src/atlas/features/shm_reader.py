# Standard Library Imports
from dataclasses import dataclass, field

# Third-Party Library Imports
import numpy as np


@dataclass
class ShmFrame:
    """One frame read from an ImageStreamIO segment."""
    data: np.ndarray
    keywords: dict = field(default_factory=dict)


# UNVERIFIED: no environment with pyImageStreamIO + a live segment has been
# available yet (see plans/ATLAS-SHM-VIEWER-PLAN.md open question 3). This is
# a best-effort implementation against pyImageStreamIO's typical shape, kept
# isolated here so it is the only thing M1's real spike needs to correct.

def attach(segment_name, shm_dir=""):
    """Attaches to an existing ImageStreamIO segment; returns an opaque handle."""
    # Imported here, not at module level, so atlas still runs when
    # pyImageStreamIO is absent and this feature is switched off.
    import os  # pylint: disable=import-outside-toplevel
    from pyImageStreamIO import Image  # pylint: disable=import-outside-toplevel

    if shm_dir:
        os.environ["MILK_SHM_DIR"] = shm_dir

    image = Image()
    image.open(segment_name)
    return image


def wait_for_frame(image, timeout):
    """Blocks until a new frame posts or timeout (seconds) elapses; None on timeout."""
    timed_out = image.semwait(timeout) != 0
    if timed_out:
        return None

    keywords = {kw.name: kw.value for kw in image.kw if kw.name}
    return ShmFrame(data=np.array(image.copy()), keywords=keywords)


def close(image):
    """Detaches from the segment."""
    image.close()
