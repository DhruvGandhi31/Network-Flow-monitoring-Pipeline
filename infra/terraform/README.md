# Terraform — GCP foundation

First slice of the cloud infrastructure. It provisions only cheap, stateless-ish
resources; the GKE Autopilot cluster (the part that bills while it runs) is a
later, separate change.

| Resource | Purpose |
|---|---|
| `google_project_service` (Artifact Registry, Cloud Storage) | Enables the APIs the rest depends on. `disable_on_destroy = false` so destroy doesn't break other things in a shared project. |
| `google_artifact_registry_repository.images` | Docker repo for the collector/agent images CI will push. |
| `google_storage_bucket.archive` | Archive for raw `FlowBatch` records. Uniform access, public access prevented, objects auto-deleted after `archive_retention_days` (default 30). |

## Usage

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars   # set project_id (gitignored)
gcloud auth application-default login          # Terraform uses ADC, not `gcloud auth login`
terraform init
terraform plan
terraform apply
# ...verify...
terraform destroy                              # tear down when finished
```

`project_id` intentionally has no default so Terraform can never silently
target whatever project `gcloud` happens to have active.

## Notes

- State is local (`terraform.tfstate`, gitignored). Fine for a solo,
  spin-up/tear-down project; a remote GCS backend would be the upgrade for
  anything shared.
- `.terraform.lock.hcl` is committed to pin provider versions.
- The bucket has `force_destroy = true` so `terraform destroy` works even
  with archived objects in it. Revisit before storing anything you care about.
- Validated with `terraform fmt -check` and `terraform validate` (v1.9.8).
  Not yet `plan`/`apply`-ed against a real project.
