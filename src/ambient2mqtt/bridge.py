"""MQTT bridge with Home Assistant MQTT autodiscovery.

Topic tree:
    <base>/bridge/availability              online/offline (LWT, retained)
    <base>/<device_id>/state                device state JSON (retained)
    <base>/<device_id>/set                  light JSON / lock LOCK|UNLOCK command
    <base>/<device_id>/temp/set             climate target-temperature command
    <discovery_prefix>/<component>/ambient_<device_id>/config   HA discovery (retained)
"""

from __future__ import annotations

import asyncio
import json
import logging

import paho.mqtt.client as mqtt

from .client import AmbientClient
from .config import Settings

log = logging.getLogger(__name__)

# Supported HA climate modes (match what the Ambient app exposes + what we can set).
CLIMATE_MODES = ["off", "heat", "cool", "auto"]

# Device read state (hvacMode) -> HA mode. Collapse to the settable set above.
HVAC_TO_HA = {
    "HVAC_MODE_OFF": "off",
    "HVAC_MODE_COOL": "cool",
    "HVAC_MODE_HEAT": "heat",
    "HVAC_MODE_AUTO": "auto",
    "HVAC_MODE_HEAT_COOL": "auto",
    "HVAC_MODE_ECO": "auto",
}

# HA mode -> Ambient SetSystemMode enum.
HA_TO_SYSTEM = {
    "off": "SYSTEM_MODE_OFF",
    "heat": "SYSTEM_MODE_HEAT",
    "cool": "SYSTEM_MODE_COOL",
    "auto": "SYSTEM_MODE_AUTO",
}


def _info(dev: dict) -> dict:
    return dev.get("traits", {}).get("infoV1", {})


def _field(dev: dict, trait_key: str, field: str):
    """Read a trait field, tolerating either a nested `status` object or a flat trait."""
    t = dev.get("traits", {}).get(trait_key, {})
    status = t.get("status") if isinstance(t, dict) else None
    if isinstance(status, dict) and field in status:
        return status[field]
    return t.get(field) if isinstance(t, dict) else None


def _binary(value, on_value: str) -> str | None:
    """Map an enum string to ON/OFF, or None when unknown/unset."""
    if not value:
        return None
    return "ON" if value == on_value else "OFF"


def _connectivity(dev: dict) -> str | None:
    cs = _field(dev, "connectivityReadV1", "connectivityStatus")
    if cs:
        return "ON" if cs == "CONNECTIVITY_STATUS_REACHABLE" else "OFF"
    r = _field(dev, "reachabilityReadV1", "reachable")
    if isinstance(r, bool):
        return "ON" if r else "OFF"
    return None


FAN_TO_HA = {
    "FAN_MODE_AUTO": "auto",
    "FAN_MODE_ON": "on",
    "FAN_MODE_CIRCULATE": "circulate",
    "FAN_MODE_OFF": "off",
}
HA_TO_FAN = {"auto": "FAN_MODE_AUTO", "on": "FAN_MODE_ON", "circulate": "FAN_MODE_CIRCULATE"}
FAN_MODES = ["auto", "on", "circulate"]

# Primary binary-sensor device types: World trait key -> (state field, ON enum, HA device_class).
# These are implemented from the decompiled schema; only light/lock/thermostat/motion are
# exercised against real hardware, so the rest are best-effort for downstream devices.
_BINARY_PRIMARY = {
    "motionSensorReadV1": ("motionSensorState", "MOTION_SENSOR_STATE_ACTIVE", "motion"),
    "leakSensorReadV1": ("leakSensorState", "LEAK_SENSOR_STATE_WET", "moisture"),
    "accessSensorReadV1": ("accessSensorState", "ACCESS_SENSOR_STATE_OPEN", "opening"),
    "binarySensorReadV1": ("binarySensorState", "BINARY_SENSOR_STATE_ON", None),
}


def build_state(dev: dict) -> dict | None:
    """Translate an Ambient device's read traits into an HA MQTT state payload."""
    traits = dev.get("traits", {})
    out: dict = {}

    if "lightReadV1" in traits:
        st = traits["lightReadV1"].get("status", {})
        out["state"] = "ON" if st.get("lightState") == "LIGHT_STATE_ON" else "OFF"
        if "levelPercentInt" in st:
            out["brightness"] = st["levelPercentInt"]
    elif "lockerReadV1" in traits:
        ls = _field(dev, "lockerReadV1", "lockState")
        out["state"] = "LOCKED" if ls == "LOCK_STATE_LOCKED" else "UNLOCKED"
    elif "thermostatReadV1" in traits:
        st = traits["thermostatReadV1"].get("status", {})
        mode = HVAC_TO_HA.get(st.get("hvacMode", ""), "off")
        out["mode"] = mode
        out["current_temperature"] = st.get("ambientTemperatureCelsius")
        out["temperature"] = (
            st.get("targetTemperatureHeatCelsius")
            if mode == "heat"
            else st.get("targetTemperatureCoolCelsius")
        )
        fan = FAN_TO_HA.get(_field(dev, "thermostatReadV1", "fanMode"))
        if fan:
            out["fan_mode"] = fan
    else:
        for key, (field, on_val, _dc) in _BINARY_PRIMARY.items():
            if key in traits:
                state = _binary(_field(dev, key, field), on_val)
                if state is not None:
                    out["state"] = state
                break

    # Auxiliary attributes that ride alongside the primary entity on many devices.
    battery = _field(dev, "powerReadV1", "batteryLevel")
    if isinstance(battery, (int, float)):
        out["battery"] = battery
    conn = _connectivity(dev)
    if conn is not None:
        out["connectivity"] = conn
    fw = _field(dev, "firmwareReadV1", "version")
    if fw:
        out["firmware"] = fw

    return out or None


def build_discovery(
    dev: dict,
    *,
    base: str,
    discovery_prefix: str,
    availability_topic: str,
    space_names: dict[str, str],
    overrides: dict[str, str] | None = None,
) -> list[tuple[str, dict]]:
    """Return a list of (component, discovery-payload) for a device, or []."""
    did = dev["deviceId"]
    override = (overrides or {}).get(did)
    traits = dev.get("traits", {})
    info = _info(dev)
    state_t = f"{base}/{did}/state"
    set_t = f"{base}/{did}/set"

    device_block: dict = {
        "identifiers": [f"ambient_{did}"],
        "name": info.get("name") or did,
        "manufacturer": "Ambient / Level",
        "model": info.get("model", "device"),
    }
    area = space_names.get(dev.get("spaceId", ""))
    if area:
        device_block["suggested_area"] = area

    common = {
        "unique_id": f"ambient_{did}",
        "name": None,
        "has_entity_name": True,
        "availability_topic": availability_topic,
        "device": device_block,
    }

    configs: list[tuple[str, dict]] = []

    # --- primary entity ---
    if "lightReadV1" in traits:
        is_dimmer = traits["lightReadV1"].get("capability") == "LIGHT_CAPABILITY_TYPE_DIMMER"
        if override == "fan":
            cfg = {
                **common,
                "state_topic": state_t,
                "state_value_template": "{{ value_json.state }}",
                "command_topic": set_t,
                "payload_on": "ON",
                "payload_off": "OFF",
            }
            if is_dimmer:  # map the dimmer level to fan speed
                cfg["percentage_state_topic"] = state_t
                cfg["percentage_value_template"] = "{{ value_json.brightness | default(0) }}"
                cfg["percentage_command_topic"] = f"{base}/{did}/percentage/set"
                cfg["speed_range_min"] = 1
                cfg["speed_range_max"] = 100
            configs.append(("fan", cfg))
        elif override == "switch":
            configs.append(
                (
                    "switch",
                    {
                        **common,
                        "state_topic": state_t,
                        "value_template": "{{ value_json.state }}",
                        "command_topic": set_t,
                        "payload_on": "ON",
                        "payload_off": "OFF",
                        "state_on": "ON",
                        "state_off": "OFF",
                    },
                )
            )
        else:
            cfg = {**common, "schema": "json", "state_topic": state_t, "command_topic": set_t}
            if is_dimmer:
                cfg["brightness"] = True
                cfg["brightness_scale"] = 100
            configs.append(("light", cfg))
    elif "lockerReadV1" in traits:
        configs.append(
            (
                "lock",
                {
                    **common,
                    "state_topic": state_t,
                    "command_topic": set_t,
                    "value_template": "{{ value_json.state }}",
                    "state_locked": "LOCKED",
                    "state_unlocked": "UNLOCKED",
                    "payload_lock": "LOCK",
                    "payload_unlock": "UNLOCK",
                },
            )
        )
    elif "thermostatReadV1" in traits:
        configs.append(
            (
                "climate",
                {
                    **common,
                    "current_temperature_topic": state_t,
                    "current_temperature_template": "{{ value_json.current_temperature }}",
                    "mode_state_topic": state_t,
                    "mode_state_template": "{{ value_json.mode }}",
                    "mode_command_topic": f"{base}/{did}/mode/set",
                    "modes": CLIMATE_MODES,
                    "fan_mode_state_topic": state_t,
                    "fan_mode_state_template": "{{ value_json.fan_mode }}",
                    "fan_mode_command_topic": f"{base}/{did}/fan/set",
                    "fan_modes": FAN_MODES,
                    "temperature_state_topic": state_t,
                    "temperature_state_template": "{{ value_json.temperature }}",
                    "temperature_command_topic": f"{base}/{did}/temp/set",
                    "temperature_unit": "C",
                    "temp_step": 0.5,
                },
            )
        )
    else:
        for key, (_field_name, _on, device_class) in _BINARY_PRIMARY.items():
            if key in traits:
                cfg = {
                    **common,
                    "state_topic": state_t,
                    "value_template": "{{ value_json.state }}",
                    "payload_on": "ON",
                    "payload_off": "OFF",
                }
                if device_class:
                    cfg["device_class"] = device_class
                configs.append(("binary_sensor", cfg))
                break

    # --- auxiliary diagnostic entities (battery / connectivity / firmware) ---
    def aux(suffix: str, name: str, component: str, extra: dict) -> tuple[str, dict]:
        return (
            component,
            {
                "unique_id": f"ambient_{did}_{suffix}",
                "name": name,
                "has_entity_name": True,
                "availability_topic": availability_topic,
                "state_topic": state_t,
                "entity_category": "diagnostic",
                "device": device_block,
                **extra,
            },
        )

    if "powerReadV1" in traits:
        configs.append(
            aux(
                "battery",
                "Battery",
                "sensor",
                {
                    "device_class": "battery",
                    "unit_of_measurement": "%",
                    "value_template": "{{ value_json.battery }}",
                },
            )
        )
    if "connectivityReadV1" in traits or "reachabilityReadV1" in traits:
        configs.append(
            aux(
                "connectivity",
                "Connectivity",
                "binary_sensor",
                {
                    "device_class": "connectivity",
                    "payload_on": "ON",
                    "payload_off": "OFF",
                    "value_template": "{{ value_json.connectivity }}",
                },
            )
        )
    if "firmwareReadV1" in traits:
        configs.append(
            aux(
                "firmware",
                "Firmware",
                "sensor",
                {
                    "value_template": "{{ value_json.firmware }}",
                },
            )
        )

    return configs


class Bridge:
    def __init__(self, client: AmbientClient, settings: Settings) -> None:
        self.client = client
        self.s = settings
        self.avail_topic = f"{settings.base_topic}/bridge/availability"
        self._loop: asyncio.AbstractEventLoop | None = None
        self._connected = asyncio.Event()
        self._space_names: dict[str, str] = {}
        self._devices: dict[str, dict] = {}

        try:
            self.mqtt = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id="ambient2mqtt")
        except AttributeError:  # paho-mqtt 1.x
            self.mqtt = mqtt.Client(client_id="ambient2mqtt")
        self.mqtt.on_connect = self._on_connect
        self.mqtt.on_disconnect = self._on_disconnect
        self.mqtt.on_message = self._on_message
        if settings.mqtt_username:
            self.mqtt.username_pw_set(settings.mqtt_username, settings.mqtt_password or "")
        if settings.mqtt_tls:
            self.mqtt.tls_set()
        self.mqtt.will_set(self.avail_topic, "offline", qos=1, retain=True)

    async def connect(self) -> None:
        self._loop = asyncio.get_running_loop()
        log.info("Connecting to MQTT %s:%s", self.s.mqtt_host, self.s.mqtt_port)
        self.mqtt.connect_async(self.s.mqtt_host, self.s.mqtt_port, keepalive=60)
        self.mqtt.loop_start()
        await asyncio.wait_for(self._connected.wait(), timeout=30)
        self.mqtt.publish(self.avail_topic, "online", qos=1, retain=True)

    def _on_connect(self, client, userdata, flags, rc):  # noqa: ANN001
        if rc == 0:
            log.info("MQTT connected")
            client.subscribe(f"{self.s.base_topic}/+/set")
            client.subscribe(f"{self.s.base_topic}/+/temp/set")
            client.subscribe(f"{self.s.base_topic}/+/mode/set")
            client.subscribe(f"{self.s.base_topic}/+/fan/set")
            client.subscribe(f"{self.s.base_topic}/+/percentage/set")
            if self._loop:
                self._loop.call_soon_threadsafe(self._connected.set)
        else:
            log.error("MQTT connect failed rc=%s", rc)

    def _on_disconnect(self, client, userdata, rc):  # noqa: ANN001
        log.warning("MQTT disconnected rc=%s", rc)

    def _publish_device(self, dev: dict, *, discovery: bool) -> None:
        if discovery:
            for component, payload in build_discovery(
                dev,
                base=self.s.base_topic,
                discovery_prefix=self.s.discovery_prefix,
                availability_topic=self.avail_topic,
                space_names=self._space_names,
                overrides=self.s.device_overrides,
            ):
                topic = f"{self.s.discovery_prefix}/{component}/{payload['unique_id']}/config"
                self.mqtt.publish(topic, json.dumps(payload), qos=1, retain=True)
                log.info(
                    "Discovery: %s -> %s (%s)",
                    _info(dev).get("name"),
                    component,
                    payload["unique_id"],
                )
        state = build_state(dev)
        if state is not None:
            self.mqtt.publish(
                f"{self.s.base_topic}/{dev['deviceId']}/state",
                json.dumps(state),
                qos=1,
                retain=True,
            )

    def _on_message(self, client, userdata, msg):  # noqa: ANN001
        if self._loop is None:
            return
        try:
            payload = msg.payload.decode()
        except Exception:
            payload = ""
        log.info("CMD %s = %s", msg.topic, payload)
        asyncio.run_coroutine_threadsafe(self._handle_command(msg.topic, payload), self._loop)

    async def _handle_command(self, topic: str, payload: str) -> None:
        try:
            parts = topic[len(self.s.base_topic) + 1 :].split("/")
            device_id = parts[0]
            sub = "/".join(parts[1:])
            traits = self._devices.get(device_id, {}).get("traits", {})
            if sub == "set" and "lightReadV1" in traits:
                data = (
                    json.loads(payload) if payload.strip().startswith("{") else {"state": payload}
                )
                on = str(data.get("state", "")).upper() == "ON"
                await self.client.set_light(device_id, on, data.get("brightness"))
            elif sub == "set" and "lockerReadV1" in traits:
                await self.client.set_lock(device_id, payload.strip().upper() == "LOCK")
            elif sub == "temp/set":
                temp = float(payload)
                st = traits.get("thermostatReadV1", {}).get("status", {})
                mode = HVAC_TO_HA.get(st.get("hvacMode", ""), "cool")
                if mode == "heat":
                    await self.client.set_thermostat(device_id, heat_celsius=temp)
                else:
                    await self.client.set_thermostat(device_id, cool_celsius=temp)
            elif sub == "mode/set":
                system_mode = HA_TO_SYSTEM.get(payload.strip())
                if system_mode:
                    await self.client.set_thermostat_mode(device_id, system_mode)
                else:
                    log.warning("Unknown climate mode %r", payload)
                    return
            elif sub == "fan/set":
                fan_mode = HA_TO_FAN.get(payload.strip())
                if fan_mode:
                    await self.client.set_fan_mode(device_id, fan_mode)
                else:
                    log.warning("Unknown fan mode %r", payload)
                    return
            elif sub == "percentage/set":
                # fan-override speed -> dimmer level on the underlying light-capable switch
                pct = int(payload)
                if pct <= 0:
                    await self.client.set_light(device_id, on=False)
                else:
                    await self.client.set_light(device_id, on=True, brightness=pct)
            else:
                log.warning("Unhandled command topic %s", topic)
                return
            await self._settle()
        except Exception as e:  # noqa: BLE001
            log.exception("command failed: %s", e)

    # Re-publish state as the device reports the result of a command. Lights reflect
    # almost instantly, but some devices (notably the lock) only report their new
    # state ~30-40s later, so re-poll a few times instead of waiting for the next
    # full sync. Delays are cumulative (~2s, 12s, 37s, 82s after the command).
    _SETTLE_DELAYS = (2, 10, 25, 45)

    async def _settle(self) -> None:
        for delay in self._SETTLE_DELAYS:
            await asyncio.sleep(delay)
            try:
                await self.refresh(discovery=False)
            except Exception as e:  # noqa: BLE001
                log.error("settle refresh error: %s", e)

    async def refresh(self, *, discovery: bool = True) -> None:
        world = await self.client.get_world()
        self._space_names = {s["spaceId"]: s.get("name", "") for s in world.get("spaces", [])}
        self._devices = {d["deviceId"]: d for d in world.get("devices", [])}
        for dev in self._devices.values():
            self._publish_device(dev, discovery=discovery)

    async def run(self) -> None:
        await self.client.login()
        await self.connect()
        await self.refresh(discovery=True)
        log.info(
            "Bridge running: %d devices, sync every %ds", len(self._devices), self.s.sync_interval
        )
        while True:
            await asyncio.sleep(self.s.sync_interval)
            try:
                await self.refresh(discovery=False)
            except Exception as e:  # noqa: BLE001
                log.error("sync error: %s", e)

    async def shutdown(self) -> None:
        try:
            self.mqtt.publish(self.avail_topic, "offline", qos=1, retain=True)
            self.mqtt.loop_stop()
            self.mqtt.disconnect()
        finally:
            await self.client.aclose()
