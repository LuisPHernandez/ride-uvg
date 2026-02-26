from __future__ import annotations

from datetime import datetime, date
from enum import Enum

from sqlalchemy import (
    DateTime,
    Date,
    Time,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    CheckConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


# ---------- Enums ----------
class RideStatus(str, Enum):
    scheduled = "scheduled"
    started = "started"
    completed = "completed"
    cancelled = "cancelled"


class BookingStatus(str, Enum):
    booked = "booked"
    cancelled = "cancelled"
    completed = "completed"
    no_show = "no_show"


class ReportReason(str, Enum):
    safety = "safety"
    harassment = "harassment"
    fraud = "fraud"
    no_show = "no_show"
    driving = "driving"
    other = "other"


# ---------- Entities ----------
class Driver(Base):
    __tablename__ = "driver"

    # Driver info
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    rating_avg: Mapped[float] = mapped_column(Numeric(3, 2), default=0) # 0.00–5.00
    drives_count: Mapped[int] = mapped_column(Integer, default=0)

    # Route info (for simplicity, we assume a single route per driver)
    route_start_lat: Mapped[float] = mapped_column(Numeric(9, 6))
    route_start_lng: Mapped[float] = mapped_column(Numeric(9, 6))
    route_polyline: Mapped[str] = mapped_column(Text, nullable=True) # encoded polyline

    # Account info
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    is_verified: Mapped[bool] = mapped_column(default=False)

    # Relationships
    vehicles: Mapped[list["Vehicle"]] = relationship(back_populates="driver", cascade="all, delete-orphan")
    rides: Mapped[list["Ride"]] = relationship(back_populates="driver", cascade="all, delete-orphan")
    reports: Mapped[list["Report"]] = relationship(back_populates="driver", cascade="all, delete-orphan")
    schedules: Mapped[list["DriverSchedule"]] = relationship(back_populates="driver", cascade="all, delete-orphan")

class DriverSchedule(Base):
    __tablename__ = "driver_schedule"
    __table_args__ = (
        UniqueConstraint("driver_id", "day_of_week", "arrive_by_time", name="uq_driver_schedule_slot"),
        CheckConstraint("day_of_week >= 0 AND day_of_week <= 6", name="ck_day_of_week"),
    )

    # Schedule info
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    driver_id: Mapped[int] = mapped_column(ForeignKey("driver.id", ondelete="CASCADE"), index=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicle.id", ondelete="RESTRICT"), index=True)
    day_of_week: Mapped[int] = mapped_column(Integer)  # 0=Mon ... 6=Sun
    arrive_by_time: Mapped[datetime.time] = mapped_column(Time)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    driver: Mapped["Driver"] = relationship(back_populates="schedules")
    rides: Mapped[list["Ride"]] = relationship(back_populates="schedule")
    vehicle: Mapped["Vehicle"] = relationship(back_populates="schedules")

class Rider(Base):
    __tablename__ = "rider"

    # Rider info
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    rating: Mapped[float] = mapped_column(Numeric(3, 2), default=0)

    # Account info
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    is_verified: Mapped[bool] = mapped_column(default=False)

    # Relationships
    bookings: Mapped[list["Booking"]] = relationship(back_populates="rider", cascade="all, delete-orphan")
    reports: Mapped[list["Report"]] = relationship(back_populates="rider", cascade="all, delete-orphan")


class Vehicle(Base):
    __tablename__ = "vehicle"
    __table_args__ = (
        UniqueConstraint("driver_id", "plate", name="uq_vehicle_driver_plate"),
        CheckConstraint("seats >= 1 AND seats <= 8", name="ck_vehicle_seats_range"),
    )

    # Vehicle info
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    driver_id: Mapped[int] = mapped_column(ForeignKey("driver.id", ondelete="CASCADE"), index=True)
    seats: Mapped[int] = mapped_column(Integer)
    brand: Mapped[str] = mapped_column(String(80))
    model: Mapped[str] = mapped_column(String(80))
    plate: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    driver: Mapped["Driver"] = relationship(back_populates="vehicles")
    rides: Mapped[list["Ride"]] = relationship(back_populates="vehicle")
    schedules: Mapped[list["DriverSchedule"]] = relationship(back_populates="vehicle")


class Ride(Base):
    __tablename__ = "ride"
    __table_args__ = (
        CheckConstraint("seats_available >= 0", name="ck_ride_seats_available_nonneg"),
        CheckConstraint("cost >= 0", name="ck_ride_cost_nonneg"),
        UniqueConstraint("schedule_id", "service_date", name="uq_ride_schedule_id")
    )

    # Ride info
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    driver_id: Mapped[int] = mapped_column(ForeignKey("driver.id", ondelete="CASCADE"), index=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicle.id", ondelete="RESTRICT"), index=True)
    schedule_id: Mapped[int | None] = mapped_column(ForeignKey("driver_schedule.id", ondelete="SET NULL"), index=True, nullable=True)
    service_date: Mapped[date] = mapped_column(Date)
    arrive_by_time: Mapped[datetime.time] = mapped_column(Time)
    status: Mapped[RideStatus] = mapped_column(SAEnum(RideStatus), default=RideStatus.scheduled)
    seats_available: Mapped[int] = mapped_column(Integer)
    cost: Mapped[float] = mapped_column(Numeric(10, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    driver: Mapped["Driver"] = relationship(back_populates="rides")
    vehicle: Mapped["Vehicle"] = relationship(back_populates="rides")
    bookings: Mapped[list["Booking"]] = relationship(back_populates="ride", cascade="all, delete-orphan")
    reports: Mapped[list["Report"]] = relationship(back_populates="ride", cascade="all, delete-orphan")
    schedule: Mapped["DriverSchedule"] = relationship(back_populates="rides")

class Booking(Base):
    __tablename__ = "booking"
    __table_args__ = (
        UniqueConstraint("ride_id", "rider_id", name="uq_booking_ride_rider"),
        CheckConstraint("seats >= 1", name="ck_booking_seats_pos"),
    )

    # Booking info
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ride_id: Mapped[int] = mapped_column(ForeignKey("ride.id", ondelete="CASCADE"), index=True)
    rider_id: Mapped[int] = mapped_column(ForeignKey("rider.id", ondelete="CASCADE"), index=True)
    seats: Mapped[int] = mapped_column(Integer)
    status: Mapped[BookingStatus] = mapped_column(SAEnum(BookingStatus), default=BookingStatus.booked)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Pickup location
    pickup_lat: Mapped[float] = mapped_column(Numeric(9, 6))
    pickup_lng: Mapped[float] = mapped_column(Numeric(9, 6))

    # Relationships
    ride: Mapped["Ride"] = relationship(back_populates="bookings")
    rider: Mapped["Rider"] = relationship(back_populates="bookings")


class Report(Base):
    __tablename__ = "report"

    # Report info
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ride_id: Mapped[int] = mapped_column(ForeignKey("ride.id", ondelete="CASCADE"), index=True)
    rider_id: Mapped[int] = mapped_column(ForeignKey("rider.id", ondelete="CASCADE"), index=True)
    driver_id: Mapped[int] = mapped_column(ForeignKey("driver.id", ondelete="CASCADE"), index=True)
    reason: Mapped[ReportReason] = mapped_column(SAEnum(ReportReason))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    ride: Mapped["Ride"] = relationship(back_populates="reports")
    rider: Mapped["Rider"] = relationship(back_populates="reports")
    driver: Mapped["Driver"] = relationship(back_populates="reports")