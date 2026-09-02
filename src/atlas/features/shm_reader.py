# Standard Library Imports
from dataclasses import dataclass, field

# Third-Party Library Imports
import numpy as np


@dataclass
class ShmFrame:
    """One frame read from an ImageStreamIO segment."""
    data: np.ndarray
    keywords: dict = field(default_factory=dict)


@dataclass
class _Handle:
    """
    An attached segment plus the semaphore index this reader waits on.

    ImageStreamIOWrap's Image doesn't support arbitrary attributes (no
    py::dynamic_attr()), so the index is tracked here instead.
    """
    image: object
    sem_index: int


def attach(segment_name, shm_dir=""):
    """Attaches to an existing ImageStreamIO segment; returns an opaque handle."""
    # Imported here, not at module level, so atlas still runs when
    # ImageStreamIOWrap is absent and this feature is switched off.
    import os  # pylint: disable=import-outside-toplevel
    import ImageStreamIOWrap  # pylint: disable=import-outside-toplevel,import-error

    if shm_dir:
        os.environ["MILK_SHM_DIR"] = shm_dir

    image = ImageStreamIOWrap.Image()
    status = image.open(segment_name)
    if status != 0:
        raise RuntimeError(f'could not open segment "{segment_name}" (status {status})')

    return _Handle(image=image, sem_index=image.getsemwaitindex(0))


def wait_for_frame(handle, timeout):
    """Blocks until a new frame posts or timeout (seconds) elapses; None on timeout."""
    timed_out = handle.image.semtimedwait(handle.sem_index, timeout) != 0
    if timed_out:
        return None

    keywords = {name: kw.value for name, kw in handle.image.get_kws().items()}
    return ShmFrame(data=np.array(handle.image.copy()), keywords=keywords)


def close(handle):
    """Detaches from the segment."""
    handle.image.close()
