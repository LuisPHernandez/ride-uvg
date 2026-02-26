from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from math import radians, sin, cos, sqrt, atan2

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models


# ---- Config ----
# UVG campus (placeholder).
UVG_CAMPUS_LAT = Decimal("14.6040")
UVG_CAMPUS_LNG = Decimal("-90.4890")

# Pricing (placeholder).
MIN_COST = Decimal("8.00")
COST_PER_KM = Decimal("2.00")


def haversine_km(lat1: Decimal, lng1: Decimal, lat2: Decimal, lng2: Decimal) -> Decimal:
    # Earth radius in km
    R = 6371.0
    phi1 = radians(float(lat1))
    phi2 = radians(float(lat2))
    dphi = radians(float(lat2 - lat1))
    dlambda = radians(float(lng2 - lng1))

    a = sin(dphi/2)**2 + cos(phi1) * cos(phi2) * sin(dlambda/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    return Decimal(str(R * c))


def default_cost_for_driver(driver: models.Driver) -> Decimal:
    dist = haversine_km(Decimal(str(driver.route_start_lat)), Decimal(str(driver.route_start_lng)),
                        UVG_CAMPUS_LAT, UVG_CAMPUS_LNG)
    raw = MIN_COST + (dist * COST_PER_KM)
    # money rounding
    return raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass
class GenerationResult:
    created: int
    skipped_existing: int
    skipped_inactive: int


def generate_rides(db: Session, days_ahead: int = 7) -> GenerationResult:
    """
    Create Ride rows for the next N days from active driver schedules.
    Avoid duplicates using UNIQUE(schedule_id, service_date).
    """
    if days_ahead < 1 or days_ahead > 30:
        raise ValueError("days_ahead must be between 1 and 30")

    today = date.today()
    end = today + timedelta(days=days_ahead)

    schedules = db.execute(
        select(models.DriverSchedule)
        .where(models.DriverSchedule.is_active == True)
    ).scalars().all()

    created = 0
    skipped_existing = 0
    skipped_inactive = 0

    for sch in schedules:
        # Verify driver and vehicle are active/valid before generating rides
        driver = db.get(models.Driver, sch.driver_id)
        if not driver or not driver.is_verified:
            skipped_inactive += 1
            continue

        vehicle = db.get(models.Vehicle, sch.vehicle_id)
        if not vehicle or vehicle.driver_id != sch.driver_id:
            skipped_inactive += 1
            continue

        # Generate dates in [today, end) matching weekday
        d = today
        while d < end:
            if d.weekday() == sch.day_of_week:
                # Check if ride already exists
                existing = db.execute(
                    select(models.Ride.id).where(
                        models.Ride.schedule_id == sch.id,
                        models.Ride.service_date == d,
                    )
                ).first()

                if existing:
                    skipped_existing += 1
                else:
                    ride = models.Ride(
                        driver_id=sch.driver_id,
                        vehicle_id=sch.vehicle_id,
                        schedule_id=sch.id,
                        service_date=d,
                        arrive_by_time=sch.arrive_by_time,
                        status=models.RideStatus.scheduled,
                        seats_available=vehicle.seats,
                        cost=default_cost_for_driver(driver),
                    )
                    db.add(ride)
                    created += 1

            d += timedelta(days=1)
            
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    return GenerationResult(created=created, skipped_existing=skipped_existing, skipped_inactive=skipped_inactive)