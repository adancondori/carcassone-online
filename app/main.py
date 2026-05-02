"""FastAPI application with lifespan for database initialization."""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.db import create_db_and_tables, engine
from app.web.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: ensure data directory exists and create tables.
    Shutdown: dispose of the engine connection pool.
    """
    os.makedirs("data", exist_ok=True)
    os.makedirs("app/static", exist_ok=True)
    create_db_and_tables()
    yield
    engine.dispose()


app = FastAPI(
    title="Carcassonne Scoreboard",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}
