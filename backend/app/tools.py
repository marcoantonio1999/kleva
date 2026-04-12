import json
from typing import Any

from twilio.rest import Client

from app.config import get_settings
from app.db import AsyncSessionLocal
from app.models import ClaimCase, ComplaintCase, EmergencyEscalation, Interaction
from app.rag import rag_service

settings = get_settings()


TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "get_basic_insurance_info",
        "description": "Obtiene informacion basica de seguros, coberturas, telefonos y proceso de ajuste.",
        "parameters": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "Pregunta del cliente"},
                "category": {
                    "type": "string",
                    "enum": ["coberturas", "emergencias", "ajuste", "poliza", "general"],
                    "description": "Categoria principal de la consulta",
                },
            },
            "required": ["question"],
        },
    },
    {
        "type": "function",
        "name": "start_claim_intake",
        "description": "Registra un nuevo caso de ajuste con relato inicial del incidente.",
        "parameters": {
            "type": "object",
            "properties": {
                "caller_phone": {"type": "string"},
                "policy_number": {"type": "string"},
                "incident_summary": {"type": "string"},
                "incident_severity": {
                    "type": "string",
                    "enum": ["baja", "media", "alta", "critica"],
                },
            },
            "required": ["incident_summary"],
        },
    },
    {
        "type": "function",
        "name": "create_complaint",
        "description": "Registra una queja formal y la prioriza para seguimiento.",
        "parameters": {
            "type": "object",
            "properties": {
                "caller_phone": {"type": "string"},
                "complaint_summary": {"type": "string"},
                "severity": {"type": "string", "enum": ["baja", "media", "alta", "critica"]},
            },
            "required": ["complaint_summary"],
        },
    },
    {
        "type": "function",
        "name": "escalate_emergency",
        "description": "Escala de inmediato un incidente grave al flujo de emergencia y ajustador.",
        "parameters": {
            "type": "object",
            "properties": {
                "caller_phone": {"type": "string"},
                "location": {"type": "string"},
                "details": {"type": "string"},
            },
            "required": ["details"],
        },
    },
    {
        "type": "function",
        "name": "query_policy_status",
        "description": "Consulta estatus basico de poliza en el sistema de demo.",
        "parameters": {
            "type": "object",
            "properties": {
                "policy_number": {"type": "string"},
                "last_name": {"type": "string"},
            },
            "required": ["policy_number"],
        },
    },
    {
        "type": "function",
        "name": "end_call_by_ai",
        "description": "Finaliza la llamada cuando el cliente lo pide o cuando el flujo ya termino.",
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Motivo breve del cierre de llamada",
                }
            },
            "required": [],
        },
    },
]


class ToolService:
    async def execute(self, tool_name: str, arguments: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        handler = getattr(self, f"_handle_{tool_name}", None)
        if handler is None:
            return {"ok": False, "error": f"Tool no implementada: {tool_name}"}
        return await handler(arguments, context)

    async def _handle_get_basic_insurance_info(
        self, arguments: dict[str, Any], context: dict[str, Any]
    ) -> dict[str, Any]:
        question = arguments.get("question", "")
        docs = await rag_service.search(question, top_k=3)
        snippets = [doc["content"][:500] for doc in docs]
        return {
            "ok": True,
            "answer": "\n\n".join(snippets) if snippets else "No se encontro informacion en la base de conocimiento.",
            "sources": [doc.get("metadata", {}) for doc in docs],
        }

    async def _handle_start_claim_intake(self, arguments: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        claim = ClaimCase(
            call_sid=context.get("call_sid", "unknown"),
            caller_phone=arguments.get("caller_phone") or context.get("from_number"),
            policy_number=arguments.get("policy_number"),
            incident_summary=arguments.get("incident_summary", ""),
            incident_severity=arguments.get("incident_severity", "media"),
        )
        async with AsyncSessionLocal() as session:
            session.add(claim)
            await session.commit()
            await session.refresh(claim)

        return {
            "ok": True,
            "claim_id": claim.id,
            "claim_status": claim.claim_status,
            "message": "Ajuste registrado correctamente.",
        }

    async def _handle_create_complaint(self, arguments: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        complaint = ComplaintCase(
            call_sid=context.get("call_sid", "unknown"),
            caller_phone=arguments.get("caller_phone") or context.get("from_number"),
            complaint_summary=arguments.get("complaint_summary", ""),
            severity=arguments.get("severity", "media"),
        )
        async with AsyncSessionLocal() as session:
            session.add(complaint)
            await session.commit()
            await session.refresh(complaint)

        return {
            "ok": True,
            "complaint_id": complaint.id,
            "resolution_status": complaint.resolution_status,
            "message": "Queja registrada y enviada a seguimiento.",
        }

    async def _handle_escalate_emergency(self, arguments: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        emergency = EmergencyEscalation(
            call_sid=context.get("call_sid", "unknown"),
            caller_phone=arguments.get("caller_phone") or context.get("from_number"),
            location=arguments.get("location"),
            details=arguments.get("details"),
        )
        async with AsyncSessionLocal() as session:
            session.add(emergency)
            await session.commit()
            await session.refresh(emergency)

        return {
            "ok": True,
            "emergency_id": emergency.id,
            "channel": emergency.escalation_channel,
            "message": "Escalamiento de emergencia generado de forma inmediata.",
        }

    async def _handle_query_policy_status(self, arguments: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        policy_number = (arguments.get("policy_number") or "").strip().upper()
        suffix = policy_number[-1:] if policy_number else "0"

        mapping = {
            "0": "activa",
            "1": "activa",
            "2": "en revision",
            "3": "pago pendiente",
            "4": "vencida",
            "5": "activa",
            "6": "en revision",
            "7": "pago pendiente",
            "8": "vencida",
            "9": "activa",
        }

        status = mapping.get(suffix, "en revision")
        return {
            "ok": True,
            "policy_number": policy_number,
            "status": status,
            "message": f"La poliza {policy_number} se encuentra {status}.",
        }

    async def _handle_end_call_by_ai(self, arguments: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        call_sid = context.get("call_sid")
        if not call_sid:
            return {"ok": False, "error": "No hay call_sid activo para finalizar."}

        try:
            client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
            client.calls(call_sid).update(status="completed")
            return {
                "ok": True,
                "call_sid": call_sid,
                "reason": arguments.get("reason") or "Solicitud de cierre",
                "message": "Llamada finalizada por la IA.",
            }
        except Exception as exc:
            return {
                "ok": False,
                "call_sid": call_sid,
                "error": f"No se pudo finalizar la llamada: {exc}",
            }


async def save_interaction(call_sid: str, role: str, content: str) -> None:
    if not content:
        return
    async with AsyncSessionLocal() as session:
        row = Interaction(call_sid=call_sid, role=role, content=content)
        session.add(row)
        await session.commit()


def parse_tool_arguments(raw_arguments: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(raw_arguments, dict):
        return raw_arguments
    if not raw_arguments:
        return {}
    try:
        return json.loads(raw_arguments)
    except json.JSONDecodeError:
        return {}


tool_service = ToolService()
