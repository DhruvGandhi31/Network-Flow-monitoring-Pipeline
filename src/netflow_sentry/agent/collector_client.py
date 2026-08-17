"""Bidirectional gRPC streaming client: pushes FlowBatch messages to the
collector on an interval and logs the acks streamed back."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Iterator

import grpc

from netflow_sentry.agent.capture import capture_flows
from netflow_sentry.common.config import AgentConfig
from netflow_sentry.proto_gen import flow_pb2, flow_pb2_grpc

logger = logging.getLogger(__name__)


class FlowStreamer:
    def __init__(self, config: AgentConfig):
        self._config = config
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def _batch_generator(self) -> Iterator[flow_pb2.FlowBatch]:
        while not self._stop_event.is_set():
            try:
                records = capture_flows(self._config.agent_id)
            except Exception:
                logger.exception("failed to capture flows, sending empty batch")
                records = []

            yield flow_pb2.FlowBatch(
                agent_id=self._config.agent_id,
                batch_timestamp=int(time.time()),
                records=records,
            )
            self._stop_event.wait(self._config.batch_flush_seconds)

    def run(self) -> None:
        channel = grpc.insecure_channel(self._config.collector_address)
        stub = flow_pb2_grpc.FlowCollectorStub(channel)
        logger.info(
            "agent %s streaming to collector at %s",
            self._config.agent_id,
            self._config.collector_address,
        )

        try:
            for ack in stub.StreamFlows(self._batch_generator()):
                logger.info(
                    "ack: success=%s records_received=%d msg=%s",
                    ack.success,
                    ack.records_received,
                    ack.message,
                )
        except grpc.RpcError as exc:
            logger.error("stream terminated: %s", exc)
        finally:
            channel.close()
