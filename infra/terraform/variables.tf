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

variable "github_repo" {
  description = "GitHub repository (owner/name) allowed to authenticate via Workload Identity Federation."
  type        = string
  default     = "DhruvGandhi31/Network-Flow-monitoring-Pipeline"
}

variable "github_allowed_ref" {
  description = "Git ref allowed to obtain GCP credentials. Pull-request and other-branch workflows are rejected."
  type        = string
  default     = "refs/heads/main"
}

variable "wif_pool_id" {
  description = "Workload Identity pool ID. GCP soft-deletes pools for 30 days after destroy and refuses to reuse the ID, so change this (e.g. github-actions-2) when re-creating soon after a destroy."
  type        = string
  default     = "github-actions"
}

variable "labels" {
  description = "Labels applied to all resources that support them."
  type        = map(string)
  default = {
    app = "netflow-sentry"
  }
}
