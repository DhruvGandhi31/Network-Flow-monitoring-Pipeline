"""Agent entrypoint."""

from __future__ import annotations

import logging

from netflow_sentry.agent.collector_client import FlowStreamer
from netflow_sentry.common.config import AgentConfig

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def main() -> None:
    config = AgentConfig.from_env()
    streamer = FlowStreamer(config)
    try:
        streamer.run()
    except KeyboardInterrupt:
        streamer.stop()


if __name__ == "__main__":
    main()
