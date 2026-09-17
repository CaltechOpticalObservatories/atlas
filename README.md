# atlas

**atlas** is a Python GUI for viewing FITS images, in the spirit of SAOImage DS9.

## Installation

Requires Python 3.14 or higher.

```sh
pip install -e .            # atlas and its runtime dependencies
pip install -e ".[zmq]"     # also the optional ZMQ tool
pip install -e ".[dev]"     # also pylint, for the CI checks
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

## Frames

atlas borrows DS9's **frame** concept: each loaded image lives in its own frame,
and the display mode decides how frames appear on screen.

| Mode | What you see | Shortcut |
| --- | --- | --- |
| `single` | one frame at a time | `Ctrl+1` |
| `tile` | every frame in a grid | `Ctrl+2` |

Move between frames with `Ctrl+]` and `Ctrl+[`, or click a tile. `Ctrl+W`
closes the current frame.

## Scales

**View → Scale** decides how pixel values map onto the brightness of the
display. It is a property of the frame, not of the window, so in `tile` mode
one image can be shown on a log scale beside another on a linear one.

| Scale | What it does | Shortcut |
| --- | --- | --- |
| `linear` | brightness proportional to pixel value | `Ctrl+3` |
| `log` | stretches the faint end, compresses the bright end | `Ctrl+4` |

Both scales first map the frame's own minimum and maximum onto the full display
range, so changing scale never clips a pixel that was visible before, it only
redistributes contrast. Only the rendered pixmap changes; the raw data is left
alone, so switching back and forth is lossless.

The histogram window has its own **Log count axis** checkbox, independent of the
frame's scale. A pixel histogram is usually dominated by a single sky or bias
peak, and a log count axis is what makes the faint tail visible.

## Hover readout

Resting the cursor on a pixel puts its index and its count on the right of the
status bar:

```
(341, 169)  27,922
```

The indices are 0-based, `x` across and `y` down, so the pair reads directly as
`data[y, x]` in whatever you are inspecting the frame with. This is numpy's
convention rather than DS9's 1-based one, and `y` counts down because atlas
draws the first row of the array at the top of the tile.

The count comes from the raw array, so it is a detector count and does not move
when the display scale changes. Blank pixels (NaN/inf) read as a dash rather
than as a number, and colour frames report one sample per channel.

The readout is always available: it needs no configuration, adds no panel, and
does no work at all until the cursor is over a frame. It sits beside the status
messages rather than replacing them, so neither overwrites the other.

A frame is usually shown smaller than it is, in which case several data pixels
share one screen pixel and the readout names one of them. It always names the
pixel whose count it shows.

While a live stream is running, the readout re-reads the hovered pixel as each
frame arrives, so resting the cursor on one pixel shows its counts changing.
When tiling, it reports whichever tile the cursor is over, prefixed with that
frame's name, which need not be the current frame.

## Statistics

The **statistics** tool adds a dock panel summarising the current frame's pixel
values: mean, median, standard deviation, min and max, plus the pixel count.
Enable it with `--enable statistics` or `tools.statistics` in a configuration.

The figures come from the raw array, not the rendered image, so they describe
detector counts and do not move when the display scale changes. Blank pixels
(NaN/inf) are excluded and reported separately, since a single NaN would
otherwise make every statistic NaN.

Recomputing is not free. The median alone costs about ten times the other
statistics put together, roughly 30 ms on a 2048x2048 frame. So while a live
stream is running the panel refreshes at `update_hz` (2 Hz by default) rather
than on every displayed frame. Switching frames by hand still recomputes
immediately, and a hidden panel does no work at all.

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
  statistics: false        # pixel statistics panel
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
  statistics:
    enabled: true
    update_hz: 2.0         # recompute rate while a live stream is running
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

## Reporting Issues

If you encounter any problems or have questions about this project, please open
an issue on the [GitHub Issues page](https://github.com/CaltechOpticalObservatories/atlas/issues).
Your feedback helps us improve the project!
