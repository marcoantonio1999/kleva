# Backend - SeguraNova Voice Agent

FastAPI backend that bridges Twilio Media Streams with OpenAI Realtime voice, executes tool calls, and persists call/case data in SQLite.

## Features

- Twilio voice webhook (`/twilio/voice`) with Media Stream handoff.
- Realtime WebSocket bridge (`/twilio/media-stream`) for low-latency speech-to-speech.
- Tool calling for claims, complaints, emergency escalation, policy lookup, and KB answers.
- Local RAG using OpenAI embeddings with optional Chroma backend (automatic fallback to in-memory vector index on environments where Chroma is unavailable).
- Monitor events over WebSocket (`/monitor/ws`) consumed by the React dashboard.
- SQLite persistence for calls, interactions, claims, complaints, and emergency escalations.

## Quick Start

1. Copy env template:

```bash
cp .env.example .env
```

2. Fill `.env` with your keys and ngrok URL.

3. Install dependencies:

```bash
pip install -r requirements.txt
```

Docker note: container builds use `requirements.docker.txt` for a lighter runtime dependency set.

### Enable Chroma on Windows (Python 3.12)

If `chromadb` fails because `chroma-hnswlib==0.7.6` needs a C++ toolchain, use this working install path:

```bash
python -m pip install --only-binary=:all: chroma-hnswlib==0.7.5
python -m pip install chromadb==0.6.3 --no-deps
python -m pip install overrides build posthog onnxruntime opentelemetry-api opentelemetry-exporter-otlp-proto-grpc opentelemetry-instrumentation-fastapi opentelemetry-sdk tokenizers pypika grpcio bcrypt typer kubernetes tenacity mmh3 rich importlib-resources
```

This leaves a `pip check` warning (`chroma-hnswlib 0.7.5` vs `0.7.6`), but Chroma is functional in runtime on this machine.

4. Run API:

```bash
uvicorn app.main:app --reload --port 8000
```

5. Expose backend with ngrok:

```bash
ngrok http 8000
```

6. Configure Twilio number webhook:
- Voice webhook URL: `https://<ngrok-domain>/twilio/voice`
- Method: `POST`

For interview/demo automation with Docker + tunnel + Twilio webhook update, use:

- `scripts/demo/start-with-cloudflared.ps1`
- `scripts/demo/start-with-ngrok.ps1`

## Important endpoints

- `GET /health`
- `POST /twilio/voice`
- `WS /twilio/media-stream`
- `WS /monitor/ws`
- `GET /api/calls`
- `GET /api/interactions/{call_sid}`
- `GET /api/cases`

## Knowledge base

Drop markdown files in `backend/data/kb/` and restart backend to re-index if needed.
