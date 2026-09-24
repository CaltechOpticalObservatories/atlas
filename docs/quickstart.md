# Quickstart

This page gets you from an installed copy of atlas to a FITS image on screen,
and names the parts of the window as it goes.

## Open an image

The quickest route is to name the file on the command line:

```sh
atlas image.fits
```

Every file you name gets its own frame:

```sh
atlas bias.fits dark.fits flat.fits
```

Or start empty and use **File → Open Image…** (<kbd>Ctrl</kbd>+<kbd>O</kbd>),
which accepts several files at once, or **File → Open Directory…** to take
every FITS file in a folder.

## Find your way around

| Part of the window | What it is |
| --- | --- |
| The image area | One frame, or a grid of tiles in `tile` mode |
| **File** menu | Opening images and directories, quitting |
| **Frame** menu | Moving between frames, deleting them |
| **View** menu | Single vs tile layout, intensity scale, panel visibility |
| **Tools** menu | Whatever optional tools your configuration switched on |
| Status bar, left | Messages, such as errors from a tool |
| Status bar, right | The [hover readout](inspecting.md#hover-readout) |

An empty **Tools** menu is normal on a default launch: every tool except the
header panel is opt-in. See [](configuration) for how to turn them on.

## The shortcuts worth learning first

| Shortcut | Does |
| --- | --- |
| <kbd>Ctrl</kbd>+<kbd>O</kbd> | Open image |
| <kbd>Ctrl</kbd>+<kbd>1</kbd> | Show one frame at a time |
| <kbd>Ctrl</kbd>+<kbd>2</kbd> | Tile every frame |
| <kbd>Ctrl</kbd>+<kbd>]</kbd> | Next frame |
| <kbd>Ctrl</kbd>+<kbd>[</kbd> | Previous frame |
| <kbd>Ctrl</kbd>+<kbd>3</kbd> | Linear scale |
| <kbd>Ctrl</kbd>+<kbd>4</kbd> | Log scale |
| <kbd>Ctrl</kbd>+<kbd>W</kbd> | Close the current frame |
| <kbd>Ctrl</kbd>+<kbd>Q</kbd> | Quit |

## Compare two images

Open both, then tile them and step between them:

```sh
atlas bias.fits dark.fits --mode tile
```

In tile mode the scale belongs to each frame separately, so you can put one
image on a log scale beside another on a linear one. Hover anywhere and the
status bar names the tile the cursor is over as well as the pixel.

## Turn a tool on for one session

You do not need a configuration file to try a tool. `--enable` takes any tool
name:

```sh
atlas image.fits --enable histogram --enable statistics
```

`--disable` does the reverse, which is useful for stripping a panel out of a
profile you otherwise want:

```sh
atlas --profile detector --disable zmq
```

## Start from a profile

Three profiles ship with atlas:

```sh
atlas --profile minimal      # image display, nothing else
atlas --profile viewer       # headers and histograms
atlas --profile detector     # tiled frames, tap subtraction, ZMQ
```

`atlas --list-profiles` prints the list, and `atlas --help` prints the full
command line. When a profile is close but not quite right, copy it into your
own YAML file and pass `--config`; [](configuration) covers the format.

## Next steps

- [](frames) for frames, layouts, and intensity scales
- [](inspecting) for reading pixel values and summary statistics
- [](live) for following a detector in real time
