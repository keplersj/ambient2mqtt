"""Unit tests for client helpers and control request shaping (no network)."""

import base64
import json

import pytest

from ambient2mqtt.client import AmbientClient, _jwt_exp
from ambient2mqtt.config import Settings


def _fake_jwt(exp: int) -> str:
    def b64(obj: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")

    return f"{b64({'alg': 'RS256'})}.{b64({'sub': 'x', 'exp': exp})}.sig"


def test_jwt_exp_parses():
    assert _jwt_exp(_fake_jwt(1791025193)) == 1791025193


def test_jwt_exp_bad_token_is_none():
    assert _jwt_exp("not-a-jwt") is None


@pytest.fixture
def client() -> AmbientClient:
    c = AmbientClient(Settings(username="u", password="p"))
    c.access_token = "tok"
    c.account_id = "acct"
    return c


async def test_set_light_on_with_brightness(monkeypatch, client):
    sent = {}

    async def fake_rpc(method, body):
        sent["method"], sent["body"] = method, body
        return {}

    monkeypatch.setattr(client, "_rpc", fake_rpc)
    await client.set_light("d1", True, 42)
    assert sent["method"] == "DeviceService/TraitLightControlV1Set"
    assert sent["body"] == {
        "deviceId": "d1",
        "accountId": "acct",
        "targetState": "LIGHT_STATE_ON",
        "targetLevelPercentInt": 42,
    }


async def test_set_light_off_omits_brightness(monkeypatch, client):
    calls = []

    async def fake_rpc(method, body):
        calls.append((method, body))
        return {}

    monkeypatch.setattr(client, "_rpc", fake_rpc)
    await client.set_light("d1", False)
    _, body = calls[0]
    assert body["targetState"] == "LIGHT_STATE_OFF"
    assert "targetLevelPercentInt" not in body


async def test_set_lock_method_names(monkeypatch, client):
    calls = []

    async def fake_rpc(method, body):
        calls.append(method)
        return {}

    monkeypatch.setattr(client, "_rpc", fake_rpc)
    await client.set_lock("d1", True)
    await client.set_lock("d1", False)
    assert calls == [
        "DeviceService/TraitLockerLockV1Lock",
        "DeviceService/TraitLockerUnlockV1Unlock",
    ]


async def test_set_thermostat_centidegrees(monkeypatch, client):
    calls = []

    async def fake_rpc(method, body):
        calls.append((method, body))
        return {}

    monkeypatch.setattr(client, "_rpc", fake_rpc)
    await client.set_thermostat("d1", cool_celsius=21.5)
    method, body = calls[0]
    assert method == "DeviceService/TraitThermostatSetV1SetSetpoints"
    assert body["occupiedCoolingSetpoint"] == {"value": 2150}


async def test_set_thermostat_mode(monkeypatch, client):
    calls = []

    async def fake_rpc(method, body):
        calls.append((method, body))
        return {}

    monkeypatch.setattr(client, "_rpc", fake_rpc)
    await client.set_thermostat_mode("d1", "SYSTEM_MODE_HEAT")
    method, body = calls[0]
    assert method == "DeviceService/TraitThermostatSetV1SetSystemMode"
    assert body == {"systemMode": "SYSTEM_MODE_HEAT", "deviceId": "d1", "accountId": "acct"}
