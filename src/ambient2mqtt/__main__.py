"""Entry point."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
import sys

from .bridge import Bridge
from .client import AmbientClient
from .config import Settings

log = logging.getLogger("ambient2mqtt")


async def _run() -> int:
    settings = Settings.from_env()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    if not settings.username or not settings.password:
        log.error("AMBIENT_USERNAME / AMBIENT_PASSWORD must be set")
        return 1

    client = AmbientClient(settings)
    bridge = Bridge(client, settings)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)

    runner = asyncio.create_task(bridge.run())
    stopper = asyncio.create_task(stop.wait())
    done, _ = await asyncio.wait({runner, stopper}, return_when=asyncio.FIRST_COMPLETED)

    log.info("Shutting down...")
    runner.cancel()
    await bridge.shutdown()
    if runner in done and runner.exception():
        log.error("bridge exited with error: %s", runner.exception())
        return 1
    return 0


def main() -> None:
    sys.exit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
