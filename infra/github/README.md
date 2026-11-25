# GitHub repo (Terraform)

Manages the `meal-planner` GitHub repository's settings as code: the repo
itself, merge rules (squash only, delete branches after merge), security
alerts, labels, and optional `main` branch protection.

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

## Create the repo and push the code

```bash
cd infra/github
terraform init
terraform plan
terraform apply

cd ../..
git remote add origin "$(terraform -chdir=infra/github output -raw clone_url_https)"
git push -u origin main
```

**If the repo already exists** (e.g. it was published from VS Code), import it
instead of creating it:

```bash
terraform -chdir=infra/github import github_repository.meal_planner meal-planner
terraform -chdir=infra/github apply
```

## Branch protection

`enable_branch_protection` defaults to `false`, because GitHub only allows
branch protection on **private** repos for paid plans. To turn it on, either
make the repo public or upgrade to GitHub Pro, then:

```bash
terraform apply -var enable_branch_protection=true
```

Apply it only *after* CI has run once on GitHub, so the required check names
(`test (3.11)`, `test (3.13)`, `terraform`) exist.

## State

State is stored locally in `terraform.tfstate` (gitignored). It contains no
secrets, but keep a copy if you want to manage the repo from another machine.
