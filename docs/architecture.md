# Architecture

## Data flow

```
┌──────────┐   bidirectional gRPC stream    ┌────────────┐   scrape /metrics   ┌────────────┐   PromQL   ┌─────────┐
│  Agent   │ ───── FlowBatch (every N s) ──▶│  Collector │◀────────────────────│ Prometheus │◀───────────│ Grafana │
│ (psutil) │◀──── BatchAck (per batch) ──── │ gRPC:50051 │      every 5s       │   :9090    │            │  :3000  │
└──────────┘                                │ HTTP:9100  │                     └────────────┘            └─────────┘
   × N hosts                                └────────────┘
   (one agent per
   monitored host)
```

Two independent transport hops:

1. **Agent → Collector**: gRPC, push-based, real-time, one persistent
   connection per agent.
2. **Prometheus → Collector**: HTTP pull, on a fixed interval, stateless —
   Prometheus doesn't know or care how many agents are connected; it only
   reads whatever counters/gauges are currently in the collector's process
   memory.

The collector is the only component that talks to both sides. It has no
persistent storage of its own — all state is in-memory Prometheus metric
objects (`prometheus_client.Counter` / `Gauge`), which is why a collector
restart resets counters to zero. That's an accepted trade-off for this stage
of the project; the roadmap's AWS/S3 archival step (see `roadmap.md`) is what
would add durable storage independent of the collector's process lifetime.

## Why bidirectional gRPC streaming (not unary calls, not REST)

A unary `SendBatch(FlowBatch) returns (BatchAck)` RPC would work, but it pays
a new-stream/connection-setup style cost model per batch and doesn't
naturally express "this agent is continuously reporting." Bidirectional
streaming (`rpc StreamFlows(stream FlowBatch) returns (stream BatchAck)`)
matches the actual shape of the problem: one agent opens one connection for
its entire lifetime and pushes an indefinite sequence of batches down it,
while acks flow back on the same connection without a new handshake each
time. It's also the more technically substantial gRPC pattern to demonstrate
on a resume project versus a unary call.

Concretely, in `agent/collector_client.py`, `FlowStreamer._batch_generator()`
is a Python generator that yields `FlowBatch` messages on a timer; that
generator is passed directly as the *request* to `stub.StreamFlows(...)`,
and iterating the *return value* of that call consumes the server's ack
stream. Both directions are live on the same call, on the same TCP
connection, which is the point.

## Why a connection-table snapshot instead of packet capture

`agent/capture.py` calls `psutil.net_connections(kind="inet")`, which reads
the OS's connection table (like `netstat`) — not raw packets. This was a
deliberate scope decision:

- **Portable**: works unmodified on Windows, Linux, and macOS, and inside an
  unprivileged Docker container.
- **No elevated privileges required** in the common case (some connections
  owned by other users/processes may be invisible without admin/root, but
  the agent doesn't crash or need `CAP_NET_RAW`/npcap either way).
- **Honest about the trade-off**: it captures connection *metadata*
  (endpoints, protocol, state, owning process) on each snapshot, not
  byte/packet *volume*. A true NetFlow/sFlow-style collector reports byte
  counters per flow; this doesn't, and the README/roadmap says so explicitly
  rather than implying otherwise.

A pcap-based capture mode (via `scapy` or similar) that yields real
byte/packet counters is on the roadmap, gated behind a config flag, because
it needs elevated privileges and isn't portable the same way.

## Why metrics.py is separate from server.py

`collector/metrics.py` defines the Prometheus metric objects and one pure
function, `record_batch(agent_id, records)`, that updates them. `server.py`
contains only gRPC plumbing (`FlowCollectorServicer.StreamFlows`) and calls
`record_batch()` per received batch. This split means the metric-update
logic — the part actually worth unit testing — can be tested by calling
`record_batch()` directly with synthetic protobuf messages (see
`tests/test_metrics.py`), without standing up a gRPC server or a network
socket.

## Why all configuration is environment variables

`common/config.py` defines `AgentConfig.from_env()` and
`CollectorConfig.from_env()`. No file paths, no CLI flags, no hardcoded
addresses anywhere in `agent/` or `collector/`. This is what makes the exact
same Docker image behave correctly in three different contexts without a
rebuild: a bare local process (`COLLECTOR_ADDRESS=localhost:50051`), a
Compose service (`COLLECTOR_ADDRESS=collector:50051`, resolved by Docker's
embedded DNS), and — per the roadmap — an AWS ECS task (`COLLECTOR_ADDRESS`
pointing at a service-discovery name or load balancer). It's the standard
12-factor-app pattern, applied because this project is explicitly meant to
demonstrate deployability, not just local correctness.
