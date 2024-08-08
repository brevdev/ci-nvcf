# Integration Guide for NVCF CI/CD Pipeline

## Overview

This guide is a starting point for incorporating the NVCF CI/CD pipeline into your existing workflows. 

## Current Scenario

- You have an existing CI pipeline that builds and pushes container images to a registry (e.g., Docker Hub, Amazon ECR, Google Container Registry, etc.).
- NVCF requires container images to be in NVIDIA Container Registry (NVCR).
- You need to integrate the NVCF deployment process with your existing workflow.

## Integration Options

### Option 1: Extend Your Existing CI/CD Pipeline

This option involves modifying your current CI/CD configuration to include the NVCF deployment process. We recommended adding the `mock-ngc-push` workflow to your current container CI/CD pipeline. This workflow will push your container image to NVCR and update the `launch-list.yml` with the new image tag. 

From there, also include the `deploy` workflow to deploy your function(s) to NVCF. This workflow is keyed to a succesful execution of the `mock-ngc-push` workflow.

**Steps:**
1. Copy the necessary files from this repository to your existing project:
   - `launch-nvcf.py`
   - `launch-list.yml`
   - `templates/launch-template.yml.j2`
   - `update-launch-list.py`

2. Modify your existing CI/CD configuration (e.g., `.gitlab-ci.yml`, `azure-pipelines.yml`, etc.) to include:
   - A step to push your container to NVCR
   - A step to run `launch-nvcf.py`

**Example (GitHub Actions):**

```yaml
name: Build, Push, and Deploy

on:
  push:
    branches: [ main ]

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    steps:
      # Your existing build and push steps here

      - name: Push to NVCR
        run: |
          docker tag your-image:tag nvcr.io/your-org/your-image:tag
          docker push nvcr.io/your-org/your-image:tag

      - name: Deploy to NVCF
        run: python3 launch-nvcf.py --manifest templates/launch-template.yml.j2 --environment production
        env:
          PRD_NVCF_API_KEY: ${{ secrets.PRD_NVCF_API_KEY }}
          # Add other necessary environment variables
```

TODO: add idea about adding a webhook that pulls from registry and then tags and pushes to NGC and then triggers the deploy workflow. This allows for this repo to stay intact.

We're happy to help provide additional guidance and support.