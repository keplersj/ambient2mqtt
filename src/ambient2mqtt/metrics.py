"""Prometheus metrics.

Everything is registered on prometheus_client's default registry, which also carries the
process_* / python_* collectors (memory, CPU, GC). Label values are bounded: API methods
and command kinds are fixed sets, and device types come from `device_type()`.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram, Info, disable_created_metrics

from . import __version__

# The *_created series double the output and nothing here queries them.
disable_created_metrics()

BUILD = Info("ambient2mqtt_build", "Build information")
BUILD.info({"version": __version__})

API_REQUESTS = Counter(
    "ambient2mqtt_api_requests_total",
    "Requests to the Ambient cloud API, by method and HTTP status ('error' = no response)",
    ["method", "status"],
)
API_LATENCY = Histogram(
    "ambient2mqtt_api_request_duration_seconds",
    "Ambient cloud API request latency",
    ["method"],
    buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10, 25),
)
LOGINS = Counter("ambient2mqtt_logins_total", "Ambient login attempts", ["result"])
TOKEN_EXPIRY = Gauge(
    "ambient2mqtt_token_expiry_timestamp_seconds",
    "Unix time the current Ambient access token expires",
)

SYNCS = Counter("ambient2mqtt_syncs_total", "State syncs from the Ambient cloud", ["result"])
SYNC_DURATION = Histogram(
    "ambient2mqtt_sync_duration_seconds",
    "Time to fetch and republish the full device snapshot",
    buckets=(0.25, 0.5, 1, 2, 5, 10, 25),
)
LAST_SYNC = Gauge(
    "ambient2mqtt_last_successful_sync_timestamp_seconds",
    "Unix time of the last successful sync (0 = never)",
)
DEVICES = Gauge("ambient2mqtt_devices", "Devices visible to the account, by type", ["type"])

MQTT_CONNECTED = Gauge("ambient2mqtt_mqtt_connected", "1 while connected to the MQTT broker")
MQTT_DISCONNECTS = Counter("ambient2mqtt_mqtt_disconnects_total", "MQTT broker disconnects")
MQTT_PUBLISHES = Counter(
    "ambient2mqtt_mqtt_publishes_total", "MQTT messages published, by kind", ["kind"]
)

COMMANDS = Counter(
    "ambient2mqtt_commands_total",
    "Commands received over MQTT, by kind and result (success / error / rejected / unhandled)",
    ["kind", "result"],
)
COMMAND_DURATION = Histogram(
    "ambient2mqtt_command_duration_seconds",
    "Time to send a command to the Ambient cloud (excludes waiting for the device to report)",
    ["kind"],
    buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10, 25),
)
STATE_CONVERGENCE = Histogram(
    "ambient2mqtt_state_convergence_seconds",
    "Time from a command until the device's reported state changes",
    ["type"],
    buckets=(1, 2, 5, 10, 15, 20, 30, 45, 60, 90),
)
STATE_UNCHANGED = Counter(
    "ambient2mqtt_state_unchanged_after_command_total",
    "Commands after which the reported state never changed within the settle window "
    "(a no-op command, or stale upstream state)",
    ["type"],
)
