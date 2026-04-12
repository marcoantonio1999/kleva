from functools import lru_cache
from pathlib import Path
from typing import List

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
