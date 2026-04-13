from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import desc, select
from twilio.twiml.voice_response import Connect, Stream, VoiceResponse

from app.config import get_settings
from app.db import AsyncSessionLocal, init_db
from app.models import CallSession, ClaimCase, ComplaintCase, EmergencyEscalation, Interaction
from app.monitor import monitor_hub
from app.rag import rag_service
from app.realtime_bridge import RealtimeCallBridge

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    await rag_service.initialize()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _build_stream_ws_url(request: Request) -> str:
    # Prefer forwarded headers from public tunnel/proxy to preserve the external host.
    proto = (request.headers.get("x-forwarded-proto") or request.url.scheme).split(",")[0].strip().lower()
    host = (
        request.headers.get("x-forwarded-host")
        or request.headers.get("host")
        or request.url.netloc
        or settings.public_base_url.replace("https://", "").replace("http://", "")
    )
    scheme = "wss" if proto == "https" else "ws"
    return f"{scheme}://{host}/twilio/media-stream"


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"ok": True, "service": settings.app_name})


@app.post("/twilio/voice")
async def twilio_voice_webhook(request: Request) -> PlainTextResponse:
    form = await request.form()
    from_number = str(form.get("From") or "")
    to_number = str(form.get("To") or "")
    account_sid = str(form.get("AccountSid") or "")
    insurer = settings.insurer_for_call(to_number=to_number, account_sid=account_sid)

    response = VoiceResponse()
    response.say(f"Conectando con {insurer['name']}. Un momento por favor.", language="es-MX", voice="alice")

    connect = Connect()
    stream = Stream(url=_build_stream_ws_url(request))
    stream.parameter(name="From", value=from_number)
    stream.parameter(name="To", value=to_number)
    stream.parameter(name="AccountSid", value=account_sid)
    stream.parameter(name="InsurerId", value=insurer["id"])
    stream.parameter(name="InsurerName", value=insurer["name"])
    connect.append(stream)
    response.append(connect)

    return PlainTextResponse(str(response), media_type="application/xml")


@app.websocket("/twilio/media-stream")
async def twilio_media_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    bridge = RealtimeCallBridge(websocket)
    try:
        await bridge.run()
    except Exception as exc:
        await monitor_hub.broadcast({"type": "bridge_error", "error": str(exc)})


@app.websocket("/monitor/ws")
async def monitor_socket(websocket: WebSocket) -> None:
    await monitor_hub.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await monitor_hub.disconnect(websocket)
    except Exception:
        await monitor_hub.disconnect(websocket)


@app.get("/api/calls")
async def list_calls(limit: int = 20) -> JSONResponse:
    safe_limit = min(max(limit, 1), 100)
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(select(CallSession).order_by(desc(CallSession.created_at)).limit(safe_limit))
        ).scalars().all()

    data = [
        {
            "call_sid": row.call_sid,
            "stream_sid": row.stream_sid,
            "from_number": row.from_number,
            "to_number": row.to_number,
            "insurer_id": row.insurer_id,
            "insurer_name": row.insurer_name,
            "status": row.status,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "ended_at": row.ended_at.isoformat() if row.ended_at else None,
        }
        for row in rows
    ]
    return JSONResponse({"items": data})


@app.get("/api/insurers")
async def list_insurers() -> JSONResponse:
    primary = settings.primary_insurer
    secondary = settings.secondary_insurer
    items = [
        {
            "id": primary["id"],
            "name": primary["name"],
            "phone_number": primary["phone_number"],
        }
    ]
    if secondary["phone_number"]:
        items.append(
            {
                "id": secondary["id"],
                "name": secondary["name"],
                "phone_number": secondary["phone_number"],
            }
        )
    return JSONResponse({"items": items})


@app.get("/api/interactions/{call_sid}")
async def list_interactions(call_sid: str) -> JSONResponse:
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(Interaction).where(Interaction.call_sid == call_sid).order_by(Interaction.created_at.asc())
            )
        ).scalars().all()

    data = [
        {
            "id": row.id,
            "role": row.role,
            "content": row.content,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]
    return JSONResponse({"items": data})


@app.get("/api/cases")
async def list_cases(limit: int = 50) -> JSONResponse:
    safe_limit = min(max(limit, 1), 200)
    async with AsyncSessionLocal() as session:
        claims = (await session.execute(select(ClaimCase).order_by(desc(ClaimCase.created_at)).limit(safe_limit))).scalars().all()
        complaints = (
            await session.execute(select(ComplaintCase).order_by(desc(ComplaintCase.created_at)).limit(safe_limit))
        ).scalars().all()
        emergencies = (
            await session.execute(
                select(EmergencyEscalation).order_by(desc(EmergencyEscalation.created_at)).limit(safe_limit)
            )
        ).scalars().all()

    return JSONResponse(
        {
            "claims": [
                {
                    "id": row.id,
                    "call_sid": row.call_sid,
                    "caller_phone": row.caller_phone,
                    "policy_number": row.policy_number,
                    "incident_summary": row.incident_summary,
                    "incident_severity": row.incident_severity,
                    "claim_status": row.claim_status,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
                for row in claims
            ],
            "complaints": [
                {
                    "id": row.id,
                    "call_sid": row.call_sid,
                    "caller_phone": row.caller_phone,
                    "complaint_summary": row.complaint_summary,
                    "severity": row.severity,
                    "resolution_status": row.resolution_status,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
                for row in complaints
            ],
            "emergencies": [
                {
                    "id": row.id,
                    "call_sid": row.call_sid,
                    "caller_phone": row.caller_phone,
                    "location": row.location,
                    "details": row.details,
                    "escalation_channel": row.escalation_channel,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
                for row in emergencies
            ],
        }
    )
