# Frames, scales and zoom

## Frames

atlas borrows DS9's **frame** concept: each loaded image lives in its own
frame, and the display mode decides how frames appear on screen.

| Mode | What you see | Shortcut |
| --- | --- | --- |
| `single` | One frame at a time | <kbd>Ctrl</kbd>+<kbd>1</kbd> |
| `tile` | Every frame in a grid | <kbd>Ctrl</kbd>+<kbd>2</kbd> |

Move between frames with <kbd>Ctrl</kbd>+<kbd>]</kbd> and
<kbd>Ctrl</kbd>+<kbd>[</kbd>, or click a tile.
<kbd>Ctrl</kbd>+<kbd>W</kbd> closes the current frame, and **Frame → Delete All
Frames** clears the lot.

Set the starting mode from the command line or a configuration:

```sh
atlas *.fits --mode tile
atlas *.fits --mode tile --tile-columns 1
```

`tile_columns` fixes the width of the grid. Left unset (`null`), atlas picks a
roughly square arrangement from however many frames are open, which is usually
what you want; fixing it to `1` gives a single column, which is how the
`detector` profile stacks a signal frame above its reset frame.

(saving)=
## Saving frames

**File → Save Frame** (<kbd>Ctrl</kbd>+<kbd>S</kbd>) writes the current frame
to a FITS file straight away, without asking where. The file holds the frame's
raw data, in its original type, and its header. What you see on screen plays
no part, so the scale and zoom are not baked in and the counts come back
exactly as they went out.

Profiles that switch on [`save_button`](configuration.md#toolssave_button),
such as `hispec_fei`, also show the command as a **Save Frame** button on a
toolbar above the image.

This is chiefly for frames from a [live stream](live.md), which have no file of
their own. The file holds the image on screen at the moment you saved. Its
header holds the segment's keywords, with any name longer than eight characters
written as a `HIERARCH` card.

Every save goes in a directory for the day under the save directory,
`/tmp/data` unless you choose another, named for the moment you saved:

```text
/tmp/data/20261012/20261012_190637.fits
```

Both the date and the time are UTC, following the UT dates observatories file
data under, and a run of saves sorts in the order it was taken. The day's
directory is created on the first save. The status bar shows the full path of
each file written.

A save never replaces an existing file. Two saves within the same second are
both kept, the second as `20261012_190637_2.fits`. If the directory cannot be
created, the status bar says why and nothing is written.

To save somewhere else, set it in the configuration, or for one session on the
command line, or from the running window with **File → Set Save Directory…**:

```yaml
save:
  directory: /data/fei
```

```sh
atlas --profile hispec_fei --save-dir /data/fei
```

A directory picked from the menu lasts until atlas quits; the next launch goes
back to the configured one.

:::{warning}
`/tmp` is cleared on reboot, and on many systems files left there for some
days are removed as well. Choose a permanent save directory, or copy anything
worth keeping out of `/tmp/data`.
:::

(zoom)=
## Zoom

**View → Zoom** magnifies the current frame. Like the scale, the zoom belongs
to the frame rather than to the window, so in `tile` mode one image can be
zoomed into a corner while its neighbour still shows the whole field.

| Command | What it does | Shortcut |
| --- | --- | --- |
| Zoom In | Doubles the magnification | <kbd>Ctrl</kbd>+<kbd>+</kbd> |
| Zoom Out | Halves it | <kbd>Ctrl</kbd>+<kbd>-</kbd> |
| Zoom to Fit | The whole frame in its tile, centred | <kbd>Ctrl</kbd>+<kbd>0</kbd> |
| Actual Pixels | One screen pixel per data pixel | <kbd>Ctrl</kbd>+<kbd>9</kbd> |

The mouse does the same thing more directly: turn the wheel over the image to
zoom about the pixel under the pointer, and drag with the left button to pan a
frame that no longer fits in its tile. Holding <kbd>Shift</kbd> while dragging
draws a [region](inspecting.md#regions) instead of panning.

Frames open fitted to their tile. A configuration can start them magnified
instead, which saves repeating the same keystrokes every session on a detector
nobody looks at whole:

```yaml
display:
  zoom: 4.0      # 1.0 fits the frame to its tile
```

Every bundled profile sets it explicitly, so a profile copied as a starting
point already has the key to edit. It is where new frames *start*, not a floor:
**Zoom to Fit** still shows the whole frame.

A zoom survives everything that does not change the frame: resizing the window,
tiling and untiling, switching scale, and the next image of a
[live stream](live.md), so a detector corner stays under the eye exposure after
exposure.

## Scales

**View → Scale** decides how pixel values map onto the brightness of the
display. It is a property of the frame, not of the window, so in `tile` mode
one image can be shown on a log scale beside another on a linear one.

| Scale | What it does | Shortcut |
| --- | --- | --- |
| `linear` | Brightness proportional to pixel value | <kbd>Ctrl</kbd>+<kbd>3</kbd> |
| `log` | Stretches the faint end, compresses the bright end | <kbd>Ctrl</kbd>+<kbd>4</kbd> |

Both scales first map the frame's own minimum and maximum onto the full display
range, so changing scale never clips a pixel that was visible before; it only
redistributes contrast.

:::{note}
Only the rendered pixmap changes. The raw data is left alone, so switching back
and forth is lossless, and everything that reports numbers (the
[hover readout](inspecting.md#hover-readout), the
[statistics panel](inspecting.md#statistics), the
[histogram](inspecting.md#histograms)) keeps reporting detector counts rather
than display brightness.
:::

### When to reach for log

A log scale earns its keep when one part of the frame is far brighter than the
rest: a saturated star over a faint field, or a bright column in an otherwise
flat bias. On a linear scale the bright feature takes the whole display range
and everything else goes black. Note that this is about *looking* at the frame;
if you want to see how the counts are actually distributed, the
[histogram](inspecting.md#histograms) is the better instrument, and it has its
own independent log option for the count axis.
