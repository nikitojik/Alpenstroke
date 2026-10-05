from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.routers import athletes, workouts
from app.web import pages

app = FastAPI(title="Alpenstroke", version="0.1.0")

app.mount(
    "/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static"
)

app.include_router(athletes.router)
app.include_router(workouts.router)
app.include_router(pages.router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/health/db")
def health_db(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="database unavailable")
    return {"database": "ok"}


@app.get("/info")
def info():
    return {"title": app.title, "version": app.version, "model": settings.apertus_model}
