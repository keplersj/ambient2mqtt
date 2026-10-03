"""Environment-driven configuration."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

# Defaults live at module level: with @dataclass(slots=True) the class-level
# attribute for a field is the slot descriptor, not its default value, so
# from_env() must reference these constants rather than cls.<field>.
DEFAULT_AUTH_URL = "https://auth.prod.ambientproptech.com"
DEFAULT_DEVICE_URL = "https://device-discovery.prod.ambientproptech.com"
DEFAULT_MQTT_HOST = "localhost"
DEFAULT_MQTT_PORT = 1883
DEFAULT_MQTT_TLS = False
DEFAULT_BASE_TOPIC = "ambient2mqtt"
DEFAULT_DISCOVERY_PREFIX = "homeassistant"
DEFAULT_SYNC_INTERVAL = 30
DEFAULT_LOG_LEVEL = "INFO"


def _bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


_VALID_OVERRIDES = {"light", "fan", "switch"}


def _parse_overrides(raw: str) -> dict[str, str]:
    """Parse DEVICE_OVERRIDES: a JSON object of {deviceId: entity_type}."""
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
        out = {}
        for k, v in data.items():
            v = str(v).lower()
            if v in _VALID_OVERRIDES:
                out[str(k)] = v
            else:
                log.warning("Ignoring device override %s -> %r (not in %s)", k, v, _VALID_OVERRIDES)
        return out
    except Exception as e:  # noqa: BLE001
        log.error("Could not parse DEVICE_OVERRIDES (%s); ignoring", e)
        return {}


@dataclass(slots=True)
class Settings:
    # Ambient account
    username: str
    password: str
    auth_url: str = DEFAULT_AUTH_URL
    device_url: str = DEFAULT_DEVICE_URL

    # MQTT
    mqtt_host: str = DEFAULT_MQTT_HOST
    mqtt_port: int = DEFAULT_MQTT_PORT
    mqtt_username: str | None = None
    mqtt_password: str | None = None
    mqtt_tls: bool = DEFAULT_MQTT_TLS

    # Topics / behavior
    base_topic: str = DEFAULT_BASE_TOPIC
    discovery_prefix: str = DEFAULT_DISCOVERY_PREFIX
    sync_interval: int = DEFAULT_SYNC_INTERVAL
    log_level: str = DEFAULT_LOG_LEVEL

    # Per-device entity-type overrides: {deviceId: "fan"|"switch"|"light"}.
    # e.g. a switch that actually drives a ceiling fan.
    device_overrides: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            device_overrides=_parse_overrides(os.environ.get("DEVICE_OVERRIDES", "")),
            username=os.environ.get("AMBIENT_USERNAME", ""),
            password=os.environ.get("AMBIENT_PASSWORD", ""),
            auth_url=os.environ.get("AMBIENT_AUTH_URL", DEFAULT_AUTH_URL).rstrip("/"),
            device_url=os.environ.get("AMBIENT_DEVICE_URL", DEFAULT_DEVICE_URL).rstrip("/"),
            mqtt_host=os.environ.get("MQTT_HOST", DEFAULT_MQTT_HOST),
            mqtt_port=int(os.environ.get("MQTT_PORT", DEFAULT_MQTT_PORT)),
            mqtt_username=os.environ.get("MQTT_USERNAME") or None,
            mqtt_password=os.environ.get("MQTT_PASSWORD") or None,
            mqtt_tls=_bool("MQTT_TLS", DEFAULT_MQTT_TLS),
            base_topic=os.environ.get("BASE_TOPIC", DEFAULT_BASE_TOPIC),
            discovery_prefix=os.environ.get("DISCOVERY_PREFIX", DEFAULT_DISCOVERY_PREFIX),
            sync_interval=int(os.environ.get("SYNC_INTERVAL", DEFAULT_SYNC_INTERVAL)),
            log_level=os.environ.get("LOG_LEVEL", DEFAULT_LOG_LEVEL),
        )
