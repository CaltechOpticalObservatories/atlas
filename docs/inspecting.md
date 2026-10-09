# Inspecting pixels

Four things in atlas report numbers rather than pictures: the hover readout,
the statistics panel, the FITS header panel, and the histogram window. All of
them read the **raw array**, not the rendered image, so none of them move when
you change the [display scale](frames.md#scales).

(hover-readout)=
## Hover readout

Resting the cursor on a pixel puts its index and its count on the right of the
status bar:

```{eval-rst}
.. container:: sample-readout

   ::

      (341, 169)  27,922
```

The indices are 0-based, `x` across and `y` down, so the pair reads directly as
`data[y, x]` in whatever you are inspecting the frame with. This is numpy's
convention rather than DS9's 1-based one, and `y` counts down because atlas
draws the first row of the array at the top of the tile.

The count comes from the raw array, so it is a detector count and does not move
when the display scale changes. Blank pixels (NaN or inf) read as a dash rather
than as a number, and colour frames report one sample per channel.

A frame is usually shown smaller than it is, in which case several data pixels
share one screen pixel and the readout names one of them. It always names the
pixel whose count it shows. [Zooming in](frames.md#zoom) past 1:1 separates
them, so every pixel becomes a block you can point at individually.

The readout is always available: it needs no configuration, adds no panel, and
does no work at all until the cursor is over a frame. It sits beside the status
messages rather than replacing them, so neither overwrites the other.

:::{tip}
While a [live stream](live.md) is running, the readout re-reads the hovered
pixel as each frame arrives, so resting the cursor on one pixel shows its
counts changing. When tiling, it reports whichever tile the cursor is over,
prefixed with that frame's name, which need not be the current frame.
:::

(statistics)=
## Statistics

The **statistics** tool adds a dock panel summarising the current frame's pixel
values: mean, median, standard deviation, variance, min, max and the
flux-weighted centroid, plus counts of the pixels summarised and the blank
pixels left out. A second column gives the same
figures for the frame's [region](#regions), when it has one.

```sh
atlas image.fits --enable statistics
```

```yaml
tools:
  statistics: true
```

The figures come from the raw array, not the rendered image, so they describe
detector counts and do not move when the display scale changes. Blank pixels
(NaN or inf) are excluded and reported separately, since a single NaN would
otherwise make every statistic NaN.

### Why the panel has an update rate

Recomputing is not free. The median alone costs about ten times the other
statistics put together, roughly 30 ms on a 2048x2048 frame. So while a live
stream is running the panel refreshes at `update_hz` (2 Hz by default) rather
than on every displayed frame:

```yaml
tools:
  statistics:
    enabled: true
    update_hz: 2.0      # between 0.1 and 60
```

Switching frames by hand still recomputes immediately, and a hidden panel does
no work at all, so closing the panel is a real way to give the display back its
time budget.

(regions)=
## Regions

Hold <kbd>Shift</kbd> and drag across a frame to draw a box on it. The box is
the frame's **region**, and the statistics panel's **Region** column summarises
just the pixels inside it, beside the whole frame's figures in the **Frame**
column, so a source and its background can be compared at a glance.

The region is drawn in green while you drag and commits when you let go. Both
corner pixels are inside it, and a drag that runs off the image stops at its
edge. Beneath the figures the panel names the region as the numpy slice that
selects it:

```{eval-rst}
.. container:: sample-readout

   ::

      Region: data[3:10, 2:6], 4 × 7
```

so `data[3:10, 2:6]` reproduces the panel's numbers exactly in a notebook.

To remove a region, **Frame → Clear Region**, or Shift+click without dragging.
Drawing a new one replaces it.

Like the zoom, the region belongs to the frame: each tile keeps its own, it
survives switching away and back, and it stays put through each new image of a
[live stream](live.md) while the counts under it change. If a smaller image
arrives, the panel summarises the part of the region still on the frame and
names that slice, not the one you drew; a region left entirely off the edge
says so.

### Flux-weighted centroid

The centroid is where the light in the box is centred, in the same 0-based
`(x, y)` indices as the [hover readout](#hover-readout). Each pixel is weighted
by its counts **above the median** of the box, and pixels below the median count
for nothing.

Subtracting the median is what makes the number useful on a detector. Weighted
by raw counts, a bias of thousands of counts in every pixel outweighs the star,
and the centroid barely moves off the middle of the box wherever the star is.

:::{tip}
Draw the box a few times the width of the source. Noise peaks above the median
carry a little weight too, and because they are spread evenly through the box
they pull the centroid towards its middle: on a noisy frame a box ten times the
star's width can be off by a few tenths of a pixel, where one three to five
times its width is good to a few hundredths. Much tighter than that and the
median rises into the source itself and trims its wings, which costs a little
accuracy again.
:::

The centroid reads as a dash when nothing rises above the median, as on a flat
field, and for colour frames, which have no single flux to weight by.

## Header panel

The **header** tool is the one tool that is on by default. It docks on the
right and shows the FITS header of whichever frame is current, following your
selection as you move between frames.

Hide and show it from the **View** menu, or switch it off entirely:

```sh
atlas image.fits --disable header
```

(histograms)=
## Histograms

The **histogram** tool adds **Tools → Histogram…**, which opens a window
plotting the pixel-value distribution of every frame currently on screen. In
tile mode that means all the tiles, one curve each, which is the quickest way
to see that two frames really do share a bias level.

```sh
atlas image.fits --enable histogram
```

The histogram window has its own **Log count axis** checkbox, independent of
the frame's [scale](frames.md#scales). A pixel histogram is usually dominated
by a single sky or bias peak, and a log count axis is what makes the faint tail
visible. Changing it affects only the plot, never the image.
