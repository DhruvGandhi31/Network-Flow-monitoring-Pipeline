# Identities for netflow-sentry. No long-lived keys are created anywhere:
#  - the collector (runs in GKE, later) will use Workload Identity for GKE;
#  - GitHub Actions authenticates via Workload Identity Federation (OIDC).

# --- Collector runtime identity ---------------------------------------------

resource "google_service_account" "collector" {
  account_id   = "${var.name_prefix}-collector"
  display_name = "netflow-sentry collector (runtime)"

  depends_on = [google_project_service.enabled]
}

# Write-only on the archive bucket; cannot read or delete archived data.
resource "google_storage_bucket_iam_member" "collector_archive_writer" {
  bucket = google_storage_bucket.archive.name
  role   = "roles/storage.objectCreator"
  member = "serviceAccount:${google_service_account.collector.email}"
}

# --- CI/CD identity (impersonated by GitHub Actions) ------------------------

resource "google_service_account" "ci" {
  account_id   = "${var.name_prefix}-ci"
  display_name = "netflow-sentry CI/CD (GitHub Actions)"

  depends_on = [google_project_service.enabled]
}

# Push images to this one repository only, not project-wide.
resource "google_artifact_registry_repository_iam_member" "ci_image_pusher" {
  project    = google_artifact_registry_repository.images.project
  location   = google_artifact_registry_repository.images.location
  repository = google_artifact_registry_repository.images.name
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.ci.email}"
}

# --- Workload Identity Federation for GitHub Actions ------------------------

resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = var.wif_pool_id
  display_name              = "GitHub Actions"

  depends_on = [google_project_service.enabled]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-oidc"
  display_name                       = "GitHub OIDC"

  attribute_mapping = {
    "google.subject"             = "assertion.sub"
    "attribute.repository"       = "assertion.repository"
    "attribute.repository_owner" = "assertion.repository_owner"
    "attribute.ref"              = "assertion.ref"
  }

  # Hard gate: tokens from any other repo, fork, or branch are rejected before
  # they can even be exchanged. Without this condition any GitHub repo could
  # try to use this provider.
  attribute_condition = "assertion.repository == '${var.github_repo}' && assertion.ref == '${var.github_allowed_ref}'"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

# Only identities from the allowed repo may impersonate the CI service account.
resource "google_service_account_iam_member" "ci_wif" {
  service_account_id = google_service_account.ci.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repo}"
}
