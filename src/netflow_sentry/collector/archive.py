"""Durable archival of received flow records.

The Prometheus path keeps only aggregates, in memory. This module persists the
raw records so they survive a collector restart and can be analysed offline.

Design:
  * `add()` is called from gRPC handler threads. It only appends to an
    in-memory buffer, so a slow or failing storage backend can never stall the
    agent stream.
  * A background thread periodically drains the buffer into ONE gzipped NDJSON
    object per flush. Writing an object per batch would produce an object every
    few seconds per agent.
  * The storage backend is a tiny `Sink` (name + bytes), so the batching logic
    is testable without GCS, and a local-directory sink allows running the whole
    pipeline without any cloud access.
"""

from __future__ import annotations

import gzip
import json
import logging
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from netflow_sentry.collector import metrics
from netflow_sentry.common.config import CollectorConfig

logger = logging.getLogger(__name__)


class Sink(Protocol):
    def write(self, name: str, data: bytes) -> None: ...


class LocalDirSink:
    """Writes objects under a local directory. For development and tests."""

    def __init__(self, root: str | Path):
        self._root = Path(root)

    def write(self, name: str, data: bytes) -> None:
        path = self._root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


class GCSSink:
    """Writes objects to a Google Cloud Storage bucket.

    Credentials come from Application Default Credentials: Workload Identity on
    GKE, `gcloud auth application-default login` locally. `client` can be
    injected for tests; the google library is imported lazily so it stays an
    optional dependency (`pip install .[gcp]`).
    """

    def __init__(self, bucket_name: str, client=None):
        if client is None:
            from google.cloud import storage

            client = storage.Client()
        self._bucket = client.bucket(bucket_name)

    def write(self, name: str, data: bytes) -> None:
        blob = self._bucket.blob(name)
        blob.upload_from_string(data, content_type="application/gzip")


def record_to_dict(record, received_at: float) -> dict:
    """Flatten a FlowRecord to a JSON-friendly dict.

    Explicit (rather than MessageToDict) so int64 fields stay numbers instead of
    strings and the archived schema is stable; a test guards against drifting
    from the proto.
    """
    return {
        "agent_id": record.agent_id,
        "src_ip": record.src_ip,
        "src_port": record.src_port,
        "dst_ip": record.dst_ip,
        "dst_port": record.dst_port,
        "protocol": record.protocol,
        "status": record.status,
        "process_name": record.process_name,
        "pid": record.pid,
        "timestamp_unix": record.timestamp_unix,
        "received_at": received_at,
    }


def object_name(now: datetime) -> str:
    """Hive-style date/hour partitions, e.g. flows/dt=2026-10-15/hour=14/....

    Partitioned names let BigQuery/Athena-style tools prune by date later.
    """
    return (
        f"flows/dt={now:%Y-%m-%d}/hour={now:%H}/"
        f"{now:%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:8]}.ndjson.gz"
    )


class FlowArchiver:
    def __init__(
        self,
        sink: Sink,
        flush_interval_seconds: float = 60.0,
        max_buffered_records: int = 50_000,
    ):
        self._sink = sink
        self._flush_interval = flush_interval_seconds
        self._max_buffered = max_buffered_records
        self._buffer: list[dict] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="flow-archiver", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def add(self, records) -> None:
        """Buffer records. Never blocks on storage; drops (and counts) on overflow."""
        now = time.time()
        rows = [record_to_dict(r, now) for r in records]
        with self._lock:
            room = self._max_buffered - len(self._buffer)
            if len(rows) > room:
                dropped = len(rows) - max(room, 0)
                metrics.ARCHIVE_RECORDS_DROPPED_TOTAL.inc(dropped)
                logger.warning("archive buffer full, dropped %d records", dropped)
                rows = rows[: max(room, 0)]
            self._buffer.extend(rows)

    def flush(self) -> None:
        """Write everything currently buffered as one object. Safe to call anytime."""
        with self._lock:
            rows, self._buffer = self._buffer, []
        if not rows:
            return

        payload = gzip.compress("\n".join(json.dumps(r) for r in rows).encode() + b"\n")
        name = object_name(datetime.now(UTC))
        try:
            self._sink.write(name, payload)
        except Exception:
            metrics.ARCHIVE_WRITE_FAILURES_TOTAL.inc()
            logger.exception("archive write failed (%s); re-buffering %d records", name, len(rows))
            self._rebuffer(rows)
            return

        metrics.ARCHIVE_OBJECTS_WRITTEN_TOTAL.inc()
        metrics.ARCHIVE_RECORDS_WRITTEN_TOTAL.inc(len(rows))
        logger.info("archived %d records to %s", len(rows), name)

    def _rebuffer(self, rows: list[dict]) -> None:
        """Put failed rows back ahead of newer ones, respecting the cap."""
        with self._lock:
            combined = rows + self._buffer
            overflow = len(combined) - self._max_buffered
            if overflow > 0:
                metrics.ARCHIVE_RECORDS_DROPPED_TOTAL.inc(overflow)
                combined = combined[overflow:]  # drop the oldest
            self._buffer = combined

    def _run(self) -> None:
        while not self._stop.wait(self._flush_interval):
            self.flush()

    def close(self) -> None:
        """Stop the background thread and do a final flush (call on shutdown)."""
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=self._flush_interval + 5)
        self.flush()


def build_archiver(config: CollectorConfig) -> FlowArchiver | None:
    """Return a started archiver for the configured backend, or None if disabled."""
    if config.archive_bucket and config.archive_local_dir:
        raise ValueError("set only one of ARCHIVE_BUCKET and ARCHIVE_LOCAL_DIR")

    if config.archive_bucket:
        sink: Sink = GCSSink(config.archive_bucket)
        logger.info("archiving to gs://%s", config.archive_bucket)
    elif config.archive_local_dir:
        sink = LocalDirSink(config.archive_local_dir)
        logger.info("archiving to local dir %s", config.archive_local_dir)
    else:
        logger.info("archival disabled (set ARCHIVE_BUCKET to enable)")
        return None

    archiver = FlowArchiver(
        sink,
        flush_interval_seconds=config.archive_flush_seconds,
        max_buffered_records=config.archive_max_buffered_records,
    )
    archiver.start()
    return archiver
