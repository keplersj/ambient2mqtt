"""Tiny asyncio HTTP server for /metrics, /healthz and /readyz.

Runs on the bridge's own event loop, so /healthz answering at all proves the loop isn't
wedged. Deliberately minimal (GET only, no keep-alive) to avoid a web-framework dependency.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from prometheus_client import REGISTRY
from prometheus_client.exposition import choose_encoder

log = logging.getLogger(__name__)

_REASONS = {200: "OK", 404: "Not Found", 405: "Method Not Allowed", 503: "Service Unavailable"}


class HealthServer:
    def __init__(self, port: int, readiness: Callable[[], tuple[bool, str]]) -> None:
        self.port = port
        self._readiness = readiness
        self._server: asyncio.Server | None = None

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, host="0.0.0.0", port=self.port)
        log.info("Serving /metrics, /healthz, /readyz on :%d", self.port)

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    def respond(self, method: str, path: str, accept: str) -> tuple[int, str, bytes]:
        """Route a request to (status, content type, body)."""
        if method not in ("GET", "HEAD"):
            return 405, "text/plain", b"method not allowed\n"
        path = path.split("?", 1)[0]
        if path == "/metrics":
            encoder, content_type = choose_encoder(accept)
            return 200, content_type, encoder(REGISTRY)
        if path == "/healthz":
            return 200, "text/plain", b"ok\n"
        if path == "/readyz":
            ready, reason = self._readiness()
            return (200 if ready else 503), "text/plain", f"{reason}\n".encode()
        return 404, "text/plain", b"not found\n"

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request = await asyncio.wait_for(reader.readline(), timeout=5)
            accept = ""
            while True:
                line = await asyncio.wait_for(reader.readline(), timeout=5)
                if line in (b"\r\n", b"\n", b""):
                    break
                name, _, value = line.decode("latin-1").partition(":")
                if name.strip().lower() == "accept":
                    accept = value.strip()
            parts = request.decode("latin-1").split()
            if len(parts) < 2:
                return
            method, path = parts[0], parts[1]
            status, content_type, body = self.respond(method, path, accept)
            head = (
                f"HTTP/1.1 {status} {_REASONS.get(status, '')}\r\n"
                f"Content-Type: {content_type}\r\n"
                f"Content-Length: {len(body)}\r\n"
                "Connection: close\r\n\r\n"
            )
            writer.write(head.encode() + (b"" if method == "HEAD" else body))
            await writer.drain()
        except (TimeoutError, ConnectionError):
            pass
        except Exception:  # noqa: BLE001
            log.exception("health server request failed")
        finally:
            writer.close()
