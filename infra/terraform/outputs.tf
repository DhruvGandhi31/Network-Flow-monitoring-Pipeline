output "artifact_registry_repo" {
  description = "Docker repository path; image refs are <this>/collector:<tag>."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}

output "archive_bucket" {
  description = "GCS bucket for archived FlowBatch records."
  value       = google_storage_bucket.archive.name
}
