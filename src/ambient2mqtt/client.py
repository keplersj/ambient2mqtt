"""Client for the Ambient Smart Home (Level / ambientproptech) cloud API.

The API shape here was determined by observing the traffic of the author's own
resident account against the production service; this is a plain HTTPS client that
authenticates with your own credentials and makes the same calls the app makes. It
contains no vendor code and performs no circumvention of any technical protection.

Endpoints:
  * login   POST {auth}/mdu-auth/v2/auth/login {username, password, enable_refresh_token}
            -> {access_token, uuid (= accountId), ...}
  * read    POST {device}/device.discovery.v1.HydratedService/World {accountId}
  * control POST {device}/device.discovery.v1.DeviceService/<Method> {deviceId, accountId, ...}

device-discovery is a Connect-RPC service; requests carry the access token in a custom
`AccessToken` header (not `Authorization`) and `Connect-Protocol-Version: 1`.
"""

from __future__ import annotations

import base64
import json
import logging
import time

import httpx

from .config import Settings

log = logging.getLogger(__name__)

USER_AGENT = "ambient2mqtt"


class AmbientError(RuntimeError):
    pass


def _jwt_exp(token: str) -> int | None:
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return int(json.loads(base64.urlsafe_b64decode(payload))["exp"])
    except Exception:
        return None


class AmbientClient:
    def __init__(self, settings: Settings) -> None:
        self._s = settings
        self.access_token: str | None = None
        self.account_id: str | None = None
        self._exp: int | None = None
        self._http = httpx.AsyncClient(http2=True, timeout=25.0)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def login(self) -> None:
        r = await self._http.post(
            f"{self._s.auth_url}/mdu-auth/v2/auth/login",
            json={
                "username": self._s.username,
                "password": self._s.password,
                "enable_refresh_token": True,
            },
            headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        )
        if r.status_code != 200:
            raise AmbientError(f"login failed: {r.status_code} {r.text[:200]}")
        data = r.json()
        self.access_token = data["access_token"]
        self.account_id = data.get("uuid")
        self._exp = _jwt_exp(self.access_token)
        log.info("Ambient login OK (account %s)", self.account_id)

    async def _ensure_token(self) -> None:
        if not self.access_token or (self._exp and time.time() > self._exp - 60):
            await self.login()

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "Connect-Protocol-Version": "1",
            "AccessToken": self.access_token or "",
        }

    async def _rpc(self, method: str, body: dict) -> dict:
        await self._ensure_token()
        url = f"{self._s.device_url}/device.discovery.v1.{method}"
        r = await self._http.post(url, json=body, headers=self._headers())
        if r.status_code == 403:
            await self.login()
            r = await self._http.post(url, json=body, headers=self._headers())
        if r.status_code != 200:
            raise AmbientError(f"{method} failed: {r.status_code} {r.text[:200]}")
        return r.json() if r.content else {}

    async def get_world(self) -> dict:
        """Full hydrated device + space snapshot for the account."""
        return await self._rpc("HydratedService/World", {"accountId": self.account_id})

    async def set_light(self, device_id: str, on: bool, brightness: int | None = None) -> None:
        body: dict = {
            "deviceId": device_id,
            "accountId": self.account_id,
            "targetState": "LIGHT_STATE_ON" if on else "LIGHT_STATE_OFF",
        }
        if on and brightness is not None:
            body["targetLevelPercentInt"] = max(0, min(100, int(brightness)))
        await self._rpc("DeviceService/TraitLightControlV1Set", body)

    async def set_lock(self, device_id: str, locked: bool) -> None:
        method = "TraitLockerLockV1Lock" if locked else "TraitLockerUnlockV1Unlock"
        await self._rpc(
            f"DeviceService/{method}",
            {"deviceId": device_id, "accountId": self.account_id},
        )

    async def set_thermostat(
        self,
        device_id: str,
        cool_celsius: float | None = None,
        heat_celsius: float | None = None,
    ) -> None:
        body: dict = {"deviceId": device_id, "accountId": self.account_id}
        if cool_celsius is not None:
            body["occupiedCoolingSetpoint"] = {"value": int(round(cool_celsius * 100))}
        if heat_celsius is not None:
            body["occupiedHeatingSetpoint"] = {"value": int(round(heat_celsius * 100))}
        await self._rpc("DeviceService/TraitThermostatSetV1SetSetpoints", body)

    async def set_thermostat_mode(self, device_id: str, system_mode: str) -> None:
        """Set HVAC mode. system_mode is a SYSTEM_MODE_* enum name (OFF/HEAT/COOL/AUTO/...)."""
        await self._rpc(
            "DeviceService/TraitThermostatSetV1SetSystemMode",
            {"systemMode": system_mode, "deviceId": device_id, "accountId": self.account_id},
        )

    async def set_fan_mode(self, device_id: str, fan_mode: str) -> None:
        """Set thermostat fan mode. fan_mode is a FAN_MODE_* enum name (AUTO/ON/CIRCULATE/OFF)."""
        await self._rpc(
            "DeviceService/TraitThermostatSetV1SetFan",
            {"fanMode": fan_mode, "deviceId": device_id, "accountId": self.account_id},
        )
