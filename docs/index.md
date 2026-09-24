# atlas

**atlas** is a Python GUI for viewing FITS images, in the spirit of
[SAOImage DS9](https://sites.google.com/cfa.harvard.edu/saoimageds9).

It opens files into *frames*, shows them singly or tiled, and lets you read
individual pixel counts straight off the image. Everything beyond the image
itself is a **tool** you switch on, so a default launch stays a plain viewer
rather than a wall of panels.

```sh
pip install -e .
atlas image.fits
```

::::{grid} 1 1 2 2
:gutter: 3

:::{grid-item-card} {octicon}`download` Install
:link: installation
:link-type: doc

Get atlas onto your machine, with or without the optional ZMQ support.
:::

:::{grid-item-card} {octicon}`rocket` Quickstart
:link: quickstart
:link-type: doc

Open your first image and find your way around the window in five minutes.
:::

:::{grid-item-card} {octicon}`image` Viewing images
:link: frames
:link-type: doc

Frames, single and tiled layouts, and the linear and log intensity scales.
:::

:::{grid-item-card} {octicon}`graph` Inspecting pixels
:link: inspecting
:link-type: doc

The hover readout, the statistics panel, headers, and histograms.
:::

:::{grid-item-card} {octicon}`broadcast` Live streams
:link: live
:link-type: doc

Follow a detector in real time over shared memory or ZMQ.
:::

:::{grid-item-card} {octicon}`gear` Configuration
:link: configuration
:link-type: doc

Profiles, YAML files, and command-line overrides, in precedence order.
:::

::::

## Where to go next

If you have never run atlas before, start with [](installation) and then
[](quickstart). If you are setting it up for an instrument, the pages you want
are [](live) and [](configuration).

```{toctree}
:hidden:
:caption: Getting started

installation
quickstart
```

```{toctree}
:hidden:
:caption: User guide

frames
inspecting
live
detector
```

```{toctree}
:hidden:
:caption: Reference

cli
configuration
```

```{toctree}
:hidden:
:caption: Development

development
```
