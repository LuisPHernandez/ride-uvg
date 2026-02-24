from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .deps import get_db
from . import models, schemas

router = APIRouter()


@router.post("/drivers", response_model=schemas.DriverOut)
def create_driver(payload: schemas.DriverCreate, db: Session = Depends(get_db)):
    driver = models.Driver(
        email=str(payload.email).lower(),
        name=payload.name,
        route_start_lat=payload.route_start_lat,
        route_start_lng=payload.route_start_lng,
        route_public=payload.route_public,
    )
    db.add(driver)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(driver)
    return driver


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

    ride = models.Ride(
        driver_id=payload.driver_id,
        vehicle_id=payload.vehicle_id,
        departure_time=payload.departure_time,
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
def create_rider(payload: schemas.RideCreate, db: Session = Depends(get_db)):
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