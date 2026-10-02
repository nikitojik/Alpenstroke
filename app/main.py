from fastapi import FastAPI, Depends
from app.config import settings
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.db import get_db
app = FastAPI(title="Alpenstroke", version="0.1.0")


@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/info")
def info():
    return {"title": app.title, "version": app.version, "model": settings.apertus_model}

@app.get("/health/db")
def health_db(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"database": "ok"}