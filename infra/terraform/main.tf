locals {
  services = [
    "artifactregistry.googleapis.com",
    "storage.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "sts.googleapis.com",
  ]
}

resource "google_project_service" "enabled" {
  for_each = toset(local.services)

  service            = each.value
  disable_on_destroy = false
}

# Container images for the collector and agent (pushed by CI in a later step).
resource "google_artifact_registry_repository" "images" {
  repository_id = var.name_prefix
  location      = var.region
  format        = "DOCKER"
  description   = "netflow-sentry collector and agent images"
  labels        = var.labels

  depends_on = [google_project_service.enabled]
}

# Archive for raw FlowBatch records (written by the collector in a later step).
resource "google_storage_bucket" "archive" {
  # Bucket names are global; the project ID makes this unique.
  name     = "${var.name_prefix}-archive-${var.project_id}"
  location = var.region
  labels   = var.labels

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  # Lets `terraform destroy` clean up even when objects exist. Fine for a
  # spin-up/verify/tear-down project; revisit before storing anything precious.
  force_destroy = true

  lifecycle_rule {
    condition {
      age = var.archive_retention_days
    }
    action {
      type = "Delete"
    }
  }

  depends_on = [google_project_service.enabled]
}
