# Components

## `common/config.py`

Two frozen dataclasses, each with a `from_env()` classmethod — the only place
environment variables are read in the whole codebase.

```python
AgentConfig:
    agent_id: str                    # AGENT_ID, default: socket.gethostname()
    collector_address: str           # COLLECTOR_ADDRESS, default: "localhost:50051"
    capture_interval_seconds: float  # CAPTURE_INTERVAL_SECONDS, default: 5  (reserved, not yet used)
    batch_flush_seconds: float       # BATCH_FLUSH_SECONDS, default: 5

CollectorConfig:
    grpc_port: int      # GRPC_PORT, default: 50051
    metrics_port: int   # METRICS_PORT, default: 9100
    archive_bucket: str                  # ARCHIVE_BUCKET, default: "" (disabled)
    archive_local_dir: str               # ARCHIVE_LOCAL_DIR, default: "" (disabled)
    archive_flush_seconds: float         # ARCHIVE_FLUSH_SECONDS, default: 60
    archive_max_buffered_records: int    # ARCHIVE_MAX_BUFFERED_RECORDS, default: 50000
```

`capture_interval_seconds` is parsed but not currently consumed anywhere —
capture happens once per flush cycle (`batch_flush_seconds`), not on a
separate sampling timer. It's reserved for a future change where capture and
flush intervals diverge (e.g. sample every 1s, batch-send every 10s).

## Agent — `src/netflow_sentry/agent/`

### `capture.py`

`capture_flows(agent_id: str) -> list[FlowRecord]`

1. Calls `psutil.net_connections(kind="inet")`.
2. Skips any connection with no `laddr` (nothing to report).
3. For each remaining connection: unpacks `laddr`/`raddr` tuples (defaulting
   `raddr` to `("", 0)` when there's no peer — e.g. a `LISTEN` socket),
   derives `protocol` from `conn.type` (psutil's `SOCK_STREAM`=1 → `"tcp"`,
   else `"udp"`), resolves the process name via `_process_name(pid)` (which
   swallows `psutil.NoSuchProcess`/`AccessDenied` and returns `""`), and
   builds a `flow_pb2.FlowRecord`.

No filtering by protocol/state — every visible connection becomes a record.
No deduplication across snapshots — if the same connection is still open on
the next capture, it's reported again as a fresh record (this is a snapshot
model, not a delta/event model).

### `collector_client.py` — `FlowStreamer`

- `_batch_generator()`: an infinite generator (until `self._stop_event` is
  set) that calls `capture_flows()`, wraps the result in a `FlowBatch` with
  the current timestamp, `yield`s it, then waits `batch_flush_seconds`
  (interruptibly, via `Event.wait()` rather than `time.sleep()`, so `stop()`
  can end the loop without waiting out a full interval). If `capture_flows()`
  raises, the exception is logged and an **empty** batch is sent instead of
  crashing the stream.
- `run()`: opens `grpc.insecure_channel(collector_address)` — no TLS, no
  auth; acceptable for a local/demo deployment, called out explicitly as a
  gap for a production posture — builds a `FlowCollectorStub`, and calls
  `stub.StreamFlows(self._batch_generator())`. Iterating the result consumes
  `BatchAck`s as they arrive and logs each one. A `grpc.RpcError` (e.g.
  collector unreachable, stream reset) is caught and logged rather than
  propagated; the channel is always closed in a `finally`.
- `stop()`: sets the stop event, letting the generator's current `wait()`
  return early and the generator itself terminate, which ends the RPC
  cleanly from the client side.

### `main.py`

Configures root logging, builds `AgentConfig.from_env()`, runs
`FlowStreamer.run()`, and calls `.stop()` on `KeyboardInterrupt`.

## Collector — `src/netflow_sentry/collector/`

### `metrics.py`

Module-level Prometheus objects (created once at import time — this is why
`prometheus_client`'s default global registry naturally has a single
instance of each metric per process):

| Metric | Type | Labels | Meaning |
|---|---|---|---|
| `netflow_flows_received_total` | Counter | `agent_id`, `protocol`, `status` | Incremented once per `FlowRecord` in every batch |
| `netflow_batches_received_total` | Counter | `agent_id` | Incremented once per `FlowBatch` |
| `netflow_active_agents` | Gauge | *(none)* | Count of distinct `agent_id`s seen since process start (tracked via a module-level `set()`, `_seen_agents`) |
| `netflow_last_batch_size` | Gauge | `agent_id` | `len(records)` from the most recent batch for that agent |

`record_batch(agent_id, records)` is the single update function — see
`architecture.md` for why it's kept separate from the gRPC servicer. Note
`_seen_agents` and all metric state live only in process memory: a collector
restart zeroes every counter and forgets every agent it had seen.

### `server.py` — `FlowCollectorServicer`

Implements the generated `flow_pb2_grpc.FlowCollectorServicer` base class.
`StreamFlows(self, request_iterator, context)` is a generator method:

```python
for batch in request_iterator:      # blocks for each incoming FlowBatch
    record_batch(batch.agent_id, batch.records)
    yield flow_pb2.BatchAck(success=True, records_received=len(batch.records), message=f"ok:batch#{n}")
```

Logs stream open/close (with `context.peer()`, the client address) and a
running batch count in a `finally` block, so a disconnect is always visible
in collector logs even if the loop exits via exception.

### `main.py`

Starts the Prometheus HTTP exporter (`prometheus_client.start_http_server`)
on `METRICS_PORT` **before** starting the gRPC server, so `/metrics` is
guaranteed reachable as soon as the process is listening on `GRPC_PORT`.
Builds a `grpc.server` backed by a `ThreadPoolExecutor(max_workers=16)` —
each concurrent agent stream occupies one worker thread for the life of the
connection, so 16 is the practical concurrent-agent ceiling for a single
collector instance as currently configured (not tuned for scale, just a
default). Registers the servicer, binds `[::]:{GRPC_PORT}` (all interfaces,
IPv4+IPv6), starts, and blocks on `wait_for_termination()`.

It also builds the optional archiver (`build_archiver`) and handles shutdown:
`SIGTERM` (sent by Kubernetes and `docker stop`) and Ctrl+C both call
`server.stop(grace=1)`, after which `archiver.close()` does a final flush so
buffered records aren't lost on a normal stop. The grace period is
deliberately short: agent streams are long-lived, so `stop()` always waits it
out, and it must fit inside the runtime's stop timeout (Docker Desktop was
observed killing the container after ~3s, which an earlier `grace=5` exceeded).

### `archive.py`

Durable archival of raw `FlowRecord`s, enabled by `ARCHIVE_BUCKET` (GCS) or
`ARCHIVE_LOCAL_DIR` (dev). Pieces:

- `FlowArchiver` — `add(records)` is called from gRPC handler threads and only
  appends to an in-memory buffer, so slow or failing storage can never stall
  an agent stream. A daemon thread calls `flush()` every
  `ARCHIVE_FLUSH_SECONDS`, writing everything buffered as **one**
  gzipped NDJSON object (one line per record, plus a collector-side
  `received_at`). One object per batch would create an object every few
  seconds per agent.
- Failure handling: a failed write increments
  `netflow_archive_write_failures_total` and the rows are put back at the
  front of the buffer to be retried on the next flush. The buffer is capped
  at `ARCHIVE_MAX_BUFFERED_RECORDS`; overflow drops the newest records on
  `add()` (or the oldest on re-buffering) and counts them in
  `netflow_archive_records_dropped_total`. Loss is bounded and visible rather
  than unbounded memory growth.
- `Sink` — a one-method protocol (`write(name, bytes)`). `GCSSink` uploads to
  a bucket via Application Default Credentials (the `google-cloud-storage`
  import is lazy, so it stays an optional `.[gcp]` dependency; the collector
  Dockerfile installs it). `LocalDirSink` writes under a directory.
- Object names are Hive-style partitioned:
  `flows/dt=YYYY-MM-DD/hour=HH/<timestamp>-<rand>.ndjson.gz` (UTC), so
  BigQuery/Athena-style tools can prune by date later.
- `record_to_dict` serializes fields explicitly rather than using
  `MessageToDict`, which would turn `int64` fields into strings. A test
  asserts it covers every field in `flow.proto`.
