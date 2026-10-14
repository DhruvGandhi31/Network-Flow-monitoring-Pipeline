# Roadmap

Everything below is **not yet built**. Listed in the order it was proposed,
not necessarily the order it should be done — see "suggested order" at the
bottom.

> **Cloud provider note**: this project originally planned the cloud step
> around AWS (S3/Kinesis/ECS/Fargate). That was pivoted to GCP before any
> cloud-specific code was written — `infra/` was still an empty placeholder
> at the time, so there was nothing AWS-specific to unwind. The sections
> below describe the current GCP plan; see `verification-log.md` for exactly
> when/why this changed.

## 1. GCP archival

Archive raw `FlowBatch` records to Cloud Storage (GCS), separate from the
real-time Prometheus path (which only ever holds aggregated counters, never
raw records — once a batch is processed, its individual `FlowRecord`s are
gone).

Two shapes considered, neither implemented:
- **Direct**: collector uses `google-cloud-storage` (to be added as a `gcp`
  extra in `pyproject.toml`, replacing the earlier unused `aws`/`boto3`
  extra) to upload each batch (or a rolled-up window of batches) to a GCS
  bucket directly from the collector process.
- **Via Pub/Sub + Dataflow**: collector publishes each batch to a Pub/Sub
  topic; a Dataflow (or Cloud Function) sink batches/writes to GCS on its
  own schedule — decouples the collector from GCS write latency/throttling,
  more realistic for a "real" pipeline, meaningfully more infrastructure to
  stand up. Direct-to-GCS is the recommended starting point (same reasoning
  that favored plain S3 over Kinesis Firehose in the original AWS plan) —
  revisit Pub/Sub+Dataflow only if the direct path proves limiting.

`infra/` exists as an empty directory, reserved for Terraform (provider
`google`) defining the GCS bucket, a service account + IAM binding for the
collector to write to it, and eventually the GKE resources below.

## 2. CI/CD deploy step

Current `.github/workflows/ci.yml` lints, tests, and builds both Docker
images — it stops there. Extending it means:
- Push built images to **Artifact Registry** (needs a repository defined in
  Terraform, and Workload Identity Federation for GitHub Actions to
  authenticate rather than a long-lived GCP service-account key in repo
  secrets).
- Deploy the collector to **GKE (Autopilot)** — chosen over Cloud Run /
  Compute Engine specifically for the Kubernetes resume signal and because
  it matches this project's "infrastructure" framing. This is a materially
  bigger lift than a single Cloud Run service: it needs a GKE Autopilot
  cluster (Terraform), Kubernetes manifests or a Helm chart for the
  collector Deployment + Service (+ a way to reach it — likely a
  `LoadBalancer` Service or an Ingress for the gRPC port and the Prometheus
  `/metrics` port), and a `kubectl apply` or GitOps-style step in CI.
  Agent deployment is a separate question — in a real fleet, agents run on
  the hosts being monitored, not as a fixed number of cluster pods; the
  demo Compose `agent` service remains a stand-in, not a deployment target.
- Cost discipline: GKE Autopilot and any LoadBalancer have real per-hour
  cost. Plan is spin-up → verify (screenshot/log evidence, same standard as
  `verification-log.md`) → `terraform destroy`, not leaving it running. See
  the cost discussion in `verification-log.md`'s latest entry.

## 3. Anomaly detection

A stats-based detector — e.g. z-score or EWMA on per-agent flow rate — that
flags spikes and exposes the result as its own Prometheus metric (so it's
visible on the same Grafana dashboard, or wired to a Grafana alert rule)
rather than a separate notification channel. Not started; no design decided
yet on whether this lives inside the collector process or as a separate
service consuming `/metrics`. Cloud-provider-agnostic — unaffected by the
AWS→GCP pivot.

## 4. Real byte/packet counters (pcap capture mode)

`capture.py` currently reports connection *metadata* only (see
`architecture.md` for why). An optional `scapy`/pcap-based capture mode
would add real byte/packet volume per flow, gated behind a config flag,
since it needs elevated privileges (raw sockets / npcap on Windows) and
loses the current mode's "works unprivileged in any container" property.
Also unaffected by the AWS→GCP pivot.

## Suggested order

GCP archival (1) before CI/CD deploy (2) — deploying a collector that has
nothing more to offer than the local version isn't worth the GKE/Terraform
investment on its own; the archival feature gives the deploy step something
new to prove. Anomaly detection (3) and pcap mode (4) are independent of
both and of each other — either could slot in anytime, based on whichever
is more useful to demonstrate next (observability depth vs. capture
fidelity).
