from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


# --- Auth ---

class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    phone: str
    college: str | None = None
    password: str = Field(min_length=8)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: UUID
    name: str
    email: str
    role: str
    college: str | None
    model_config = ConfigDict(from_attributes=True)


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# --- Events ---

class EventOut(BaseModel):
    id: UUID
    name: str
    description: str | None
    venue: str | None
    start_time: datetime
    registration_deadline: datetime
    capacity: int
    registered_count: int
    price: float
    is_active: bool
    spots_left: int = 0
    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def compute_spots_left(self):
        self.spots_left = max(0, self.capacity - self.registered_count)
        return self


# --- Registrations ---

class CreateRegistrationRequest(BaseModel):
    event_id: UUID


class RegistrationOut(BaseModel):
    id: UUID
    event_id: UUID
    status: str
    ticket_number: str | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


# --- Payments ---

class InitiatePaymentRequest(BaseModel):
    registration_id: UUID


class InitiatePaymentResponse(BaseModel):
    razorpay_order_id: str
    amount: float
    currency: str = "INR"
    key_id: str


class VerifyPaymentRequest(BaseModel):
    registration_id: UUID
    razorpay_payment_id: str
    razorpay_order_id: str
    razorpay_signature: str


class PaymentVerifiedResponse(BaseModel):
    ticket_number: str
    status: str
    message: str


# --- Check-in ---

class ScanRequest(BaseModel):
    qr_token: str
    gate: str | None = None


class ScanResponse(BaseModel):
    student_name: str
    ticket_number: str
    event_name: str
    college: str | None
    message: str = "Check-in successful"


class CheckInStats(BaseModel):
    event_name: str
    capacity: int
    confirmed: int
    checked_in: int
    pending: int


# --- API envelope ---

class APIResponse(BaseModel):
    data: dict | list | None = None
    error: str | None = None
