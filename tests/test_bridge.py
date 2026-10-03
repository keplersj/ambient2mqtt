"""Unit tests for the pure state/discovery mapping functions (no network, no creds)."""

from ambient2mqtt.bridge import build_discovery, build_state

DIMMER = {
    "deviceId": "dev-dimmer",
    "spaceId": "space-1",
    "traits": {
        "infoV1": {"make": "z_wave", "model": "dimmer", "name": "Master Bedroom"},
        "lightReadV1": {
            "capability": "LIGHT_CAPABILITY_TYPE_DIMMER",
            "status": {"lightState": "LIGHT_STATE_ON", "levelPercentInt": 30},
        },
        "lightControlV1": {},
    },
}
SWITCH = {
    "deviceId": "dev-switch",
    "spaceId": "space-1",
    "traits": {
        "infoV1": {"model": "switch", "name": "Hallway"},
        "lightReadV1": {
            "capability": "LIGHT_CAPABILITY_TYPE_ON_OFF",
            "status": {"lightState": "LIGHT_STATE_OFF"},
        },
    },
}
LOCK = {
    "deviceId": "dev-lock",
    "spaceId": "space-1",
    "traits": {
        "infoV1": {"model": "lock", "name": "Front Door"},
        "lockerReadV1": {"status": {"lockState": "LOCK_STATE_UNLOCKED"}},
    },
}
THERMOSTAT = {
    "deviceId": "dev-thermo",
    "spaceId": "space-1",
    "traits": {
        "infoV1": {"model": "thermostat", "name": "Kitchen"},
        "thermostatReadV1": {
            "status": {
                "hvacMode": "HVAC_MODE_COOL",
                "targetTemperatureCoolCelsius": 20.56,
                "targetTemperatureHeatCelsius": 18.33,
                "ambientTemperatureCelsius": 20.56,
            }
        },
    },
}
HUB = {"deviceId": "dev-hub", "traits": {"infoV1": {"model": "hub", "name": "Level Hub"}}}

SPACES = {"space-1": "B210"}
DISCOVERY_KW = {
    "base": "ambient2mqtt",
    "discovery_prefix": "homeassistant",
    "availability_topic": "ambient2mqtt/bridge/availability",
    "space_names": SPACES,
}


def test_state_dimmer_on_with_brightness():
    assert build_state(DIMMER) == {"state": "ON", "brightness": 30}


def test_state_switch_off_no_brightness():
    assert build_state(SWITCH) == {"state": "OFF"}


def test_state_lock_unlocked():
    assert build_state(LOCK) == {"state": "UNLOCKED"}


def test_state_thermostat_cool_uses_cooling_setpoint():
    s = build_state(THERMOSTAT)
    assert s["mode"] == "cool"
    assert s["current_temperature"] == 20.56
    assert s["temperature"] == 20.56


def test_state_unknown_device_is_none():
    assert build_state(HUB) is None


def test_discovery_dimmer_is_json_light_with_brightness():
    ((component, cfg),) = build_discovery(DIMMER, **DISCOVERY_KW)
    assert component == "light"
    assert cfg["schema"] == "json"
    assert cfg["brightness"] is True
    assert cfg["brightness_scale"] == 100
    assert cfg["unique_id"] == "ambient_dev-dimmer"
    assert cfg["command_topic"] == "ambient2mqtt/dev-dimmer/set"
    # clean single name: use device name, not a duplicated entity name
    assert cfg["name"] is None
    assert cfg["has_entity_name"] is True
    assert cfg["device"]["suggested_area"] == "B210"


def test_discovery_switch_has_no_brightness():
    ((_, cfg),) = build_discovery(SWITCH, **DISCOVERY_KW)
    assert "brightness" not in cfg


def test_discovery_lock_payloads():
    ((component, cfg),) = build_discovery(LOCK, **DISCOVERY_KW)
    assert component == "lock"
    assert cfg["payload_lock"] == "LOCK"
    assert cfg["payload_unlock"] == "UNLOCK"


def test_discovery_climate_temperature_command_only():
    ((component, cfg),) = build_discovery(THERMOSTAT, **DISCOVERY_KW)
    assert component == "climate"
    assert cfg["temperature_command_topic"] == "ambient2mqtt/dev-thermo/temp/set"
    # mode is read-only (the setpoint API carries no HVAC-mode field)
    assert "mode_command_topic" not in cfg


def test_discovery_unknown_device_empty():
    assert build_discovery(HUB, **DISCOVERY_KW) == []
