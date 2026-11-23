# GKE Autopilot cluster for the collector.
#
# This is the one part of the stack that costs money while it exists, so every
# resource here is gated on var.create_cluster (default false). A plain
# `terraform apply` will not start billing; opt in with
# `terraform apply -var create_cluster=true`, verify, then destroy.

locals {
  cluster_count = var.create_cluster ? 1 : 0
}

# Dedicated node identity instead of the over-privileged default Compute SA.
resource "google_service_account" "gke_nodes" {
  count = local.cluster_count

  account_id   = "${var.name_prefix}-gke-nodes"
  display_name = "netflow-sentry GKE nodes"

  depends_on = [google_project_service.enabled]
}

resource "google_project_iam_member" "gke_nodes" {
  for_each = var.create_cluster ? toset([
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
    "roles/monitoring.viewer",
    "roles/stackdriver.resourceMetadata.writer",
  ]) : toset([])

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.gke_nodes[0].email}"
}

# Pull images from the one registry repo only.
resource "google_artifact_registry_repository_iam_member" "gke_nodes_image_puller" {
  count = local.cluster_count

  project    = google_artifact_registry_repository.images.project
  location   = google_artifact_registry_repository.images.location
  repository = google_artifact_registry_repository.images.name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.gke_nodes[0].email}"
}

resource "google_container_cluster" "autopilot" {
  count = local.cluster_count

  name     = var.cluster_name
  location = var.region

  enable_autopilot = true

  # Provider default is true, which would make `terraform destroy` fail. This
  # project is spin-up / verify / tear-down by design.
  deletion_protection = false

  release_channel {
    channel = "REGULAR"
  }

  # Autopilot enables Workload Identity (<project>.svc.id.goog) automatically.
  cluster_autoscaling {
    auto_provisioning_defaults {
      service_account = google_service_account.gke_nodes[0].email
      oauth_scopes    = ["https://www.googleapis.com/auth/cloud-platform"]
    }
  }

  resource_labels = var.labels

  depends_on = [
    google_project_service.enabled,
    google_project_iam_member.gke_nodes,
  ]
}

# Workload Identity: lets the Kubernetes service account used by the collector
# pod act as the collector GCP service account (which can write to the archive
# bucket). Needs the cluster to exist first because that is what creates the
# <project>.svc.id.goog identity pool.
resource "google_service_account_iam_member" "collector_workload_identity" {
  count = local.cluster_count

  service_account_id = google_service_account.collector.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[${var.k8s_namespace}/${var.k8s_service_account}]"

  depends_on = [google_container_cluster.autopilot]
}

# Lets the CI identity run `gcloud container clusters get-credentials` and
# apply manifests. Scoped to this dedicated project.
resource "google_project_iam_member" "ci_gke_deployer" {
  count = local.cluster_count

  project = var.project_id
  role    = "roles/container.developer"
  member  = "serviceAccount:${google_service_account.ci.email}"
}
