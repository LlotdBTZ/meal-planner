# GitHub repo (Terraform)

Manages the `meal-planner` GitHub repository's settings as code: the repo
itself, merge rules (squash only, delete branches after merge), security
alerts, labels, optional `main` branch protection, and release-tag rulesets.

The Raspberry Pi itself is **not** managed here. It's set up by
`deploy/install.sh`, because Terraform isn't a good fit for configuring a
single machine on a home network.

## One-time setup

1. Install Terraform ≥ 1.6.
2. Create a fine-grained personal access token at
   <https://github.com/settings/personal-access-tokens/new> with:
   - Repository access: **All repositories** (it must be able to create one)
   - Permissions: **Administration: Read and write**, **Contents: Read and write**,
     **Issues: Read and write**, **Metadata: Read**
3. Export it (don't save it in a file in this repo):
   ```bash
   export GITHUB_TOKEN=github_pat_...
   ```

## Bring the existing repo under Terraform

The repo was created with `gh` (same settings as `main.tf`), so import it
rather than create it. Run once, with `GITHUB_TOKEN` exported:

```bash
cd infra/github
terraform init
terraform import github_repository.meal_planner meal-planner
terraform import github_repository_dependabot_security_updates.meal_planner meal-planner
terraform import 'github_branch_protection.main[0]' meal-planner:main
for label in "type: feature" "type: bug" "type: chore" "type: docs" \
             "area: extract" "area: list" "area: deploy"; do
  terraform import "github_issue_label.labels[\"$label\"]" "meal-planner:$label"
done
terraform plan    # should show few or no changes; review before applying
terraform apply
```

If `plan` wants to create something that already exists, import that too.

## Public repo and secrets

The repo is **public**. Secrets must never be committed (see `CLAUDE.md`):

- GitHub **secret scanning push protection** rejects pushes containing known
  key formats.
- CI runs **gitleaks** on every PR and push, and over the whole history weekly.
- CI runs **pip-audit** on the locked runtime dependencies on every PR and
  push, and weekly to catch newly published advisories.
- Real secrets live only in `/etc/meal-planner/.env` on the Pi. GitHub Actions
  holds no deploy secrets: the Pi pulls releases itself.

If a secret is ever pushed: **rotate it first** (removing it from history is
not enough once it was public), then clean up.

## Branch protection

On (free for public repos): `main` needs a PR, linear history, and green
`test (3.11)`, `test (3.13)`, `shellcheck`, `terraform`, `gitleaks`, and
`pip-audit` checks. `enforce_admins = false` keeps an owner bypass for emergencies.
If you rename a CI job, update `required_checks` in the same PR.

## Release tags

A `vX.Y.Z` tag on `main` deploys to the Pi, so two tag rulesets guard `v*`:

- **Immutable:** nobody can move, force-push, or delete a release tag, so a
  version always names the same commit. To fix a bad release, tag a new patch
  version. Break-glass: set that ruleset's `enforcement` to `disabled`.
- **Admins only:** only repo admins (the owner) can create release tags.
  Collaborators, apps, and workflow tokens can't.

These don't stop someone holding *your* credentials, since the owner can
always create tags. Keep tokens fine-grained and short-lived.

## State

State is stored locally in `terraform.tfstate` (gitignored). It contains no
secrets, but keep a copy if you want to manage the repo from another machine.
