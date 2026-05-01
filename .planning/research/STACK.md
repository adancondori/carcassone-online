# Technology Stack

**Project:** Carcassonne Scoreboard
**Researched:** 2026-05-01
**Overall Confidence:** HIGH (all technologies verified via PyPI/GitHub releases, multiple sources cross-referenced)

## Recommended Stack

### Runtime & Language

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Python | 3.13.x | Runtime | Latest stable with full ecosystem support. All dependencies (FastAPI, SQLModel, Alembic) support 3.13. Use 3.13, not 3.14 (too new, dependency gaps). Not 3.12 (entering maintenance-only phase). |
| Docker base image | `python:3.13-slim` | Container base | Debian Bookworm-based, ~50MB. Slim variant drops build tools we don't need. Not Alpine (musl libc causes cryptic C extension issues with SQLAlchemy/pydantic). |

### Backend Framework

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| FastAPI | ~=0.136.1 | Web framework | Async-native, type-safe, Jinja2 template support built in, HTMX-friendly (returns HTML fragments). Same author as SQLModel -- tight integration. Pin `~=0.136.1` (compatible release) because FastAPI is 0.x semver and minor bumps can break. |
| Uvicorn | ~=0.46.0 | ASGI server | Default FastAPI server. Install with `uvicorn[standard]` to get uvloop + httptools for production performance. Use `--reload` in dev only. |
| Pydantic | >=2.7 (transitive) | Validation | Pulled in by FastAPI. Do not pin separately -- let FastAPI manage the constraint. Pydantic v2 is required (v1 support deprecated in FastAPI). |
| Starlette | (transitive) | ASGI toolkit | Pulled in by FastAPI. Provides `Jinja2Templates`, `StaticFiles`, `HTMLResponse`. Do not pin separately. |

### Database

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| SQLite | 3.x (system) | Database | Zero config, no extra container, single-file. A Carcassonne game produces ~100 rows. SQLite handles this trivially. Ships with Python stdlib (`sqlite3`). WAL mode for safe concurrent reads during HTMX partial fetches. |
| SQLModel | ~=0.0.38 | ORM | Single class = SQLAlchemy model + Pydantic schema. Eliminates model/schema duplication. Built by FastAPI's author for exactly this use case. Sits on SQLAlchemy 2.0 under the hood -- drop down to raw SA when needed. |
| SQLAlchemy | >=2.0 (transitive) | SQL toolkit | Pulled in by SQLModel. Provides the engine, session, connection pool, and DDL that SQLModel wraps. Do not pin separately. |
| Alembic | ~=1.18.4 | Migrations | Standard SQLAlchemy migration tool. Autogenerate from SQLModel models. Version 1.18+ uses batched reflection (O(1) queries). |

### Frontend (Server-Rendered)

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Jinja2 | >=3.1.6 (transitive) | Templates | Pulled in by Starlette (via FastAPI). Server-side HTML rendering. Template inheritance (`base.html` -> page templates), macros for components. Do not install separately -- already a FastAPI dependency. |
| HTMX | 2.0.10 (CDN) | Interactivity | Server-driven partial updates via HTML fragments. No build step, no npm, no bundler. Include via CDN `<script>` tag. Pin exact version in the URL: `https://unpkg.com/htmx.org@2.0.10/dist/htmx.min.js`. Stick with 2.x stable -- HTMX 4.0 is alpha, not production-ready until 2027. |
| Vanilla JavaScript | ES2022+ | SVG board, animations | Only for board token positioning, step-by-step animation, and stacking logic. No framework needed -- these are ~100 lines of DOM manipulation. ES modules, no transpilation. |
| CSS | Custom (no framework) | Styling | Mobile-first responsive layout with CSS Grid/Flexbox. No Tailwind/Bootstrap -- the UI is a single dashboard page with a fixed layout. A framework would add weight for zero benefit. CSS custom properties for the Carcassonne blue/gold palette. |

### Configuration & Settings

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| pydantic-settings | ~=2.14.0 | Config from env | Loads `.env` and environment variables into typed Pydantic models. Standard FastAPI pattern. Replaces manual `os.getenv()` with validated, typed settings. |
| python-dotenv | >=1.0 (transitive) | .env file loading | Pulled in by pydantic-settings. Reads `.env` file in development. |

### Testing

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| pytest | ~=9.0.3 | Test runner | Industry standard. Fixtures, parametrize, clear assertion introspection. |
| pytest-cov | ~=7.1.0 | Coverage | Measures code coverage. Target 90%+ on services layer. |
| httpx | >=0.27 | HTTP test client | FastAPI's recommended test client (`TestClient` uses httpx internally). Needed for endpoint tests. |
| pytest-asyncio | >=0.24 | Async test support | For testing async endpoints and database operations if using async sessions. |

### Infrastructure

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Docker | 27.x | Containerization | Reproducible environment. Single `Dockerfile` with multi-stage not needed (app is tiny). |
| Docker Compose | 2.x (v2 spec) | Orchestration | Single-service compose for dev (`docker compose up`). Volume for SQLite data persistence. Bind-mount source for `--reload` in dev. |

### Build & Package Management

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| pyproject.toml | PEP 621 | Project metadata | Single source of truth for dependencies, project metadata, tool config (pytest, coverage). No `setup.py`, no `requirements.txt`. |
| pip | latest | Installer | `pip install -e ".[dev]"` for editable install with dev extras. No Poetry, no PDM -- pip is sufficient for a single-package project with no complex dependency resolution needs. |

## SQLite Pragmas (Critical Configuration)

These pragmas must be set on every connection for correctness and performance:

```python
# In db.py, on engine creation or connect event
PRAGMA journal_mode=WAL;       # Write-Ahead Logging: concurrent reads during writes
PRAGMA synchronous=NORMAL;     # Safe with WAL, faster than FULL
PRAGMA busy_timeout=5000;      # Wait 5s on lock instead of failing immediately
PRAGMA foreign_keys=ON;        # SQLite does NOT enforce FKs by default!
PRAGMA cache_size=-8000;       # 8MB page cache (negative = KB)
```

**CRITICAL: `PRAGMA foreign_keys=ON`** -- SQLite ignores foreign key constraints by default. Without this, the `score_entries.action_id REFERENCES score_actions(id)` constraint is decorative. Must be set per-connection (not persisted).

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| ORM | SQLModel | SQLAlchemy 2.0 (direct) | SQLModel eliminates model/schema duplication for FastAPI. SA is there under the hood when needed. No reason to use raw SA for a simple 4-table schema. |
| ORM | SQLModel | Tortoise ORM | Async-first ORM, but FastAPI+SQLModel is the canonical pairing. Tortoise has weaker ecosystem and fewer resources. |
| Database | SQLite | PostgreSQL | Overkill. Adds a container, connection management, and ops burden for a single-user app with ~100 rows per game. SQLite migration path to PG exists via connection string swap if ever needed. |
| Database | SQLite | MySQL | Same as PostgreSQL argument, plus less SQLAlchemy ecosystem support than PG. |
| Frontend | HTMX 2.x | React/Vue/Svelte SPA | Adds npm, bundler, build step, client-side state management, API serialization layer. HTMX returns HTML fragments -- the server IS the single source of truth, which aligns perfectly with the event-sourcing data model. |
| Frontend | HTMX 2.x | HTMX 4.0 alpha | 4.0 is alpha as of May 2026. Beta expected mid-2026, stable early 2027. Use 2.x which is stable and will receive security fixes. |
| Frontend helper | None (vanilla FastAPI) | fasthx | Adds decorator abstraction over FastAPI's built-in `Jinja2Templates`. For a 3-route web app, the abstraction isn't justified. Revisit if route count grows past 15+. |
| Frontend helper | None (vanilla FastAPI) | fastapi-htmx | Same reasoning as fasthx. The standard `TemplateResponse` + checking `HX-Request` header is ~2 lines of code. |
| CSS | Custom CSS | Tailwind CSS | Requires npm + build step + PostCSS pipeline. The app has one page with a fixed layout. Custom CSS is under 200 lines. |
| CSS | Custom CSS | Bootstrap / DaisyUI | Adds 50-150KB of unused CSS for a single-page app. The Carcassonne color palette is custom anyway. |
| ASGI Server | Uvicorn | Gunicorn + Uvicorn workers | Gunicorn adds process management for multi-worker deployments. This is a single-user app on a LAN -- one Uvicorn worker is sufficient. |
| Package manager | pip | Poetry | Poetry adds lock file management and virtual environment abstraction. For a single-package project installed in Docker, pip + pyproject.toml is simpler and has zero learning curve. |
| Package manager | pip | PDM / uv | uv is fast but adds another tool to learn. pip is universally available in the Docker image. For ~15 dependencies, pip install speed is irrelevant. |
| Testing | httpx | requests | FastAPI's `TestClient` is built on httpx. Using requests would add a redundant dependency. |

## What NOT to Use (Anti-Recommendations)

### Do NOT add npm or any JS build tooling
The entire frontend is Jinja2 templates + one `<script>` tag for HTMX + vanilla JS for the SVG board. There is no JSX, no TypeScript, no bundling. Adding npm creates a second dependency tree, a second build step, and a second category of build failures -- for zero user-facing benefit.

### Do NOT use async SQLAlchemy / aiosqlite
SQLite queries on this data volume (single-digit milliseconds) complete faster than the async context-switch overhead. Async DB access adds complexity (async session management, greenlet dependency) with negative performance benefit for SQLite. Use synchronous sessions. FastAPI handles sync route functions fine via threadpool.

### Do NOT use an auto-migration tool (e.g., `create_all()` in production)
Use Alembic for all schema changes. `SQLModel.metadata.create_all()` is fine for tests (in-memory DB) but skips migration history, making rollbacks impossible and collaborative development painful. Alembic autogenerate catches schema drift.

### Do NOT add Redis or any caching layer
The entire game state is 4 tables with ~100 rows. SQLite serves this from OS page cache in <1ms. Adding Redis creates a consistency problem (cache invalidation) that does not need to exist.

### Do NOT use WebSockets for real-time updates
This is a single-device app used by one person at a game table. HTMX's polling (`hx-trigger="every 2s"`) or simple request-response is sufficient. WebSockets add connection lifecycle management and reconnection logic for a use case that doesn't exist.

### Do NOT use Celery or any task queue
There are no background tasks. Scoring is synchronous: write to DB, return updated HTML fragment. A task queue adds a broker (Redis/RabbitMQ), a worker process, and result backend -- all for nothing.

## Installation

```toml
# pyproject.toml
[project]
name = "carcassonne-scoreboard"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = [
    "fastapi~=0.136.1",
    "uvicorn[standard]~=0.46.0",
    "sqlmodel~=0.0.38",
    "alembic~=1.18.4",
    "pydantic-settings~=2.14.0",
    "python-multipart>=0.0.18",
]

[project.optional-dependencies]
dev = [
    "pytest~=9.0.3",
    "pytest-cov~=7.1.0",
    "httpx>=0.27",
]
```

```bash
# In Dockerfile
pip install -e ".[dev]"

# HTMX (no install -- CDN in base.html)
# <script src="https://unpkg.com/htmx.org@2.0.10/dist/htmx.min.js"></script>
```

## Dockerfile Reference

```dockerfile
FROM python:3.13-slim

WORKDIR /code

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install dependencies first (layer caching)
COPY pyproject.toml .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e ".[dev]"

COPY . .

EXPOSE 8000

# Use exec form for graceful shutdown
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

## Docker Compose Reference

```yaml
services:
  web:
    build: .
    container_name: carcassonne_web
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    ports:
      - "8000:8000"
    volumes:
      - .:/code          # Bind mount for --reload in dev
      - db_data:/code/data  # Named volume for SQLite persistence
    env_file:
      - .env

volumes:
  db_data:
```

## Sources

- [FastAPI 0.136.1 on PyPI](https://pypi.org/project/fastapi/) -- verified latest version April 23, 2026
- [SQLModel 0.0.38 on PyPI](https://pypi.org/project/sqlmodel/) -- verified latest version April 2, 2026
- [Alembic 1.18.4 documentation](https://alembic.sqlalchemy.org/) -- verified latest version February 10, 2026
- [HTMX 2.0.10 releases](https://github.com/bigskysoftware/htmx/releases) -- stable, 4.0 alpha not recommended for production
- [Uvicorn 0.46.0 on PyPI](https://pypi.org/project/uvicorn/) -- verified latest version April 23, 2026
- [pytest 9.0.3 on PyPI](https://pypi.org/project/pytest/) -- verified latest version April 7, 2026
- [pytest-cov 7.1.0 on PyPI](https://pypi.org/project/pytest-cov/) -- verified latest version March 21, 2026
- [pydantic-settings 2.14.0 on PyPI](https://pypi.org/project/pydantic-settings/) -- verified latest version April 20, 2026
- [Jinja2 3.1.6 on PyPI](https://pypi.org/project/Jinja2/) -- transitive via FastAPI/Starlette, March 5, 2025
- [Python 3.13 Docker image recommendations](https://pythonspeed.com/articles/base-image-python-docker-images/) -- February 2026
- [FastAPI Docker deployment best practices](https://fastapi.tiangolo.com/deployment/docker/) -- official docs
- [FastAPI + HTMX patterns](https://blakecrosley.com/guides/fastapi-htmx) -- community reference
- [FastAPI + Jinja2 + HTMX server-rendered dashboards](https://www.johal.in/fastapi-templating-jinja2-server-rendered-ml-dashboards-with-htmx-2025/) -- pattern validation
