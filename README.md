# TechFest Registration API

REST API for IEEE RVCE TechFest 2026 — handles student registrations, Razorpay payments, QR ticket generation, and volunteer gate check-in.

## Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12 |
| Framework | FastAPI 0.115 |
| Database | PostgreSQL (async via asyncpg) |
| Auth | JWT (python-jose, HS256, 15-min expiry) |
| Payments | Razorpay SDK (test mode) |
| Task Queue | Celery + Redis |

## Prerequisites

- Docker & Docker Compose (recommended)
- OR: Python 3.12+, PostgreSQL, Redis

## Running Locally

### With Docker (recommended)

```bash
git clone <repo-url>
cd ieee_webdev

cp .env.example .env
# Edit .env and fill in RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, RAZORPAY_WEBHOOK_SECRET

docker-compose up --build -d

# Run migrations
docker-compose exec api alembic upgrade head

# Seed database (creates 1 event + 1 volunteer account)
docker-compose exec api python seed.py
```

API: http://localhost:8000  
Interactive docs: http://localhost:8000/docs

### Without Docker

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env — set DATABASE_URL to your local PostgreSQL connection string

alembic upgrade head
python seed.py
uvicorn app.main:app --reload
```

Start the Celery worker (in a separate terminal):
```bash
celery -A workers.celery_app.celery_app worker --loglevel=info
```

## Volunteer Account

After running `seed.py`:

| Field | Value |
|---|---|
| Email | volunteer@techfest.com |
| Password | volunteer123 |

To create additional volunteer accounts (admin only):
```bash
curl -X POST http://localhost:8000/internal/create-volunteer \
  -H "X-Admin-Secret: <ADMIN_SECRET from .env>" \
  -H "Content-Type: application/json" \
  -d '{"name": "Jane", "email": "jane@techfest.com", "phone": "9999999999", "password": "secure123"}'
```

## Razorpay Setup

1. Create a Razorpay account and get test-mode keys from the dashboard.
2. Set `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, and `RAZORPAY_WEBHOOK_SECRET` in `.env`.
3. Test mode credentials work end-to-end with Razorpay's test card numbers.

**To test without Razorpay**: set the event `price` to `0` in `seed.py`. Free events skip Razorpay entirely and confirm immediately.

## API Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/v1/auth/register` | None | Register a new student account |
| POST | `/api/v1/auth/login` | None | Login and get JWT |
| POST | `/api/v1/auth/refresh` | Student/Volunteer | Refresh JWT before expiry |
| POST | `/api/v1/auth/logout` | Student/Volunteer | Stateless logout (client drops token) |
| GET | `/api/v1/events/` | None | List all active events |
| GET | `/api/v1/events/{event_id}` | None | Get event details + spots left |
| POST | `/api/v1/registrations/` | Student | Register for an event |
| GET | `/api/v1/registrations/me` | Student | List my registrations |
| GET | `/api/v1/registrations/` | Volunteer | List all registrations (filterable) |
| GET | `/api/v1/registrations/{id}` | Student/Volunteer | Get single registration |
| GET | `/api/v1/registrations/{id}/qr` | Student | Download QR PNG (confirmed only) |
| POST | `/api/v1/payments/initiate` | Student | Create Razorpay order |
| POST | `/api/v1/payments/verify` | Student | Verify signature and confirm ticket |
| POST | `/api/v1/payments/webhook` | Razorpay | Webhook for payment.captured events |
| POST | `/api/v1/checkin/scan` | Volunteer | Scan QR and check in student |
| GET | `/api/v1/checkin/stats/{event_id}` | Volunteer | Live attendance breakdown |
| POST | `/internal/create-volunteer` | Admin secret | Create a volunteer account |
| GET | `/health` | None | Health check (pings DB) |

## Testing with Postman

Import `postman_collection.json` into Postman. Then:

1. Run **Internal / Health Check** to verify the server is up
2. Run **Auth / Login Student** — the test script auto-captures `STUDENT_TOKEN`
3. Run **Auth / Login Volunteer** — auto-captures `VOLUNTEER_TOKEN`
4. Run **Events / List Events** — auto-captures `EVENT_ID`
5. Work through the remaining folders in order

The **Edge Cases** folder has pre-built requests that demonstrate constraint handling — each one is designed to return an error.

## Running Tests

```bash
pytest tests/ -v
```

Tests use SQLite (no external DB needed). The 12 tests cover the edge cases from the spec: duplicate registrations, capacity enforcement, authorization boundaries, tampered payment signatures, double scan prevention, and expired tokens.

## Assumptions

1. **Stateless logout**: JWTs are short-lived (15 min). Logout is client-side token deletion. No server-side blacklist is maintained — this is acceptable for an event of this scale.
2. **Single Razorpay payment per registration**: If a student initiates payment twice, the second call returns a conflict error. Each registration has exactly one payment record.
3. **Webhook is the source of truth**: Both `/payments/verify` (client-side) and the Razorpay webhook can confirm a payment. The webhook uses idempotency (unique `webhook_event_id`) to avoid double-processing.
4. **Free events**: Events with `price = 0.00` skip Razorpay entirely. Calling `/payments/initiate` returns a confirmed ticket immediately.
5. **QR in app, not email**: Ticket emails contain event details and instructions to download the QR from the app. The PNG is not attached to the email to keep email delivery fast and reliable.
6. **No admin UI**: Volunteers and admins interact via the API directly. A frontend would be a natural next step but is out of scope for this challenge.
