# SeguraNova Voice Demo

End-to-end demo for a voice insurance assistant using Twilio + OpenAI Realtime + local RAG + React live monitor.

## Stack

- Backend: FastAPI + WebSocket bridge + SQLite + local vector retrieval (optional Chroma)
- Frontend: React + Vite live monitor
- Voice transport: Twilio Media Streams
- Realtime model: OpenAI Realtime (speech-to-speech)

## 1) Backend setup

```bash
cd backend
cp .env.example .env
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

If you want strict Chroma runtime on Windows + Python 3.12, also run:

```bash
python -m pip install --only-binary=:all: chroma-hnswlib==0.7.5
python -m pip install chromadb==0.6.3 --no-deps
python -m pip install overrides build posthog onnxruntime opentelemetry-api opentelemetry-exporter-otlp-proto-grpc opentelemetry-instrumentation-fastapi opentelemetry-sdk tokenizers pypika grpcio bcrypt typer kubernetes tenacity mmh3 rich importlib-resources
```

Fill `backend/.env` with your credentials:

- `OPENAI_API_KEY`
- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_PHONE_NUMBER`
- `PUBLIC_BASE_URL` (your ngrok https URL)

## 2) Expose backend with ngrok

```bash
ngrok http 8000
```

Set your Twilio number Voice webhook to:

- URL: `https://<ngrok-domain>/twilio/voice`
- Method: `POST`

## 3) Frontend setup

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

Open `http://localhost:5173`.

## 3.1) Run with Docker Compose (interview mode)

This project now includes containerization for backend + frontend.
Frontend assets are built automatically inside the Docker image.

```bash
docker compose up --build
```

Services:

- Backend API: `http://localhost:8000`
- Frontend monitor: `http://localhost:5173`

To stop:

```bash
docker compose down
```

Optional: run a public tunnel as a third containerized service (no auth required):

```bash
docker compose --profile tunnel up --build
```

Then read the public URL from logs:

```bash
docker compose logs cloudflared
```

If you prefer ngrok instead:

```bash
set NGROK_AUTHTOKEN=<your-token>
docker compose --profile ngrok up --build
```

Then check ngrok inspector at `http://localhost:4040`.

Notes:

- Keep `backend/.env` populated with OpenAI and Twilio credentials.
- Twilio still needs a public URL to reach `/twilio/voice`, so keep ngrok (or similar) pointing to local port `8000`.
- If you use the `tunnel` profile, point Twilio to the `trycloudflare.com` URL shown by `cloudflared`.
- If you use the `ngrok` profile, point Twilio to the public URL shown by ngrok.
- SQLite and local KB data remain persisted in `backend/data`.

## 3.2) One-command tunnel setup for demo video

To make the interview flow reproducible on GitHub, this repo includes PowerShell scripts that:

- Start Docker services.
- Fetch the public tunnel URL.
- Update `backend/.env` (`PUBLIC_BASE_URL`).
- Update Twilio Voice webhook automatically.

Run from repository root:

Cloudflared (no token required):

```bash
powershell -ExecutionPolicy Bypass -File .\scripts\demo\start-with-cloudflared.ps1
```

Ngrok (requires `NGROK_AUTHTOKEN`):

```bash
set NGROK_AUTHTOKEN=<your-token>
powershell -ExecutionPolicy Bypass -File .\scripts\demo\start-with-ngrok.ps1
```

Optional flag for both scripts (skip Twilio API update):

```bash
... -NoTwilioUpdate
```

## 4) Test call flow

1. Call your Twilio phone number.
2. Speak with the assistant in Spanish.
3. Watch live transcript and tool calls in the React monitor.
4. Verify generated cases in backend (`/api/cases`).

## 5) CI/CD pipelines

GitHub Actions workflows included:

- `.github/workflows/ci.yml`: backend/frontend checks + compose validation on PR/push.
- `.github/workflows/release-images.yml`: build and publish Docker images to GHCR.
- `.github/workflows/deploy-k8s.yml`: manual Kubernetes deployment by image tag.

## 6) Container orchestration (Kubernetes)

Kubernetes manifests are under `k8s/`:

- Backend + frontend deployments/services
- Ingress split for app and voice webhook domains
- Persistent storage claim for backend data
- Optional quick tunnel deployment: `k8s/optional/cloudflared-quick-tunnel.yaml`

See detailed setup in `docs/CI-CD-K8S.md`.

## Demo tools implemented

- `get_basic_insurance_info`
- `start_claim_intake`
- `create_complaint`
- `escalate_emergency`
- `query_policy_status`
- `end_call_by_ai`

## Notes

- WhatsApp send is intentionally omitted in this build.
- Knowledge base is fictional and stored in `backend/data/kb/insurance_basics.md`.

For an interview-friendly execution checklist, see `docs/DEMO-VIDEO.md`.
