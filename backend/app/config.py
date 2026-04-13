from functools import lru_cache
from pathlib import Path
from typing import Any, List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = Field(default="Voice Assist Platform", alias="APP_NAME")
    default_language: str = Field(default="es-MX", alias="DEFAULT_LANGUAGE")
    voice_name: str = Field(default="shimmer", alias="VOICE_NAME")
    vad_silence_duration_ms: int = Field(default=450, alias="VAD_SILENCE_DURATION_MS")
    vad_threshold: float = Field(default=0.8, alias="VAD_THRESHOLD")
    vad_prefix_padding_ms: int = Field(default=180, alias="VAD_PREFIX_PADDING_MS")
    audio_gate_enabled: bool = Field(default=True, alias="AUDIO_GATE_ENABLED")
    audio_gate_rms_min: int = Field(default=240, alias="AUDIO_GATE_RMS_MIN")

    openai_api_key: str = Field(alias="OPENAI_API_KEY")
    openai_realtime_model: str = Field(default="gpt-4o-realtime-preview", alias="OPENAI_REALTIME_MODEL")
    openai_embedding_model: str = Field(default="text-embedding-3-small", alias="OPENAI_EMBEDDING_MODEL")

    twilio_account_sid: str = Field(alias="TWILIO_ACCOUNT_SID")
    twilio_auth_token: str = Field(alias="TWILIO_AUTH_TOKEN")
    twilio_phone_number: str = Field(alias="TWILIO_PHONE_NUMBER")

    secondary_insurer_id: str = Field(default="aseguradora_secundaria", alias="SECONDARY_INSURER_ID")
    secondary_insurer_name: str = Field(default="Seguros Horizonte", alias="SECONDARY_INSURER_NAME")
    secondary_insurer_phone_number: str = Field(default="", alias="SECONDARY_INSURER_PHONE_NUMBER")
    secondary_twilio_account_sid: str = Field(default="", alias="SECONDARY_TWILIO_ACCOUNT_SID")
    secondary_twilio_auth_token: str = Field(default="", alias="SECONDARY_TWILIO_AUTH_TOKEN")
    primary_insurer_phone_number: str = Field(default="", alias="PRIMARY_INSURER_PHONE_NUMBER")

    public_base_url: str = Field(alias="PUBLIC_BASE_URL")

    database_url: str = Field(default="sqlite+aiosqlite:///./data/app.db", alias="DATABASE_URL")
    chroma_dir: str = Field(default="./data/chroma", alias="CHROMA_DIR")
    kb_collection: str = Field(default="insurance_kb", alias="KB_COLLECTION")

    allowed_origins: str = Field(default="http://localhost:5173,http://localhost:4173", alias="ALLOWED_ORIGINS")

    @property
    def allowed_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    @property
    def realtime_ws_url(self) -> str:
        return f"wss://api.openai.com/v1/realtime?model={self.openai_realtime_model}"

    @property
    def kb_path(self) -> Path:
        return Path("data/kb")

    @staticmethod
    def normalize_phone(value: str | None) -> str:
        if not value:
            return ""
        raw = value.strip()
        if not raw:
            return ""
        prefix = "+" if raw.startswith("+") else ""
        digits = "".join(ch for ch in raw if ch.isdigit())
        if not digits:
            return ""
        return f"{prefix}{digits}" if prefix else digits

    @property
    def primary_insurer(self) -> dict[str, str]:
        primary_phone = self.normalize_phone(self.primary_insurer_phone_number) or self.normalize_phone(self.twilio_phone_number)
        return {
            "id": "seguranova",
            "name": self.app_name,
            "phone_number": primary_phone,
            "account_sid": self.twilio_account_sid,
            "auth_token": self.twilio_auth_token,
        }

    @property
    def secondary_insurer(self) -> dict[str, str]:
        return {
            "id": self.secondary_insurer_id,
            "name": self.secondary_insurer_name,
            "phone_number": self.normalize_phone(self.secondary_insurer_phone_number),
            "account_sid": self.secondary_twilio_account_sid,
            "auth_token": self.secondary_twilio_auth_token,
        }

    def insurer_for_call(self, to_number: str | None, account_sid: str | None = None) -> dict[str, str]:
        normalized_to = self.normalize_phone(to_number)
        primary = self.primary_insurer
        secondary = self.secondary_insurer

        if account_sid and secondary["account_sid"] and account_sid == secondary["account_sid"]:
            return {
                "id": secondary["id"],
                "name": secondary["name"],
                "phone_number": secondary["phone_number"] or normalized_to,
            }

        if account_sid and primary["account_sid"] and account_sid == primary["account_sid"]:
            return {
                "id": primary["id"],
                "name": primary["name"],
                "phone_number": primary["phone_number"] or normalized_to,
            }

        if secondary["phone_number"] and secondary["phone_number"] == normalized_to:
            return {
                "id": secondary["id"],
                "name": secondary["name"],
                "phone_number": secondary["phone_number"],
            }

        if primary["phone_number"] and primary["phone_number"] == normalized_to:
            return {
                "id": primary["id"],
                "name": primary["name"],
                "phone_number": primary["phone_number"],
            }

        return {
            "id": primary["id"],
            "name": primary["name"],
            "phone_number": normalized_to or primary["phone_number"],
        }

    def twilio_credentials_for_context(self, account_sid: str | None, to_number: str | None) -> dict[str, str]:
        primary = self.primary_insurer
        secondary = self.secondary_insurer
        selected: dict[str, Any] = primary

        if account_sid and account_sid not in {
            primary.get("account_sid"),
            secondary.get("account_sid"),
        }:
            return {"account_sid": "", "auth_token": ""}

        if account_sid and secondary.get("account_sid") and account_sid == secondary.get("account_sid"):
            selected = secondary
        elif account_sid and primary.get("account_sid") and account_sid == primary.get("account_sid"):
            selected = primary
        elif to_number and self.normalize_phone(to_number) == secondary.get("phone_number"):
            selected = secondary

        return {
            "account_sid": str(selected.get("account_sid") or ""),
            "auth_token": str(selected.get("auth_token") or ""),
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
