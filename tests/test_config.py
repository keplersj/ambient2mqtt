"""Tests for Settings.from_env() (regression for the slots-dataclass default bug)."""

import pytest

from ambient2mqtt import config
from ambient2mqtt.config import Settings

_ENV_VARS = [
    "AMBIENT_USERNAME",
    "AMBIENT_PASSWORD",
    "AMBIENT_AUTH_URL",
    "AMBIENT_DEVICE_URL",
    "MQTT_HOST",
    "MQTT_PORT",
    "MQTT_USERNAME",
    "MQTT_PASSWORD",
    "MQTT_TLS",
    "BASE_TOPIC",
    "DISCOVERY_PREFIX",
    "SYNC_INTERVAL",
    "LOG_LEVEL",
]


@pytest.fixture
def clean_env(monkeypatch):
    for var in _ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def test_from_env_empty_uses_defaults(clean_env):
    # Must not raise (previously: AttributeError on a slot member_descriptor).
    s = Settings.from_env()
    assert s.username == ""
    assert s.password == ""
    assert s.auth_url == config.DEFAULT_AUTH_URL
    assert s.device_url == config.DEFAULT_DEVICE_URL
    assert s.mqtt_host == "localhost"
    assert s.mqtt_port == 1883
    assert isinstance(s.mqtt_port, int)
    assert s.mqtt_username is None
    assert s.mqtt_tls is False
    assert s.base_topic == "ambient2mqtt"
    assert s.discovery_prefix == "homeassistant"
    assert s.sync_interval == 30
    assert s.log_level == "INFO"


def test_from_env_overrides(clean_env, monkeypatch):
    monkeypatch.setenv("AMBIENT_USERNAME", "u@example.com")
    monkeypatch.setenv("AMBIENT_PASSWORD", "pw")
    monkeypatch.setenv("AMBIENT_AUTH_URL", "https://auth.example.com/")  # trailing slash
    monkeypatch.setenv("MQTT_HOST", "mosquitto")
    monkeypatch.setenv("MQTT_PORT", "1884")
    monkeypatch.setenv("MQTT_TLS", "true")
    monkeypatch.setenv("SYNC_INTERVAL", "15")
    s = Settings.from_env()
    assert s.username == "u@example.com"
    assert s.auth_url == "https://auth.example.com"  # rstrip("/")
    assert s.mqtt_host == "mosquitto"
    assert s.mqtt_port == 1884
    assert s.mqtt_tls is True
    assert s.sync_interval == 15
