"""
Saving a frame to FITS.

Saving never asks where: Ctrl+S or the toolbar button writes the current frame
straight to <save directory>/<date>/<date>_<time>.fits. With no dialog there is also
nothing to confirm an overwrite, so the tests that matter most are that a save
lands where it should and never replaces an earlier one.
"""

# pytest injects fixtures as arguments of the same name.
# pylint: disable=redefined-outer-name

# Standard Library Imports
from datetime import datetime, timezone

# Third-Party Library Imports
from astropy.io import fits
import numpy as np
import pytest

from PyQt5.QtWidgets import QFileDialog, QToolBar

from atlas.config.loader import load_config
from atlas.config.schema import AtlasConfig, ConfigError, SaveConfig, ToolsConfig
from atlas.main import overrides_from_args, parse_args
from atlas.model import saving

COUNTS = (np.arange(64, dtype=np.uint16) + 60000).reshape(8, 8)
WHEN = datetime(2026, 10, 12, 19, 6, 37, tzinfo=timezone.utc)


@pytest.fixture
def save_root(tmp_path):
    """Stands in for /tmp/data, so no test writes outside its own directory."""
    root = tmp_path / "data"
    root.mkdir()
    return root


def saving_to(root, **sections):
    """A configuration that saves under `root` rather than /tmp/data."""
    return AtlasConfig(save=SaveConfig(directory=str(root)), **sections)


@pytest.fixture
def window(make_window, save_root):
    """A window and its view model, with no tools switched on."""
    return make_window(saving_to(save_root))


def save(window, save_root):
    """Presses Save Frame once and returns the one file it wrote."""
    atlas_window, _ = window
    before = set(save_root.rglob("*.fits"))
    atlas_window.save_action.trigger()
    (saved,) = set(save_root.rglob("*.fits")) - before
    return saved


def test_live_frame_saves_counts_and_keywords(window, save_root):
    """A shared-memory frame has no file, so this is the only way to keep it."""
    _, view_model = window
    view_model.update_live_frame(COUNTS, {"EXPTIME": 1.5, "MODE": "CDS"})

    data, header = fits.getdata(save(window, save_root), header=True)

    assert data.dtype == np.uint16
    assert np.array_equal(data, COUNTS)
    assert header["EXPTIME"] == 1.5
    assert header["MODE"] == "CDS"


def test_saves_under_todays_directory_without_asking(window, save_root):
    """The usual case: one keystroke, and the frame is filed by UTC date."""
    atlas_window, view_model = window
    view_model.update_live_frame(COUNTS, {})

    before = datetime.now(timezone.utc)
    saved = save(window, save_root)

    # Either date, in case the test happened to straddle UTC midnight.
    assert saved.parent.name in {before.strftime("%Y%m%d"),
                                 datetime.now(timezone.utc).strftime("%Y%m%d")}
    assert saved.name.startswith(saved.parent.name + "_")
    # The path was never shown in a dialog, so the status bar gives it in full.
    assert atlas_window.statusBar().currentMessage() == f"Saved {saved}"


def test_file_frame_from_an_extension_round_trips(window, save_root, tmp_path):
    """Data read from an image extension comes back as a primary HDU."""
    _, view_model = window
    source = tmp_path / "source.fits"
    fits.HDUList([fits.PrimaryHDU(),
                  fits.ImageHDU(COUNTS, header=fits.Header({"FILTER": "H"}))]
                 ).writeto(source)
    view_model.load_file(str(source))

    reloaded = view_model.load_file(str(save(window, save_root)))

    assert np.array_equal(reloaded.data, COUNTS)
    assert reloaded.header["FILTER"] == "H"


def test_path_is_dated_directory_and_timestamp(save_root):
    """root/<date>/<date>_<time>.fits, with the directory made ready."""
    path = saving.next_save_path(str(save_root), WHEN)

    assert path == str(save_root / "20261012" / "20261012_190637.fits")
    assert (save_root / "20261012").is_dir()


def test_saves_in_the_same_second_are_all_kept(save_root):
    """Nothing confirms an overwrite any more, so a name is never reused."""
    first = saving.next_save_path(str(save_root), WHEN)
    with open(first, "wb"):
        pass
    second = saving.next_save_path(str(save_root), WHEN)
    with open(second, "wb"):
        pass

    assert second == str(save_root / "20261012" / "20261012_190637_2.fits")
    assert saving.next_save_path(str(save_root), WHEN).endswith("20261012_190637_3.fits")


def test_existing_file_is_never_replaced(window, save_root):
    """The model refuses to overwrite too, in case a name is ever reused."""
    _, view_model = window
    view_model.update_live_frame(COUNTS, {})
    target = save_root / "taken.fits"
    target.write_bytes(b"precious")

    assert not view_model.save_frame(view_model.current_frame, str(target))
    assert target.read_bytes() == b"precious"


def test_unwritable_root_is_reported_not_raised(window, tmp_path):
    """No dialog means no other place to put it: say so and write nothing."""
    atlas_window, view_model = window
    view_model.update_live_frame(COUNTS, {})
    blocker = tmp_path / "not_a_directory"
    blocker.write_text("")
    atlas_window.save_directory = str(blocker)

    atlas_window.save_current_frame()

    assert atlas_window.statusBar().currentMessage().startswith("Could not save")
    assert not list(tmp_path.rglob("*.fits"))


def test_save_is_disabled_with_nothing_to_save(window):
    """The command goes grey until there is a frame, like Delete does."""
    atlas_window, view_model = window
    assert not atlas_window.save_action.isEnabled()

    view_model.update_live_frame(COUNTS, {})
    assert atlas_window.save_action.isEnabled()


def test_save_button_is_off_unless_a_profile_asks(window):
    """The default window stays a plain viewer, with no toolbar at all."""
    atlas_window, _ = window
    assert not atlas_window.findChildren(QToolBar)


def test_save_button_is_the_menu_command(make_window, save_root):
    """One action in two places, so the button can never drift from the menu."""
    atlas_window, view_model = make_window(
        saving_to(save_root, tools=ToolsConfig(save_button=True)))
    (toolbar,) = atlas_window.findChildren(QToolBar)

    assert toolbar.actions() == [atlas_window.save_action]
    assert not atlas_window.save_action.isEnabled()
    view_model.update_live_frame(COUNTS, {})
    assert atlas_window.save_action.isEnabled()


def test_fei_profile_shows_the_save_button():
    """The FEI station saves live frames often enough to want it on screen."""
    assert load_config(profile="hispec_fei").tools.save_button


def test_save_directory_defaults_to_tmp_data():
    """Anyone can write there, so saving works before anything is configured."""
    assert AtlasConfig().save.directory == "/tmp/data"


def test_save_directory_comes_from_the_command_line():
    """--save-dir overrides whatever the profile or config file says."""
    args = parse_args(["--profile", "hispec_fei", "--save-dir", "/data/fei"])
    config = load_config(profile=args.profile, overrides=overrides_from_args(args))
    assert config.save.directory == "/data/fei"


def test_an_empty_save_directory_is_rejected():
    """Like every other key, a bad value stops atlas starting, not saving."""
    with pytest.raises(ConfigError, match="save.directory"):
        AtlasConfig(save=SaveConfig(directory="")).validate()


def test_save_directory_can_be_changed_from_the_menu(window, monkeypatch, tmp_path):
    """File → Set Save Directory… sends later saves somewhere else."""
    atlas_window, view_model = window
    view_model.update_live_frame(COUNTS, {})
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.setattr(QFileDialog, "getExistingDirectory",
                        lambda *_: str(elsewhere))

    atlas_window.choose_save_directory()
    atlas_window.save_current_frame()

    (saved,) = elsewhere.rglob("*.fits")
    assert np.array_equal(fits.getdata(saved), COUNTS)


def test_cancelling_the_directory_picker_keeps_the_directory(window, monkeypatch, save_root):
    """An empty answer from the picker means the user backed out."""
    atlas_window, _ = window
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *_: "")

    atlas_window.choose_save_directory()

    assert atlas_window.save_directory == str(save_root)
