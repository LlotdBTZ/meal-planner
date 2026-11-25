terraform {
  required_version = ">= 1.6"

  required_providers {
    github = {
      source  = "integrations/github"
      version = "~> 6.0"
    }
  }
}

# Auth: export GITHUB_TOKEN (fine-grained PAT; see README.md in this folder).
provider "github" {
  owner = var.github_owner
}

resource "github_repository" "meal_planner" {
  name        = var.repo_name
  description = "Save recipes from TikTok/Instagram links, plan the week, copy a grocery list. Self-hosted on a Raspberry Pi."
  visibility  = var.visibility
  topics      = ["recipes", "meal-planning", "fastapi", "raspberry-pi", "self-hosted"]

  has_issues   = true
  has_projects = false
  has_wiki     = false

  # Squash-merge only keeps main's history one-commit-per-PR.
  allow_merge_commit          = false
  allow_rebase_merge          = false
  allow_squash_merge          = true
  squash_merge_commit_title   = "PR_TITLE"
  squash_merge_commit_message = "PR_BODY"
  delete_branch_on_merge      = true
  allow_update_branch         = true

  # Code is pushed from the local repo after apply; don't create an initial commit.
  auto_init = false

  # Free on public repos: GitHub blocks pushes that contain known secret formats.
  dynamic "security_and_analysis" {
    for_each = var.visibility == "public" ? [1] : []
    content {
      secret_scanning {
        status = "enabled"
      }
      secret_scanning_push_protection {
        status = "enabled"
      }
    }
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "github_repository_vulnerability_alerts" "meal_planner" {
  repository = github_repository.meal_planner.name
  enabled    = true
}

resource "github_repository_dependabot_security_updates" "meal_planner" {
  repository = github_repository.meal_planner.name
  enabled    = true

  depends_on = [github_repository_vulnerability_alerts.meal_planner]
}

# Branch protection on private repos needs GitHub Pro/Team; on a free account
# it only works for public repos. Toggle with var.enable_branch_protection.
# enforce_admins = false leaves the owner a break-glass bypass.
resource "github_branch_protection" "main" {
  count = var.enable_branch_protection ? 1 : 0

  repository_id  = github_repository.meal_planner.node_id
  pattern        = "main"
  enforce_admins = false

  required_status_checks {
    strict   = true
    contexts = var.required_checks
  }

  required_pull_request_reviews {
    # Solo project: require a PR, but not an approving review from someone else.
    required_approving_review_count = 0
    dismiss_stale_reviews           = true
  }

  required_linear_history = true
  allows_force_pushes     = false
  allows_deletions        = false
}

resource "github_issue_label" "labels" {
  for_each = var.labels

  repository  = github_repository.meal_planner.name
  name        = each.key
  color       = each.value.color
  description = each.value.description
}

# Release tags deploy: the Pi runs any vX.Y.Z tag on main (deploy/update.sh).
# Free for public repos. Rulesets apply on top of branch protection.

# Once pushed, a release tag can't be moved or deleted, by anyone, so a
# deployed version always means the same commit. No bypass on purpose: to fix
# a bad release, tag a new patch version. (Break-glass: disable this ruleset.)
resource "github_repository_ruleset" "release_tags_immutable" {
  name        = "release tags are immutable"
  repository  = github_repository.meal_planner.name
  target      = "tag"
  enforcement = "active"

  conditions {
    ref_name {
      include = ["refs/tags/v*"]
      exclude = []
    }
  }

  rules {
    update           = true
    deletion         = true
    non_fast_forward = true
  }
}

# Only repo admins (the owner) can create release tags, not collaborators,
# apps, or workflow tokens.
resource "github_repository_ruleset" "release_tags_create" {
  name        = "only admins create release tags"
  repository  = github_repository.meal_planner.name
  target      = "tag"
  enforcement = "active"

  conditions {
    ref_name {
      include = ["refs/tags/v*"]
      exclude = []
    }
  }

  bypass_actors {
    actor_id    = 5 # base repository role "admin"
    actor_type  = "RepositoryRole"
    bypass_mode = "always"
  }

  rules {
    creation = true
  }
}
