# Configuration

## How a configuration is resolved

A configuration is resolved from four sources, in increasing order of
precedence:

1. Built-in defaults
2. The `--profile`
3. The `--config` file
4. Command-line overrides (`--mode`, `--tile-columns`, `--enable`, `--disable`)

Each layer overrides the one before it, so `--profile detector --disable zmq`
is exactly the detector profile with one tool switched off.

:::{important}
Unknown keys are **rejected with an error** rather than ignored, so a typo
cannot silently leave a feature switched off. The error names the key and lists
the ones that section does accept:

```text
atlas: unknown key in tools.statistics: update_hertz (known: enabled, update_hz)
```

Values are validated too, and the whole configuration is resolved before any
widget exists. atlas either starts as you asked or exits with status 2.
:::

## A complete file

Every key below is optional; what is shown is the default.

```yaml
window:
  title: atlas
  width_fraction: 0.8       # of the screen, 0.1 to 1.0
  height_fraction: 0.8

display:
  mode: single              # single | tile
  tile_columns: null        # null picks a roughly square grid

tools:
  header: true              # FITS header panel
  histogram: false          # pixel-intensity histograms
  tap_subtraction: false    # COO detector signal/reset taps
  zmq: false                # load frames announced over ZMQ
  shm: false                # live ImageStreamIO shared-memory frames
  statistics: false         # pixel statistics panel
```

## Boolean shorthand

Any tool taking options can be written either as a bare boolean or as a
section. These two are identical:

::::{grid} 1 1 2 2
:gutter: 2

:::{grid-item-card} Shorthand
```yaml
tools:
  statistics: true
```
:::

:::{grid-item-card} Full form
```yaml
tools:
  statistics:
    enabled: true
    update_hz: 2.0
```
:::

::::

Write the section form when you want to change an option, the shorthand when
you only want the tool on. A bare `false` switches a tool off without losing
the defaults for its other keys.

## Section reference

### `window`

| Key | Type | Default | Notes |
| --- | --- | --- | --- |
| `title` | string | `atlas` | Window title |
| `width_fraction` | number | `0.8` | Fraction of screen width, 0.1 to 1.0 |
| `height_fraction` | number | `0.8` | Fraction of screen height, 0.1 to 1.0 |

### `display`

| Key | Type | Default | Notes |
| --- | --- | --- | --- |
| `mode` | `single` or `tile` | `single` | See [](frames) |
| `tile_columns` | integer or `null` | `null` | Positive; `null` picks a square-ish grid |

### `tools.header`

A plain boolean, on by default. Adds the FITS header dock panel described in
[](inspecting.md#header-panel).

### `tools.histogram`

A plain boolean, off by default. Adds **Tools → Histogram…**; see
[](inspecting.md#histograms).

### `tools.statistics`

| Key | Type | Default | Notes |
| --- | --- | --- | --- |
| `enabled` | boolean | `false` | |
| `update_hz` | number | `2.0` | 0.1 to 60; recompute rate during a live stream |

See [](inspecting.md#statistics) for why the rate is capped.

### `tools.tap_subtraction`

| Key | Type | Default | Notes |
| --- | --- | --- | --- |
| `enabled` | boolean | `false` | |
| `tap_width` | integer | `128` | Positive and **even** |
| `num_taps` | integer | `32` | Positive |

See [](detector.md#tap-subtraction).

### `tools.zmq`

| Key | Type | Default | Notes |
| --- | --- | --- | --- |
| `enabled` | boolean | `false` | Needs the `zmq` extra installed |
| `address` | string | `tcp://localhost:5555` | Must contain `://` |
| `socket_type` | `SUB` or `PULL` | `SUB` | |
| `bind` | boolean | `false` | Bind instead of connect |
| `topic` | string | `""` | `SUB` prefix filter; empty means everything |

See [](live.md#zmq).

### `tools.shm`

| Key | Type | Default | Notes |
| --- | --- | --- | --- |
| `enabled` | boolean | `false` | |
| `segment_name` | string | `camera` | Non-empty; the `.im.shm` file's stem |
| `shm_dir` | string | `""` | Empty falls back to `MILK_SHM_DIR`, `/milk/shm`, `/tmp` |
| `display_fps_cap` | number | `15.0` | Positive; adjustable live from the menu |

See [](live.md#shared-memory).

## Bundled profiles

| Profile | Purpose |
| --- | --- |
| `minimal` | Image display only: no panels, no tools |
| `viewer` | General FITS viewing: headers and histograms |
| `detector` | COO detector work: tiled frames, tap subtraction, ZMQ |

`atlas --list-profiles` prints them. The YAML lives in
`src/atlas/config/profiles/`, which is a good place to look when writing your
own: copy the closest one and pass it with `--config`.

## Worked example

An observing configuration that watches a camera live, keeps statistics
updating slowly enough not to fight the display, and leaves ZMQ alone:

```yaml
window:
  title: HISPEC tracking camera
  width_fraction: 0.9
  height_fraction: 0.9

display:
  mode: single

tools:
  header: true
  histogram: true
  statistics:
    enabled: true
    update_hz: 1.0
  shm:
    enabled: true
    segment_name: hispec_tracking_camera
    display_fps_cap: 20.0
```

```sh
atlas --config hispec.yaml
```
