"""Collector entrypoint: starts the gRPC server and the Prometheus /metrics
HTTP server side by side."""

from __future__ import annotations

import logging
import signal
from concurrent import futures

import grpc
from prometheus_client import start_http_server

from netflow_sentry.collector.archive import build_archiver
from netflow_sentry.collector.server import FlowCollectorServicer
from netflow_sentry.common.config import CollectorConfig
from netflow_sentry.proto_gen import flow_pb2_grpc

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# Agent streams are long-lived, so stop() always waits out the full grace period.
# Keep it short so shutdown + the archiver's final flush finish well inside the
# container runtime's stop timeout (observed as low as ~3s on Docker Desktop).
SHUTDOWN_GRACE_SECONDS = 1


def serve() -> None:
    config = CollectorConfig.from_env()

    start_http_server(config.metrics_port)
    logger.info("Prometheus metrics exposed on :%d/metrics", config.metrics_port)

    archiver = build_archiver(config)

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=16))
    flow_pb2_grpc.add_FlowCollectorServicer_to_server(FlowCollectorServicer(archiver), server)
    server.add_insecure_port(f"[::]:{config.grpc_port}")
    server.start()
    logger.info("gRPC FlowCollector listening on :%d", config.grpc_port)

    # Kubernetes (and `docker stop`) send SIGTERM; stop gracefully so the
    # archiver's final flush below runs instead of losing the buffered records.
    signal.signal(signal.SIGTERM, lambda *_: server.stop(grace=SHUTDOWN_GRACE_SECONDS))

    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        server.stop(grace=SHUTDOWN_GRACE_SECONDS).wait()
    finally:
        if archiver is not None:
            archiver.close()


if __name__ == "__main__":
    serve()
