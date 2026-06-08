# AWS Deployment (ECS Fargate)

This Terraform configuration deploys the Event Ledger to AWS ECS Fargate with an Application Load Balancer exposing the Gateway.

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

terraform init
terraform plan
terraform apply
```

## Outputs

After apply, `gateway_url` provides the public HTTP endpoint for the Event Gateway API.

## Production notes

- Replace SQLite with RDS or another managed database for production durability
- Use AWS Secrets Manager for sensitive configuration
- Add HTTPS via ACM certificate on the ALB
- Use service discovery or internal ALB for Gateway → Account communication instead of public DNS
