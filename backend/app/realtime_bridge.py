import asyncio
import audioop
import base64
import json
from datetime import datetime
from typing import Any

import websockets
from fastapi import WebSocket
from sqlalchemy import select

from app.config import get_settings
from app.db import AsyncSessionLocal
from app.models import CallSession
from app.monitor import monitor_hub
from app.tools import TOOL_DEFINITIONS, parse_tool_arguments, save_interaction, tool_service

settings = get_settings()

SYSTEM_PROMPT = """
Eres un agente de voz para SeguraNova. Habla siempre en espanol claro, calmado, empatico y profesional.
Objetivos:
1) Resolver dudas basicas de seguros usando herramientas.
2) Registrar ajustes cuando haya incidente no grave.
3) Registrar quejas con resumen claro y prioridad.
4) Si detectas riesgo fisico, heridos o accidente grave, ejecuta de inmediato escalate_emergency.
Reglas:
- Prioriza seguridad de personas.
- No inventes datos de poliza: usa query_policy_status cuando se solicite.
- Resume al final de cada llamada en lenguaje breve.
- Usa tools siempre que la accion implique registro o consulta estructurada.
- No interrumpas al cliente: espera una pausa natural antes de responder.
- Si el cliente pide terminar o colgar, confirma con una despedida corta y ejecuta end_call_by_ai.
""".strip()

HANGUP_KEYWORDS = (
    "cuelga",
    "cuelgue",
    "colgar",
    "cortar la llamada",
    "termina la llamada",
    "terminar la llamada",
    "finaliza la llamada",
    "adios, cuelga",
)


class RealtimeCallBridge:
    def __init__(self, twilio_ws: WebSocket) -> None:
        self.twilio_ws = twilio_ws
        self.stream_sid: str | None = None
        self.call_sid: str | None = None
        self.from_number: str | None = None
        self.to_number: str | None = None
        self._call_closed = False
        self._handled_tool_call_ids: set[str] = set()

    async def run(self) -> None:
        headers = {
            "Authorization": f"Bearer {settings.openai_api_key}",
            "OpenAI-Beta": "realtime=v1",
        }

        async with websockets.connect(settings.realtime_ws_url, additional_headers=headers) as openai_ws:
            await self._initialize_openai_session(openai_ws)
            relay_in = asyncio.create_task(self._relay_twilio_to_openai(openai_ws))
            relay_out = asyncio.create_task(self._relay_openai_to_twilio(openai_ws))

            done, pending = await asyncio.wait([relay_in, relay_out], return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            for task in done:
                _ = task.result()
        if not self._call_closed:
            await self._finalize_call()

    async def _initialize_openai_session(self, openai_ws: websockets.ClientConnection) -> None:
        session_update = {
            "type": "session.update",
            "session": {
                "modalities": ["audio", "text"],
                "voice": settings.voice_name,
                "instructions": SYSTEM_PROMPT,
                "input_audio_format": "g711_ulaw",
                "output_audio_format": "g711_ulaw",
                "input_audio_transcription": {
                    "model": "gpt-4o-mini-transcribe",
                    "language": "es",
                },
                "turn_detection": {
                    "type": "server_vad",
                    "silence_duration_ms": settings.vad_silence_duration_ms,
                    "threshold": settings.vad_threshold,
                    "prefix_padding_ms": settings.vad_prefix_padding_ms,
                },
                "tools": TOOL_DEFINITIONS,
                "tool_choice": "auto",
                "temperature": 0.8,
            },
        }
        await openai_ws.send(json.dumps(session_update))

    async def _relay_twilio_to_openai(self, openai_ws: websockets.ClientConnection) -> None:
        while True:
            try:
                raw = await self.twilio_ws.receive_text()
            except Exception:
                return

            event = json.loads(raw)
            event_type = event.get("event")

            if event_type == "start":
                start_data = event.get("start", {})
                self.stream_sid = start_data.get("streamSid")
                self.call_sid = start_data.get("callSid")
                self.from_number = start_data.get("customParameters", {}).get("From")
                self.to_number = start_data.get("customParameters", {}).get("To")
                await self._upsert_call_session(status="in_progress")
                await monitor_hub.broadcast(
                    {
                        "type": "call_started",
                        "callSid": self.call_sid,
                        "streamSid": self.stream_sid,
                        "from": self.from_number,
                        "to": self.to_number,
                    }
                )

            elif event_type == "media":
                payload = event.get("media", {}).get("payload")
                if payload and self._should_forward_audio(payload):
                    await openai_ws.send(json.dumps({"type": "input_audio_buffer.append", "audio": payload}))

            elif event_type == "stop":
                await self._finalize_call()
                return

    async def _relay_openai_to_twilio(self, openai_ws: websockets.ClientConnection) -> None:
        async for raw in openai_ws:
            message = json.loads(raw)
            m_type = message.get("type", "")

            if m_type == "response.audio.delta":
                if self.stream_sid:
                    await self.twilio_ws.send_text(
                        json.dumps(
                            {
                                "event": "media",
                                "streamSid": self.stream_sid,
                                "media": {"payload": message.get("delta", "")},
                            }
                        )
                    )

            elif m_type == "conversation.item.input_audio_transcription.completed":
                text = message.get("transcript", "").strip()
                if text:
                    await self._handle_transcript("caller", text)

            elif m_type == "response.audio_transcript.done":
                text = message.get("transcript", "").strip()
                if text:
                    await self._handle_transcript("assistant", text)

            elif m_type == "response.output_item.done":
                item = message.get("item", {})
                if item.get("type") == "function_call":
                    await self._handle_function_call(openai_ws, item)

            elif m_type == "response.function_call_arguments.done":
                await self._handle_function_call(
                    openai_ws,
                    {
                        "name": message.get("name", ""),
                        "call_id": message.get("call_id", ""),
                        "arguments": message.get("arguments", "{}"),
                    },
                )

            elif m_type == "error":
                await monitor_hub.broadcast(
                    {
                        "type": "openai_error",
                        "callSid": self.call_sid,
                        "error": message.get("error", {}),
                    }
                )

            elif m_type == "session.created":
                # Kick off the first assistant turn so the caller hears immediate audio.
                await openai_ws.send(
                    json.dumps(
                        {
                            "type": "response.create",
                            "response": {
                                "modalities": ["audio", "text"],
                                "instructions": "Saluda brevemente en espanol, preséntate como asistente de SeguraNova y pregunta en que puedes ayudar.",
                            },
                        }
                    )
                )
                await monitor_hub.broadcast(
                    {
                        "type": "openai_session_ready",
                        "callSid": self.call_sid,
                    }
                )

    async def _handle_function_call(
        self, openai_ws: websockets.ClientConnection, function_call_item: dict[str, Any]
    ) -> None:
        tool_name = function_call_item.get("name", "")
        call_id = function_call_item.get("call_id", "")
        if call_id and call_id in self._handled_tool_call_ids:
            return
        if call_id:
            self._handled_tool_call_ids.add(call_id)
        arguments = parse_tool_arguments(function_call_item.get("arguments", "{}"))

        await monitor_hub.broadcast(
            {
                "type": "tool_called",
                "callSid": self.call_sid,
                "name": tool_name,
                "arguments": arguments,
            }
        )

        context = {
            "call_sid": self.call_sid,
            "from_number": self.from_number,
            "to_number": self.to_number,
        }
        result = await tool_service.execute(tool_name=tool_name, arguments=arguments, context=context)

        await monitor_hub.broadcast(
            {
                "type": "tool_result",
                "callSid": self.call_sid,
                "name": tool_name,
                "result": result,
            }
        )

        output_event = {
            "type": "conversation.item.create",
            "item": {
                "type": "function_call_output",
                "call_id": call_id,
                "output": json.dumps(result, ensure_ascii=True),
            },
        }
        await openai_ws.send(json.dumps(output_event))
        await openai_ws.send(json.dumps({"type": "response.create"}))

    async def _handle_transcript(self, role: str, text: str) -> None:
        if not self.call_sid:
            return
        await save_interaction(call_sid=self.call_sid, role=role, content=text)
        await monitor_hub.broadcast(
            {
                "type": "transcript",
                "callSid": self.call_sid,
                "role": role,
                "text": text,
            }
        )

        if role == "caller" and self._is_hangup_request(text):
            context = {
                "call_sid": self.call_sid,
                "from_number": self.from_number,
                "to_number": self.to_number,
            }
            result = await tool_service.execute(
                tool_name="end_call_by_ai",
                arguments={"reason": "Solicitud verbal de cierre de llamada"},
                context=context,
            )
            await monitor_hub.broadcast(
                {
                    "type": "tool_result",
                    "callSid": self.call_sid,
                    "name": "end_call_by_ai",
                    "result": result,
                }
            )

    def _is_hangup_request(self, text: str) -> bool:
        lowered = text.lower()
        return any(keyword in lowered for keyword in HANGUP_KEYWORDS)

    def _should_forward_audio(self, payload: str) -> bool:
        if not settings.audio_gate_enabled:
            return True

        try:
            ulaw = base64.b64decode(payload)
            pcm = audioop.ulaw2lin(ulaw, 2)
            rms = audioop.rms(pcm, 2)
            return rms >= settings.audio_gate_rms_min
        except Exception:
            # If decoding fails, forward audio to avoid clipping user speech.
            return True

    async def _upsert_call_session(self, status: str) -> None:
        if not self.call_sid:
            return

        async with AsyncSessionLocal() as session:
            existing = (
                await session.execute(select(CallSession).where(CallSession.call_sid == self.call_sid))
            ).scalar_one_or_none()
            if existing is None:
                row = CallSession(
                    call_sid=self.call_sid,
                    stream_sid=self.stream_sid,
                    from_number=self.from_number,
                    to_number=self.to_number,
                    status=status,
                )
                session.add(row)
            else:
                existing.stream_sid = self.stream_sid
                existing.status = status
            await session.commit()

    async def _finalize_call(self) -> None:
        if not self.call_sid or self._call_closed:
            return

        self._call_closed = True

        async with AsyncSessionLocal() as session:
            existing = (
                await session.execute(select(CallSession).where(CallSession.call_sid == self.call_sid))
            ).scalar_one_or_none()
            if existing is not None:
                existing.status = "completed"
                existing.ended_at = datetime.utcnow()
                await session.commit()

        await monitor_hub.broadcast(
            {
                "type": "call_ended",
                "callSid": self.call_sid,
            }
        )
