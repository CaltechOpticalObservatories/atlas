# Standard Library Imports
import argparse
import sys

# Third-Party Library Imports
from PyQt5.QtWidgets import QApplication

from atlas.config.loader import load_config, available_profiles
from atlas.config.schema import ConfigError, DISPLAY_MODES
from atlas.features import registered_names
from atlas.view.main_window import AtlasWindow
from atlas.viewmodel.frame_viewmodel import FrameViewModel


def parse_args(argv):
    """Parses the command line."""
    parser = argparse.ArgumentParser(
        prog="atlas",
        description="View FITS images. The set of features is chosen before "
                    "the GUI starts, via a profile or configuration file.")

    parser.add_argument("files", nargs="*",
                        help="FITS files to open, one frame each")
    parser.add_argument("-c", "--config", metavar="FILE",
                        help="YAML configuration file")
    parser.add_argument("-p", "--profile", metavar="NAME",
                        help=f"bundled profile ({', '.join(available_profiles())})")
    parser.add_argument("-m", "--mode", choices=DISPLAY_MODES,
                        help="display mode, overriding the configuration")
    parser.add_argument("--tile-columns", type=int, metavar="N",
                        help="columns to use when tiling")
    parser.add_argument("--enable", action="append", default=[], metavar="TOOL",
                        help=f"turn a tool on ({', '.join(registered_names())})")
    parser.add_argument("--disable", action="append", default=[], metavar="TOOL",
                        help="turn a tool off")
    parser.add_argument("--list-profiles", action="store_true",
                        help="list the bundled profiles and exit")

    return parser.parse_args(argv)


def overrides_from_args(args):
    """Turns command-line flags into a nested override dict."""
    display = {}
    if args.mode:
        display["mode"] = args.mode
    if args.tile_columns is not None:
        display["tile_columns"] = args.tile_columns

    tools = {}
    for name in args.enable:
        tools[name] = True
    for name in args.disable:
        tools[name] = False

    overrides = {}
    if display:
        overrides["display"] = display
    if tools:
        overrides["tools"] = tools
    return overrides


def main(argv=None):
    """Runs atlas."""
    args = parse_args(sys.argv[1:] if argv is None else argv)

    if args.list_profiles:
        for name in available_profiles():
            print(name)
        return 0

    # The configuration is resolved before any widget exists, so a disabled
    # feature is never constructed rather than being built and hidden.
    try:
        config = load_config(args.config, args.profile, overrides_from_args(args))
    except ConfigError as error:
        print(f"atlas: {error}", file=sys.stderr)
        return 2

    app = QApplication(sys.argv[:1])

    view_model = FrameViewModel(config)
    window = AtlasWindow(view_model, config)
    window.show()

    if args.files:
        view_model.load_files(args.files)

    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
