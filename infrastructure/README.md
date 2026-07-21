# Infrastructure

- Local/one-box: [`../docker-compose.yml`](../docker-compose.yml) — Postgres 16,
  Redis 7, backend API, APScheduler worker, frontend.
- Backend image: [`../backend/Dockerfile`](../backend/Dockerfile) (python:3.12-slim).
- Frontend image: [`../frontend/Dockerfile`](../frontend/Dockerfile) (node:22-alpine, standalone build).
- Production guidance (Vercel + container host + managed Postgres/Redis):
  [`../README.md#deployment`](../README.md#deployment).

Terraform/K8s manifests are intentionally out of scope for this portfolio build.
