"""gRPC servicer implementing the FlowCollector service.

Agents open one long-lived bidirectional stream and push FlowBatch messages;
for each batch received, we update Prometheus metrics and send back an ack.
"""

from __future__ import annotations

import logging

from netflow_sentry.collector.metrics import record_batch
from netflow_sentry.proto_gen import flow_pb2, flow_pb2_grpc

logger = logging.getLogger(__name__)


class FlowCollectorServicer(flow_pb2_grpc.FlowCollectorServicer):
    def StreamFlows(self, request_iterator, context):
        peer = context.peer()
        logger.info("agent stream opened: %s", peer)
        batch_count = 0
        try:
            for batch in request_iterator:
                batch_count += 1
                record_batch(batch.agent_id, batch.records)
                logger.debug(
                    "batch #%d from %s: %d records",
                    batch_count,
                    batch.agent_id,
                    len(batch.records),
                )
                yield flow_pb2.BatchAck(
                    success=True,
                    records_received=len(batch.records),
                    message=f"ok:batch#{batch_count}",
                )
        finally:
            logger.info("agent stream closed: %s (%d batches)", peer, batch_count)
