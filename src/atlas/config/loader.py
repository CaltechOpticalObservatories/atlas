# Standard Library Imports
import copy
import os

# Third-Party Library Imports
import yaml

from .schema import from_dict, ConfigError

PROFILE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "profiles")


def available_profiles():
    """Names of the profiles bundled with atlas."""
    if not os.path.isdir(PROFILE_DIR):
        return []
    return sorted(os.path.splitext(name)[0]
                  for name in os.listdir(PROFILE_DIR) if name.endswith(".yaml"))


def profile_path(name):
    """Resolves a profile name to its YAML file."""
    path = os.path.join(PROFILE_DIR, f"{name}.yaml")
    if not os.path.isfile(path):
        raise ConfigError(
            f"unknown profile {name!r}; available: {', '.join(available_profiles()) or 'none'}")
    return path


def read_yaml(path):
    """Reads one YAML configuration file into a dict."""
    if not os.path.isfile(path):
        raise ConfigError(f"configuration file not found: {path}")

    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    except yaml.YAMLError as error:
        raise ConfigError(f"could not parse {path}: {error}") from error

    if data is not None and not isinstance(data, dict):
        raise ConfigError(f"{path} must contain a mapping at the top level")

    return data or {}


def deep_merge(base, override):
    """
    Merges `override` onto `base`, recursing into nested mappings.

    Nested sections merge key by key rather than wholesale, so a config file
    that sets one tool option does not discard the rest of the section.
    """
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def load_config(config_path=None, profile=None, overrides=None):
    """
    Resolves the configuration for a session.

    Precedence, lowest first: schema defaults, the named profile, the config
    file, then command-line overrides.

    Args:
        config_path (str): Path to a YAML configuration file, or None.
        profile (str): Name of a bundled profile, or None.
        overrides (dict): Nested dict of command-line overrides, or None.

    Returns:
        AtlasConfig: the validated configuration.
    """
    data = {}

    if profile:
        data = deep_merge(data, read_yaml(profile_path(profile)))

    if config_path:
        data = deep_merge(data, read_yaml(config_path))

    if overrides:
        data = deep_merge(data, overrides)

    return from_dict(data)
