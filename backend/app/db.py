from pathlib import Path
from typing import AsyncGenerator

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


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
