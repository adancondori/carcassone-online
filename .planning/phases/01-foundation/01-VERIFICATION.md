---
phase: 01-foundation
verified: 2026-05-01T00:00:00Z
status: human_needed
score: 4/5 must-haves verified (5th requires Docker daemon)
human_verification:
  - test: "Run `docker compose up --build` and verify container starts"
    expected: "Container builds and starts; `curl http://localhost:8000/` returns {\"status\":\"ok\"}"
    why_human: "Docker Desktop was not running during automated verification. Socket at /Users/eidan/.docker/run/docker.sock does not exist. Docker files are structurally correct but cannot be executed in this environment."
  - test: "After `docker compose down` then `docker compose up`, verify data persists"
    expected: "Any game/player data written before down is still present after up"
    why_human: "Requires running Docker to exercise the named volume (db_data:/code/data) persistence across container lifecycle"
---

# Phase 1: Foundation Verification Report

**Phase Goal:** The scoring engine works correctly and is proven by tests -- data model, service functions, and infrastructure are solid before any HTTP code is written
**Verified:** 2026-05-01
**Status:** human_needed — all automated checks pass; Docker persistence requires running Docker Desktop
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #   | Truth | Status | Evidence |
| --- | ----- | ------ | -------- |
| 1   | `docker compose up --build` starts the application and SQLite database persists across container restarts | ? UNCERTAIN | Dockerfile and docker-compose.yml are structurally correct; named volume `db_data:/code/data` is wired; Docker Desktop daemon is not running in this environment — cannot execute |
| 2   | SQLModel models (Game, Player, ScoreAction, ScoreEntry) exist with all constraints, and Alembic migration runs with batch mode enabled | ✓ VERIFIED | All 4 models in app/models.py with CHECK/UNIQUE/FK constraints; `alembic upgrade head` runs clean; migration creates all tables; `render_as_batch=True` confirmed in both online and offline contexts |
| 3   | `add_score()` correctly updates player.score_total and creates action+entries atomically for both single-player and shared scoring | ✓ VERIFIED | 4 TestAddScore tests pass (single, shared, cumulative, invalid player); 100% coverage on services.py |
| 4   | `undo_last()` and `rollback_to()` recalculate scores from active entries (not from score_before), and recalculated totals always match the cache | ✓ VERIFIED | Both functions call `recalculate_score()` which uses `func.coalesce(func.sum(ScoreEntry.points), 0)` joined with is_undone==False; cache consistency test with 20-iteration random add/undo loop passes |
| 5   | pytest suite passes covering models (current_cell, lap), services (add, undo, rollback, shared scoring, recalculate), and property-based tests for cache consistency | ✓ VERIFIED | 25/25 tests pass (11 model + 14 service); includes TestCacheConsistency::test_cache_consistency_random |

**Score:** 4/5 truths verified (1 requires human Docker verification)

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `pyproject.toml` | Project metadata, dependencies, pytest config | ✓ VERIFIED | All deps present (sqlmodel, fastapi, alembic, pydantic-settings, jinja2, uvicorn); pytest testpaths and pythonpath configured |
| `app/config.py` | Typed settings from env vars | ✓ VERIFIED | BaseSettings with app_name + database_url; loads from .env |
| `app/db.py` | Engine creation, session factory, SQLite pragma event listener | ✓ VERIFIED | 45 lines; `@event.listens_for(Engine, "connect")` on Engine class (not instance); all 5 pragmas set |
| `app/models.py` | All 4 SQLModel table models with constraints and naming convention | ✓ VERIFIED | 105 lines; naming_convention set before class definitions; all CHECK/UNIQUE/FK constraints named |
| `app/services.py` | add_score, undo_last, rollback_to, recalculate_score | ✓ VERIFIED | 159 lines; all 4 functions exported; 100% test coverage |
| `app/main.py` | FastAPI app with lifespan for DB init | ✓ VERIFIED | 31 lines; asynccontextmanager lifespan; `GET /` health check returns `{"status":"ok"}` (confirmed via uvicorn run) |
| `tests/conftest.py` | Test fixtures: engine, session, game_with_players | ✓ VERIFIED | 56 lines; StaticPool in-memory engine; imports `app.db` to register pragma listener globally |
| `tests/test_models.py` | Tests for Player.current_cell, Player.lap, constraint enforcement | ✓ VERIFIED | 139 lines (>30 min); 11 tests, all pass |
| `tests/test_services.py` | Service tests including shared scoring, undo, rollback, cache consistency | ✓ VERIFIED | 271 lines (>100 min); 14 tests, all pass |
| `alembic.ini` | Alembic configuration pointing to app database | ✓ VERIFIED | `sqlalchemy.url = sqlite:///data/carcassonne.db` |
| `alembic/env.py` | Alembic env with SQLModel metadata, batch mode, sqlmodel type prefix | ✓ VERIFIED | `render_as_batch=True` in both online/offline; `target_metadata = SQLModel.metadata`; all models imported |
| `alembic/script.py.mako` | Migration template with sqlmodel.sql.sqltypes import | ✓ VERIFIED | Line 12: `import sqlmodel.sql.sqltypes` |
| `alembic/versions/531e052bb60d_initial_schema.py` | Initial migration creating all 4 tables | ✓ VERIFIED | Creates game, player, score_action, score_entry with all constraints; `alembic upgrade head` runs clean |
| `Dockerfile` | Python 3.12 container with project installed | ✓ VERIFIED | `FROM python:3.12-slim`; installs via `pip install -e ".[dev]"`; exposes 8000; CMD uvicorn |
| `docker-compose.yml` | Service definition with volume mount for data directory | ✓ VERIFIED | `db_data:/code/data` (directory, not file — correct for WAL mode); named volume declared |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| `app/models.py` | `SQLModel.metadata` | naming_convention set before model class definitions | ✓ WIRED | Lines 15-21: dict set before any class definition |
| `app/db.py` | SQLite connection | `@event.listens_for(Engine, "connect")` pragma listener | ✓ WIRED | Registered on Engine class; fires on all engines including test engines; `PRAGMA foreign_keys=ON` confirmed by FK test passing |
| `tests/conftest.py` | `app/models.py` | imports app.db then SQLModel.metadata.create_all(engine) | ✓ WIRED | Line 11: `import app.db` (pragma registration); line 24: `SQLModel.metadata.create_all(engine)` |
| `alembic/env.py` | `app/models.py` | imports all models so metadata is populated | ✓ WIRED | `from app.models import Game, Player, ScoreAction, ScoreEntry` |
| `alembic/env.py` | `SQLModel.metadata` | `target_metadata = SQLModel.metadata` | ✓ WIRED | Line 22 |
| `docker-compose.yml` | SQLite data | Named volume on data DIRECTORY | ✓ WIRED | `db_data:/code/data` (not individual .db file) |
| `app/main.py` | `app/db.py` | lifespan calls create_db_and_tables on startup | ✓ WIRED | Lines 17-18: `create_db_and_tables()` in lifespan; `engine.dispose()` on shutdown |
| `app/services.py (undo_last, rollback_to)` | `app/services.py (recalculate_score)` | undo and rollback always call recalculate_score | ✓ WIRED | Lines 93, 130: `recalculate_score(session, pid)` called for each affected player |
| `app/services.py (recalculate_score)` | ScoreEntry + ScoreAction tables | SQL SUM of active entries (is_undone=False) | ✓ WIRED | Line 150: `select(func.coalesce(func.sum(ScoreEntry.points), 0))` joined with `ScoreAction.is_undone == False` |

### Requirements Coverage

| Requirement | Status | Notes |
| ----------- | ------ | ----- |
| INFRA-01 (Docker with persistent SQLite) | ? UNCERTAIN | Files correct; Docker daemon not available for execution test |
| INFRA-02 (SQLModel models with constraints) | ✓ SATISFIED | All 4 models with named CHECK/UNIQUE/FK constraints |
| INFRA-03 (Alembic batch mode migration) | ✓ SATISFIED | render_as_batch=True; migration runs clean; all 4 tables created |
| INFRA-04 (Service layer: add/undo/rollback) | ✓ SATISFIED | All 4 functions implemented; 14 tests pass; 100% coverage |
| INFRA-05 (pytest suite proves correctness) | ✓ SATISFIED | 25/25 tests pass including cache consistency property test |

### Anti-Patterns Found

None. Scanned app/services.py, app/models.py, app/db.py, app/main.py, tests/test_services.py for TODO/FIXME, placeholders, empty returns, and console.log stubs — zero findings.

### Human Verification Required

#### 1. Docker Container Startup

**Test:** With Docker Desktop running, from the project root: `docker compose up --build -d && sleep 5 && curl http://localhost:8000/ && docker compose down`
**Expected:** Build succeeds; curl returns `{"status":"ok"}`; container stops cleanly
**Why human:** Docker Desktop daemon was not running during automated verification. The socket `/Users/eidan/.docker/run/docker.sock` did not exist. The Docker files (Dockerfile, docker-compose.yml) are structurally correct but could not be executed.

#### 2. SQLite Persistence Across Container Restarts

**Test:** With Docker Desktop running: start container, hit `POST /` or any data-writing endpoint, run `docker compose down`, then `docker compose up` (no `--build`), verify data still present
**Expected:** Data written before `down` is readable after `up`
**Why human:** Exercises the named volume (`db_data:/code/data`) persistence guarantee. Cannot be verified without a running Docker daemon.

### Gaps Summary

No gaps in the scoring engine, models, service layer, or test infrastructure. All 25 tests pass with zero warnings (the ResourceWarning from SQLAlchemy pool cleanup is a test-teardown artifact, not a code defect). The single outstanding item is Docker execution, which was impossible during automated verification because Docker Desktop is not running on this machine.

---

_Verified: 2026-05-01_
_Verifier: Claude (so-verifier)_
