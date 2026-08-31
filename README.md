# atlas

**atlas** is a Python GUI for viewing FITS images, in the spirit of SAOImage DS9
but deliberately not a kitchen sink. Which features exist in a session is chosen
*before* the GUI starts, from a profile or a configuration file — a feature that
is switched off is never built, not merely hidden.

## Installation

Requires Python 3.10 or higher.

```sh
pip install -e .            # atlas and its runtime dependencies
pip install -e ".[zmq]"     # also the optional ZMQ tool
pip install -e ".[dev]"     # also pylint, for the CI checks
```

Dependencies are declared in `pyproject.toml`; `requirements.txt` is kept as a
thin wrapper so `pip install -r requirements.txt` still works.

## Usage

Installing puts an `atlas` command on your path:

```sh
atlas                              # defaults: single frame, header panel
atlas image.fits                   # open a file straight away
atlas *.fits --mode tile           # every file in its own tile
atlas --profile minimal            # image display and nothing else
atlas --config observing.yaml      # your own configuration
```

It also runs straight from a checkout without installing:

```sh
PYTHONPATH=src python -m atlas.main --profile viewer image.fits
```

Run `atlas --help` for the full command line, and `--list-profiles` for the
bundled profiles.

## Frames

atlas borrows DS9's **frame** concept: each loaded image lives in its own frame,
and the display mode decides how frames appear on screen.

| Mode | What you see | Shortcut |
| --- | --- | --- |
| `single` | one frame at a time | `Ctrl+1` |
| `tile` | every frame in a grid | `Ctrl+2` |

Move between frames with `Ctrl+]` and `Ctrl+[`, or click a tile. `Ctrl+W`
closes the current frame.

## Configuration

A configuration is resolved from, in increasing order of precedence: built-in
defaults, the `--profile`, the `--config` file, then command-line overrides.
Unknown keys are rejected with an error rather than ignored, so a typo cannot
silently leave a feature switched off.

```yaml
window:
  title: atlas
  width_fraction: 0.8      # of the screen
  height_fraction: 0.8

display:
  mode: single             # single | tile
  tile_columns: null       # null picks a roughly square grid

tools:
  header: true             # FITS header panel
  histogram: false         # pixel-intensity histograms
  tap_subtraction: false   # COO detector signal/reset taps
  zmq: false               # load frames announced over ZMQ
```

Any tool taking options can be written either as a bare boolean or as a section:

```yaml
tools:
  tap_subtraction:
    enabled: true
    tap_width: 128
    num_taps: 32
  zmq:
    enabled: true
    address: tcp://localhost:5555
    socket_type: SUB       # SUB | PULL
    bind: false
```

Individual tools can be toggled from the command line without editing anything:

```sh
python src/main.py --profile minimal --enable histogram
python src/main.py --profile detector --disable zmq
```

### Bundled profiles

| Profile | Purpose |
| --- | --- |
| `minimal` | Image display only — no panels, no tools. |
| `viewer` | General FITS viewing: headers and histograms. |
| `detector` | COO detector work: tiled frames, tap subtraction, ZMQ. |

## Project structure

atlas uses a src layout, so everything lives under one importable package:

- **`pyproject.toml`** — packaging, dependencies and the `atlas` entry point.
- **`src/atlas/main.py`** — command line, configuration, then launch.
- **`src/atlas/config/`** — configuration schema, loader and bundled profiles.
- **`src/atlas/model/`** — FITS reading and the `Frame` type.
- **`src/atlas/viewmodel/`** — the frame list and display state.
- **`src/atlas/view/`** — main window, frame widgets and the tiling grid.
- **`src/atlas/features/`** — optional tools, each registered under the config
  key that enables it. Adding a feature means adding a module here and a key in
  the schema; nothing else needs to know about it.

## Reporting Issues

If you encounter any problems or have questions about this project, please open
an issue on the [GitHub Issues page](https://github.com/CaltechOpticalObservatories/atlas/issues).
Your feedback helps us improve the project!
