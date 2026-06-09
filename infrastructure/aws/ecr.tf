resource "aws_ecr_repository" "gateway" {
  name                 = "${var.project_name}-gateway"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Name = "${var.project_name}-gateway"
  }
}

resource "aws_ecr_repository" "otel_collector" {
  name                 = "${var.project_name}-otel-collector"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Name = "${var.project_name}-otel-collector"
  }
}

resource "aws_ecr_repository" "account" {
  name                 = "${var.project_name}-account"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Name = "${var.project_name}-account"
  }
}

output "ecr_gateway_url" {
  value = aws_ecr_repository.gateway.repository_url
}

output "ecr_account_url" {
  value = aws_ecr_repository.account.repository_url
}

output "ecr_otel_collector_url" {
  value = aws_ecr_repository.otel_collector.repository_url
}
