# Frames and scales

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
