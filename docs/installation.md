# Installation

## Requirements

atlas needs **Python 3.12 or newer**. Check what you have:

```sh
python --version
```

It draws its window with PyQt5, so it also needs a graphical session. Over SSH
that means X11 forwarding (`ssh -Y`) or a remote desktop; there is no
terminal-only mode.

## Install

From a checkout of the repository:

::::{tab-set}

:::{tab-item} Just atlas
```sh
pip install -e .
```
Everything you need to open FITS files and use the built-in tools.
:::

:::{tab-item} With ZMQ
```sh
pip install -e ".[zmq]"
```
Adds `pyzmq`, needed only for the [ZMQ tool](live.md#zmq), which is off by
default.
:::

:::{tab-item} For development
```sh
pip install -e ".[dev,zmq]"
```
Adds pylint and pytest, the two checks CI runs. See [](development).
:::

::::

A virtual environment is strongly recommended, so atlas and its Qt build stay
out of your system Python:

```sh
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Runtime dependencies are declared in `pyproject.toml`. The `requirements.txt`
at the top of the repository exists only so that `pip install -r
requirements.txt` still does the right thing; it installs atlas in editable
mode with the ZMQ extra.

## Check it worked

Installing puts an `atlas` command on your path:

```sh
atlas --list-profiles
```

`--list-profiles` prints the three bundled profiles and exits without opening a
window, which makes it a good smoke test on a machine with no display:

```text
detector
minimal
viewer
```

Then launch it properly:

```sh
atlas
```

## Running without installing

atlas also runs straight from a checkout:

```sh
PYTHONPATH=src python -m atlas.main --profile viewer image.fits
```

This is handy when you are editing the source and do not want an editable
install in the way, but note that `--profile` still needs the bundled YAML
files in `src/atlas/config/profiles/`, which a checkout always has.

## Optional: ImageStreamIO shared memory

The [shared-memory tool](live.md#shared-memory) reads
[ImageStreamIO](https://github.com/milk-org/ImageStreamIO) segments directly
with `mmap`, so there is **nothing extra to install**: no `ImageStreamIOWrap`,
no pybind11, no cmake build. It does need a producer such as `camerad` writing
to a segment, and a shared-memory directory it can find (see
[](live.md#shared-memory) for how that directory is resolved).

## Next steps

Go to [](quickstart) to open your first image.
