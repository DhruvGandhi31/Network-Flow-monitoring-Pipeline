"""Prometheus metric definitions and update logic for the collector.

Kept separate from the gRPC service so it can be unit tested without
spinning up a server.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge

FLOWS_RECEIVED_TOTAL = Counter(
    "netflow_flows_received_total",
    "Total number of flow records received, by protocol and status.",
    ["agent_id", "protocol", "status"],
)

BATCHES_RECEIVED_TOTAL = Counter(
    "netflow_batches_received_total",
    "Total number of flow batches received from agents.",
    ["agent_id"],
)

ACTIVE_AGENTS = Gauge(
    "netflow_active_agents",
    "Number of distinct agents that have sent a batch in the current process lifetime.",
)

LAST_BATCH_SIZE = Gauge(
    "netflow_last_batch_size",
    "Number of records in the most recently received batch, by agent.",
    ["agent_id"],
)

_seen_agents: set[str] = set()


def record_batch(agent_id: str, records) -> None:
    """Update Prometheus metrics for a single received FlowBatch."""
    if agent_id not in _seen_agents:
        _seen_agents.add(agent_id)
        ACTIVE_AGENTS.set(len(_seen_agents))

    BATCHES_RECEIVED_TOTAL.labels(agent_id=agent_id).inc()
    LAST_BATCH_SIZE.labels(agent_id=agent_id).set(len(records))

    for record in records:
        FLOWS_RECEIVED_TOTAL.labels(
            agent_id=agent_id,
            protocol=record.protocol or "unknown",
            status=record.status or "unknown",
        ).inc()
