# atlas

**atlas** is a Python GUI for viewing FITS images, in the spirit of SAOImage DS9.

It opens files into *frames*, shows them singly or tiled, and lets you read
individual pixel counts straight off the image. Everything beyond the image
itself is a tool you switch on, so a default launch stays a plain viewer rather
than a wall of panels.

## Installation

Requires Python 3.12 or higher.

```sh
pip install -e .            # atlas and its runtime dependencies
pip install -e ".[zmq]"     # also the optional ZMQ tool
pip install -e ".[dev]"     # also pylint and pytest, for the CI checks
```

Dependencies are declared in `pyproject.toml`.

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

## What it does

| | |
| --- | --- |
| **Frames** | Each image in its own frame, shown singly or tiled |
| **Scales** | Linear or log, per frame rather than per window |
| **Hover readout** | Pixel index and raw count in the status bar, always on |
| **Header panel** | The current frame's FITS header, on by default |
| **Statistics** | Mean, median, standard deviation, min, max, pixel count |
| **Histograms** | Pixel-value distributions for every frame on screen |
| **Live streams** | Follow a detector over ImageStreamIO shared memory or ZMQ |
| **Tap subtraction** | COO detector signal and reset taps |

Everything except the header panel is opt-in, from a profile, a configuration
file, or `--enable` on the command line.

## Documentation

The documentation is published at
<https://caltechopticalobservatories.github.io/atlas/>, and its source lives
in [`docs/`](docs/):

- [Installation](docs/installation.md) and [Quickstart](docs/quickstart.md)
- [Frames and scales](docs/frames.md)
- [Inspecting pixels](docs/inspecting.md): hover readout, statistics, headers, histograms
- [Live streams](docs/live.md): shared memory and ZMQ
- [Detector tools](docs/detector.md): tap subtraction
- [Command line](docs/cli.md) and [Configuration](docs/configuration.md) reference
- [Development](docs/development.md)

Build it with [tox](https://tox.wiki/):

```sh
tox -e docs      # writes docs/_build/html/index.html
tox -e serve     # rebuilds on save at http://127.0.0.1:8000
```

## Development

```sh
tox              # the test suite and pylint, as CI runs them
tox -e tests
tox -e lint
```

See [Development](docs/development.md) for the full set of environments and how
to add a documentation page.

## Reporting Issues

If you encounter any problems or have questions about this project, please open
an issue on the [GitHub Issues page](https://github.com/CaltechOpticalObservatories/atlas/issues).
Your feedback helps us improve the project!
