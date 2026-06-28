import os

# Must be set before any app.* imports so pydantic-settings reads these values
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-testing-only-at-least-32")
os.environ.setdefault("RAZORPAY_KEY_ID", "rzp_test_fake")
os.environ.setdefault("RAZORPAY_KEY_SECRET", "fake_razorpay_secret")
os.environ.setdefault("RAZORPAY_WEBHOOK_SECRET", "fake_webhook_secret")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("ADMIN_SECRET", "test-admin-secret")

from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from passlib.context import CryptContext
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal, Base, engine
from app.main import app
from app.models import Event, User
from app.routers.auth import create_access_token

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@pytest.fixture(scope="session", autouse=True)
async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture(autouse=True)
async def clear_tables():
    yield
    async with AsyncSessionLocal() as session:
        # Delete in FK-safe order
        await session.execute(text("DELETE FROM checkins"))
        await session.execute(text("DELETE FROM payments"))
        await session.execute(text("DELETE FROM registrations"))
        await session.execute(text("DELETE FROM events"))
        await session.execute(text("DELETE FROM users"))
        await session.commit()


@pytest.fixture
async def db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
        await session.commit()


@pytest.fixture
async def client() -> AsyncClient:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def make_student(db: AsyncSession, email: str = "student@test.com") -> tuple[User, str]:
    user = User(
        name="Test Student",
        email=email,
        phone="1234567890",
        college="Test College",
        password_hash=pwd_context.hash("testpass123"),
        role="student",
    )
    db.add(user)
    await db.flush()
    return user, create_access_token(str(user.id), "student")


async def make_volunteer(db: AsyncSession, email: str = "volunteer@test.com") -> tuple[User, str]:
    user = User(
        name="Test Volunteer",
        email=email,
        phone="9876543210",
        college="Test College",
        password_hash=pwd_context.hash("testpass123"),
        role="volunteer",
    )
    db.add(user)
    await db.flush()
    return user, create_access_token(str(user.id), "volunteer")


async def make_event(db: AsyncSession, **kwargs) -> Event:
    defaults = {
        "name": "Test Event",
        "description": "Test description",
        "venue": "Test Venue",
        "start_time": datetime.now(timezone.utc) + timedelta(days=30),
        "registration_deadline": datetime.now(timezone.utc) + timedelta(days=7),
        "capacity": 5,
        "registered_count": 0,
        "price": 0.00,
        "is_active": True,
    }
    defaults.update(kwargs)
    event = Event(**defaults)
    db.add(event)
    await db.flush()
    return event


@pytest.fixture
async def student_token(db: AsyncSession) -> dict:
    user, token = await make_student(db)
    await db.commit()
    return {"user": user, "headers": {"Authorization": f"Bearer {token}"}}


@pytest.fixture
async def volunteer_token(db: AsyncSession) -> dict:
    user, token = await make_volunteer(db)
    await db.commit()
    return {"user": user, "headers": {"Authorization": f"Bearer {token}"}}


@pytest.fixture
async def sample_event(db: AsyncSession) -> Event:
    event = await make_event(db, capacity=5, price=0.00)
    await db.commit()
    return event
