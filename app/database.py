from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

from app.config import settings

_db_url = settings.DATABASE_URL
# pool_size=10 keeps enough connections ready for concurrent requests without overwhelming Postgres
# SQLite (used in tests) uses NullPool and doesn't accept pool_size/max_overflow
_pool_kwargs = {} if _db_url.startswith("sqlite") else {"pool_size": 10, "max_overflow": 5}

engine = create_async_engine(_db_url, **_pool_kwargs)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

Base = declarative_base()


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
