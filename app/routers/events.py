from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.models import Event
from app.schemas import EventOut

router = APIRouter(prefix="/events", tags=["events"])


@router.get("/", response_model=list[EventOut])
async def list_events(db: AsyncSession = Depends(get_db)):
    # TODO: add pagination
    result = await db.execute(select(Event).where(Event.is_active == True))
    events = result.scalars().all()
    return [EventOut.model_validate(e) for e in events]


@router.get("/{event_id}", response_model=EventOut)
async def get_event(event_id: str, db: AsyncSession = Depends(get_db)):
    event = await db.get(Event, event_id)
    if not event:
        raise HTTPException(404, "Event not found")
    return EventOut.model_validate(event)
