# Terraform — GCP foundation

Cloud infrastructure so far. It provisions only cheap, stateless-ish resources
(storage, registry, identities); the GKE Autopilot cluster (the part that bills while it runs) is a
later, separate change.

| Resource | Purpose |
|---|---|
| `google_project_service` (Artifact Registry, Cloud Storage) | Enables the APIs the rest depends on. `disable_on_destroy = false` so destroy doesn't break other things in a shared project. |
| `google_artifact_registry_repository.images` | Docker repo for the collector/agent images CI will push. |
| `google_storage_bucket.archive` | Archive for raw `FlowBatch` records. Uniform access, public access prevented, objects auto-deleted after `archive_retention_days` (default 30). |

### Identity (`iam.tf`)

No service-account keys are created anywhere.

| Resource | Purpose |
|---|---|
| `google_service_account.collector` | Runtime identity for the collector. Has `roles/storage.objectCreator` on the archive bucket only (write-only; can't read or delete). Gets bound to a Kubernetes service account via Workload Identity for GKE once the cluster exists. |
| `google_service_account.ci` | Identity GitHub Actions impersonates. Has `roles/artifactregistry.writer` on the one image repo, not project-wide. |
| Workload Identity pool + `github-oidc` provider | Lets GitHub Actions exchange its OIDC token for short-lived GCP credentials. `attribute_condition` only accepts tokens where `repository == var.github_repo` **and** `ref == var.github_allowed_ref` (default `refs/heads/main`), so PR workflows, forks and other repos are rejected. |
| `google_service_account_iam_member.ci_wif` | Allows only that repo's identities to impersonate the CI service account. |

After `apply`, copy the `ci_service_account` and `workload_identity_provider`
outputs into the deploy workflow (next change) for
`google-github-actions/auth`.

**Destroy/re-create caveat:** GCP soft-deletes a Workload Identity pool for 30
days and won't reuse its ID. If you `destroy` and re-`apply` within that
window, set `wif_pool_id` to a new value (e.g. `github-actions-2`). Service
accounts have a similar, shorter delay before names can be reused.

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
