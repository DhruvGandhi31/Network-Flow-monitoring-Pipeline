"""Collector entrypoint: starts the gRPC server and the Prometheus /metrics
HTTP server side by side."""

from __future__ import annotations

import logging
from concurrent import futures

import grpc
from prometheus_client import start_http_server

from netflow_sentry.collector.server import FlowCollectorServicer
from netflow_sentry.common.config import CollectorConfig
from netflow_sentry.proto_gen import flow_pb2_grpc

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def serve() -> None:
    config = CollectorConfig.from_env()

    start_http_server(config.metrics_port)
    logger.info("Prometheus metrics exposed on :%d/metrics", config.metrics_port)

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=16))
    flow_pb2_grpc.add_FlowCollectorServicer_to_server(FlowCollectorServicer(), server)
    server.add_insecure_port(f"[::]:{config.grpc_port}")
    server.start()
    logger.info("gRPC FlowCollector listening on :%d", config.grpc_port)

    server.wait_for_termination()


if __name__ == "__main__":
    serve()
