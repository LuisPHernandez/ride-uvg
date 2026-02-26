from datetime import date, datetime, time
from enum import Enum
from pydantic import BaseModel, Field, EmailStr, conint, condecimal

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

# ---------- Driver ----------
class DriverCreate(BaseModel):
    email: EmailStr
    name: str
    route_start_lat: condecimal(max_digits=9, decimal_places=6)
    route_start_lng: condecimal(max_digits=9, decimal_places=6)
    route_polyline: str  # encoded polyline

class DriverOut(BaseModel):
    id: int
    email: EmailStr
    name: str
    rating_avg: float
    drives_count: int
    route_start_lat: float
    route_start_lng: float
    route_polyline: str
    is_verified: bool

    class Config:
        from_attributes = True

# ---------- Driver schedule ----------
class DriverScheduleCreate(BaseModel):
    vehicle_id: int
    day_of_week: int = Field(ge=0, le=6)
    arrive_by_time: time

class DriverScheduleOut(BaseModel):
    id: int
    driver_id: int
    vehicle_id: int
    day_of_week: int
    arrive_by_time: time
    is_active: bool

    class Config:
        from_attributes = True

# ---------- Vehicle ----------
class VehicleCreate(BaseModel):
    driver_id: int
    seats: conint(ge=1, le=8)
    brand: str
    model: str
    plate: str

class VehicleOut(BaseModel):
    id: int
    driver_id: int
    seats: int
    brand: str
    model: str
    plate: str

    class Config:
        from_attributes = True

# ---------- Ride ----------
class RideCreate(BaseModel):
    driver_id: int
    vehicle_id: int
    schedule_id: int | None
    service_date: date
    arrive_by_time: time
    seats_available: conint(ge=0, le=8)
    cost: condecimal(max_digits=10, decimal_places=2)

class RideOut(BaseModel):
    id: int
    driver_id: int
    vehicle_id: int
    schedule_id: int | None
    service_date: date
    arrive_by_time: time
    seats_available: int
    cost: float
    status: RideStatus

    class Config:
        from_attributes = True

# ---------- Booking (seat-safe) ----------
class BookingCreate(BaseModel):
    ride_id: int
    rider_id: int
    seats: conint(ge=1, le=8)
    pickup_lat: condecimal(max_digits=9, decimal_places=6)
    pickup_lng: condecimal(max_digits=9, decimal_places=6)

class BookingOut(BaseModel):
    id: int
    ride_id: int
    rider_id: int
    seats: int
    status: BookingStatus
    created_at: datetime
    cancelled_at: datetime | None
    pickup_lat: float
    pickup_lng: float

    class Config:
        from_attributes = True

# ---------- Rider ----------
class RiderCreate(BaseModel):
    email: EmailStr
    name: str

class RiderOut(BaseModel):
    id: int
    email: EmailStr
    name: str
    rating: float
    created_at: datetime
    is_verified: bool

    class Config:
        from_attributes = True

# ---------- Rides list ----------
class DriverSummary(BaseModel):
    id: int
    name: str
    rating_avg: float

    class Config:
        from_attributes = True

class RideSummary(BaseModel):
    id: int
    arrive_by_time: time
    status: RideStatus
    seats_available: int
    cost: float

    class Config:
        from_attributes = True

class RideListItem(RideSummary):
    driver: DriverSummary

    class Config:
        from_attributes = True

# ---------- Rides detail ----------
class DriverDetail(BaseModel):
    id: int
    name: str
    rating_avg: float
    drives_count: int

    class Config:
        from_attributes = True