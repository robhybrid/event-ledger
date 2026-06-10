# AWS Deployment (ECS Fargate)

> See also: [Cloud Architecture](../../docs/cloud-architecture.md) | [CI/CD Guide](../../docs/ci-cd.md)

This Terraform configuration deploys the Event Ledger to AWS ECS Fargate with a **public Gateway** and a **private Account Service**.

## Network topology

```
Internet → ALB (public) → Gateway ECS (public subnet)
                              │
                              └──→ Account ECS (private subnet, no public IP)
                                   DNS: account-service.event-ledger.local
```

| Component | Exposure | Notes |
|---|---|---|
| **ALB + Gateway** | Public internet | Only entry point for clients |
| **Account Service** | VPC-private | Private subnets, no public IP, security group allows port 8001 from Gateway SG only |
| **Service discovery** | Internal DNS | Gateway reaches Account at `http://account-service.<project>.local:8001` |

## Prerequisites

- AWS CLI configured with appropriate credentials
- Terraform >= 1.5
- Docker images pushed to ECR

## Build and push images

```bash
# From project root
aws ecr create-repository --repository-name event-ledger-gateway
aws ecr create-repository --repository-name event-ledger-account

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION=us-east-1
REGISTRY="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $REGISTRY

docker build --target gateway -t $REGISTRY/event-ledger-gateway:latest .
docker build --target account -t $REGISTRY/event-ledger-account:latest .
docker push $REGISTRY/event-ledger-gateway:latest
docker push $REGISTRY/event-ledger-account:latest
```

## Deploy

```bash
cd infrastructure/aws
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your ECR image URIs

terraform init \
  -backend-config="bucket=event-ledger-terraform-state-<ACCOUNT_ID>" \
  -backend-config="key=event-ledger/terraform.tfstate" \
  -backend-config="region=us-east-1"

terraform plan
terraform apply
```

## Teardown

To stop all running resources and avoid idle AWS cost:

```bash
cd infrastructure/aws
terraform destroy
```

Use the same `-var` flags (or `terraform.tfvars`) as deploy. ECS services and the NAT Gateway can take several minutes to drain.

**Automated:** set GitHub repo variable `DESTROY_AFTER` (`YYYY-MM-DD`). The [destroy-aws workflow](../../.github/workflows/destroy-aws.yml) runs daily and destroys on or after that date. Manual immediate destroy: run that workflow with **force** checked.

## Outputs

| Output | Description |
|---|---|
| `gateway_url` | Public HTTP endpoint for the Event Gateway API |
| `account_service_dns` | Private DNS name for Account Service (not internet-reachable) |
| `ecs_cluster` | ECS cluster name |

## Production notes

- Replace SQLite with RDS or another managed database for production durability
- Use AWS Secrets Manager for sensitive configuration
- Add HTTPS via ACM certificate on the ALB
- NAT Gateway is included so private-subnet tasks can pull images and reach AWS APIs
