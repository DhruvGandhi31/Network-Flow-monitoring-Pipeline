"""Shared configuration, sourced from environment variables so both the
agent and collector run unmodified in Docker/AWS without code changes."""

from __future__ import annotations

import os
import socket
from dataclasses import dataclass


@dataclass(frozen=True)
class AgentConfig:
    agent_id: str
    collector_address: str
    capture_interval_seconds: float
    batch_flush_seconds: float

    @classmethod
    def from_env(cls) -> "AgentConfig":
        return cls(
            agent_id=os.environ.get("AGENT_ID", socket.gethostname()),
            collector_address=os.environ.get("COLLECTOR_ADDRESS", "localhost:50051"),
            capture_interval_seconds=float(os.environ.get("CAPTURE_INTERVAL_SECONDS", "5")),
            batch_flush_seconds=float(os.environ.get("BATCH_FLUSH_SECONDS", "5")),
        )


@dataclass(frozen=True)
class CollectorConfig:
    grpc_port: int
    metrics_port: int

    @classmethod
    def from_env(cls) -> "CollectorConfig":
        return cls(
            grpc_port=int(os.environ.get("GRPC_PORT", "50051")),
            metrics_port=int(os.environ.get("METRICS_PORT", "9100")),
        )
