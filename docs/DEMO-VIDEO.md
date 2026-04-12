# Demo Video Runbook

This runbook is for interview/demo recording and for reviewers running the project from GitHub.

## Goal

Show end-to-end voice flow on Docker with a public webhook URL.

## Prerequisites

- Docker Desktop running.
- `backend/.env` configured with OpenAI and Twilio credentials.
- Twilio phone number SID set in `TWILIO_PHONE_NUMBER_SID`.
- Optional for ngrok profile: `NGROK_AUTHTOKEN`.

## Option A: Cloudflared (no token)

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\demo\start-with-cloudflared.ps1
```

What the script does:

- Starts `backend`, `frontend`, and `cloudflared` with Docker Compose.
- Extracts active `trycloudflare` URL from logs.
- Updates `PUBLIC_BASE_URL` in `backend/.env`.
- Restarts backend to apply URL.
- Updates Twilio Voice webhook to `<public-url>/twilio/voice`.

## Option B: ngrok

```powershell
set NGROK_AUTHTOKEN=<your-token>
powershell -ExecutionPolicy Bypass -File .\scripts\demo\start-with-ngrok.ps1
```

What the script does:

- Starts `backend`, `frontend`, and `ngrok` with Docker Compose.
- Reads ngrok HTTPS URL from `http://localhost:4040/api/tunnels`.
- Updates `PUBLIC_BASE_URL` in `backend/.env`.
- Restarts backend to apply URL.
- Updates Twilio Voice webhook to `<public-url>/twilio/voice`.

## URLs to show during demo

- Dashboard: `http://localhost:5173`
- Backend health: `http://localhost:8000/health`
- Twilio webhook: `<public-url>/twilio/voice`
- Twilio media stream: `<public-url>/twilio/media-stream`

## Optional: do not touch Twilio config

Use `-NoTwilioUpdate` in either script if you only want tunnel setup.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\demo\start-with-cloudflared.ps1 -NoTwilioUpdate
```

## Stop everything

```powershell
docker compose --profile tunnel --profile ngrok down
```
