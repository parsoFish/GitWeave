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

# Organization Baseline Resources will go here
