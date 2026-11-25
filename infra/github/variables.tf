variable "github_owner" {
  description = "GitHub user or org that owns the repo."
  type        = string
  default     = "LlotdBTZ"
}

variable "repo_name" {
  description = "Repository name."
  type        = string
  default     = "meal-planner"
}

variable "visibility" {
  description = "public or private."
  type        = string
  default     = "private"

  validation {
    condition     = contains(["public", "private"], var.visibility)
    error_message = "visibility must be \"public\" or \"private\"."
  }
}

variable "enable_branch_protection" {
  description = "Protect main (requires a public repo, or GitHub Pro for private repos)."
  type        = bool
  default     = false
}

variable "required_checks" {
  description = "CI check names that must pass before merging to main."
  type        = list(string)
  default     = ["test (3.11)", "test (3.13)", "terraform"]
}

variable "labels" {
  description = "Issue/PR labels to manage."
  type = map(object({
    color       = string
    description = string
  }))
  default = {
    "type: feature" = { color = "1d76db", description = "New functionality" }
    "type: bug"     = { color = "d73a4a", description = "Something is broken" }
    "type: chore"   = { color = "c5def5", description = "Maintenance, deps, tooling" }
    "type: docs"    = { color = "0075ca", description = "Documentation" }
    "area: extract" = { color = "fbca04", description = "Link → recipe extraction" }
    "area: list"    = { color = "0e8a16", description = "Weekly grocery list" }
    "area: deploy"  = { color = "5319e7", description = "Raspberry Pi / infra" }
  }
}
