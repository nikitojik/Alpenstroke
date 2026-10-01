from fastapi import FastAPI
from app.config import settings
app = FastAPI(title="Alpenstroke", version="0.1.0")

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/info")
def info():
    return {"title": app.title, "version": app.version, "model": settings.apertus_model}