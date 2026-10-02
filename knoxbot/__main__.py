"""Entrypoint: py -m knoxbot

Loads config, initialises the messenger client (device registration +
encryption key) when credentials are present, and serves the Receiving API
on POST /message.
"""

from __future__ import annotations

import logging
import sys

import uvicorn

from .config import load_config
from .messenger import MessengerClient
from .server import create_app


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger = logging.getLogger("knoxbot")

    config = load_config()

    missing = config.validate()
    client = None
    if missing:
        logger.warning(
            "missing config %s — starting in log-only mode (no replies). "
            "Copy .env.example to .env and fill it in.",
            ", ".join(missing),
        )
    else:
        client = MessengerClient(config)
        try:
            client.ensure_ready()
        except Exception:  # noqa: BLE001
            logger.exception(
                "device registration / key fetch failed; starting without "
                "reply capability"
            )
            client = None

    app = create_app(config, client=client)
    logger.info("listening on %s:%d (POST /message)", config.host, config.port)
    uvicorn.run(app, host=config.host, port=config.port, log_level="info")


if __name__ == "__main__":
    sys.exit(main())
