# Deployment

## Dockerfiles

`docker/collector.Dockerfile` and `docker/agent.Dockerfile` are near-mirrors,
both `python:3.12-slim`:

1. Copy only `pyproject.toml` + `requirements.txt` first, `pip install -r
   requirements.txt grpcio-tools` — isolates the dependency-install layer so
   it's Docker-cached across builds that only change application code.
2. Copy `proto/`, `scripts/`, `src/`.
3. Run `python scripts/generate_proto.py` **inside the image build** — stubs
   are generated fresh at build time, never copied in stale (see
   `protocol.md`).
4. `pip install -e .` — installs the package itself.
5. `CMD` runs the service's `main` module
   (`python -m netflow_sentry.collector.main` /
   `python -m netflow_sentry.agent.main`).

Collector `EXPOSE`s `50051` (gRPC) and `9100` (Prometheus metrics). Agent
exposes nothing — it only makes outbound connections.

## `deploy/docker-compose.yml`

Four services on one default bridge network (`deploy_default`), addressed by
Compose's embedded DNS using the service name as hostname:

| Service | Image | Ports (host:container) | Notes |
|---|---|---|---|
| `collector` | built from `docker/collector.Dockerfile` | `50051:50051`, `9100:9100` | `GRPC_PORT`/`METRICS_PORT` set explicitly (matches defaults, but explicit for clarity) |
| `agent` | built from `docker/agent.Dockerfile` | *(none)* | `depends_on: collector`; `COLLECTOR_ADDRESS=collector:50051`; `AGENT_ID=agent-local-1`; 5s flush interval |
| `prometheus` | `prom/prometheus:latest` | `9090:9090` | mounts `prometheus/prometheus.yml` read-only |
| `grafana` | `grafana/grafana:latest` | `3000:3000` | mounts `grafana/provisioning` and `grafana/dashboards` read-only; anonymous viewer access enabled |

`depends_on` only sequences container *start order*, not readiness — the
agent may attempt its first connection before the collector's gRPC server is
listening. In practice this hasn't caused a problem because `grpc.insecure_channel`
+ `StreamFlows` will simply retry/queue at the gRPC layer rather than fail
hard on first send, and the observed startup gap in this stack has been
well under a second. Worth revisiting with an explicit healthcheck if that
ever changes.

**Note on what the agent container can see**: because it's an unprivileged
container on its own network namespace, `psutil.net_connections()` inside it
only returns that container's own connections (its loopback + its outbound
gRPC connection to the collector) — typically ~3 records per batch. This is
correct, expected container isolation, not a bug. To monitor the actual
Windows/Linux host's real traffic, run the agent as a bare process on the
host instead of inside Compose (see root `README.md`).

## CI — `.github/workflows/ci.yml`

Triggers on push/PR to `main`. Two jobs:

1. **`test`** (ubuntu-latest): checkout → `actions/setup-python@v5` (3.12) →
   `pip install -r requirements.txt` + `pip install -e ".[dev]"` → **regenerate
   proto stubs** (`python scripts/generate_proto.py` — CI does not rely on
   any committed generated code, consistent with the gitignore policy) →
   `ruff check src tests` → `pytest -v`.
2. **`build-images`** (`needs: test`): checkout → `docker build -f
   docker/collector.Dockerfile -t netflow-sentry-collector:ci .` → same for
   the agent image. This only proves the images *build*; nothing is pushed
   to a registry and nothing is deployed. Extending this to push to ECR and
   deploy to ECS/Fargate is the CI/CD half of the roadmap (`roadmap.md`).

## Running it

```bash
cd deploy
docker compose up --build -d     # requires Docker Desktop's daemon running
docker compose ps                # confirm all 4 containers are Up, not restarting
docker compose logs collector    # confirm "agent stream opened"
docker compose logs agent        # confirm "ack: success=True"
docker compose down              # tear down when finished
```
