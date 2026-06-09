terraform {
  backend "s3" {
    # Bucket and key are provided via -backend-config at init time.
    # See docs/ci-cd.md and .github/workflows/deploy.yml.
    encrypt = true
  }
}
