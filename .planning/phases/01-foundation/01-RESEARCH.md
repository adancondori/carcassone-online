# Phase 1: Foundation - Research

**Researched:** 2026-05-01
**Domain:** Data model (SQLModel), service layer, Alembic migrations, SQLite configuration, Docker, pytest
**Confidence:** HIGH

## Summary

Phase 1 builds the scoring engine without any HTTP layer: SQLModel models with constraints, service functions (add_score, undo_last, rollback_to, recalculate_score), Alembic migrations with SQLite batch mode, Docker with persistent SQLite, and a pytest suite proving correctness.

The standard approach is well-established: SQLModel models use `__table_args__` for CHECK/UNIQUE constraints, SQLAlchemy event listeners set SQLite pragmas per-connection, Alembic needs `render_as_batch=True` plus a naming convention set on metadata BEFORE model classes are defined, and pytest uses in-memory SQLite with `StaticPool` for fast isolated tests.

Three critical pitfalls from prior research are confirmed and have concrete prevention patterns: (1) score_total cache divergence -- prevent with property-based tests running random add/undo/rollback sequences, (2) SQLite WAL files lost in Docker -- prevent by mounting the data DIRECTORY as a named volume, (3) Alembic batch mode -- prevent by enabling `render_as_batch=True` and naming all constraints.

**Primary recommendation:** Build bottom-up: naming convention + models first, then db.py with pragmas, then services with tests, then Alembic + Docker. Every constraint must be explicitly named for batch mode compatibility.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| SQLModel | ~=0.0.38 | ORM models | Single class = SQLAlchemy table + Pydantic schema. `table=True` models map directly to DB. Eliminates model/schema duplication. |
| SQLAlchemy | >=2.0 (transitive) | Engine, session, events | Provides `create_engine`, `Session`, `@event.listens_for` for SQLite pragmas, `func.sum`/`func.coalesce` for aggregation. |
| Alembic | ~=1.18.4 | Schema migrations | Autogenerate from SQLModel metadata. Batch mode required for SQLite. |
| pytest | ~=9.0.3 | Test runner | Fixtures, parametrize, assertion introspection. |
| FastAPI | ~=0.136.1 | App shell (lifespan only) | Needed for INFRA-05. Phase 1 only uses lifespan for DB init -- no routes yet. |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pydantic-settings | ~=2.14.0 | Config from env | Load DATABASE_URL from `.env` with typed validation. |
| pytest-cov | ~=7.1.0 | Coverage reporting | Target 90%+ on services layer. |
| uvicorn[standard] | ~=0.46.0 | ASGI server | For Docker CMD. Phase 1 just needs it installed, not heavily used. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| SQLModel constraints via `__table_args__` | `sa_column=Column(...)` per field | `__table_args__` is cleaner for multi-column and table-level constraints; `sa_column` is per-field only and loses Field convenience features |
| `@event.listens_for(Engine, "connect")` for pragmas | `engine.execute()` after create | Event listener fires on EVERY connection including reconnects; one-time execute misses connection pool recycling |
| `StaticPool` for tests | File-based SQLite for tests | StaticPool + in-memory is faster and auto-cleans; file-based needed only for WAL-specific testing |

## Architecture Patterns

### Recommended Project Structure (Phase 1 scope)

```
app/
  __init__.py
  main.py               # FastAPI app with lifespan (DB init only)
  config.py             # pydantic-settings: DATABASE_URL, APP_NAME
  models.py             # SQLModel: Game, Player, ScoreAction, ScoreEntry
  db.py                 # Engine creation, session factory, pragma event listener
  services.py           # add_score, undo_last, rollback_to, recalculate_score

tests/
  __init__.py
  conftest.py           # Fixtures: in-memory engine, session, game_with_players
  test_models.py        # current_cell, lap properties
  test_services.py      # Scoring, undo, rollback, shared scoring, recalculate

alembic/
  env.py                # target_metadata = SQLModel.metadata, render_as_batch=True
  script.py.mako        # import sqlmodel.sql.sqltypes
  versions/

alembic.ini
pyproject.toml
Dockerfile
docker-compose.yml
.env
```

### Pattern 1: Naming Convention BEFORE Models

**What:** Set `SQLModel.metadata.naming_convention` before any model class is defined.
**When to use:** Always -- Alembic batch mode needs named constraints to drop/modify them.
**Why critical:** The naming convention applies names to Constraint objects at class definition time. If set after models are defined, constraints remain unnamed and batch operations fail silently.

```python
# app/models.py -- naming convention MUST come first
from sqlmodel import SQLModel

# Set BEFORE any model classes are defined
SQLModel.metadata.naming_convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# NOW define models -- they pick up the naming convention
class Game(SQLModel, table=True):
    ...
```

**Source:** Alembic naming conventions docs (https://alembic.sqlalchemy.org/en/latest/naming.html) -- HIGH confidence

### Pattern 2: SQLite Pragmas via Event Listener

**What:** Use `@event.listens_for(Engine, "connect")` to set pragmas on every connection.
**When to use:** Always with SQLite -- pragmas are per-connection, not persisted.

```python
# app/db.py
from sqlalchemy import event
from sqlalchemy.engine import Engine

@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA cache_size=-8000")
    cursor.close()
```

**Source:** SQLAlchemy SQLite dialect docs (https://docs.sqlalchemy.org/en/20/dialects/sqlite.html) -- HIGH confidence

**Important:** The SQLAlchemy docs show toggling `dbapi_connection.autocommit` around the PRAGMA execution. However, for modern SQLAlchemy 2.0+ with pysqlite, the pragmas work without this toggle in practice. If WAL mode fails to set, wrap with the autocommit toggle as shown in the official docs.

### Pattern 3: SQLModel CHECK and UNIQUE Constraints

**What:** Use `__table_args__` tuple with SQLAlchemy constraint objects for table-level constraints.
**When to use:** For multi-column UNIQUE, CHECK on column values, and composite constraints.

```python
# app/models.py
from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlmodel import Field, SQLModel

class Player(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="game.id")
    name: str
    color: str
    score_total: int = Field(default=0)
    turn_order: int

    __table_args__ = (
        CheckConstraint("turn_order BETWEEN 1 AND 6", name="player_turn_order_range"),
        UniqueConstraint("game_id", "color", name="uq_player_game_color"),
        UniqueConstraint("game_id", "turn_order", name="uq_player_game_turn_order"),
        UniqueConstraint("game_id", "name", name="uq_player_game_name"),
    )
```

**Source:** SQLModel GitHub issues #82 and #292, confirmed with SQLAlchemy constraints docs -- HIGH confidence

**Important:** Every constraint MUST have an explicit `name=` parameter. Unnamed constraints cannot be targeted by Alembic batch operations. The naming convention provides automatic names for simple cases, but explicit names on `__table_args__` constraints are safer and more readable.

### Pattern 4: Alembic env.py for SQLModel + SQLite

**What:** Configure Alembic to use SQLModel metadata, render_as_batch, and user_module_prefix.

```python
# alembic/env.py (key sections)
from sqlmodel import SQLModel
from app.models import *  # Import all models so metadata is populated
from app.config import settings

target_metadata = SQLModel.metadata

def run_migrations_online():
    connectable = create_engine(settings.DATABASE_URL)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # CRITICAL for SQLite
            user_module_prefix="sqlmodel.sql.sqltypes.",  # For SQLModel types
        )
        with context.begin_transaction():
            context.run_migrations()
```

Also add to `alembic/script.py.mako`:
```mako
import sqlmodel.sql.sqltypes
```

**Source:** Alembic batch docs + SQLModel discussions -- HIGH confidence

**Why `user_module_prefix`:** Without this, autogenerated migrations reference `sqlmodel.sql.sqltypes.AutoString()` as an unresolvable type. The prefix tells Alembic how to qualify SQLModel custom types in generated migration files.

**Why import models:** `target_metadata = SQLModel.metadata` is an empty MetaData unless the model classes have been imported (i.e., the class bodies have executed). Alembic autogenerate will see zero tables and generate DROP TABLE operations for existing tables.

### Pattern 5: FastAPI Lifespan (NOT on_event)

**What:** Use `asynccontextmanager` lifespan instead of deprecated `@app.on_event("startup")`.

```python
# app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.db import create_db_and_tables, engine

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()  # Alembic handles production; this is for dev
    yield
    # Shutdown: optionally checkpoint WAL
    engine.dispose()

app = FastAPI(lifespan=lifespan)
```

**Source:** FastAPI official docs (https://fastapi.tiangolo.com/advanced/events/) -- HIGH confidence. `on_event` is explicitly deprecated.

### Pattern 6: pytest Fixtures for SQLModel

**What:** In-memory SQLite with StaticPool for fast, isolated tests.

```python
# tests/conftest.py
import pytest
from sqlmodel import SQLModel, Session, create_engine
from sqlmodel.pool import StaticPool

@pytest.fixture(name="engine")
def engine_fixture():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine

@pytest.fixture(name="session")
def session_fixture(engine):
    with Session(engine) as session:
        yield session

@pytest.fixture(name="game_with_players")
def game_with_players_fixture(session):
    game = Game(name="Test Game", status="playing")
    session.add(game)
    session.flush()
    p1 = Player(game_id=game.id, name="Alice", color="blue", turn_order=1)
    p2 = Player(game_id=game.id, name="Bob", color="red", turn_order=2)
    session.add_all([p1, p2])
    session.commit()
    session.refresh(game)
    session.refresh(p1)
    session.refresh(p2)
    return game, [p1, p2]
```

**Source:** SQLModel official testing tutorial (https://sqlmodel.tiangolo.com/tutorial/fastapi/tests/) -- HIGH confidence

**Note on foreign_keys pragma in tests:** The in-memory SQLite for tests should also have `PRAGMA foreign_keys=ON` if you want FK constraints enforced during testing. The event listener approach (Pattern 2) handles this automatically IF the listener is registered before the test engine is created. Since the listener targets `Engine` class globally, importing `db.py` in conftest.py will activate it.

### Anti-Patterns to Avoid

- **Unnamed constraints:** Never use `CheckConstraint("...")` or `UniqueConstraint(...)` without `name=`. Alembic batch mode cannot drop unnamed constraints.
- **`create_all()` in production:** Use Alembic migrations. `create_all()` is fine for test fixtures only.
- **`async def` routes with sync DB calls:** Use `def` (not `async def`) for all route handlers that call synchronous SQLAlchemy session methods. FastAPI runs sync handlers in a threadpool automatically.
- **Setting pragmas in `create_engine()`:** Use event listeners instead. `create_engine` connect_args only runs at pool creation; event listeners fire on every connection including reconnects.
- **Importing models AFTER setting target_metadata:** Models must be imported before `target_metadata = SQLModel.metadata` is used by Alembic, otherwise metadata is empty.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Score recalculation | Manual cache invalidation with triggers | `func.coalesce(func.sum(ScoreEntry.points), 0)` with SQLAlchemy ORM query | SQL SUM is atomic, correct, and O(N) with N~100 rows. No custom code needed. |
| Named constraints for Alembic | Manual constraint name strings | `SQLModel.metadata.naming_convention` dict | Automatic, consistent naming that Alembic understands for batch operations. |
| Database session management | Manual connection open/close | SQLModel `Session` context manager + FastAPI `Depends(get_session)` | Automatic cleanup on exit, exception-safe. |
| Config from environment | `os.getenv()` with manual validation | `pydantic-settings` `BaseSettings` class | Typed, validated, .env file support, default values. |
| Migration scripts | Hand-written SQL DDL | `alembic revision --autogenerate` | Detects model changes, generates migration code, tracks version history. |

**Key insight:** Every "plumbing" problem in this phase has a standard solution in the SQLModel/Alembic/FastAPI ecosystem. The only custom code should be the four service functions (add_score, undo_last, rollback_to, recalculate_score).

## Common Pitfalls

### Pitfall 1: score_total Cache Diverges from Entry Source of Truth

**What goes wrong:** `player.score_total` drifts from `SUM(score_entries.points WHERE is_undone=FALSE)` after undo/rollback sequences.
**Why it happens:** Two write paths exist (direct update on add_score, recalculate on undo). Any new code path that modifies entries without updating the cache creates divergence.
**How to avoid:**
1. `add_score()` updates cache directly (fast path)
2. `undo_last()` and `rollback_to()` ALWAYS recalculate from entries (safe path)
3. Write a consistency assertion test: after every operation, verify `player.score_total == recalculate_score(session, player.id)`
4. Property-based test with random sequences of add/undo/rollback
**Warning signs:** `recalculate_score()` returns a different value than `player.score_total` in any test.

### Pitfall 2: SQLite WAL Files Lost in Docker Volume

**What goes wrong:** SQLite WAL mode creates `.db-wal` and `.db-shm` sidecar files alongside the main `.db` file. If only the `.db` file is in the volume mount, uncommitted WAL data is lost on container restart.
**Why it happens:** The Docker volume must mount the entire DATA DIRECTORY, not the individual `.db` file.
**How to avoid:**
1. Mount `db_data:/code/data` (directory), never `db_data:/code/data/carcassonne.db` (file)
2. `DATABASE_URL=sqlite:///data/carcassonne.db` -- path is inside the mounted directory
3. Smoke test: create data, `docker compose down`, `docker compose up`, verify data survives
4. Optionally checkpoint WAL on shutdown: `PRAGMA wal_checkpoint(TRUNCATE)` in lifespan shutdown
**Warning signs:** Data disappears after container restart; `.db` file size is unexpectedly small.

### Pitfall 3: Alembic Batch Mode Not Enabled

**What goes wrong:** Alembic autogenerate creates migration scripts that fail silently on SQLite. Constraints are not created or are silently dropped.
**Why it happens:** SQLite only supports `ADD COLUMN` and `RENAME COLUMN` in ALTER TABLE. Everything else requires table recreation (batch mode).
**How to avoid:**
1. Set `render_as_batch=True` in `context.configure()` in env.py
2. Name ALL constraints explicitly (either in `__table_args__` or via naming convention)
3. Set `user_module_prefix="sqlmodel.sql.sqltypes."` for SQLModel type rendering
4. Add `import sqlmodel.sql.sqltypes` to `script.py.mako`
5. After migration, inspect schema with `PRAGMA table_info()` to verify constraints exist
**Warning signs:** Migration runs without errors but `PRAGMA table_info()` shows missing constraints.

### Pitfall 4: Naming Convention Set After Model Definition

**What goes wrong:** Naming convention is set on `SQLModel.metadata` but AFTER model classes are defined. Constraints created during class definition are already unnamed.
**Why it happens:** Python executes class bodies at import time. If the naming convention assignment is below the class definitions in the same file, or in a different file imported later, it is too late.
**How to avoid:** Set `SQLModel.metadata.naming_convention = {...}` at the TOP of `models.py`, before any `class Foo(SQLModel, table=True)` definition.
**Warning signs:** Alembic autogenerate produces constraint names like `None` or raises "Can't drop unnamed constraint."

### Pitfall 5: Foreign Keys Not Enforced in SQLite

**What goes wrong:** SQLite accepts INSERT/UPDATE that violates foreign key constraints without error.
**Why it happens:** SQLite does NOT enforce foreign keys by default. `PRAGMA foreign_keys=ON` must be set per-connection.
**How to avoid:** Use `@event.listens_for(Engine, "connect")` to set the pragma on every connection. Verify in tests by attempting an FK violation and asserting it raises `IntegrityError`.
**Warning signs:** Tests that insert entries with invalid `action_id` or `player_id` values pass without error.

## Code Examples

### Service: add_score (atomic multi-player scoring)

```python
# app/services.py
from sqlmodel import Session, select
from sqlalchemy import func
from app.models import Game, Player, ScoreAction, ScoreEntry

def add_score(
    session: Session,
    game_id: int,
    player_points: list[tuple[int, int]],  # [(player_id, points), ...]
    event_type: str,
    description: str | None = None,
) -> ScoreAction:
    action = ScoreAction(
        game_id=game_id,
        event_type=event_type,
        description=description,
    )
    session.add(action)
    session.flush()  # Get action.id without committing

    for player_id, points in player_points:
        player = session.get(Player, player_id)
        if player is None:
            raise ValueError(f"Player {player_id} not found")
        score_before = player.score_total
        player.score_total += points

        entry = ScoreEntry(
            action_id=action.id,
            player_id=player_id,
            points=points,
            score_before=score_before,
            score_after=player.score_total,
        )
        session.add(entry)

    session.commit()
    return action
```

**Source:** Derived from docs/plan.md service signatures, verified patterns from SQLModel docs.

### Service: recalculate_score (source of truth)

```python
def recalculate_score(session: Session, player_id: int) -> int:
    total = session.exec(
        select(func.coalesce(func.sum(ScoreEntry.points), 0))
        .join(ScoreAction, ScoreEntry.action_id == ScoreAction.id)
        .where(ScoreEntry.player_id == player_id)
        .where(ScoreAction.is_undone == False)
    ).one()

    player = session.get(Player, player_id)
    player.score_total = total
    return total
```

**Note on query style:** SQLModel's `session.exec(select(...))` wraps SQLAlchemy's `session.execute(select(...))` and returns results directly. Use `session.exec` for SQLModel compatibility. The `.one()` method returns the scalar value from a single-column query.

### Service: undo_last

```python
def undo_last(session: Session, game_id: int) -> ScoreAction | None:
    # Get last active (non-undone) action for this game
    statement = (
        select(ScoreAction)
        .where(ScoreAction.game_id == game_id)
        .where(ScoreAction.is_undone == False)
        .order_by(ScoreAction.id.desc())
        .limit(1)
    )
    last_action = session.exec(statement).first()
    if last_action is None:
        return None

    last_action.is_undone = True

    # Recalculate all affected players from entries
    entries = session.exec(
        select(ScoreEntry).where(ScoreEntry.action_id == last_action.id)
    ).all()
    affected_player_ids = {e.player_id for e in entries}
    for pid in affected_player_ids:
        recalculate_score(session, pid)

    session.commit()
    return last_action
```

### Service: rollback_to

```python
def rollback_to(session: Session, game_id: int, action_id: int) -> int:
    # Get all active actions after the target action
    statement = (
        select(ScoreAction)
        .where(ScoreAction.game_id == game_id)
        .where(ScoreAction.id > action_id)
        .where(ScoreAction.is_undone == False)
    )
    actions = session.exec(statement).all()
    if not actions:
        return 0

    affected_player_ids: set[int] = set()
    for action in actions:
        action.is_undone = True
        entries = session.exec(
            select(ScoreEntry).where(ScoreEntry.action_id == action.id)
        ).all()
        for entry in entries:
            affected_player_ids.add(entry.player_id)

    for pid in affected_player_ids:
        recalculate_score(session, pid)

    session.commit()
    return len(actions)
```

### Model: Player with computed properties

```python
BOARD_SIZE = 50

class Player(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="game.id")
    name: str
    color: str
    score_total: int = Field(default=0)
    turn_order: int

    __table_args__ = (
        CheckConstraint("turn_order BETWEEN 1 AND 6", name="player_turn_order_range"),
        UniqueConstraint("game_id", "color", name="uq_player_game_color"),
        UniqueConstraint("game_id", "turn_order", name="uq_player_game_turn_order"),
        UniqueConstraint("game_id", "name", name="uq_player_game_name"),
    )

    @property
    def current_cell(self) -> int:
        return self.score_total % BOARD_SIZE

    @property
    def lap(self) -> int:
        return self.score_total // BOARD_SIZE
```

### Model: ScoreAction with CHECK constraint

```python
class ScoreAction(SQLModel, table=True):
    __tablename__ = "score_action"

    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="game.id")
    event_type: str
    description: str | None = None
    is_undone: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    __table_args__ = (
        CheckConstraint(
            "event_type IN ('ROAD_COMPLETED', 'CITY_COMPLETED', 'MONASTERY_COMPLETED', "
            "'ROAD_FINAL', 'CITY_FINAL', 'MONASTERY_FINAL', 'FARM_FINAL', 'MANUAL')",
            name="score_action_event_type_check",
        ),
    )
```

### db.py: Engine + Pragmas + Session Factory

```python
# app/db.py
from sqlmodel import SQLModel, Session, create_engine
from sqlalchemy import event
from sqlalchemy.engine import Engine
from app.config import settings

@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA cache_size=-8000")
    cursor.close()

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

def get_session():
    with Session(engine) as session:
        yield session
```

### Docker Compose: Volume for data directory

```yaml
services:
  web:
    build: .
    container_name: carcassonne_web
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    ports:
      - "8000:8000"
    volumes:
      - .:/code                 # Bind mount for --reload in dev
      - db_data:/code/data      # Named volume for ENTIRE data directory
    env_file:
      - .env

volumes:
  db_data:                      # Persists across docker compose down/up
```

**Critical:** The volume mounts `/code/data` (directory), so `.db`, `.db-wal`, and `.db-shm` files are all persisted.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `@app.on_event("startup")` | `lifespan` async context manager | FastAPI 0.109+ | `on_event` is deprecated. Use `asynccontextmanager` lifespan. |
| SQLModel 0.0.x with SA 1.4 | SQLModel 0.0.38 with SA 2.0 | SQLModel 0.0.14+ | SA 2.0 select() style, `session.exec()` preferred over `session.query()`. |
| `session.query(Model)` | `session.exec(select(Model))` | SQLAlchemy 2.0 | Legacy query API is deprecated. Use `select()` statements. |
| Unnamed constraints + SQLite | Named constraints + batch mode | Alembic 1.7+ | Named CHECK constraints are reflected and managed by batch mode. Unnamed constraints cannot be targeted. |
| `requirements.txt` | `pyproject.toml` with `[project]` | PEP 621 (2021+) | Single file for metadata, dependencies, tool config. No separate requirements files. |

**Deprecated/outdated:**
- `@app.on_event("startup"/"shutdown")`: Use `lifespan` instead
- `session.query()`: Use `select()` + `session.exec()`/`session.execute()`
- `setup.py` / `requirements.txt`: Use `pyproject.toml`

## Open Questions

1. **Relationship loading strategy for ScoreAction -> entries**
   - What we know: SQLModel `Relationship()` supports `back_populates`. Services need to access `action.entries` to find affected players.
   - What's unclear: Whether to use eager loading (`selectinload`) or lazy loading for the action->entries relationship in service functions. Lazy loading works but may cause N+1 queries in history display (Phase 2+).
   - Recommendation: Use lazy loading for Phase 1 (simpler, tests are direct). Revisit with `selectinload` in Phase 2 when history display needs all actions+entries in one query.

2. **Table naming: singular vs plural**
   - What we know: docs/plan.md uses plural (`games`, `players`, `score_actions`, `score_entries`). SQLModel defaults to the class name lowercased (`game`, `player`).
   - What's unclear: Whether to follow SQLModel default or override with `__tablename__`.
   - Recommendation: Use `__tablename__` to match plan.md explicitly (e.g., `__tablename__ = "game"` for singular, or `__tablename__ = "games"` for plural). Pick one convention and be consistent. The plan.md SQL uses plural, but the Python class names are singular -- either works as long as it is intentional. Suggest singular to match SQLModel convention.

3. **Transaction management in services**
   - What we know: Services call `session.commit()` at the end of each operation.
   - What's unclear: Should services commit, or should the caller (route handler) commit? Committing in services is simpler but means services cannot be composed (calling two services in sequence produces two commits, not one transaction).
   - Recommendation: Services commit for Phase 1 (no composition needed). If Phase 2 needs composed service calls, refactor to have services `flush()` and let routes `commit()`.

## Sources

### Primary (HIGH confidence)
- Context7: `/websites/sqlmodel_tiangolo` -- models, relationships, Field options, session management
- Context7: `/websites/alembic_sqlalchemy` -- batch mode, naming conventions, env.py configuration
- Context7: `/websites/fastapi_tiangolo` -- lifespan, session dependency, testing patterns
- SQLAlchemy SQLite dialect docs (https://docs.sqlalchemy.org/en/20/dialects/sqlite.html) -- pragma event listener pattern
- Alembic batch migrations docs (https://alembic.sqlalchemy.org/en/latest/batch.html) -- render_as_batch, constraint naming
- Alembic naming conventions docs (https://alembic.sqlalchemy.org/en/latest/naming.html) -- naming_convention dict
- FastAPI lifespan events docs (https://fastapi.tiangolo.com/advanced/events/) -- asynccontextmanager pattern
- SQLModel testing tutorial (https://sqlmodel.tiangolo.com/tutorial/fastapi/tests/) -- StaticPool, session fixture
- FastAPI SQL databases tutorial (https://fastapi.tiangolo.com/tutorial/sql-databases/) -- SessionDep pattern
- FastAPI full-stack template env.py (https://github.com/fastapi/full-stack-fastapi-template/blob/master/backend/app/alembic/env.py) -- target_metadata = SQLModel.metadata

### Secondary (MEDIUM confidence)
- SQLModel GitHub issue #82 (https://github.com/fastapi/sqlmodel/issues/82) -- UniqueConstraint via __table_args__
- SQLModel GitHub issue #292 (https://github.com/fastapi/sqlmodel/issues/292) -- CheckConstraint via __table_args__
- SQLModel + Alembic common issues (https://blog.thornewolf.com/alembic-migrations-with-sqlmodel-micro-tutorial/) -- model import order
- SQLModel + Alembic user_module_prefix (https://github.com/fastapi/sqlmodel/discussions/901) -- sqlmodel.sql.sqltypes

### Tertiary (LOW confidence)
- None -- all findings verified with primary or secondary sources.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all versions verified via PyPI, patterns from official docs and Context7
- Architecture: HIGH -- patterns from SQLModel/FastAPI/Alembic official docs and full-stack template
- Pitfalls: HIGH -- all three critical pitfalls verified with official documentation
- Code examples: HIGH -- derived from Context7 docs, verified against official tutorials

**Research date:** 2026-05-01
**Valid until:** 2026-06-01 (stable stack, 30-day validity)
