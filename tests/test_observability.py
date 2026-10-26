"""Tests for metrics, health/readiness, the HTTP server and JSON logging (no network)."""

import asyncio
import json
import logging
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from prometheus_client import REGISTRY

from ambient2mqtt.bridge import Bridge, command_kind, device_type
from ambient2mqtt.client import AmbientClient, AmbientError
from ambient2mqtt.config import Settings
from ambient2mqtt.httpserver import HealthServer
from ambient2mqtt.logs import JsonFormatter


def sample(name: str, **labels) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


def light(state: str) -> dict:
    return {
        "deviceId": "dev-light",
        "traits": {
            "infoV1": {"name": "Hall"},
            "lightReadV1": {"status": {"lightState": state}},
        },
    }


@pytest.fixture
def bridge() -> Bridge:
    b = Bridge(MagicMock(), Settings(username="u", password="p"))
    b.mqtt = MagicMock()
    return b


def test_device_type():
    assert device_type(light("LIGHT_STATE_ON")) == "light"
    assert device_type({"traits": {"lockerReadV1": {}}}) == "lock"
    assert device_type({"traits": {"accessSensorReadV1": {}}}) == "contact"
    assert device_type({"traits": {"infoV1": {}}}) == "other"


def test_command_kind():
    assert command_kind("set", {"lightReadV1": {}}) == "light"
    assert command_kind("set", {"lockerReadV1": {}}) == "lock"
    assert command_kind("set", {}) == "unhandled"
    assert command_kind("temp/set", {}) == "temperature"
    assert command_kind("bogus/set", {}) == "unhandled"


def test_readiness_requires_mqtt_and_recent_sync(bridge):
    assert bridge.readiness() == (False, "mqtt disconnected")
    bridge._on_connect(MagicMock(), None, None, 0)
    assert bridge.readiness() == (False, "no successful sync yet")
    bridge._last_sync = 0.0  # monotonic epoch: long ago
    ready, reason = bridge.readiness()
    assert not ready and "last successful sync" in reason
    bridge._last_sync = None


async def test_refresh_success_marks_ready_and_counts_devices(bridge):
    bridge.client.get_world = AsyncMock(return_value={"devices": [light("LIGHT_STATE_ON")]})
    bridge.mqtt_connected = True
    ok_before = sample("ambient2mqtt_syncs_total", result="success")
    await bridge.refresh(discovery=False)
    assert sample("ambient2mqtt_syncs_total", result="success") == ok_before + 1
    assert sample("ambient2mqtt_devices", type="light") == 1
    assert sample("ambient2mqtt_last_successful_sync_timestamp_seconds") > 0
    assert bridge.readiness() == (True, "ok")


async def test_refresh_error_is_counted_and_reraised(bridge):
    bridge.client.get_world = AsyncMock(side_effect=AmbientError("boom"))
    before = sample("ambient2mqtt_syncs_total", result="error")
    with pytest.raises(AmbientError):
        await bridge.refresh()
    assert sample("ambient2mqtt_syncs_total", result="error") == before + 1


def test_mqtt_disconnect_metrics(bridge):
    bridge._on_connect(MagicMock(), None, None, 0)
    assert sample("ambient2mqtt_mqtt_connected") == 1
    before = sample("ambient2mqtt_mqtt_disconnects_total")
    bridge._on_disconnect(MagicMock(), None, 1)
    assert sample("ambient2mqtt_mqtt_connected") == 0
    assert sample("ambient2mqtt_mqtt_disconnects_total") == before + 1
    assert not bridge.mqtt_connected


async def test_unhandled_command_is_counted(bridge):
    before = sample("ambient2mqtt_commands_total", kind="unhandled", result="unhandled")
    await bridge._handle_command("ambient2mqtt/unknown-dev/set", "ON")
    assert sample("ambient2mqtt_commands_total", kind="unhandled", result="unhandled") == (
        before + 1
    )


async def test_rejected_mode_is_counted(bridge):
    bridge._devices = {"t": {"deviceId": "t", "traits": {"thermostatReadV1": {}}}}
    before = sample("ambient2mqtt_commands_total", kind="mode", result="rejected")
    await bridge._handle_command("ambient2mqtt/t/mode/set", "dry")
    assert sample("ambient2mqtt_commands_total", kind="mode", result="rejected") == before + 1


async def test_failed_command_is_counted(bridge):
    bridge._devices = {"dev-light": light("LIGHT_STATE_OFF")}
    bridge.client.set_light = AsyncMock(side_effect=AmbientError("nope"))
    before = sample("ambient2mqtt_commands_total", kind="light", result="error")
    await bridge._handle_command("ambient2mqtt/dev-light/set", "ON")
    assert sample("ambient2mqtt_commands_total", kind="light", result="error") == before + 1


async def test_command_success_times_state_convergence(bridge, monkeypatch):
    monkeypatch.setattr(Bridge, "_SETTLE_DELAYS", (0, 0))
    bridge._devices = {"dev-light": light("LIGHT_STATE_OFF")}
    bridge.client.set_light = AsyncMock()
    bridge.client.get_world = AsyncMock(return_value={"devices": [light("LIGHT_STATE_ON")]})
    ok = sample("ambient2mqtt_commands_total", kind="light", result="success")
    conv = sample("ambient2mqtt_state_convergence_seconds_count", type="light")
    await bridge._handle_command("ambient2mqtt/dev-light/set", "ON")
    assert sample("ambient2mqtt_commands_total", kind="light", result="success") == ok + 1
    # observed once, even though the settle loop polled twice
    assert sample("ambient2mqtt_state_convergence_seconds_count", type="light") == conv + 1


async def test_command_without_state_change_is_counted_unchanged(bridge, monkeypatch):
    monkeypatch.setattr(Bridge, "_SETTLE_DELAYS", (0,))
    bridge._devices = {"dev-light": light("LIGHT_STATE_ON")}
    bridge.client.set_light = AsyncMock()
    bridge.client.get_world = AsyncMock(return_value={"devices": [light("LIGHT_STATE_ON")]})
    before = sample("ambient2mqtt_state_unchanged_after_command_total", type="light")
    await bridge._handle_command("ambient2mqtt/dev-light/set", "ON")
    assert sample("ambient2mqtt_state_unchanged_after_command_total", type="light") == (before + 1)


def test_health_routes():
    server = HealthServer(0, lambda: (False, "mqtt disconnected"))
    assert server.respond("GET", "/healthz", "")[0] == 200
    assert server.respond("GET", "/readyz", "") == (503, "text/plain", b"mqtt disconnected\n")
    status, ctype, body = server.respond("GET", "/metrics", "")
    assert status == 200 and ctype.startswith("text/plain")
    assert b"ambient2mqtt_build_info" in body
    assert "openmetrics" in server.respond("GET", "/metrics", "application/openmetrics-text")[1]
    assert server.respond("POST", "/metrics", "")[0] == 405
    assert server.respond("GET", "/nope", "")[0] == 404


async def test_health_server_over_tcp():
    server = HealthServer(0, lambda: (True, "ok"))
    await server.start()
    assert server._server is not None
    port = server._server.sockets[0].getsockname()[1]
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(b"GET /readyz HTTP/1.1\r\nHost: x\r\n\r\n")
        await writer.drain()
        response = await reader.read()
        writer.close()
    finally:
        await server.stop()
    assert response.startswith(b"HTTP/1.1 200 OK")
    assert response.endswith(b"\r\n\r\nok\n")


def test_json_formatter_includes_extras():
    record = logging.LogRecord("ambient2mqtt.bridge", logging.INFO, "", 0, "hi %s", ("x",), None)
    record.device_id = "dev-1"
    out = json.loads(JsonFormatter().format(record))
    assert out["msg"] == "hi x"
    assert out["level"] == "info"
    assert out["device_id"] == "dev-1"
    assert "args" not in out


async def test_client_records_api_status_and_login_failures(monkeypatch):
    client = AmbientClient(Settings(username="u", password="p"))
    resp = httpx.Response(401, text="bad creds", request=httpx.Request("POST", "http://x"))
    monkeypatch.setattr(client._http, "post", AsyncMock(return_value=resp))
    reqs = sample("ambient2mqtt_api_requests_total", method="login", status="401")
    fails = sample("ambient2mqtt_logins_total", result="failure")
    with pytest.raises(AmbientError):
        await client.login()
    assert sample("ambient2mqtt_api_requests_total", method="login", status="401") == reqs + 1
    assert sample("ambient2mqtt_logins_total", result="failure") == fails + 1
    await client.aclose()
