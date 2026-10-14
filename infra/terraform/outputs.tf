output "artifact_registry_repo" {
  description = "Docker repository path; image refs are <this>/collector:<tag>."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}

output "collector_service_account" {
  description = "Runtime identity for the collector (bound to a Kubernetes SA once GKE exists)."
  value       = google_service_account.collector.email
}

output "ci_service_account" {
  description = "Service account GitHub Actions impersonates. Set as GCP_SERVICE_ACCOUNT in the workflow."
  value       = google_service_account.ci.email
}

output "workload_identity_provider" {
  description = "Full provider resource name. Set as GCP_WORKLOAD_IDENTITY_PROVIDER in the workflow (google-github-actions/auth)."
  value       = google_iam_workload_identity_pool_provider.github.name
}

output "archive_bucket" {
  description = "GCS bucket for archived FlowBatch records."
  value       = google_storage_bucket.archive.name
}
