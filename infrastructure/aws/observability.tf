resource "aws_security_group" "otel_collector" {
  name        = "${var.project_name}-otel-collector-sg"
  description = "OTel Collector - accepts OTLP from Gateway and Account"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 4317
    to_port         = 4317
    protocol        = "tcp"
    security_groups = [aws_security_group.gateway.id, aws_security_group.account.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "jaeger" {
  name        = "${var.project_name}-jaeger-sg"
  description = "Jaeger - accepts OTLP from collector and UI from ALB"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port       = 4317
    to_port         = 4317
    protocol        = "tcp"
    security_groups = [aws_security_group.otel_collector.id]
  }

  ingress {
    from_port       = 16686
    to_port         = 16686
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_service_discovery_service" "otel_collector" {
  name = "otel-collector"

  dns_config {
    namespace_id = aws_service_discovery_private_dns_namespace.main.id

    dns_records {
      ttl  = 10
      type = "A"
    }

    routing_policy = "MULTIVALUE"
  }

  health_check_custom_config {
    failure_threshold = 1
  }
}

resource "aws_service_discovery_service" "jaeger" {
  name = "jaeger"

  dns_config {
    namespace_id = aws_service_discovery_private_dns_namespace.main.id

    dns_records {
      ttl  = 10
      type = "A"
    }

    routing_policy = "MULTIVALUE"
  }

  health_check_custom_config {
    failure_threshold = 1
  }
}

resource "aws_cloudwatch_log_group" "otel_collector" {
  name              = "/ecs/${var.project_name}/otel-collector"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_group" "jaeger" {
  name              = "/ecs/${var.project_name}/jaeger"
  retention_in_days = 14
}

resource "aws_lb_target_group" "jaeger" {
  name        = "${var.project_name}-jaeger-tg"
  port        = 16686
  protocol    = "HTTP"
  vpc_id      = aws_vpc.main.id
  target_type = "ip"

  health_check {
    path                = "/"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 5
    interval            = 30
    matcher             = "200"
  }
}

resource "aws_lb_listener" "jaeger" {
  load_balancer_arn = aws_lb.main.arn
  port              = 8080
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.jaeger.arn
  }
}

resource "aws_ecs_task_definition" "otel_collector" {
  family                   = "${var.project_name}-otel-collector"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.ecs_execution.arn

  container_definitions = jsonencode([{
    name  = "otel-collector"
    image = var.otel_collector_image
    portMappings = [{ containerPort = 4317, protocol = "tcp" }]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.otel_collector.name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "ecs"
      }
    }
  }])
}

resource "aws_ecs_task_definition" "jaeger" {
  family                   = "${var.project_name}-jaeger"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.ecs_execution.arn

  container_definitions = jsonencode([{
    name  = "jaeger"
    image = var.jaeger_image
    portMappings = [
      { containerPort = 4317, protocol = "tcp" },
      { containerPort = 16686, protocol = "tcp" },
    ]
    environment = [
      { name = "COLLECTOR_OTLP_ENABLED", value = "true" },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.jaeger.name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "ecs"
      }
    }
  }])
}

resource "aws_ecs_service" "jaeger" {
  name            = "${var.project_name}-jaeger"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.jaeger.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.jaeger.id]
    assign_public_ip = false
  }

  service_registries {
    registry_arn = aws_service_discovery_service.jaeger.arn
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.jaeger.arn
    container_name   = "jaeger"
    container_port   = 16686
  }

  depends_on = [aws_lb_listener.jaeger]
}

resource "aws_ecs_service" "otel_collector" {
  name            = "${var.project_name}-otel-collector"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.otel_collector.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.private[*].id
    security_groups  = [aws_security_group.otel_collector.id]
    assign_public_ip = false
  }

  service_registries {
    registry_arn = aws_service_discovery_service.otel_collector.arn
  }

  depends_on = [aws_ecs_service.jaeger]
}

output "jaeger_url" {
  value       = "http://${aws_lb.main.dns_name}:8080"
  description = "Public URL for Jaeger UI (via ALB port 8080)"
}
