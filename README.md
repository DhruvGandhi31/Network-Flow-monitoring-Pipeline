# netflow-sentry

A distributed network flow monitoring pipeline. Lightweight agents snapshot
active network connections on each host and stream them over gRPC to a
central collector, which exposes Prometheus metrics visualized in Grafana.

```
 ┌──────────┐  bidi gRPC stream   ┌───────────┐   scrape    ┌────────────┐   query   ┌─────────┐
 │  Agent   │ ───FlowBatch───────▶│ Collector │◀────────────│ Prometheus │◀──────────│ Grafana │
 │ (psutil) │◀───BatchAck──────── │ (gRPC +   │             └────────────┘           └─────────┘
 └──────────┘                     │  /metrics)│
      ...                         └───────────┘
 (N agents,
  one per host)
```

## Why this exists

A resume-scale project meant to demonstrate: protobuf/gRPC service design
(bidirectional streaming), containerization, an observability stack
(Prometheus + Grafana), and — as the roadmap below fills in — cloud
integration and CI/CD.

## Components

- `proto/flow.proto` — the `FlowRecord` / `FlowBatch` / `BatchAck` schema and
  the `FlowCollector` bidi-streaming service.
- `src/netflow_sentry/agent` — captures active connections (`psutil.net_connections`)
  every `CAPTURE_INTERVAL_SECONDS` and streams batches to the collector every
  `BATCH_FLUSH_SECONDS`.
- `src/netflow_sentry/collector` — gRPC server that receives batches, updates
  Prometheus counters/gauges, and serves them on `/metrics`.
- `deploy/` — Docker Compose stack: collector, agent, Prometheus, Grafana
  (with datasource + dashboard auto-provisioned).

## Running locally

Requires Docker Desktop.

```bash
cd deploy
docker compose up --build
```

Then open:
- Grafana: http://localhost:3000 (anonymous viewer access enabled; admin/admin for editing)
- Prometheus: http://localhost:9090
- Collector raw metrics: http://localhost:9100/metrics

The bundled `agent` service runs inside its own container, so on Linux hosts
it only sees that container's loopback connections — enough to prove the
pipeline end-to-end. To monitor your actual host's connections, run the
agent directly on the host instead (see below).

## Running the agent on your host (not in a container)

```bash
pip install -r requirements.txt
pip install -e ".[dev]"
python scripts/generate_proto.py   # generates src/netflow_sentry/proto_gen/*_pb2*.py

# terminal 1
python -m netflow_sentry.collector.main

# terminal 2
set COLLECTOR_ADDRESS=localhost:50051   # PowerShell: $env:COLLECTOR_ADDRESS = "localhost:50051"
python -m netflow_sentry.agent.main
```

`psutil.net_connections()` may need elevated privileges (admin/root) to see
connections owned by other processes/users, depending on OS.

## Configuration (env vars)

| Var | Component | Default | Meaning |
|---|---|---|---|
| `AGENT_ID` | agent | hostname | Label attached to every flow/metric from this agent |
| `COLLECTOR_ADDRESS` | agent | `localhost:50051` | `host:port` of the collector's gRPC endpoint |
| `CAPTURE_INTERVAL_SECONDS` | agent | `5` | (reserved for future sampling control) |
| `BATCH_FLUSH_SECONDS` | agent | `5` | How often a batch is captured and sent |
| `GRPC_PORT` | collector | `50051` | gRPC listen port |
| `METRICS_PORT` | collector | `9100` | Prometheus `/metrics` HTTP port |

## Tests

```bash
pytest -v
```

## Roadmap

- [ ] **AWS integration**: archive raw `FlowBatch` records to S3 (via Kinesis
      Firehose or direct `boto3` PutRecord) for durable storage / offline
      analysis, separate from the real-time Prometheus path.
- [ ] **CI/CD**: `.github/workflows/ci.yml` currently lints, tests, and
      builds images. Extend to push images to ECR and deploy the collector
      to ECS/Fargate via Terraform (`infra/`).
- [ ] **Anomaly detection**: a simple stats-based detector (e.g. z-score on
      per-agent flow rate) that flags spikes and exposes them as a Prometheus
      metric/alert.
- [ ] **Real byte/packet counters**: optional scapy/pcap-based capture mode
      for actual traffic volume, gated behind a config flag since it needs
      elevated privileges.
