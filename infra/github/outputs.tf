output "repo_url" {
  value = github_repository.meal_planner.html_url
}

output "clone_url_https" {
  value = github_repository.meal_planner.http_clone_url
}

output "clone_url_ssh" {
  value = github_repository.meal_planner.ssh_clone_url
}
