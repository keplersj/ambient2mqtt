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


def test_discovery_climate_has_mode_and_temp_commands():
    ((component, cfg),) = build_discovery(THERMOSTAT, **DISCOVERY_KW)
    assert component == "climate"
    assert cfg["temperature_command_topic"] == "ambient2mqtt/dev-thermo/temp/set"
    assert cfg["mode_command_topic"] == "ambient2mqtt/dev-thermo/mode/set"
    assert cfg["modes"] == ["off", "heat", "cool", "auto"]
    assert cfg["fan_mode_command_topic"] == "ambient2mqtt/dev-thermo/fan/set"
    assert cfg["fan_modes"] == ["auto", "on", "circulate"]


# --- device types not present in the author's unit (blind, from the decomp) ---

ACCESS = {
    "deviceId": "dev-contact",
    "spaceId": "space-1",
    "traits": {
        "infoV1": {"model": "contact_sensor", "name": "Patio Door"},
        "accessSensorReadV1": {"status": {"accessSensorState": "ACCESS_SENSOR_STATE_OPEN"}},
    },
}
MOTION = {
    "deviceId": "dev-motion",
    "spaceId": "space-1",
    "traits": {
        "infoV1": {"model": "motion_sensor", "name": "Hall Motion"},
        "motionSensorReadV1": {"status": {"motionSensorState": "MOTION_SENSOR_STATE_ACTIVE"}},
    },
}
LEAK = {
    "deviceId": "dev-leak",
    "traits": {
        "infoV1": {"model": "leak_sensor", "name": "Sink"},
        "leakSensorReadV1": {"status": {"leakSensorState": "LEAK_SENSOR_STATE_DRY"}},
    },
}
# A lock that also reports battery + firmware (fields at the trait root -> exercises the fallback).
LOCK_AUX = {
    "deviceId": "dev-lock2",
    "spaceId": "space-1",
    "traits": {
        "infoV1": {"model": "lock", "name": "Side Door"},
        "lockerReadV1": {"status": {"lockState": "LOCK_STATE_LOCKED"}},
        "powerReadV1": {"batteryLevel": 87},
        "firmwareReadV1": {"version": "1.4.2"},
        "connectivityReadV1": {"status": {"connectivityStatus": "CONNECTIVITY_STATUS_REACHABLE"}},
    },
}


def test_state_access_open():
    assert build_state(ACCESS) == {"state": "ON"}


def test_state_motion_active():
    assert build_state(MOTION) == {"state": "ON"}


def test_state_leak_dry_is_off():
    assert build_state(LEAK) == {"state": "OFF"}


def test_state_unknown_sensor_value_omitted():
    dev = {"deviceId": "d", "traits": {"motionSensorReadV1": {"status": {}}}}
    assert build_state(dev) is None


def test_discovery_access_is_opening_binary_sensor():
    ((component, cfg),) = build_discovery(ACCESS, **DISCOVERY_KW)
    assert component == "binary_sensor"
    assert cfg["device_class"] == "opening"


def test_state_lock_with_aux():
    assert build_state(LOCK_AUX) == {
        "state": "LOCKED",
        "battery": 87,
        "firmware": "1.4.2",
        "connectivity": "ON",
    }


def test_override_switch_to_fan():
    ((component, cfg),) = build_discovery(SWITCH, overrides={"dev-switch": "fan"}, **DISCOVERY_KW)
    assert component == "fan"
    assert cfg["command_topic"] == "ambient2mqtt/dev-switch/set"
    assert cfg["state_value_template"] == "{{ value_json.state }}"
    assert "percentage_command_topic" not in cfg  # on/off switch -> no speed


def test_override_dimmer_to_fan_has_speed():
    ((component, cfg),) = build_discovery(DIMMER, overrides={"dev-dimmer": "fan"}, **DISCOVERY_KW)
    assert component == "fan"
    assert cfg["percentage_command_topic"] == "ambient2mqtt/dev-dimmer/percentage/set"


def test_override_to_switch():
    ((component, _),) = build_discovery(SWITCH, overrides={"dev-switch": "switch"}, **DISCOVERY_KW)
    assert component == "switch"


def test_no_override_stays_light():
    ((component, _),) = build_discovery(SWITCH, **DISCOVERY_KW)
    assert component == "light"


def test_discovery_aux_entities_distinct_ids():
    configs = build_discovery(LOCK_AUX, **DISCOVERY_KW)
    assert {c for c, _ in configs} == {"lock", "sensor", "binary_sensor"}
    uids = {cfg["unique_id"] for _, cfg in configs}
    assert uids == {
        "ambient_dev-lock2",
        "ambient_dev-lock2_battery",
        "ambient_dev-lock2_firmware",
        "ambient_dev-lock2_connectivity",
    }


def test_discovery_unknown_device_empty():
    assert build_discovery(HUB, **DISCOVERY_KW) == []
