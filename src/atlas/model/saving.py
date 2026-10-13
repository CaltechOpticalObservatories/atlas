# Standard Library Imports
import os


def day_directory(root, when):
    """
    The directory for saves made at `when`, root/<date> in UTC, created if it
    does not exist yet.

    Raises:
        OSError: when the directory cannot be created.
    """
    directory = os.path.join(os.path.expanduser(root), when.strftime("%Y%m%d"))
    os.makedirs(directory, exist_ok=True)
    return directory


def next_save_path(root, when):
    """
    Path for a save made at `when`: root/<date>/<date>_<time>.fits, in UTC,
    creating the day's directory.

    Nothing asks before a save, so nothing confirms an overwrite either: a
    second save within the same second gets _2, _3, ... rather than replacing
    the first.

    Raises:
        OSError: when the day's directory cannot be created.
    """
    stem = os.path.join(day_directory(root, when), when.strftime("%Y%m%d_%H%M%S"))
    file_name, copy = f"{stem}.fits", 1
    while os.path.exists(file_name):
        copy += 1
        file_name = f"{stem}_{copy}.fits"
    return file_name
