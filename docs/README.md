# netflow-sentry documentation

Detailed documentation of what's been built, why it's built that way, and
what's been verified to actually work. The top-level `README.md` is the
quick-start; this folder is the deep dive. `CLAUDE.md` at the repo root is
the terse command/convention reference for an AI agent picking this project
back up.

## Contents

1. [architecture.md](architecture.md) — system design, data flow, why bidirectional
   gRPC streaming and a connection-table snapshot rather than packet capture.
2. [protocol.md](protocol.md) — the `flow.proto` schema, field by field, and the codegen process.
3. [components.md](components.md) — the agent and collector implementations, module by module.
4. [observability.md](observability.md) — every Prometheus metric emitted and every Grafana panel, with the PromQL behind each.
5. [deployment.md](deployment.md) — Dockerfiles, Compose stack, and the CI pipeline.
6. [configuration.md](configuration.md) — every environment variable, its default, and what reads it.
7. [verification-log.md](verification-log.md) — the actual commands run and real output observed while building this, session by session.
8. [roadmap.md](roadmap.md) — what's explicitly not built yet (AWS, CI/CD deploy, anomaly detection) and the shape each is expected to take.

## One-paragraph summary

Agents run `psutil.net_connections()` on an interval, wrap the results in a
protobuf `FlowBatch`, and push it down a long-lived bidirectional gRPC stream
to a collector. The collector updates in-process Prometheus counters/gauges
per batch and acks back over the same stream. Prometheus scrapes the
collector's `/metrics` endpoint; Grafana queries Prometheus and renders a
pre-provisioned dashboard. Everything is containerized and wired together
with Docker Compose for local development; a GitHub Actions workflow lints,
tests, and builds (but does not yet deploy) the two service images.
