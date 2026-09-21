# Verification log

A record of what has actually been run and observed, as distinct from what
has merely been written. Kept so future work doesn't have to guess whether a
claim like "the dashboard works" was verified or assumed. See `CLAUDE.md` →
"Verification standard for this repo" for the policy this log is enforcing.

## Session 1 — initial build, bare-process smoke test

After scaffolding the full project (proto, agent, collector, Docker,
Compose, Prometheus/Grafana config, CI, tests, README):

1. Created `.venv`, installed `requirements.txt` + `.[dev]` extra.
2. Ran `python scripts/generate_proto.py` — confirmed `flow_pb2.py`,
   `flow_pb2.pyi`, `flow_pb2_grpc.py` were generated in
   `src/netflow_sentry/proto_gen/`.
3. Ran `pytest -v` — all 3 tests passed (`test_capture_flows_builds_records_from_connections`,
   `test_capture_flows_skips_connections_without_laddr`,
   `test_record_batch_increments_counters_per_record`).
4. Started the collector as a **bare local process** (not Docker) —
   confirmed via logs it bound gRPC on `:50051` and Prometheus metrics on
   `:9100`.
5. Started the agent as a **bare local process** pointed at
   `localhost:50051`, `BATCH_FLUSH_SECONDS=2`, ran ~7 seconds, then stopped
   it. Agent logs showed 4 real acked batches against this Windows host's
   actual connection table:
   ```
   ack: success=True records_received=102 msg=ok:batch#1
   ack: success=True records_received=104 msg=ok:batch#2
   ack: success=True records_received=105 msg=ok:batch#3
   ack: success=True records_received=105 msg=ok:batch#4
   ```
6. Hit `http://localhost:9100/metrics` directly and confirmed real output,
   e.g.:
   ```
   netflow_flows_received_total{agent_id="smoke-test-agent",protocol="tcp",status="LISTEN"} 128.0
   netflow_flows_received_total{agent_id="smoke-test-agent",protocol="udp",status="NONE"} 172.0
   netflow_flows_received_total{agent_id="smoke-test-agent",protocol="tcp",status="ESTABLISHED"} 92.0
   netflow_flows_received_total{agent_id="smoke-test-agent",protocol="tcp",status="TIME_WAIT"} 24.0
   netflow_batches_received_total{agent_id="smoke-test-agent"} 4.0
   netflow_active_agents 1.0
   netflow_last_batch_size{agent_id="smoke-test-agent"} 105.0
   ```
7. Killed the collector process, deleted the temporary redirected
   stdout/stderr log files so they wouldn't get committed.
8. `git init`, `git add -A`, one commit: `2394853` "Scaffold netflow-sentry:
   gRPC agent/collector, Prometheus/Grafana, Docker, CI".

**What this proved**: the protobuf schema, codegen pipeline, bidirectional
gRPC streaming, and Prometheus metric-label wiring all work correctly
against real data, end to end — outside of Docker.

**What this didn't prove**: that the Dockerfiles build correctly, that
Compose wiring (service DNS, port mappings, volume mounts) works, or that
Grafana actually renders anything.

## Session 2 — full Compose stack + Grafana visual verification

Goal: close the gap Session 1 left open.

1. `docker compose ps` initially failed — Docker Desktop's daemon wasn't
   running (`failed to connect to the docker API at
   npipe:////./pipe/dockerDesktopLinuxEngine`). Located and launched
   `Docker Desktop.exe`, then polled `docker info` in a background task
   until the daemon came up.
2. `docker compose up --build -d` in `deploy/` — all 4 images built and all
   4 containers started (`deploy-collector-1`, `deploy-agent-1`,
   `deploy-prometheus-1`, `deploy-grafana-1`).
3. `docker compose ps` after a 5s settle — all 4 containers `Up`, none
   restarting.
4. `docker compose logs collector` — confirmed `agent stream opened:
   ipv4:172.19.0.3:39342`, i.e. the containerized agent's gRPC stream
   actually connected to the containerized collector over the Compose
   network.
5. `docker compose logs agent` — confirmed 4 acked batches,
   `records_received=3` each. This is the *correct* number for a container
   with its own isolated network namespace (it only sees its own loopback +
   outbound connections) — documented as expected in `deployment.md`, not
   treated as a discrepancy from Session 1's ~100+ on the bare host.
6. `curl http://localhost:9090/api/v1/targets` → parsed JSON, confirmed job
   `netflow-collector` health = `up`.
7. `curl -u admin:admin http://localhost:3000/api/datasources` → confirmed
   the Prometheus datasource was auto-provisioned (`name: Prometheus, type:
   prometheus, url: http://prometheus:9090`).
8. `curl -u admin:admin http://localhost:3000/api/search?type=dash-db` →
   confirmed the dashboard was auto-provisioned (`NetFlow Sentry Overview`,
   uid `netflow-sentry-overview`).
9. Neither `chromium-cli` nor Playwright was present in the environment.
   Installed Playwright's Chromium browser (`npx playwright install
   --with-deps chromium`) and the `playwright` npm package, then wrote a
   short script to navigate to the dashboard URL with `waitUntil:
   "networkidle"`, wait for the dashboard title text to appear, wait an
   additional 4s for the timeseries panels to finish drawing, and take a
   full-page screenshot; also captured `pageerror` events.
10. Read the resulting screenshot directly (not just checked the script
    exited 0). Confirmed all 5 panels rendered with real data curves — flow
    rate by protocol (tcp/udp lines), flow rate by connection status
    (ESTABLISHED/LISTEN/NONE/SYN_SENT), active agents stat = 1, last batch
    size chart, batches-received-per-agent chart. No "No data" placeholder
    panels. `pageerror` array was empty.
11. Sent the screenshot to the user via `SendUserFile` so it could be
    inspected outside the session too.
12. Cleanup: removed the temporary `node_modules_tmp/` Playwright install
    directory, confirmed `git status` was clean (no stray files leaked into
    the repo), stopped a leftover background `find /` process from an
    earlier (abandoned) attempt to locate `chromium-cli` on disk.
13. Noticed and fixed an unrelated deprecation warning — `docker-compose.yml`
    had a `version: "3.9"` key that Compose v2 no longer needs and warns
    about on every invocation. Removed it, re-ran `docker compose config
    --quiet` to confirm the file still validates, and committed as `c44591b`
    "Remove obsolete compose version key".

**What this proved**: the Dockerfiles build correctly, Compose's service
discovery and port mappings work, Grafana's datasource/dashboard
provisioning works, and — critically, since provisioning YAML being present
doesn't guarantee a page actually renders — the dashboard visually renders
live data with no errors, confirmed by actually looking at a screenshot
rather than trusting the API responses alone.

**Left running**: the full stack was left up after this session (`docker
compose down` was not run), so `localhost:3000`/`:9090`/`:9100`/`:50051`
were occupied at the end of Session 2. Check `docker compose ps` in
`deploy/` before assuming these ports are free.
