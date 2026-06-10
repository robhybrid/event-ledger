# CI/CD Guide

GitHub Actions CI (pytest) and CD (ECS Fargate via Terraform + OIDC).

## Workflows

| Workflow | Trigger | Purpose |
|---|---|---|
| [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) | Push / PR to `main` | Run unit, integration, and contract tests |
| [`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml) | Push to `main` (after CI) | Build Docker images, push to ECR, deploy via Terraform |

## Continuous integration

CI runs on every push and pull request to `main`:

```bash
uv venv
uv pip install -e ".[dev]"
uv run pytest -v
```

An HTML coverage report is generated at `htmlcov/index.html` on every run. In GitHub Actions, download the **`html-coverage-report`** artifact from the workflow run summary.

No AWS credentials are required for CI.

## Continuous deployment

CD runs automatically when a commit is pushed to `main` and CI passes.

### Deployment steps

1. Authenticate to AWS via **OIDC** (no long-lived access keys in the repo).
2. Build Gateway and Account Docker images.
3. Push images to Amazon ECR (`:latest` and `:<git-sha>` tags).
4. Run `terraform apply` with updated image URIs.
5. ECS performs a rolling deployment of new task definitions.

### Required GitHub configuration

After the first `terraform apply`, add this repository secret:

| Secret | Value | Source |
|---|---|---|
| `AWS_ROLE_ARN` | `arn:aws:iam::<account-id>:role/event-ledger-github-actions` | `terraform output github_actions_role_arn` |

OIDC trust is scoped to this repository — no access keys are stored in GitHub.

### Manual deployment

```bash
# From project root
AWS_REGION=us-east-1
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGISTRY="${ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

aws ecr get-login-password --region $AWS_REGION | \
  docker login --username AWS --password-stdin $REGISTRY

docker build --target gateway -t $REGISTRY/event-ledger-gateway:latest .
docker build --target account  -t $REGISTRY/event-ledger-account:latest .
docker push $REGISTRY/event-ledger-gateway:latest
docker push $REGISTRY/event-ledger-account:latest

cd infrastructure/aws
terraform init
terraform apply \
  -var="gateway_image=$REGISTRY/event-ledger-gateway:latest" \
  -var="account_image=$REGISTRY/event-ledger-account:latest"
```

### Terraform remote state

State is stored in S3 (`event-ledger-terraform-state-<account-id>`) so GitHub Actions and local runs share the same state.

## Rollback

Re-run the deploy workflow on a previous commit, or manually apply Terraform with a known-good image tag:

```bash
terraform apply \
  -var="gateway_image=$REGISTRY/event-ledger-gateway:<previous-sha>" \
  -var="account_image=$REGISTRY/event-ledger-account:<previous-sha>"
```
