from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.models import Base

settings = get_settings()

# Ensure local sqlite target directory exists when using file-based DB.
if settings.database_url.startswith("sqlite"):
    db_file = settings.database_url.split("///")[-1]
    Path(db_file).parent.mkdir(parents=True, exist_ok=True)

engine = create_async_engine(settings.database_url, future=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Lightweight migration for existing sqlite databases.
        result = await conn.execute(text("PRAGMA table_info(call_sessions)"))
        existing_columns = {str(row[1]) for row in result.fetchall()}

        if "insurer_id" not in existing_columns:
            await conn.execute(text("ALTER TABLE call_sessions ADD COLUMN insurer_id VARCHAR(64)"))
        if "insurer_name" not in existing_columns:
            await conn.execute(text("ALTER TABLE call_sessions ADD COLUMN insurer_name VARCHAR(128)"))


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
