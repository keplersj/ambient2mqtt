# ambient2mqtt

Bridge **Ambient Smart Home** (Level) devices onto **MQTT** — open, vendor-neutral, and
yours. Point it at your MQTT broker and the lights, locks, thermostats, and sensors in your
unit become structured, self-describing MQTT entities, auto-announced via the widely-used
MQTT discovery convention — so Home Assistant and other MQTT-native platforms pick them up
with no manual config.

Once your devices are on MQTT, they can go anywhere an open standard reaches — dashboards,
your own automations, or onward to **[Matter](https://csa-iot.org/all-solutions/matter/)**
through a controller of your choice.

> **Unofficial & independent.** Not affiliated with, authorized, endorsed, or sponsored
> by Ambient Property Technologies or Level Home. "Ambient" and "Level" are trademarks of
> their respective owners, used here only to describe what this tool interoperates with.
> See [disclaimer](#disclaimer).

## Status

| Capability | State |
|---|---|
| Login + device discovery | ✅ working |
| Lights (on/off + brightness) | ✅ verified |
| Lock (lock/unlock) | ✅ verified — note the reported state can lag ~30–40s behind the command |
| Thermostat (mode + setpoint + fan) | ⚠️ control works (setpoint actuation confirmed on-device; mode + fan routes confirmed), but Ambient's reported state is stale, so HA may show a frozen reading |
| Motion / leak sensors | ✅ motion verified-capable; leak mapped from the schema |
| Contact / door-window, generic binary sensors | 🔬 blind — mapped from the decompiled schema, not tested on hardware |
| Battery / connectivity / firmware | 🔬 blind — per-device diagnostic sensors when those traits are present |
| Doorbell | ❌ not supported — the API trait is a WebRTC camera (stream ARNs), not ring/motion events (those need the separate doorbell service) |

State is refreshed by polling (default every 30s); there is no push channel yet. Some
devices also report their own state slowly or unreliably upstream: the lock reflects a
change after ~30–40s, and the thermostat's reported temperature/setpoint can be stale even
though setpoint commands take effect — so Home Assistant may lag or not fully track those.

## How it works

`ambient2mqtt` logs into the Ambient cloud with **your own account credentials**, lists the
devices your account can see, and republishes their state to MQTT using the
[MQTT discovery](https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery) convention
(the de-facto scheme popularized by Home Assistant). Commands published back on a device's
command topic are translated into Ambient API calls.

It is a plain HTTPS/MQTT client: it uses the (observed) cloud API with the credentials you
provide, embeds no vendor code, and does not circumvent any technical protection. The API
shape was learned by observing the author's own account.

## Quick start (Docker Compose)

```bash
cp .env.example .env     # fill in AMBIENT_USERNAME / AMBIENT_PASSWORD
docker compose up -d
```

This starts the bridge plus a local Mosquitto. Point any MQTT-native platform (for example
Home Assistant's MQTT integration) at the same broker and the entities appear automatically.

## Kubernetes (Helm)

```bash
# credentials (or use External Secrets):
kubectl create secret generic ambient2mqtt-secrets \
  --from-literal=AMBIENT_USERNAME=you@example.com \
  --from-literal=AMBIENT_PASSWORD='...'

helm install ambient2mqtt oci://ghcr.io/keplersj/charts/ambient2mqtt \
  --set mqtt.host=mosquitto
```

## Configuration

All configuration is via environment variables:

| Variable | Default | Notes |
|---|---|---|
| `AMBIENT_USERNAME` | — | required |
| `AMBIENT_PASSWORD` | — | required |
| `MQTT_HOST` | `localhost` | |
| `MQTT_PORT` | `1883` | |
| `MQTT_USERNAME` / `MQTT_PASSWORD` | — | optional |
| `MQTT_TLS` | `false` | |
| `BASE_TOPIC` | `ambient2mqtt` | |
| `DISCOVERY_PREFIX` | `homeassistant` | discovery topic prefix; must match your MQTT platform's |
| `SYNC_INTERVAL` | `30` | seconds between polls |
| `LOG_LEVEL` | `INFO` | |
| `DEVICE_OVERRIDES` | `{}` | JSON map of `deviceId → entity type` to re-type a device (see below) |

### Device type overrides

Some switches actually drive a ceiling fan, exhaust fan, etc. rather than a light. Re-type
them with `DEVICE_OVERRIDES`, a JSON object of `deviceId` → `"fan"` / `"switch"` / `"light"`:

```bash
DEVICE_OVERRIDES={"<device-uuid-a>":"fan","<device-uuid-b>":"fan"}
```

The device UUIDs are the `ambient_<uuid>` unique IDs surfaced by your MQTT platform (e.g.
Home Assistant) or printed in the bridge's discovery logs. A dimmer re-typed to `fan` exposes
its level as fan speed; an on/off switch becomes a simple on/off fan.

## Development

Uses the [uv](https://docs.astral.sh/uv/) stack:

```bash
uv sync
uv run ruff check . && uv run ruff format --check .
uv run ty check          # type check (pre-1.0; advisory for now)
uv run pytest
uv run ambient2mqtt      # run locally (reads env)
```

## Disclaimer

This project is for **personal interoperability**. In many deployments (e.g. apartments/MDUs)
the IoT devices are owned by a landlord or property-management company, and you are an
**authorized resident** who controls them through your own account — not the device owner.
Your use may be subject to the vendor's Terms of Service and to any agreements with your
building/property manager. **You are responsible for ensuring your use complies with the terms
that apply to you.** The software is provided "AS IS", without warranty of any kind (Apache-2.0).

## License

[Apache-2.0](LICENSE) — see also [NOTICE](NOTICE).
