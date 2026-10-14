variable "project_id" {
  description = "GCP project to deploy into. Deliberately has no default so a stale gcloud config can never silently pick the project."
  type        = string
}

variable "region" {
  description = "Region for Artifact Registry and the GCS bucket."
  type        = string
  default     = "us-central1"
}

variable "name_prefix" {
  description = "Prefix for resource names."
  type        = string
  default     = "netflow-sentry"
}

variable "archive_retention_days" {
  description = "Days before archived FlowBatch objects are deleted. Keeps storage cost bounded."
  type        = number
  default     = 30
}

variable "labels" {
  description = "Labels applied to all resources that support them."
  type        = map(string)
  default = {
    app = "netflow-sentry"
  }
}
