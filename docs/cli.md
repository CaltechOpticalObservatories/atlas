# Command line

```text
atlas [files ...] [-c FILE] [-p NAME] [-m MODE] [--tile-columns N]
      [--enable TOOL] [--disable TOOL] [--list-profiles] [-h]
```

Run `atlas --help` for the same list from the program itself.

## Arguments

`files`
: Zero or more FITS files, each opened into its own frame. Shell globs work:
  `atlas *.fits`.

## Options

`-c FILE`, `--config FILE`
: A YAML configuration file. See [](configuration).

`-p NAME`, `--profile NAME`
: One of the bundled profiles: `minimal`, `viewer`, `detector`.

`-m MODE`, `--mode MODE`
: Display mode, `single` or `tile`, overriding the configuration.

`--tile-columns N`
: Columns to use when tiling. Omit it to let atlas pick a roughly square grid.

`--enable TOOL`
: Turn a tool on. Repeatable. Valid names are `header`, `histogram`, `shm`,
  `statistics`, `tap_subtraction`, `zmq`.

`--disable TOOL`
: Turn a tool off. Repeatable.

`--list-profiles`
: Print the bundled profile names and exit, without opening a window.

`-h`, `--help`
: Print usage and exit.

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Normal exit, including `--list-profiles` |
| `2` | The configuration was rejected; the reason is printed to stderr |

A rejected configuration is caught before any widget is created, so atlas
either starts with the features you asked for or does not start at all. It
never opens a window with a feature silently missing.

## Examples

```sh
atlas                              # defaults: single frame, header panel
atlas image.fits                   # open a file straight away
atlas *.fits --mode tile           # every file in its own tile
atlas --profile minimal            # image display and nothing else
atlas --config observing.yaml      # your own configuration
atlas --profile detector --disable zmq
atlas image.fits --enable histogram --enable statistics
```

Running from a checkout without installing:

```sh
PYTHONPATH=src python -m atlas.main --profile viewer image.fits
```
