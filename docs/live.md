# Live streams

atlas can follow a running detector instead of opening files by hand. There are
two ways in, and they solve different problems:

| Tool | Carries | Use it when |
| --- | --- | --- |
| [Shared memory](#shared-memory) | Pixel data, frame by frame | You want to *watch* the detector at video rates |
| [ZMQ](#zmq) | File **names**, not pixels | Something else is writing FITS files and wants atlas to open them |

Both are off by default. A plain local viewing session has no reason to attach
to a segment or open a network socket, so you have to ask.

(shared-memory)=
## Shared memory

The **shm** tool live-displays frames arriving on an
[ImageStreamIO](https://github.com/milk-org/ImageStreamIO) shared-memory
segment, the format `milk` and `camerad` write.

### Turning it on

```yaml
tools:
  shm:
    enabled: true
    segment_name: hispec_tracking_camera
    shm_dir: ""             # empty means "work it out", see below
    display_fps_cap: 15.0
```

```sh
atlas --config observing.yaml
```

Once enabled, the tool adds a **Tools → Shared Memory** submenu:

- **Connect to *segment*** starts reading.
- **Disconnect from SHM** stops.
- **Set display rate…** opens a slider, 1 to 120 Hz.

To keep the image currently on screen, use **File → Save Frame**
(<kbd>Ctrl</kbd>+<kbd>S</kbd>); see [saving frames](frames.md#saving-frames). With
the [save button](configuration.md#toolssave_button) on, a **Frames** box saves
several consecutive frames into one cube.

### Where the segment is looked for

atlas opens `<shm_dir>/<segment_name>.im.shm`, resolving the directory the way
ImageStreamIO itself does. It takes the first of these that exists:

1. The `shm_dir` you configured
2. The `MILK_SHM_DIR` environment variable
3. `/milk/shm`
4. `/tmp`

Leaving `shm_dir` empty is the normal case on a machine where `MILK_SHM_DIR` is
already set for the rest of the toolchain.

### The display rate cap

A detector can produce frames faster than a GUI can draw them; 60 Hz arrival
against a display that needs tens of milliseconds per frame is a losing race.
atlas follows the segment on a background thread but only hands the **latest** frame
to the GUI, no more often than `display_fps_cap` (15 Hz by default). Frames in
between are dropped rather than queued, so the display stays current instead of
falling steadily further behind.

The **Set display rate…** slider changes the cap live, whether or not you are
connected, so you can turn it down when the window starts to feel heavy and back
up when it does not. Turning the cap down does **not** slow the producer or lose
you any data on disk; it only changes how often atlas redraws.

:::{tip}
If you have the [statistics panel](inspecting.md#statistics) open during a live
stream, it has its own, much lower, `update_hz`. That is deliberate: the median
is expensive enough that recomputing it per displayed frame would compete with
drawing the frame.
:::

### Keeping every frame: the capture process

The display can drop frames, but a [multi-frame save](frames.md#saving-several-frames-at-once)
must not, and its keywords have to be each frame's own. Neither waits long:

- A segment holds keywords only for its newest frame. They are rewritten just
  before the next frame is published, which at 1 kHz is under a millisecond
  later.
- The pixels last a little longer if the segment has a ring buffer (its
  `CBsize`), which keeps the last few frames, but only `CBsize − 1` frame
  periods. That is 3 ms at 1 kHz with a ring of 4.

A reader sharing Python with the window cannot keep those deadlines: drawing
holds the interpreter for milliseconds at a time. So when you connect, atlas
also starts a **capture process** with an interpreter of its own. It waits
idle until a multi-frame save starts. Then it watches the frame counter
continuously, copying each frame's keywords and pixels the moment the frame
is published. The frames go straight into shared memory that the window then
writes to the file. A frame published while it was held up is caught up on
from the ring if the ring still holds it, though without keywords of its own.

Nothing about the segment or its producer needs changing. atlas checks the
keywords it copied against ImageStreamIO's own per-keyword write counter. A
copy taken after the next frame's keywords were already written is masked
rather than attached to the wrong frame. Frames or keywords that were missed
are always counted, in the file's `NSKIPPED` and `NKWMISS`, never hidden.

The capture process spins on one CPU core while a save is under way, and only
then.

### Installation notes

There is nothing extra to install. atlas reads the segment directly with `mmap`
and `struct` rather than through `ImageStreamIOWrap`, which needs a from-source
pybind11 and cmake build and does not work on macOS at all, since Darwin has no
`sem_timedwait`. The trade is that atlas polls the frame counter rather than
waiting on the segment's semaphore.

(zmq)=
## ZMQ

The **zmq** tool listens on a ZMQ endpoint for FITS **file names** and loads
each one into a frame. The pixels travel over the filesystem; only the
announcement travels over the socket. That makes it the right tool when some
other process in your pipeline already writes files and simply wants a viewer
to keep up.

It needs the optional dependency:

```sh
pip install -e ".[zmq]"
```

```yaml
tools:
  zmq:
    enabled: true
    address: tcp://localhost:5555
    socket_type: SUB        # SUB or PULL
    bind: false
    topic: ""               # SUB topic filter
```

**Tools → Connect to ZMQ…** prompts for an endpoint, pre-filled with the
configured one, so you can point a configured session somewhere else without
editing anything. **Disconnect from ZMQ** stops listening.

| Setting | Meaning |
| --- | --- |
| `address` | A ZMQ endpoint, such as `tcp://localhost:5555` |
| `socket_type` | `SUB` for a publisher fan-out, `PULL` for a work queue |
| `bind` | `true` to bind the socket instead of connecting to a peer |
| `topic` | Prefix filter, `SUB` sockets only; empty means everything |

Because atlas loads whatever path arrives, the announcing process and atlas
must see the same filesystem. Over NFS, announce the path as atlas will see it,
not as the writer sees it.

## Trying it without a detector

`scripts/demo_shm_viewer.py` launches the real UI against a synthetic producer,
an orbiting bright spot at 60 Hz, so you can see the live path work without a
segment or a camera:

```sh
PYTHONPATH=src python scripts/demo_shm_viewer.py
```

Pass a FITS file as an argument to load it alongside the live view in tile
mode. To try a bundled profile's tools and layout against the feed, name it
with `--profile`; the feed is switched on whatever the profile says:

```sh
PYTHONPATH=src python scripts/demo_shm_viewer.py --profile hispec_fei
```

This is a manual demo, not a test; pytest does not pick it up.
