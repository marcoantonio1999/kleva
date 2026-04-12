# CI/CD and Kubernetes Integration

This project includes GitHub Actions pipelines and Kubernetes manifests to satisfy interview requirements for automation and container orchestration.

## 1) CI pipeline

File: `.github/workflows/ci.yml`

What it does:

- Backend checks:
  - Installs Python 3.12.
  - Installs backend dependencies.
  - Compiles backend source (`python -m compileall app`).
- Frontend checks:
  - Installs Node 20.
  - Installs frontend dependencies.
  - Builds frontend (`npm run build`).
- Docker Compose validation:
  - Validates `docker-compose.yml` with `docker compose config`.

When it runs:

- On pull requests.
- On pushes to `main`.

## 2) Image release pipeline

File: `.github/workflows/release-images.yml`

What it does:

- Builds backend and frontend Docker images.
- Pushes both images to GHCR:
  - `ghcr.io/<owner>/kleva-backend`
  - `ghcr.io/<owner>/kleva-frontend`
- Tags images with commit SHA and `latest` on default branch.

When it runs:

- On pushes to `main`.
- Manual trigger (`workflow_dispatch`).

## 3) Kubernetes deploy pipeline

File: `.github/workflows/deploy-k8s.yml`

What it does:

- Runs manually with input `imageTag`.
- Applies base manifests from `k8s/`.
- Updates deployment images to selected tag.
- Waits for rollout completion.

Required GitHub secret:

- `KUBE_CONFIG_B64`: base64-encoded kubeconfig.

Additional required GitHub Secrets for app runtime:

- `OPENAI_API_KEY`
- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_PHONE_NUMBER`
- `TWILIO_PHONE_NUMBER_SID`
- `PUBLIC_BASE_URL`

## 4) Kubernetes manifests

Folder: `k8s/`

Included resources:

- `namespace.yaml`
- `configmap.yaml`
- `secret.example.yaml` (template only)
- `backend-pvc.yaml`
- `backend-deployment.yaml`
- `backend-service.yaml`
- `frontend-deployment.yaml`
- `frontend-service.yaml`
- `ingress.yaml`
- `kustomization.yaml`
- `optional/cloudflared-quick-tunnel.yaml`

## 5) How to deploy to Kubernetes

Local/manual deploy path:

1. Create a real secret file from template:

```bash
cp k8s/secret.example.yaml k8s/secret.yaml
```

2. Edit `k8s/secret.yaml` with real credentials.

3. Apply resources:

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/secret.yaml
kubectl apply -k k8s/
```

GitHub Actions deploy path:

1. Configure required GitHub Secrets.
2. Run `Deploy to Kubernetes` workflow with `imageTag`.
3. Workflow creates/updates `kleva-secrets` automatically and deploys images.

Set image owner once:

- Replace `REPLACE_OWNER` in:
  - `k8s/backend-deployment.yaml`
  - `k8s/frontend-deployment.yaml`

Configure ingress hosts:

- `app.example.com` for frontend.
- `voice.example.com` for backend webhook/media stream.

Point Twilio webhook to:

- `https://voice.example.com/twilio/voice`

## 6) Notes for interview

- CI validates backend/frontend build health on every PR.
- CD publishes versioned container images automatically.
- Kubernetes manifests show production-style orchestration with probes, service separation, ingress routing, and persistent volume for backend data.
