terraform {
  required_version = ">= 1.0.0"
  required_providers {
    github = {
      source  = "integrations/github"
      version = "~> 6.0"
    }
  }
  # Backend configuration should be added here by the user
  # backend "s3" {}
}

provider "github" {
  owner = var.github_org
}

locals {
  teams_config = yamldecode(file("${path.module}/../config/teams.yaml"))

  # Build a map keyed by team name for use with for_each
  teams = { for t in local.teams_config.teams : t.name => t }

  # Flatten nested members lists into a single map keyed by "team/username"
  # so github_team_membership can iterate with for_each
  team_memberships = merge([
    for team in local.teams_config.teams : {
      for member in lookup(team, "members", []) :
      "${team.name}/${member.username}" => {
        team_name = team.name
        username  = member.username
        role      = member.role
      }
    }
  ]...)
}

resource "github_team" "teams" {
  for_each = local.teams

  name           = each.value.name
  description    = each.value.description
  privacy        = each.value.privacy
  parent_team_id = lookup(each.value, "parent_team", null) != null ? github_team.teams[each.value.parent_team].id : null
}

resource "github_team_membership" "memberships" {
  for_each = local.team_memberships

  team_id  = github_team.teams[each.value.team_name].id
  username = each.value.username
  role     = each.value.role
}
