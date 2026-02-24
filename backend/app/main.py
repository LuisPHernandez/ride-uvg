from fastapi import FastAPI
from . import models
from .routes import router

app = FastAPI(title="Ride UVG API")
app.include_router(router)

@app.get("/health")
def health():
    return {"status": "ok"}