from collections.abc import Generator

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

from app.config import settings


def set_sqlite_pragma(dbapi_connection, connection_record):
    """Set SQLite pragmas on every new connection.

    - journal_mode=WAL: concurrent reads during writes
    - synchronous=NORMAL: safe with WAL, better performance
    - foreign_keys=ON: enforce FK constraints (off by default in SQLite)
    - busy_timeout=5000: wait up to 5s for locks instead of failing
    - cache_size=-8000: use 8MB page cache (negative = KiB)
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA cache_size=-8000")
    cursor.close()


engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},
    echo=False,
)

event.listen(engine, "connect", set_sqlite_pragma)


def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
