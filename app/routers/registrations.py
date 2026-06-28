import io
import logging
from datetime import datetime, timezone
from uuid import UUID

import qrcode
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.dependencies import get_current_user, get_db, require_role
from app.models import Event, Registration, User
from app.schemas import CreateRegistrationRequest, RegistrationOut, VolunteerRegistrationOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/registrations", tags=["registrations"])


@router.post("/", response_model=RegistrationOut)
async def create_registration(
    body: CreateRegistrationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("student")),
):
    """Register the current student for an event."""
    event_id = body.event_id

    event = await db.get(Event, str(event_id))
    if not event:
        raise HTTPException(404, "Event not found")
    if not event.is_active:
        raise HTTPException(400, "Event is not available")
    deadline = event.registration_deadline
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > deadline:
        raise HTTPException(400, "Registration is closed")

    existing = await db.execute(
        select(Registration).where(
            Registration.user_id == current_user.id,
            Registration.event_id == event_id,
            Registration.status != "CANCELLED",
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, "You are already registered for this event")

    # Atomic increment — avoids TOCTOU race where two requests both read the same count
    # and both pass the capacity check before either writes. The WHERE clause acts as a lock.
    result = await db.execute(
        update(Event)
        .where(Event.id == event_id, Event.registered_count < Event.capacity)
        .values(registered_count=Event.registered_count + 1)
        .returning(Event.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(409, "Event is sold out")

    reg = Registration(user_id=current_user.id, event_id=event_id, status="PENDING")
    db.add(reg)
    await db.flush()

    logger.info(f"User {current_user.id} registered for event {event_id}")
    return RegistrationOut.model_validate(reg)


@router.get("/me", response_model=list[RegistrationOut])
async def my_registrations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("student")),
):
    """List all registrations for the logged-in student."""
    result = await db.execute(
        select(Registration)
        .where(Registration.user_id == current_user.id)
        .order_by(Registration.created_at.desc())
    )
    regs = result.scalars().all()
    return [RegistrationOut.model_validate(r) for r in regs]


@router.get("/", response_model=list[VolunteerRegistrationOut])
async def list_all_registrations(
    event_id: UUID | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("volunteer")),
):
    """List all registrations. Volunteer only. Filterable by event_id and status."""
    # TODO: add pagination
    query = select(Registration).options(
        joinedload(Registration.event),
        joinedload(Registration.user),
    )
    if event_id:
        query = query.where(Registration.event_id == event_id)
    if status:
        query = query.where(Registration.status == status)

    result = await db.execute(query)
    regs = result.scalars().all()

    return [
        VolunteerRegistrationOut(
            id=r.id,
            event_id=r.event_id,
            event_name=r.event.name,
            student_name=r.user.name,
            status=r.status,
            ticket_number=r.ticket_number,
            created_at=r.created_at,
        )
        for r in regs
    ]


@router.get("/{registration_id}", response_model=RegistrationOut)
async def get_registration(
    registration_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a single registration. Students can only view their own."""
    reg = await db.get(Registration, str(registration_id))
    if not reg:
        raise HTTPException(404, "Registration not found")
    if current_user.role == "student" and reg.user_id != current_user.id:
        raise HTTPException(403, "Access denied")
    return RegistrationOut.model_validate(reg)


@router.get("/{registration_id}/qr")
async def get_qr_code(
    registration_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("student")),
):
    """Download the QR PNG for a confirmed ticket."""
    reg = await db.get(Registration, str(registration_id))
    if not reg:
        raise HTTPException(404, "Registration not found")
    if reg.user_id != current_user.id:
        raise HTTPException(403, "Access denied")
    if reg.status not in ("CONFIRMED", "CHECKED_IN"):
        raise HTTPException(403, "Ticket not yet confirmed — complete payment first")

    qr = qrcode.make(reg.qr_token)
    buf = io.BytesIO()
    qr.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")
