# Architecture Patterns

**Domain:** Board game scoring web application (Carcassonne scoreboard)
**Researched:** 2026-05-01
**Overall confidence:** HIGH (well-established stack, patterns verified against official docs and plan.md)

## Recommended Architecture

Server-rendered monolith with HTMX-driven partial updates. No SPA, no client-side state management, no build toolchain. The server owns all state; the browser renders HTML fragments it receives.

```
┌─────────────────────────────────────────────────────────┐
│                      BROWSER                            │
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  Jinja2 HTML │  │  HTMX        │  │  Vanilla JS  │  │
│  │  (full pages │  │  (partial    │  │  (SVG board,  │  │
│  │   + fragments│  │   swaps via  │  │   animations, │  │
│  │   from       │  │   hx-get/    │  │   stacking,   │  │
│  │   server)    │  │   hx-post)   │  │   controls)   │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  │
│         │                 │                 │           │
└─────────┼─────────────────┼─────────────────┼───────────┘
          │ full page       │ HTML            │ (reads
          │ loads           │ fragments       │  from DOM,
          │                 │                 │  no own
          │                 │                 │  API calls)
          ▼                 ▼                 │
┌─────────────────────────────────────────────┼───────────┐
│                  FastAPI SERVER              │           │
│                                             │           │
│  ┌──────────────────────────────────────────┴────────┐  │
│  │  Web Routes (app/web/routes.py)                   │  │
│  │  ─ GET  /                     → redirect or home  │  │
│  │  ─ GET  /games/new            → setup.html (full) │  │
│  │  ─ GET  /games/{id}           → dashboard (full)  │  │
│  │  ─ POST /games/{id}/score     → HTMX fragments    │  │
│  │  ─ POST /games/{id}/undo      → HTMX fragments    │  │
│  │  ─ POST /games/{id}/rollback  → HTMX fragments    │  │
│  │  ─ GET  /games/{id}/history   → HTMX fragment     │  │
│  └──────────────────────┬───────────────────────────┘  │
│                         │                               │
│  ┌──────────────────────┴───────────────────────────┐  │
│  │  Service Layer (app/services.py)                  │  │
│  │  ─ add_score()          (atomic, multi-player)    │  │
│  │  ─ undo_last()          (recalc from entries)     │  │
│  │  ─ rollback_to()        (recalc from entries)     │  │
│  │  ─ recalculate_score()  (source of truth)         │  │
│  │  ─ create_game()                                  │  │
│  │  ─ add_player()                                   │  │
│  │  ─ transition_state()                             │  │
│  └──────────────────────┬───────────────────────────┘  │
│                         │                               │
│  ┌──────────────────────┴───────────────────────────┐  │
│  │  Data Layer                                       │  │
│  │  ─ SQLModel models (app/models.py)                │  │
│  │  ─ SQLite via SQLAlchemy engine (app/db.py)       │  │
│  │  ─ Alembic migrations (alembic/)                  │  │
│  └──────────────────────────────────────────────────┘  │
│                                                         │
└─────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────┐
│  SQLite file         │
│  data/carcassonne.db │
└─────────────────────┘
```

### Component Boundaries

| Component | Responsibility | Communicates With | Technology |
|-----------|---------------|-------------------|------------|
| **Web Routes** | Accept HTTP requests, call services, render templates, return HTML (full pages or fragments) | Service Layer, Jinja2 Templates | FastAPI router, Jinja2 |
| **Service Layer** | All business logic: scoring, undo, rollback, recalculation, game state transitions | Data Layer (SQLModel session) | Pure Python, SQLModel queries |
| **Data Layer** | Schema definition, DB connection, session management, migrations | SQLite file | SQLModel, SQLAlchemy, Alembic |
| **Jinja2 Templates** | HTML generation for full pages and HTMX fragments | Receives context from Web Routes | Jinja2 |
| **HTMX (browser)** | Intercepts user actions, sends requests, swaps HTML fragments into DOM | Web Routes (via HTTP) | HTMX attributes in HTML |
| **Vanilla JS (browser)** | SVG board rendering, token animation, stacking offsets, control interactivity | DOM only (reads data attributes set by Jinja2) | Plain JavaScript |
| **Static Assets** | CSS, JS files, board image | Served by FastAPI static mount | Files on disk |

### Key Boundary Rule

**No API-only endpoints in the MVP.** Every route returns HTML -- either a full page or an HTML fragment for HTMX to swap. This eliminates the "two interfaces" problem (JSON API + template routes) and keeps the codebase small. If a JSON API is needed later (e.g., for a mobile app), it can be added as a separate router without modifying existing routes.

---

## Data Flow

### 1. Full Page Load (initial or hard navigation)

```
Browser                   FastAPI                    Service              DB
  │                         │                          │                   │
  │── GET /games/5 ────────>│                          │                   │
  │                         │── get_game_state(5) ────>│                   │
  │                         │                          │── SELECT games ──>│
  │                         │                          │── SELECT players ─>│
  │                         │                          │── SELECT actions ─>│
  │                         │                          │<── results ───────│
  │                         │<── GameState object ─────│                   │
  │                         │                          │                   │
  │                         │── render dashboard.html  │                   │
  │                         │   with full context       │                   │
  │<── complete HTML page ──│                          │                   │
  │                         │                          │                   │
  │ (HTMX + JS initialize) │                          │                   │
```

### 2. Score Action (HTMX partial update)

```
Browser                   FastAPI                    Service              DB
  │                         │                          │                   │
  │── POST /games/5/score ─>│                          │                   │
  │   (hx-post, form data)  │                          │                   │
  │   event_type, points,   │── add_score(5, [...]) ──>│                   │
  │   player_ids, note      │                          │── BEGIN TX ───────│
  │                         │                          │── INSERT action ──>│
  │                         │                          │── INSERT entries ─>│
  │                         │                          │── UPDATE players ─>│
  │                         │                          │── COMMIT ─────────│
  │                         │<── updated GameState ────│                   │
  │                         │                          │                   │
  │                         │── render fragments:      │                   │
  │                         │   scoretable.html        │                   │
  │                         │   board.html (tokens)    │                   │
  │                         │   history.html           │                   │
  │<── HTML fragments ──────│                          │                   │
  │                         │                          │                   │
  │ (HTMX swaps fragments   │                          │                   │
  │  into DOM via hx-swap)  │                          │                   │
  │ (JS animates token      │                          │                   │
  │  movement on board)     │                          │                   │
```

### 3. Undo (HTMX partial update)

```
Browser                   FastAPI                    Service              DB
  │                         │                          │                   │
  │── POST /games/5/undo ──>│                          │                   │
  │   (hx-post)             │── undo_last(5) ────────>│                   │
  │                         │                          │── BEGIN TX ───────│
  │                         │                          │── UPDATE action   │
  │                         │                          │   is_undone=true ─>│
  │                         │                          │── recalculate     │
  │                         │                          │   affected players>│
  │                         │                          │── COMMIT ─────────│
  │                         │<── updated GameState ────│                   │
  │                         │                          │                   │
  │                         │── render fragments:      │                   │
  │                         │   scoretable.html        │                   │
  │                         │   board.html (tokens)    │                   │
  │                         │   history.html           │                   │
  │<── HTML fragments ──────│                          │                   │
```

### HTMX Fragment Strategy

HTMX needs to know which parts of the page to update after a server action. The recommended pattern for this project:

**Multi-target swap using `hx-swap-oob` (Out of Band):**

After a scoring action, the server returns multiple HTML fragments in a single response. The primary target gets the main swap, and additional fragments use `hx-swap-oob="true"` to update other parts of the page simultaneously.

```html
<!-- Primary response: score table -->
<div id="score-table-body">
  <!-- updated score table rows -->
</div>

<!-- Out-of-band updates (included in same response) -->
<div id="board-tokens" hx-swap-oob="true">
  <!-- updated SVG tokens -->
</div>

<div id="history-list" hx-swap-oob="true">
  <!-- updated history -->
</div>
```

This means a single POST to `/games/{id}/score` returns all three updated fragments. No extra round-trips.

**Confidence:** HIGH -- `hx-swap-oob` is a core, well-documented HTMX feature specifically designed for this multi-region update pattern.

### SVG Board Data Flow

The SVG board is a special case. Token positions, stacking, and lap badges are best rendered server-side in Jinja2 (using the same CELLS coordinate array from the prototype). Animation of token movement is the one piece that requires client-side JS.

**Recommended approach:**
- Server renders the SVG `<g id="tokens-layer">` with all current token positions as a Jinja2 template
- HTMX swaps the tokens layer after score actions
- For animation: the client JS reads `data-prev-cell` and `data-new-cell` attributes from the swapped tokens, then runs the step-by-step animation before settling into final position
- The CELLS coordinate array lives in a static JS file and is also mirrored as a Python constant for server-side rendering

```
Server renders:  <g id="token-1" data-cell="23" data-prev-cell="15" ...>
JS on swap:      reads prev/new, animates through intermediate cells
JS on settle:    token is already at correct final position from server HTML
```

---

## Patterns to Follow

### Pattern 1: Service Layer Owns All Business Logic

**What:** All scoring, undo, rollback, state transitions, and validation live in `services.py`. Routes are thin -- they parse input, call a service function, and render a template.

**Why:** Testability. Services can be tested with a DB session alone, without HTTP. Routes only need integration tests.

**Example structure:**

```python
# app/web/routes.py -- thin route
@router.post("/games/{game_id}/score")
async def score_action(game_id: int, request: Request, session: Session = Depends(get_session)):
    form = await request.form()
    player_points = parse_score_form(form)  # extract [(player_id, points), ...]
    event_type = form["event_type"]
    description = form.get("description") or None

    action = add_score(session, game_id, player_points, event_type, description)
    game_state = get_game_state(session, game_id)

    return templates.TemplateResponse("fragments/score_update.html", {
        "request": request,
        "game": game_state,
        "last_action": action,
    })
```

```python
# app/services.py -- all logic here
def add_score(session, game_id, player_points, event_type, description=None):
    # validation, INSERT, UPDATE, all in one transaction
    ...
```

### Pattern 2: Template Fragments as First-Class Components

**What:** Jinja2 templates are split into full pages and fragments. Full pages `{% include %}` fragments. HTMX endpoints return only fragments.

**Why:** DRY -- the same fragment renders both in full page loads and in HTMX partial updates.

**Template structure:**

```
templates/
  base.html                    # <html>, <head>, CSS, HTMX script
  setup.html                   # full page: extends base
  dashboard.html               # full page: extends base, includes fragments
  fragments/
    score_table.html           # <tbody> rows -- used by dashboard and HTMX
    board_tokens.html          # <g id="tokens-layer"> -- used by dashboard and HTMX
    history.html               # <ul> items -- used by dashboard and HTMX
    controls.html              # scoring controls -- used by dashboard
    score_update.html          # multi-fragment response for HTMX (includes OOB swaps)
```

### Pattern 3: Event-Sourcing-Lite for Scoring

**What:** Score state is derived from an append-only log of actions. `player.score_total` is a materialized cache. On undo/rollback, the cache is rebuilt from active entries.

**Why:** Audit trail, atomic undo of multi-player actions, corruption-proof recalculation.

**Key invariant:** `player.score_total == SUM(points) FROM active entries WHERE player_id = X`

This is NOT full event sourcing (no event bus, no projections, no replay infrastructure). It is the minimum viable version: an ordered log of immutable-ish actions (only `is_undone` changes) with a derived cache.

### Pattern 4: Single Transaction Per User Action

**What:** Every user-visible operation (score, undo, rollback) executes in exactly one database transaction. The transaction includes all writes: action, entries, and player score updates.

**Why:** SQLite allows only one writer at a time. Keeping transactions short and atomic avoids locking issues and guarantees consistency.

### Pattern 5: Game State Object as Template Context

**What:** A `GameState` dataclass (or Pydantic model) aggregates everything a template needs: game metadata, players (sorted), actions with entries, current status. Routes build this once and pass it to templates.

**Why:** Templates should not run queries. The route gathers all data, the template renders it. This also makes the template context explicit and testable.

```python
@dataclass
class GameState:
    game: Game
    players: list[Player]          # sorted by score descending
    actions: list[ScoreAction]     # with entries loaded, reverse chronological
    status: str
```

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Client-Side State Duplication

**What:** Maintaining a JavaScript state object that mirrors server state (as the prototype does with `let state = {...}`).

**Why bad:** Two sources of truth. State drift between client and server. The prototype needs this because it is a standalone HTML file. The real app must not replicate this.

**Instead:** Server is the single source of truth. HTMX swaps bring fresh HTML from the server. The only client-side "state" should be ephemeral UI state (which players are selected in the scoring form, which point button is highlighted). This ephemeral state resets on each score submission, which is correct behavior.

### Anti-Pattern 2: Separate JSON API and HTML Routes

**What:** Building `/api/games/{id}/score` (returns JSON) AND `/games/{id}/score` (returns HTML) that both call the same service.

**Why bad:** Double the routes, double the maintenance, and the JSON API has no consumer in v1. YAGNI.

**Instead:** Routes return HTML only. If a JSON API is needed later, add it as a separate concern. The service layer is already decoupled from the response format.

### Anti-Pattern 3: Fat Templates with Logic

**What:** Putting scoring calculations, validation, or conditional business logic in Jinja2 templates.

**Why bad:** Untestable. Jinja2 templates should only contain presentation logic (loops, conditionals for display, formatting).

**Instead:** All derived values (current_cell, lap, ranking position) are computed in Python (model properties or service layer) and passed to templates as ready-to-render values.

### Anti-Pattern 4: Individual HTMX Requests Per Fragment

**What:** After scoring, making three separate HTMX requests to update the score table, board, and history individually.

**Why bad:** Three HTTP round-trips, three DB queries, potential visual inconsistency between fragments during the update window.

**Instead:** Single POST returns all fragments via `hx-swap-oob`. One request, one service call, one consistent state snapshot.

---

## Build Order Recommendations

Dependencies flow downward. Each layer must be built and tested before the layers above it can be meaningfully developed.

```
PHASE 1: Foundation (no UI)
├── 1a. Data Layer: models.py, db.py, Alembic initial migration
├── 1b. Service Layer: add_score, undo_last, recalculate_score
├── 1c. Tests: test_models.py, test_services.py (in-memory SQLite)
└── 1d. Docker: Dockerfile, docker-compose.yml, pyproject.toml

PHASE 2: Minimal Web UI
├── 2a. Jinja2 setup: base.html, template engine config in main.py
├── 2b. Setup page: create game, add players (full page, form POST)
├── 2c. Dashboard page: score table, basic controls (full page)
├── 2d. HTMX integration: score submission with fragment swap
├── 2e. Undo via HTMX
└── 2f. Tests: test_web.py (TestClient, HTML response assertions)

PHASE 3: History + Rollback
├── 3a. History fragment (rendered server-side, Jinja2)
├── 3b. Rollback service function + route
├── 3c. Undone actions visual treatment (strikethrough via CSS class)
└── 3d. Event type labels + optional notes

PHASE 4: SVG Board
├── 4a. Board fragment: server-rendered SVG tokens (Jinja2)
├── 4b. Static JS: CELLS coordinates, stacking offset
├── 4c. Token animation on HTMX swap (afterSwap event)
├── 4d. Lap badges
└── 4e. OOB swap: board updates alongside score table

PHASE 5: Game States + Final Scoring
├── 5a. State machine transitions (service layer)
├── 5b. Different controls for playing vs scoring states
├── 5c. Finished state: results screen
└── 5d. Type filtering (completed events in playing, final events in scoring)
```

### Build Order Rationale

1. **Data + Service first** because everything depends on correct scoring logic. These can be fully tested without any HTTP or HTML. The service layer is the heart of the application -- getting `add_score`, `undo_last`, and `recalculate_score` right with comprehensive tests is the highest-value first step.

2. **Minimal web UI second** because HTMX fragment swaps need working routes and templates. Building setup + dashboard + basic scoring gives an end-to-end vertical slice: create game, add players, score points, see results.

3. **History + rollback third** because they depend on the scoring system being solid but are UI extensions. Rollback is a more complex operation than undo and benefits from the scoring foundation being battle-tested first.

4. **SVG board fourth** because it is visually complex but functionally independent of scoring logic. It reads the same player data (score_total, current_cell, lap) that the score table already uses. The board is a rendering concern, not a data concern.

5. **Game states last** because the core scoring workflow (playing state) works without state transitions. Adding setup/scoring/finished states is an orchestration layer on top of already-working components.

### Critical Dependency Chain

```
models.py ──> services.py ──> web/routes.py ──> templates/
                                    │
                              ┌─────┴──────┐
                              │ fragments/  │
                              │ (HTMX)     │
                              └────────────┘
                                    │
                              ┌─────┴──────┐
                              │ static/js/  │
                              │ (SVG board) │
                              └────────────┘
```

- `models.py` has zero internal dependencies (only SQLModel)
- `services.py` depends only on models
- `web/routes.py` depends on services + templates
- Templates depend on the context shape (GameState)
- Static JS depends on DOM structure from templates + CELLS coordinates

### What Can Be Built in Parallel

If multiple contributors were working:
- **Service tests** and **Docker setup** can proceed simultaneously after models
- **Setup page** and **dashboard page** can proceed simultaneously after base template
- **SVG board JS** and **history fragment** can proceed simultaneously after basic HTMX works
- **CSS styling** can be refined at any point (the prototype CSS is nearly final)

---

## Scalability Considerations

This is a single-user, single-device application used at a game table. Scalability is not a real concern, but noting it for completeness:

| Concern | This Project (1 user) | Notes |
|---------|----------------------|-------|
| DB writes | ~1 write per minute (scoring) | SQLite handles this trivially |
| DB reads | ~1 read per user action | Single query per fragment render |
| Concurrent access | None (single device) | SQLite WAL mode if ever needed |
| Data volume | ~100-200 rows per game | Entire DB fits in memory |
| Response size | ~2-5 KB per HTMX fragment | Negligible |

**If multi-device support were ever needed:** Replace SQLite with PostgreSQL (connection string change), add WebSocket or SSE for push updates to other devices. The architecture supports this because the server already owns all state.

---

## Sources

- **FastAPI templates documentation:** Jinja2 integration is built-in via `fastapi.templating.Jinja2Templates`. Confidence: HIGH (stable, well-documented feature since FastAPI 0.60+).
- **HTMX `hx-swap-oob`:** Core feature for multi-target updates in a single response. Documented at htmx.org/attributes/hx-swap-oob/. Confidence: HIGH (fundamental HTMX pattern, stable since HTMX 1.x).
- **SQLModel session management:** `Session` from SQLModel wraps SQLAlchemy session. Used with FastAPI `Depends()` for request-scoped sessions. Confidence: HIGH (documented pattern from SQLModel creator, same as SQLAlchemy).
- **Project plan (`docs/plan.md`):** Primary source for data model, service signatures, API design, and development phases. Confidence: HIGH (first-party project documentation).
- **UI prototypes (`docs/prototype/`):** Validated by the user. Provide exact CSS, HTML structure, and interaction patterns. Confidence: HIGH (user-approved).

**Note:** Context7 was unavailable for this research session. FastAPI, HTMX, and SQLModel architectural patterns are based on training knowledge of these mature, stable libraries. The core patterns recommended (server-rendered templates, HTMX fragment swaps, service layer separation) are well-established and unlikely to have changed.
