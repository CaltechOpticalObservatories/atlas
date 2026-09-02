# Standard Library Imports
from dataclasses import dataclass, field, fields, is_dataclass
from typing import Optional


class ConfigError(ValueError):
    """Raised when a configuration file or command-line override is not valid."""


DISPLAY_MODES = ("single", "tile")
ZMQ_SOCKET_TYPES = ("SUB", "PULL")


@dataclass
class WindowConfig:
    """Size and titling of the main window."""
    title: str = "atlas"
    width_fraction: float = 0.8
    height_fraction: float = 0.8

    def validate(self, path):
        for name in ("width_fraction", "height_fraction"):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or not 0.1 <= value <= 1.0:
                raise ConfigError(
                    f"{path}.{name} must be a number between 0.1 and 1.0, got {value!r}")


@dataclass
class DisplayConfig:
    """How loaded frames are laid out."""
    mode: str = "single"
    # None means "choose a roughly square grid from the frame count".
    tile_columns: Optional[int] = None

    def validate(self, path):
        if self.mode not in DISPLAY_MODES:
            raise ConfigError(
                f"{path}.mode must be one of {', '.join(DISPLAY_MODES)}, got {self.mode!r}")
        if self.tile_columns is not None:
            if not isinstance(self.tile_columns, int) or self.tile_columns < 1:
                raise ConfigError(
                    f"{path}.tile_columns must be a positive integer or null, "
                    f"got {self.tile_columns!r}")


@dataclass
class TapSubtractionConfig:
    """
    Signal/reset tap subtraction for COO detector frames.

    This is instrument-specific, so it stays off unless a configuration asks
    for it; when disabled the feature is never constructed at all.
    """
    enabled: bool = False
    tap_width: int = 128
    num_taps: int = 32

    def validate(self, path):
        for name in ("tap_width", "num_taps"):
            value = getattr(self, name)
            if not isinstance(value, int) or value < 1:
                raise ConfigError(f"{path}.{name} must be a positive integer, got {value!r}")
        if self.tap_width % 2:
            raise ConfigError(
                f"{path}.tap_width must be even -- each tap splits into a signal "
                f"and a reset half, got {self.tap_width}")


@dataclass
class ZmqConfig:
    """
    Receives file names to display over ZMQ.

    Off by default: it opens a network socket, which a plain local viewing
    session has no reason to do.
    """
    enabled: bool = False
    address: str = "tcp://localhost:5555"
    socket_type: str = "SUB"
    bind: bool = False
    topic: str = ""

    def validate(self, path):
        if self.socket_type not in ZMQ_SOCKET_TYPES:
            raise ConfigError(
                f"{path}.socket_type must be one of {', '.join(ZMQ_SOCKET_TYPES)}, "
                f"got {self.socket_type!r}")
        if not isinstance(self.address, str) or "://" not in self.address:
            raise ConfigError(
                f"{path}.address must be a ZMQ endpoint such as "
                f"tcp://localhost:5555, got {self.address!r}")
        if not isinstance(self.bind, bool):
            raise ConfigError(f"{path}.bind must be true or false, got {self.bind!r}")


@dataclass
class ShmConfig:
    """
    Live-displays frames arriving on an ImageStreamIO shared-memory segment.

    Off by default: attaching to a segment assumes a running producer
    (camerad); a plain local viewing session has no reason to do that.
    """
    enabled: bool = False
    segment_name: str = "camera"
    shm_dir: str = ""
    display_fps_cap: float = 15.0

    def validate(self, path):
        if not isinstance(self.segment_name, str) or not self.segment_name:
            raise ConfigError(
                f"{path}.segment_name must be a non-empty string, got {self.segment_name!r}")
        if not isinstance(self.shm_dir, str):
            raise ConfigError(f"{path}.shm_dir must be a string, got {self.shm_dir!r}")
        if not isinstance(self.display_fps_cap, (int, float)) or self.display_fps_cap <= 0:
            raise ConfigError(
                f"{path}.display_fps_cap must be a positive number, got {self.display_fps_cap!r}")


@dataclass
class ToolsConfig:
    """
    Optional tools. Everything here is opt-in so that a default launch stays a
    plain image viewer rather than accumulating panels.
    """
    header: bool = True
    histogram: bool = False
    tap_subtraction: TapSubtractionConfig = field(default_factory=TapSubtractionConfig)
    zmq: ZmqConfig = field(default_factory=ZmqConfig)
    shm: ShmConfig = field(default_factory=ShmConfig)

    def enabled_names(self):
        """Names of the tools this configuration switches on."""
        names = []
        for tool in fields(self):
            value = getattr(self, tool.name)
            if getattr(value, "enabled", value):
                names.append(tool.name)
        return names

    def validate(self, path):
        for name in ("header", "histogram"):
            value = getattr(self, name)
            if not isinstance(value, bool):
                raise ConfigError(f"{path}.{name} must be true or false, got {value!r}")
        self.tap_subtraction.validate(f"{path}.tap_subtraction")
        self.zmq.validate(f"{path}.zmq")
        self.shm.validate(f"{path}.shm")


@dataclass
class AtlasConfig:
    """The complete resolved configuration for one atlas session."""
    window: WindowConfig = field(default_factory=WindowConfig)
    display: DisplayConfig = field(default_factory=DisplayConfig)
    tools: ToolsConfig = field(default_factory=ToolsConfig)

    def validate(self):
        self.window.validate("window")
        self.display.validate("display")
        self.tools.validate("tools")
        return self


def build(section, data, path):
    """
    Builds a config dataclass from a plain dict, rejecting unknown keys.

    Unknown keys are an error rather than being ignored: a typo in a config
    file would otherwise silently leave a feature switched off with no clue why.
    """
    if data is None:
        return section()
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must be a mapping, got {type(data).__name__}")

    known = {f.name: f for f in fields(section)}
    unknown = sorted(set(data) - set(known))
    if unknown:
        raise ConfigError(
            f"unknown key{'s' if len(unknown) > 1 else ''} in {path}: "
            f"{', '.join(unknown)} (known: {', '.join(sorted(known))})")

    values = {}
    for name, value in data.items():
        field_type = known[name].type
        if isinstance(value, bool) and is_dataclass_shorthand(field_type):
            # Allow `tap_subtraction: true` as shorthand for `{enabled: true}`.
            # This must be tried before recursing, or the bool is rejected as
            # "not a mapping".
            values[name] = field_type(enabled=value)
        elif is_dataclass(field_type):
            values[name] = build(field_type, value, f"{path}.{name}")
        else:
            values[name] = value

    return section(**values)


def is_dataclass_shorthand(field_type):
    """True for nested sections that accept a bare boolean as `enabled`."""
    return is_dataclass(field_type) and any(f.name == "enabled" for f in fields(field_type))


def from_dict(data):
    """Builds and validates an AtlasConfig from a nested dict."""
    if data is None:
        return AtlasConfig().validate()
    if not isinstance(data, dict):
        raise ConfigError(f"configuration must be a mapping, got {type(data).__name__}")

    known = {f.name for f in fields(AtlasConfig)}
    unknown = sorted(set(data) - known)
    if unknown:
        raise ConfigError(
            f"unknown top-level section{'s' if len(unknown) > 1 else ''}: "
            f"{', '.join(unknown)} (known: {', '.join(sorted(known))})")

    return AtlasConfig(
        window=build(WindowConfig, data.get("window"), "window"),
        display=build(DisplayConfig, data.get("display"), "display"),
        tools=build(ToolsConfig, data.get("tools"), "tools"),
    ).validate()
