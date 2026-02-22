from fastapi import FastAPI

app = FastAPI(title="Ride UVG API")

@app.get("/health")
def health():
    return {"status": "ok"}