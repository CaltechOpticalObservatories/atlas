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

### Saving several frames at once

With shared memory switched on, the toolbar also has a **Frames** box beside
the Save Frame button. At 1, saving works as above. Set it higher, say 50, and
a save takes the **next** 50 frames off the stream and writes them to one file,
a cube of shape (50, height, width). The menu command and
<kbd>Ctrl</kbd>+<kbd>S</kbd> follow the box too.

The frames are kept by a [capture process](live.md#keeping-every-frame-the-capture-process)
of atlas's own, not taken from the display, so they are consecutive frames
from the detector even when the [display rate](live.md#the-display-rate-cap) is
far below the frame rate. The status bar counts them in (`saving frame 12 of 50`), and the file is named for
the moment you pressed Save. Once all the frames are in, the file is written in
the background (`writing 20261012_190637.fits…`), so the window stays usable
however large the cube; the next multi-frame save waits until it is done.

The cube's header is the first frame's keywords. Each frame's own keywords,
and its `cnt0` frame counter from the segment, go in a table extension named
`FRAMES`, one row per frame:

```python
from astropy.io import fits

cube = fits.getdata("20261012_190637.fits")              # (50, height, width)
frames = fits.getdata("20261012_190637.fits", "FRAMES")  # one row per plane
```

Every row's keywords are the ones that frame was published with, so `FRAMENO`
and friends can be relied on for timing. A segment holds keywords only for its
newest frame, so the capture process copies them the moment each frame
appears. When it could not, because it was held up past the next frame, the
row's keyword values are masked: they read back as blank or `None`, never a
neighbour's. The header's `NKWMISS` counts such frames, and the status bar
says so. Each frame's pixels and `cnt0` are always its own.

If the detector outruns the capture and frames go by unread, the gaps in `cnt0`
show where, the header's `NSKIPPED` says how many, and the status bar warns you.
Disconnecting before the count is reached cancels the save and writes nothing.

#### How many frames fit

Every frame of a save is held in memory until the file is written, so the
Frames box goes only as high as fits in memory. The limit is worked out from
the segment's frame size when atlas connects, so the box stays at 1 until then.
Hover over the box to see the limit and how it was worked out.

```text
limit = (free memory × capture_memory_fraction − 64 MB) ÷ bytes per frame
```

`capture_memory_fraction` is 0.5 unless the
[configuration](configuration.md#toolsshm) says otherwise, and the 64 MB is
what writing the cube out needs on top of it. Each frame costs its pixels plus
a copy of the segment's keywords, 128 bytes for each keyword. A 256×256 `uint16`
frame is 128 KB, so 16 GB free allows about 65,000 frames. On Linux the frames
are held in `/dev/shm`, so the limit is also kept within
`capture_memory_fraction` of the space free there. Free memory is checked
again when you press Save. If it has dropped below what the count needs, the
save is refused with the new limit rather than started.

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
