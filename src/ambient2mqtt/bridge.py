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

HVAC_TO_HA = {
    "HVAC_MODE_OFF": "off",
    "HVAC_MODE_COOL": "cool",
    "HVAC_MODE_HEAT": "heat",
    "HVAC_MODE_AUTO": "auto",
    "HVAC_MODE_HEAT_COOL": "heat_cool",
    "HVAC_MODE_ECO": "auto",
}


def _info(dev: dict) -> dict:
    return dev.get("traits", {}).get("infoV1", {})


def build_state(dev: dict) -> dict | None:
    """Translate an Ambient device's read traits into an HA MQTT state payload."""
    traits = dev.get("traits", {})
    if "lightReadV1" in traits:
        st = traits["lightReadV1"].get("status", {})
        out: dict = {"state": "ON" if st.get("lightState") == "LIGHT_STATE_ON" else "OFF"}
        if "levelPercentInt" in st:
            out["brightness"] = st["levelPercentInt"]
        return out
    if "lockerReadV1" in traits:
        ls = traits["lockerReadV1"].get("status", {}).get("lockState", "")
        return {"state": "LOCKED" if ls == "LOCK_STATE_LOCKED" else "UNLOCKED"}
    if "thermostatReadV1" in traits:
        st = traits["thermostatReadV1"].get("status", {})
        mode = HVAC_TO_HA.get(st.get("hvacMode", ""), "off")
        target = (
            st.get("targetTemperatureHeatCelsius")
            if mode == "heat"
            else st.get("targetTemperatureCoolCelsius")
        )
        return {
            "mode": mode,
            "current_temperature": st.get("ambientTemperatureCelsius"),
            "temperature": target,
        }
    if "motionSensorReadV1" in traits:
        st = traits["motionSensorReadV1"].get("status", {})
        return (
            {"state": "ON" if st["motionDetected"] else "OFF"} if "motionDetected" in st else None
        )
    if "leakSensorReadV1" in traits:
        st = traits["leakSensorReadV1"].get("status", {})
        return {"state": "ON" if st["leakDetected"] else "OFF"} if "leakDetected" in st else None
    return None


def build_discovery(
    dev: dict,
    *,
    base: str,
    discovery_prefix: str,
    availability_topic: str,
    space_names: dict[str, str],
) -> list[tuple[str, dict]]:
    """Return a list of (component, discovery-payload) for a device, or []."""
    did = dev["deviceId"]
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

    if "lightReadV1" in traits:
        cfg = {**common, "schema": "json", "state_topic": state_t, "command_topic": set_t}
        if traits["lightReadV1"].get("capability") == "LIGHT_CAPABILITY_TYPE_DIMMER":
            cfg["brightness"] = True
            cfg["brightness_scale"] = 100
        return [("light", cfg)]
    if "lockerReadV1" in traits:
        return [
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
        ]
    if "thermostatReadV1" in traits:
        # Mode is read-only (the setpoint API carries no HVAC-mode field); temperature is settable.
        return [
            (
                "climate",
                {
                    **common,
                    "current_temperature_topic": state_t,
                    "current_temperature_template": "{{ value_json.current_temperature }}",
                    "mode_state_topic": state_t,
                    "mode_state_template": "{{ value_json.mode }}",
                    "modes": ["off", "cool", "heat", "auto", "heat_cool"],
                    "temperature_state_topic": state_t,
                    "temperature_state_template": "{{ value_json.temperature }}",
                    "temperature_command_topic": f"{base}/{did}/temp/set",
                    "temperature_unit": "C",
                    "temp_step": 0.5,
                },
            )
        ]
    if "motionSensorReadV1" in traits:
        return [
            (
                "binary_sensor",
                {
                    **common,
                    "state_topic": state_t,
                    "value_template": "{{ value_json.state }}",
                    "payload_on": "ON",
                    "payload_off": "OFF",
                    "device_class": "motion",
                },
            )
        ]
    if "leakSensorReadV1" in traits:
        return [
            (
                "binary_sensor",
                {
                    **common,
                    "state_topic": state_t,
                    "value_template": "{{ value_json.state }}",
                    "payload_on": "ON",
                    "payload_off": "OFF",
                    "device_class": "moisture",
                },
            )
        ]
    return []


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
            ):
                topic = f"{self.s.discovery_prefix}/{component}/ambient_{dev['deviceId']}/config"
                self.mqtt.publish(topic, json.dumps(payload), qos=1, retain=True)
                log.info(
                    "Discovery: %s -> %s (%s)",
                    _info(dev).get("name"),
                    component,
                    dev["deviceId"][:8],
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
            else:
                log.warning("Unhandled command topic %s", topic)
                return
            await asyncio.sleep(1.5)
            await self.refresh(discovery=False)
        except Exception as e:  # noqa: BLE001
            log.exception("command failed: %s", e)

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
