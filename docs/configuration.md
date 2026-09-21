# Configuration reference

All configuration is environment variables, read exclusively in
`src/netflow_sentry/common/config.py`. There are no config files, no CLI
flags, and no hardcoded addresses in application code.

| Variable | Read by | Default | Purpose |
|---|---|---|---|
| `AGENT_ID` | `AgentConfig` | `socket.gethostname()` | Label attached to every `FlowRecord`/`FlowBatch` from this agent, and to every Prometheus metric series it produces. Set explicitly (e.g. `agent-local-1` in Compose) when the hostname isn't meaningful, or to distinguish multiple agents on one host. |
| `COLLECTOR_ADDRESS` | `AgentConfig` | `localhost:50051` | `host:port` the agent's gRPC channel connects to. `collector:50051` inside Compose (Docker DNS), `localhost:50051` for a bare local process. |
| `CAPTURE_INTERVAL_SECONDS` | `AgentConfig` | `5` | Parsed but currently unused — reserved for decoupling capture cadence from send cadence. |
| `BATCH_FLUSH_SECONDS` | `AgentConfig` | `5` | How often the agent captures a fresh snapshot and sends it as a `FlowBatch`. |
| `GRPC_PORT` | `CollectorConfig` | `50051` | Port the collector's gRPC server binds (`[::]:{port}`, all interfaces). |
| `METRICS_PORT` | `CollectorConfig` | `9100` | Port serving the Prometheus `/metrics` endpoint. |

## Where each is set today

- **Bare local process**: not set at all (defaults apply), or exported
  manually — e.g. `$env:COLLECTOR_ADDRESS = "localhost:50051"` in PowerShell.
- **Docker Compose**: `deploy/docker-compose.yml`, under each service's
  `environment:` block.
- **CI**: not set — the CI pipeline only lints/tests/builds, it doesn't run
  the services against each other.
- **AWS (not yet built)**: expected to come from ECS task definition
  environment variables / Secrets Manager, per `roadmap.md`.
