"""
Edge-case tests for the TechFest API.
Happy paths are covered by the Postman collection.
These tests verify that the system handles abnormal inputs and concurrent scenarios correctly.
"""
import secrets
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import CheckIn, Payment, Registration
from tests.conftest import make_event, make_student, make_volunteer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def register(client: AsyncClient, token: str, event_id: str):
    return await client.post(
        "/api/v1/registrations/",
        json={"event_id": event_id},
        headers={"Authorization": f"Bearer {token}"},
    )


# ---------------------------------------------------------------------------
# 1. Duplicate registration
# ---------------------------------------------------------------------------

async def test_duplicate_registration(client: AsyncClient, db: AsyncSession):
    user, token = await make_student(db)
    event = await make_event(db)
    await db.commit()

    await register(client, token, str(event.id))
    res = await register(client, token, str(event.id))

    assert res.status_code == 409


# ---------------------------------------------------------------------------
# 2. Registration past deadline
# ---------------------------------------------------------------------------

async def test_registration_closed(client: AsyncClient, db: AsyncSession):
    user, token = await make_student(db)
    event = await make_event(
        db,
        registration_deadline=datetime.now(timezone.utc) - timedelta(days=1),
    )
    await db.commit()

    res = await register(client, token, str(event.id))

    assert res.status_code == 400
    assert "closed" in res.json()["error"].lower()


# ---------------------------------------------------------------------------
# 3. Event sold out
# ---------------------------------------------------------------------------

async def test_registration_sold_out(client: AsyncClient, db: AsyncSession):
    _, token1 = await make_student(db, email="sold_s1@test.com")
    _, token2 = await make_student(db, email="sold_s2@test.com")
    event = await make_event(db, capacity=1)
    await db.commit()

    r1 = await register(client, token1, str(event.id))
    assert r1.status_code == 200

    r2 = await register(client, token2, str(event.id))
    assert r2.status_code == 409
    assert "sold out" in r2.json()["error"].lower()


# ---------------------------------------------------------------------------
# 4. Student B cannot view Student A's registration
# ---------------------------------------------------------------------------

async def test_unauthorized_access_to_other_registration(client: AsyncClient, db: AsyncSession):
    _, token_a = await make_student(db, email="auth_a@test.com")
    _, token_b = await make_student(db, email="auth_b@test.com")
    event = await make_event(db)
    await db.commit()

    reg_res = await register(client, token_a, str(event.id))
    reg_id = reg_res.json()["id"]

    res = await client.get(
        f"/api/v1/registrations/{reg_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert res.status_code == 403


# ---------------------------------------------------------------------------
# 5. Student cannot access volunteer-only endpoint
# ---------------------------------------------------------------------------

async def test_student_cannot_access_volunteer_endpoint(client: AsyncClient, db: AsyncSession):
    _, token = await make_student(db)
    await db.commit()

    res = await client.post(
        "/api/v1/checkin/scan",
        json={"qr_token": "any-token"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403


# ---------------------------------------------------------------------------
# 6. Volunteer cannot register as a student
# ---------------------------------------------------------------------------

async def test_volunteer_cannot_register(client: AsyncClient, db: AsyncSession):
    _, token = await make_volunteer(db)
    event = await make_event(db)
    await db.commit()

    res = await register(client, token, str(event.id))
    assert res.status_code == 403


# ---------------------------------------------------------------------------
# 7. QR code not available before payment
# ---------------------------------------------------------------------------

async def test_qr_not_available_before_payment(client: AsyncClient, db: AsyncSession):
    user, token = await make_student(db)
    event = await make_event(db, price=0.00)
    # Create registration directly with PENDING status — skips the payment confirmation step
    reg = Registration(user_id=user.id, event_id=event.id, status="PENDING")
    db.add(reg)
    await db.commit()

    res = await client.get(
        f"/api/v1/registrations/{reg.id}/qr",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 403


# ---------------------------------------------------------------------------
# 8. Scanning a QR token that doesn't exist
# ---------------------------------------------------------------------------

async def test_invalid_qr_scan(client: AsyncClient, db: AsyncSession):
    _, token = await make_volunteer(db)
    await db.commit()

    res = await client.post(
        "/api/v1/checkin/scan",
        json={"qr_token": "fake-token-that-does-not-exist"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# 9. Double scan rejected
# ---------------------------------------------------------------------------

async def test_double_scan_rejected(client: AsyncClient, db: AsyncSession):
    student, _ = await make_student(db)
    volunteer, vol_token = await make_volunteer(db)
    event = await make_event(db)

    qr_token = secrets.token_urlsafe(32)
    reg = Registration(
        user_id=student.id,
        event_id=event.id,
        status="CONFIRMED",
        qr_token=qr_token,
        ticket_number="TF2026-000001",
    )
    db.add(reg)
    await db.commit()

    headers = {"Authorization": f"Bearer {vol_token}"}
    r1 = await client.post("/api/v1/checkin/scan", json={"qr_token": qr_token}, headers=headers)
    assert r1.status_code == 200

    r2 = await client.post("/api/v1/checkin/scan", json={"qr_token": qr_token}, headers=headers)
    assert r2.status_code == 409


# ---------------------------------------------------------------------------
# 10. Payment signature tampered
# ---------------------------------------------------------------------------

async def test_payment_signature_tampered(client: AsyncClient, db: AsyncSession):
    user, token = await make_student(db)
    event = await make_event(db, price=199.00)

    reg = Registration(user_id=user.id, event_id=event.id, status="PAYMENT_PENDING")
    db.add(reg)
    await db.flush()

    payment = Payment(
        registration_id=reg.id,
        amount=199.00,
        razorpay_order_id="order_test_fake_123",
        status="INITIATED",
    )
    db.add(payment)
    await db.commit()

    res = await client.post(
        "/api/v1/payments/verify",
        json={
            "registration_id": str(reg.id),
            "razorpay_payment_id": "pay_fake_456",
            "razorpay_order_id": "order_test_fake_123",
            "razorpay_signature": "this-is-a-tampered-signature",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 400
    assert "signature" in res.json()["error"].lower()


# ---------------------------------------------------------------------------
# 11. Unauthenticated request
# ---------------------------------------------------------------------------

async def test_unauthenticated_request(client: AsyncClient):
    res = await client.get("/api/v1/registrations/me")
    assert res.status_code == 403  # HTTPBearer returns 403 when no credentials


# ---------------------------------------------------------------------------
# 12. Expired JWT rejected
# ---------------------------------------------------------------------------

async def test_expired_token(client: AsyncClient):
    expired_payload = {
        "sub": "00000000-0000-0000-0000-000000000001",
        "role": "student",
        "exp": datetime.now(timezone.utc) - timedelta(minutes=30),
    }
    expired_token = jwt.encode(
        expired_payload,
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )

    res = await client.get(
        "/api/v1/registrations/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert res.status_code == 401
    assert "expired" in res.json()["error"].lower()
