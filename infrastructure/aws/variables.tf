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

variable "otel_collector_image" {
  description = "ECR image URI for the OTel Collector"
  type        = string
}

variable "jaeger_image" {
  description = "Container image for Jaeger all-in-one"
  type        = string
  default     = "jaegertracing/all-in-one:1.54"
}

variable "github_repository" {
  description = "GitHub repository in owner/repo format for OIDC trust"
  type        = string
  default     = "robhybrid/event-ledger"
}
