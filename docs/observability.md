# Observability — Prometheus + Grafana

## Metrics exposed (`collector/metrics.py`, served at `:9100/metrics`)

See `components.md` for the full table. Prometheus scrapes this endpoint
every 5 seconds (`deploy/prometheus/prometheus.yml`, single job
`netflow-collector`, target `collector:9100` — the Docker Compose service
name, resolved via Compose's embedded DNS).

`prometheus_client` also auto-exports standard process/GC metrics
(`python_gc_objects_collected_total`, `python_info`, etc.) alongside the
`netflow_*` metrics — visible on `/metrics` but not surfaced on the
dashboard.

## Grafana provisioning

Grafana auto-configures itself from files mounted read-only into the
container — no manual UI setup required after `docker compose up`:

- `deploy/grafana/provisioning/datasources/datasource.yml` registers
  Prometheus (`http://prometheus:9090`) as the default datasource.
- `deploy/grafana/provisioning/dashboards/dashboard.yml` tells Grafana to
  load any dashboard JSON found in `/var/lib/grafana/dashboards` (mounted
  from `deploy/grafana/dashboards/`).
- `deploy/grafana/dashboards/flow_overview.json` is that dashboard —
  UID `netflow-sentry-overview`, 5s auto-refresh, last-15-minutes default
  window.

Anonymous viewer access is enabled in `docker-compose.yml`
(`GF_AUTH_ANONYMOUS_ENABLED=true`, role `Viewer`) so the dashboard is
viewable at `http://localhost:3000` with no login; `admin`/`admin` is set for
editing.

## Dashboard panels (`flow_overview.json`)

| Panel | Type | PromQL | What it shows |
|---|---|---|---|
| Flow rate by protocol | timeseries | `sum by (protocol) (rate(netflow_flows_received_total[1m]))` | tcp vs udp flow throughput |
| Flow rate by connection status | timeseries | `sum by (status) (rate(netflow_flows_received_total[1m]))` | ESTABLISHED / LISTEN / TIME_WAIT / etc. breakdown |
| Active agents | stat | `netflow_active_agents` | Count of distinct agents that have connected |
| Last batch size by agent | timeseries | `netflow_last_batch_size` (legend `{{agent_id}}`) | Most recent batch record count, per agent |
| Batches received per agent | timeseries | `sum by (agent_id) (rate(netflow_batches_received_total[1m]))` | Batch send rate, per agent — a stand-in health signal for "is this agent still reporting" |

## Verified rendering

This dashboard was not just provisioned and assumed correct — it was
rendered in an actual headless browser (Playwright + Chromium, installed for
this purpose since neither was already present in the environment) against
the live running stack, and screenshotted. All five panels showed real data
curves with no "No data" placeholders and zero browser console errors. Full
details, including the exact commands and API responses checked beforehand
(Prometheus target health, Grafana datasource/dashboard listing via its
REST API), are in `verification-log.md`.
