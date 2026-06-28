import logging

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import get_db
from app.models import User
from app.routers import auth, checkin, events, payments, registrations
from app.routers.auth import limiter, pwd_context
from app.schemas import RegisterRequest

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="TechFest Registration API",
    description="IEEE RVCE TechFest 2026 — Student registration, payments, and gate check-in.",
    version="1.0.0",
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Unhandled error: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"data": None, "error": "Internal server error"})


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(status_code=exc.status_code, content={"data": None, "error": exc.detail})


# Routers already have their own prefix (/auth, /events, etc.) — only add /api/v1 here
app.include_router(auth.router, prefix="/api/v1")
app.include_router(events.router, prefix="/api/v1")
app.include_router(registrations.router, prefix="/api/v1")
app.include_router(payments.router, prefix="/api/v1")
app.include_router(checkin.router, prefix="/api/v1")


@app.post("/internal/create-volunteer")
async def create_volunteer(
    body: RegisterRequest,
    x_admin_secret: str = Header(None, alias="X-Admin-Secret"),
    db: AsyncSession = Depends(get_db),
):
    """Create a volunteer account. Requires X-Admin-Secret header."""
    if x_admin_secret != settings.ADMIN_SECRET:
        raise HTTPException(403, "Invalid admin secret")

    from sqlalchemy import select
    result = await db.execute(select(User).where(User.email == body.email))
    if result.scalar_one_or_none():
        raise HTTPException(400, "Email already registered")

    user = User(
        name=body.name,
        email=body.email,
        phone=body.phone,
        college=body.college,
        password_hash=pwd_context.hash(body.password),
        role="volunteer",
    )
    db.add(user)
    await db.flush()
    logger.info(f"Volunteer account created: {user.email}")
    return {"id": str(user.id), "name": user.name, "email": user.email, "role": user.role}


@app.get("/health")
async def health(db: AsyncSession = Depends(get_db)):
    await db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}


@app.on_event("startup")
async def startup():
    logger.info("TechFest API starting up")
