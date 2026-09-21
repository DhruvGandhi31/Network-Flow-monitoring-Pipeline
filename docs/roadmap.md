# Roadmap

Everything below is **not yet built**. Listed in the order it was proposed,
not necessarily the order it should be done — see "suggested order" at the
bottom.

## 1. AWS integration

Archive raw `FlowBatch` records to S3, separate from the real-time
Prometheus path (which only ever holds aggregated counters, never raw
records — once a batch is processed, its individual `FlowRecord`s are
gone).

Two shapes considered, neither implemented:
- **Direct**: collector uses `boto3` (already listed as the `aws` extra in
  `pyproject.toml`, unused so far) to `PutObject` each batch (or a rolled-up
  window of batches) to S3 directly from the collector process.
- **Via Kinesis Firehose**: collector `PutRecord`s to a Firehose delivery
  stream, which buffers and batches to S3 on its own schedule — decouples
  the collector from S3 write latency/throttling, more realistic for a
  "real" pipeline, more infrastructure to stand up.

`infra/` exists as an empty directory, reserved for Terraform defining the
S3 bucket (and Kinesis stream, if that path is chosen), IAM role/policy for
the collector to write, and eventually the ECS/Fargate resources below.

## 2. CI/CD deploy step

Current `.github/workflows/ci.yml` lints, tests, and builds both Docker
images — it stops there. Extending it means:
- Push built images to ECR (needs an ECR repo per service, defined in
  Terraform, and an IAM role/OIDC trust relationship for GitHub Actions to
  assume rather than long-lived AWS keys in repo secrets).
- Deploy the collector to ECS/Fargate (agent deployment is a separate
  question — in a real fleet, agents run on the hosts being monitored, not
  as a fixed number of Fargate tasks; the demo Compose `agent` service is a
  stand-in, not a deployment target).

## 3. Anomaly detection

A stats-based detector — e.g. z-score or EWMA on per-agent flow rate — that
flags spikes and exposes the result as its own Prometheus metric (so it's
visible on the same Grafana dashboard, or wired to a Grafana alert rule)
rather than a separate notification channel. Not started; no design decided
yet on whether this lives inside the collector process or as a separate
service consuming `/metrics`.

## 4. Real byte/packet counters (pcap capture mode)

`capture.py` currently reports connection *metadata* only (see
`architecture.md` for why). An optional `scapy`/pcap-based capture mode
would add real byte/packet volume per flow, gated behind a config flag,
since it needs elevated privileges (raw sockets / npcap on Windows) and
loses the current mode's "works unprivileged in any container" property.

## Suggested order

AWS archival (1) before CI/CD deploy (2) — deploying a collector that has
nothing more to offer than the local version isn't worth the Terraform
investment on its own; the archival feature gives the deploy step something
new to prove. Anomaly detection (3) and pcap mode (4) are independent of
both and of each other — either could slot in anytime, based on whichever
is more useful to demonstrate next (observability depth vs. capture
fidelity).
