"""ambient2mqtt -- Ambient Smart Home (Level) to MQTT bridge with Home Assistant autodiscovery."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("ambient2mqtt")
except PackageNotFoundError:  # running from a source checkout without install
    __version__ = "0.0.0+dev"

__all__ = ["__version__"]
