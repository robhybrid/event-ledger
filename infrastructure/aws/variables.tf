variable "aws_region" {
  description = "AWS region for deployment"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name prefix for AWS resources"
  type        = string
  default     = "event-ledger"
}

variable "gateway_image" {
  description = "ECR image URI for the gateway service"
  type        = string
}

variable "account_image" {
  description = "ECR image URI for the account service"
  type        = string
}

variable "github_repository" {
  description = "GitHub repository in owner/repo format for OIDC trust"
  type        = string
  default     = "robhybrid/event-ledger"
}
