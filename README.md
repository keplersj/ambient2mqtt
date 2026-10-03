# ambient2mqtt

Bridge **Ambient Smart Home** (Level) devices to **MQTT**, with **Home Assistant**
MQTT autodiscovery. Point it at your MQTT broker and the lights, locks, thermostats,
and sensors in your unit show up as native Home Assistant entities.

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
| Thermostat (setpoints) | ⚠️ implemented; not yet verified against an online thermostat |
| Motion / leak sensors | ✅ state passthrough when the device reports it |

State is refreshed by polling (default every 30s); there is no push channel yet. Some
devices (notably the lock) also report their own state slowly, so a change can take tens
of seconds to appear in Home Assistant.

## How it works

`ambient2mqtt` logs into the Ambient cloud with **your own account credentials**, lists the
devices your account can see, and republishes their state to MQTT using the Home Assistant
[MQTT discovery](https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery) convention.
Commands HA publishes on the device command topics are translated back into Ambient API calls.

It is a plain HTTPS/MQTT client: it uses the (observed) cloud API with the credentials you
provide, embeds no vendor code, and does not circumvent any technical protection. The API
shape was learned by observing the author's own account.

## Quick start (Docker Compose)

```bash
cp .env.example .env     # fill in AMBIENT_USERNAME / AMBIENT_PASSWORD
docker compose up -d
```

This starts the bridge plus a local Mosquitto. Pointing an existing Home Assistant's MQTT
integration at the same broker is all that's needed — entities appear automatically.

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
| `DISCOVERY_PREFIX` | `homeassistant` | must match HA's MQTT discovery prefix |
| `SYNC_INTERVAL` | `30` | seconds between polls |
| `LOG_LEVEL` | `INFO` | |

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
