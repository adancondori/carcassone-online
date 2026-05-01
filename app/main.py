"""FastAPI application with lifespan for database initialization."""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import create_db_and_tables, engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: ensure data directory exists and create tables.
    Shutdown: dispose of the engine connection pool.
    """
    os.makedirs("data", exist_ok=True)
    create_db_and_tables()
    yield
    engine.dispose()


app = FastAPI(
    title="Carcassonne Scoreboard",
    lifespan=lifespan,
)


@app.get("/")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}
