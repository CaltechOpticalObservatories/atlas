# Detector tools

## Tap subtraction

COO detectors read out in **taps**, and each tap carries a signal half and a
reset half side by side. The **tap_subtraction** tool rebuilds a corrected
frame by gathering the reset halves of one frame, gathering the signal halves
of another, and subtracting one from the other.

This is instrument-specific, so it stays off unless you ask for it:

```yaml
tools:
  tap_subtraction:
    enabled: true
    tap_width: 128        # pixels per tap, must be even
    num_taps: 32
```

Or for a single session:

```sh
atlas signal.fits reset.fits --enable tap_subtraction
```

### Using it

**Tools → Subtract Signal/Reset Taps** operates on the **current frame and the
one before it**: the earlier frame supplies the signal halves, the current one
supplies the reset halves. So you choose the pair with **Frame → Next** and
**Previous** rather than from a dialog, and the result arrives as a new frame.

The difference is computed in `int64`, which matters: reset minus signal is
genuinely signed, and an unsigned accumulator would wrap negative pixels around
to full brightness.

### Geometry, and the errors it produces

The frame has to match the configured geometry. atlas expects a width of
`tap_width * (num_taps + 1)`, the extra tap being the reference tap, and it
says so plainly when the numbers do not line up:

```text
Tap subtraction failed: frame is 2048 px wide but 32 taps of 128 px needs 4224
```

Two other cases you may meet in the status bar:

| Message | Means |
| --- | --- |
| `Tap subtraction needs two frames; open a second image first.` | Only one frame is open |
| `expected a 2D frame, got shape ...` | The frame is a cube or a colour image |

`tap_width` must be even, since each tap splits into two halves; a configuration
with an odd `tap_width` is rejected at startup rather than at the moment you
click the menu item.

## The detector profile

The bundled `detector` profile assembles the pieces a COO detector session
usually wants:

```sh
atlas --profile detector
```

```yaml
display:
  mode: tile
  tile_columns: 1         # signal above reset, not side by side
tools:
  header: true
  histogram: true
  tap_subtraction:
    enabled: true
    tap_width: 128
    num_taps: 32
  zmq:
    enabled: true
    address: tcp://localhost:5555
    socket_type: SUB
  shm:
    enabled: false        # off until verified against a real segment
    segment_name: hispec_tracking_camera
```

Note that `shm` is present but disabled in the shipped profile. Turn it on for
a session with `atlas --profile detector --enable shm`, or copy the profile
into your own `--config` file and set it there along with the right
`segment_name`. See [](live.md#shared-memory).
