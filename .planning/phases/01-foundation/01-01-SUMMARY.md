---
phase: 01-foundation
plan: 01
subsystem: database
tags: [sqlmodel, sqlalchemy, sqlite, pydantic-settings, pytest]

# Dependency graph
requires: []
provides:
  - "SQLModel models: Game, Player, ScoreAction, ScoreEntry with full constraints"
  - "SQLite pragma event listener (WAL, FK enforcement, busy_timeout)"
  - "Typed config via pydantic-settings"
  - "pytest infrastructure with in-memory SQLite and StaticPool"
affects: [01-02, 01-03, 02-web-ui]

# Tech tracking
tech-stack:
  added: [sqlmodel, sqlalchemy, fastapi, uvicorn, pydantic-settings, alembic, jinja2, pytest, pytest-cov]
  patterns:
    - "naming_convention set before model class definitions for Alembic batch mode"
    - "@event.listens_for(Engine, 'connect') for SQLite pragmas on all engines"
    - "StaticPool in-memory SQLite for fast isolated tests"

key-files:
  created:
    - pyproject.toml
    - app/__init__.py
    - app/config.py
    - app/db.py
    - app/models.py
    - tests/__init__.py
    - tests/conftest.py
    - tests/test_models.py
    - .gitignore
  modified: []

key-decisions:
  - "Use @event.listens_for on Engine class (not instance) so pragma listener fires on all engines including test engines"
  - "Use datetime.now(UTC) instead of deprecated datetime.utcnow() for Python 3.12+ compatibility"
  - "Hatchling build backend with explicit packages config for editable installs"

patterns-established:
  - "naming_convention before models: Alembic batch mode requires all constraints to be named"
  - "Engine-class pragma listener: every SQLite connection gets WAL, FK, busy_timeout"
  - "conftest imports app.db to register pragma listener globally for all test engines"

# Metrics
duration: 4min
completed: 2026-05-01
---

# Phase 1 Plan 1: Data Models & Database Layer Summary

**SQLModel models (Game, Player, ScoreAction, ScoreEntry) with CHECK/UNIQUE/FK constraints, SQLite pragma event listener, and 11 passing model tests**

## Performance

- **Duration:** 4 min
- **Started:** 2026-05-01T23:21:18Z
- **Completed:** 2026-05-01T23:25:15Z
- **Tasks:** 2
- **Files modified:** 9

## Accomplishments
- Project structure with pyproject.toml, typed config, and all core dependencies
- 4 SQLModel table models with explicit naming convention, CHECK constraints, UNIQUE constraints, and foreign keys
- Player.current_cell and Player.lap computed properties for board position tracking
- SQLite pragma event listener enforcing WAL mode, FK constraints, and performance tuning on every connection
- 11 model tests covering computed properties, constraint enforcement, and FK enforcement

## Task Commits

Each task was committed atomically:

1. **Task 1: Create project structure, dependencies, config, and database layer** - `46f7e6e` (feat)
2. **Task 2: Create SQLModel models with constraints and model tests** - `0423daa` (feat)

## Files Created/Modified
- `pyproject.toml` - Project metadata, dependencies (sqlmodel, fastapi, alembic, etc.), pytest config
- `.gitignore` - Python project gitignore (venv, pycache, sqlite, coverage)
- `app/__init__.py` - Package marker
- `app/config.py` - Typed Settings from .env via pydantic-settings BaseSettings
- `app/db.py` - Engine creation, SQLite pragma event listener, session factory
- `app/models.py` - Game, Player, ScoreAction, ScoreEntry models with constraints and naming convention
- `tests/__init__.py` - Package marker
- `tests/conftest.py` - Test fixtures: engine (in-memory StaticPool), session, game_with_players
- `tests/test_models.py` - 11 tests for properties, CHECK, UNIQUE, and FK enforcement

## Decisions Made
- Used `@event.listens_for(Engine, "connect")` on the Engine **class** instead of a specific instance, so pragma listener fires on all engines including test engines -- without this, test FK enforcement would silently pass
- Replaced deprecated `datetime.utcnow()` with `datetime.now(UTC)` for Python 3.12+ forward compatibility
- Added Hatchling `[tool.hatch.build.targets.wheel] packages = ["app"]` to fix editable install metadata generation

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Pragma listener bound to instance, not Engine class**
- **Found during:** Task 2 (test_foreign_key_enforcement failed)
- **Issue:** `event.listen(engine, "connect", set_sqlite_pragma)` only registered on the app's engine instance. Test engines created via `create_engine("sqlite://")` did not inherit the listener, so `PRAGMA foreign_keys=ON` was never set and FK violations were silently accepted.
- **Fix:** Changed to `@event.listens_for(Engine, "connect")` decorator on the function, which registers on all Engine instances.
- **Files modified:** app/db.py
- **Verification:** test_foreign_key_enforcement now passes (IntegrityError raised for nonexistent game_id)
- **Committed in:** 0423daa

**2. [Rule 1 - Bug] Deprecated datetime.utcnow() causing 20 warnings**
- **Found during:** Task 2 (pytest warnings output)
- **Issue:** `datetime.utcnow()` is deprecated in Python 3.12+ and scheduled for removal. Generated 20 deprecation warnings per test run.
- **Fix:** Changed all `default_factory=datetime.utcnow` to `default_factory=lambda: datetime.now(UTC)` across all 3 models with created_at fields.
- **Files modified:** app/models.py
- **Verification:** pytest runs with zero warnings
- **Committed in:** 0423daa

**3. [Rule 3 - Blocking] Missing hatchling wheel package config**
- **Found during:** Task 1 (pip install -e ".[dev]" failed)
- **Issue:** Hatchling build backend could not auto-discover the `app` package, failing with "At least one file selection option must be defined"
- **Fix:** Added `[tool.hatch.build.targets.wheel] packages = ["app"]` to pyproject.toml
- **Files modified:** pyproject.toml
- **Verification:** `pip install -e ".[dev]"` succeeds
- **Committed in:** 46f7e6e

---

**Total deviations:** 3 auto-fixed (2 bugs, 1 blocking)
**Impact on plan:** All auto-fixes necessary for correctness and build success. No scope creep.

## Issues Encountered
None beyond the auto-fixed deviations above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All 4 models defined and tested, ready for service layer (01-02)
- Database layer with pragma enforcement proven by FK test
- pytest infrastructure ready for service-level tests
- No blockers for subsequent plans

---
*Phase: 01-foundation*
*Completed: 2026-05-01*
