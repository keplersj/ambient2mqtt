"""Environment-driven configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


@dataclass(slots=True)
class Settings:
    # Ambient account
    username: str
    password: str
    auth_url: str = "https://auth.prod.ambientproptech.com"
    device_url: str = "https://device-discovery.prod.ambientproptech.com"

    # MQTT
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_username: str | None = None
    mqtt_password: str | None = None
    mqtt_tls: bool = False

    # Topics / behavior
    base_topic: str = "ambient2mqtt"
    discovery_prefix: str = "homeassistant"
    sync_interval: int = 30
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            username=os.environ.get("AMBIENT_USERNAME", ""),
            password=os.environ.get("AMBIENT_PASSWORD", ""),
            auth_url=os.environ.get("AMBIENT_AUTH_URL", cls.auth_url).rstrip("/"),
            device_url=os.environ.get("AMBIENT_DEVICE_URL", cls.device_url).rstrip("/"),
            mqtt_host=os.environ.get("MQTT_HOST", cls.mqtt_host),
            mqtt_port=int(os.environ.get("MQTT_PORT", cls.mqtt_port)),
            mqtt_username=os.environ.get("MQTT_USERNAME") or None,
            mqtt_password=os.environ.get("MQTT_PASSWORD") or None,
            mqtt_tls=_bool("MQTT_TLS", cls.mqtt_tls),
            base_topic=os.environ.get("BASE_TOPIC", cls.base_topic),
            discovery_prefix=os.environ.get("DISCOVERY_PREFIX", cls.discovery_prefix),
            sync_interval=int(os.environ.get("SYNC_INTERVAL", cls.sync_interval)),
            log_level=os.environ.get("LOG_LEVEL", cls.log_level),
        )
