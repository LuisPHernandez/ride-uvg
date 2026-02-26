from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from .deps import get_db
from . import models, schemas
from .ride_generator import generate_rides

router = APIRouter()

@router.post("/drivers", response_model=schemas.DriverOut)
def create_driver(payload: schemas.DriverCreate, db: Session = Depends(get_db)):
    driver = models.Driver(
        email=str(payload.email).lower(),
        name=payload.name,
        route_start_lat=payload.route_start_lat,
        route_start_lng=payload.route_start_lng,
        route_polyline=payload.route_polyline,
    )
    db.add(driver)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(driver)
    return driver

@router.post("/drivers/{driver_id}/schedules", response_model=schemas.DriverScheduleOut)
def create_driver_schedule(driver_id: int, payload: schemas.DriverScheduleCreate, db: Session = Depends(get_db)):
    # Ensure driver exists
    driver_exists = db.scalar(
        select(models.Driver.id).where(models.Driver.id == driver_id)
    )
    if driver_exists is None:
        raise HTTPException(status_code=404, detail="Driver not found")
    
    # Ensure vehicle exists and belongs to driver
    vehicle = db.get(models.Vehicle, payload.vehicle_id)
    if not vehicle or vehicle.driver_id != driver_id:
        raise HTTPException(status_code=400, detail="Vehicle not found or does not belong to driver")
    
    # Prevent duplicate schedule for same day
    existing = db.scalar(
        select(models.DriverSchedule.id).where(
            models.DriverSchedule.driver_id == driver_id,
            models.DriverSchedule.day_of_week == payload.day_of_week,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="Schedule for that day already exists")

    schedule = models.DriverSchedule(
        driver_id=driver_id,
        vehicle_id=payload.vehicle_id,
        day_of_week=payload.day_of_week,
        arrive_by_time=payload.arrive_by_time,
    )
    db.add(schedule)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(schedule)
    return schedule

@router.post("/vehicles", response_model=schemas.VehicleOut)
def create_vehicle(payload: schemas.VehicleCreate, db: Session = Depends(get_db)):
    # Ensure driver exists
    driver = db.get(models.Driver, payload.driver_id)
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    vehicle = models.Vehicle(
        driver_id=payload.driver_id,
        seats=payload.seats,
        brand=payload.brand,
        model=payload.model,
        plate=payload.plate.upper(),
    )
    db.add(vehicle)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(vehicle)
    return vehicle

@router.post("/rides", response_model=schemas.RideOut)
def create_ride(payload: schemas.RideCreate, db: Session = Depends(get_db)):
    # Ensure driver exists
    driver = db.get(models.Driver, payload.driver_id)
    if not driver:
        raise HTTPException(status_code=404, detail="Driver not found")

    # Ensure vehicle exists
    vehicle = db.get(models.Vehicle, payload.vehicle_id)
    if not vehicle or vehicle.driver_id != payload.driver_id:
        raise HTTPException(status_code=400, detail="Vehicle not found or does not belong to driver")

    # Ensure seats logic
    if payload.seats_available > vehicle.seats:
        raise HTTPException(status_code=400, detail="seats available cannot exceed vehicle seats")
    
    # Check if schedule was provided and validate it belongs to driver
    if payload.schedule_id:
        schedule = db.get(models.DriverSchedule, payload.schedule_id)
        if not schedule or schedule.driver_id != payload.driver_id:
            raise HTTPException(status_code=400, detail="Schedule not found or does not belong to driver")
        
        # Ensure arrive_by_time is consistent with schedule (if provided)
        if payload.arrive_by_time != schedule.arrive_by_time:
            raise HTTPException(status_code=400, detail="Arrive-by time must match schedule time")
        
    # Ensure service_date is in the future
    today = datetime.utcnow().date()
    if payload.service_date < today:
        raise HTTPException(status_code=400, detail="Service date must be in the future")

    ride = models.Ride(
        driver_id=payload.driver_id,
        vehicle_id=payload.vehicle_id,
        schedule_id=payload.schedule_id,
        service_date=payload.service_date,
        arrive_by_time=payload.arrive_by_time,
        seats_available=payload.seats_available,
        cost=payload.cost,
        status=models.RideStatus.scheduled,
    )
    db.add(ride)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(ride)
    return ride

@router.post("/bookings", response_model=schemas.BookingOut)
def create_booking(payload: schemas.BookingCreate, db: Session = Depends(get_db)):
    """
    Seat-safe booking:
    - lock the ride row
    - validate seats
    - decrement seats
    - insert booking
    all inside one transaction
    """
    # Ensure rider exists
    rider = db.get(models.Rider, payload.rider_id)
    if not rider:
        raise HTTPException(status_code=404, detail="Rider not found")

    # Lock ride row to prevent race conditions
    stmt = (
        select(models.Ride)
        .where(models.Ride.id == payload.ride_id)
        .with_for_update()
    )
    ride = db.execute(stmt).scalar_one_or_none()
    if not ride:
        raise HTTPException(status_code=404, detail="Ride not found")

    if ride.status != models.RideStatus.scheduled:
        raise HTTPException(status_code=400, detail="Ride is not available for booking")

    if payload.seats > ride.seats_available:
        raise HTTPException(status_code=409, detail="Not enough seats available")

    # Check duplicate booking (unique constraint will also protect)
    existing = db.execute(
        select(models.Booking).where(
            models.Booking.ride_id == payload.ride_id,
            models.Booking.rider_id == payload.rider_id,
            models.Booking.status == models.BookingStatus.booked,  # allow rebooking if previously cancelled
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Rider already booked this ride")

    # Update seats + create booking
    ride.seats_available -= payload.seats

    booking = models.Booking(
        ride_id=payload.ride_id,
        rider_id=payload.rider_id,
        seats=payload.seats,
        status=models.BookingStatus.booked,
        created_at=datetime.utcnow(),
        pickup_lat=payload.pickup_lat,
        pickup_lng=payload.pickup_lng,
    )
    db.add(booking)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(booking)
    return booking

@router.post("/riders", response_model=schemas.RiderOut)
def create_rider(payload: schemas.RiderCreate, db: Session = Depends(get_db)):
    rider = models.Rider(
        email=str(payload.email).lower(),
        name=payload.name,
    )
    db.add(rider)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(rider)
    return rider

@router.post("/bookings/{booking_id}/cancel", response_model=schemas.BookingOut)
def cancel_booking(booking_id: int, db: Session = Depends(get_db)):
    """
    Transaction-safe cancellation:
    - lock booking row
    - lock ride row
    - if booking is booked -> set cancelled + add seats back
    - if already cancelled -> return as-is
    """
    # Lock booking row
    booking_stmt = (
        select(models.Booking)
        .where(models.Booking.id == booking_id)
        .with_for_update()
    )
    booking = db.execute(booking_stmt).scalar_one_or_none()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    # If already cancelled, do nothing
    if booking.status == models.BookingStatus.cancelled:
        return booking
    
    # Only allow cancellation if currently booked (not cancelled, no show or completed)
    if booking.status != models.BookingStatus.booked:
        raise HTTPException(
            status_code=400,
            detail=f"Booking cannot be cancelled from status '{booking.status}'"
        )
    
    # Lock the ride row so seats_available can't race
    ride_stmt = (
        select(models.Ride)
        .where(models.Ride.id == booking.ride_id)
        .with_for_update()
    )
    ride = db.execute(ride_stmt).scalar_one_or_none()
    if not ride:
        raise HTTPException(status_code=404, detail="Ride not found")
    
    # Dont allow cancellation if ride is not scheduled (i.e. it already departed or was cancelled)
    if ride.status != models.RideStatus.scheduled:
        raise HTTPException(status_code=400, detail="Ride is not cancellable")
    
    # Apply cancellation + restore seats
    booking.status = models.BookingStatus.cancelled
    booking.cancelled_at = datetime.utcnow()

    ride.seats_available += booking.seats
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(booking)
    return booking

@router.get("/rides", response_model=list[schemas.RideListItem])
def list_rides(
    db: Session = Depends(get_db),
    time_from: datetime | None = Query(default=None),
    time_to: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    stmt = (
        select(models.Ride)
        .options(
            joinedload(models.Ride.driver),
        )
        .where(
            models.Ride.status == models.RideStatus.scheduled,
            models.Ride.seats_available > 0,
        )
        .order_by(
            models.Ride.service_date.asc(),
            models.Ride.arrive_by_time.desc()
        )
    )

    if time_from:
        stmt = stmt.where(models.Ride.departure_time >= time_from)
    if time_to:
        stmt = stmt.where(models.Ride.departure_time <= time_to)

    stmt = stmt.offset(offset).limit(limit)
    rides = db.execute(stmt).scalars().all()
    return rides


@router.post("/internal/generate-rides")
def internal_generate_rides(
    days: int = Query(default=7, ge=1, le=30),
    db: Session = Depends(get_db),
):
    result = generate_rides(db, days_ahead=days)
    return {
        "created": result.created,
        "skipped_existing": result.skipped_existing,
        "skipped_inactive": result.skipped_inactive,
    }