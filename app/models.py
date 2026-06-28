from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    name = mapped_column(String(100), nullable=False)
    email = mapped_column(String(255), unique=True, nullable=False, index=True)
    phone = mapped_column(String(20), nullable=False)
    college = mapped_column(String(200), nullable=True)
    password_hash = mapped_column(String(255), nullable=False)
    role = mapped_column(String(20), nullable=False, server_default="student")
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())

    registrations = relationship("Registration", back_populates="user")


class Event(Base):
    __tablename__ = "events"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    name = mapped_column(String(200), nullable=False)
    description = mapped_column(Text, nullable=True)
    venue = mapped_column(String(300), nullable=True)
    start_time = mapped_column(DateTime(timezone=True), nullable=False)
    registration_deadline = mapped_column(DateTime(timezone=True), nullable=False)
    capacity = mapped_column(Integer, nullable=False)
    registered_count = mapped_column(Integer, nullable=False, server_default="0")
    price = mapped_column(Numeric(10, 2), nullable=False, server_default="0")
    is_active = mapped_column(Boolean, server_default="true")
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())

    registrations = relationship("Registration", back_populates="event")


class Registration(Base):
    __tablename__ = "registrations"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    event_id = mapped_column(UUID(as_uuid=True), ForeignKey("events.id"), nullable=False, index=True)
    status = mapped_column(String(30), nullable=False, server_default="PENDING")
    qr_token = mapped_column(String(100), unique=True, nullable=True, index=True)
    ticket_number = mapped_column(String(30), unique=True, nullable=True)
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="registrations")
    event = relationship("Event", back_populates="registrations")
    payment = relationship("Payment", back_populates="registration", uselist=False)
    checkin = relationship("CheckIn", back_populates="registration", uselist=False)


class Payment(Base):
    __tablename__ = "payments"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    registration_id = mapped_column(UUID(as_uuid=True), ForeignKey("registrations.id"), unique=True, nullable=False)
    amount = mapped_column(Numeric(10, 2), nullable=False)
    razorpay_order_id = mapped_column(String(100), unique=True, nullable=False)
    razorpay_payment_id = mapped_column(String(100), unique=True, nullable=True)
    razorpay_signature = mapped_column(String(500), nullable=True)
    status = mapped_column(String(20), nullable=False, server_default="INITIATED")
    webhook_event_id = mapped_column(String(100), unique=True, nullable=True)
    initiated_at = mapped_column(DateTime(timezone=True), server_default=func.now())
    confirmed_at = mapped_column(DateTime(timezone=True), nullable=True)

    registration = relationship("Registration", back_populates="payment")


class CheckIn(Base):
    __tablename__ = "checkins"

    id = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    # UNIQUE here means Postgres rejects a second INSERT for the same registration — no app-level lock needed
    registration_id = mapped_column(UUID(as_uuid=True), ForeignKey("registrations.id"), unique=True, nullable=False)
    volunteer_id = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    gate = mapped_column(String(50), nullable=True)
    scanned_at = mapped_column(DateTime(timezone=True), server_default=func.now())

    registration = relationship("Registration", back_populates="checkin")
    volunteer = relationship("User")
