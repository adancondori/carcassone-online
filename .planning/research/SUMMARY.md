# Project Research Summary

**Project:** Carcassonne Scoreboard
**Domain:** Single-page web app for in-person board game scoring
**Researched:** 2026-05-01
**Confidence:** HIGH (stack and architecture), MEDIUM (feature landscape)

## Executive Summary

This project is a mobile-first, self-hosted web app for tracking Carcassonne scores at the game table. The right approach is a server-rendered monolith using FastAPI + Jinja2 + HTMX + SQLite — no SPA framework, no npm, no build pipeline, no external services. The server owns all state and serves HTML fragments on user interactions. This is not a simplification; it is the architecturally correct choice for a single-user, single-device app used over a local network.

The unique market position is the combination of a visual SVG scoreboard track (replicating the physical board), event-sourced undo/rollback, and atomic shared scoring — none of which exist together in any web-based competitor. The core differentiator is the visual board; everything else is table stakes. Build the data model and scoring logic first, get the visual board working, then layer on history/rollback. The temptation to skip ahead to the board before the data layer is solid is the main productivity risk.

The three critical pitfalls that must be addressed from day one are: (1) `score_total` cache divergence from the event-sourced entry log, (2) SQLite data loss in Docker from WAL file misconfiguration, and (3) Alembic batch mode not enabled for SQLite schema changes. All three are preventable with known solutions, but all three require explicit setup in Phase 1. Missing any one of them will cause data loss or require a rewrite later.

---

## Key Findings

### Recommended Stack

The entire stack is settled and cross-referenced. Python 3.13 + FastAPI 0.136.1 + SQLModel 0.0.38 + SQLite + Alembic 1.18.4 on the backend; HTMX 2.0.10 (CDN) + Jinja2 (transitive) + vanilla JS + custom CSS on the frontend. No npm. No bundler. Docker with `python:3.13-slim` as base image.

SQLModel is the correct ORM choice — it eliminates model/schema duplication by serving as both the SQLAlchemy model and the Pydantic schema. HTMX 2.x (not 4.0 alpha) is the correct choice for interactivity — it returns HTML fragments, keeping the server as the single source of truth, which aligns precisely with the event-sourcing data model. The alternatives table in STACK.md is comprehensive; every common "but what about X?" has been pre-answered.

**Core technologies:**
- Python 3.13 + FastAPI 0.136.1: async-native web framework with built-in Jinja2 and SQLModel integration
- SQLModel 0.0.38 + SQLite + Alembic: unified ORM/schema layer on zero-config embedded DB, with migration history
- HTMX 2.0.10 (CDN): server-driven partial updates with no build tooling required
- Jinja2 (transitive via FastAPI): server-side HTML rendering with template inheritance and fragment support
- Vanilla JS (ES2022+): ~100 lines for SVG board token positioning and step-by-step animation only
- Docker + `python:3.13-slim`: reproducible self-hosted deployment, single named volume for SQLite persistence

**Must NOT add:** async SQLAlchemy/aiosqlite (sync is faster for SQLite at this scale), Redis/caching (no need), WebSockets (HTMX polling is sufficient), npm/Tailwind/any JS framework (adds build complexity for zero benefit).

### Expected Features

The competitor analysis surveyed 15+ apps across Android, iOS, and web. The gap is real: no web app combines a visual SVG track + event-sourced undo/rollback + atomic shared scoring + mobile-first design. This is the product's identity.

**Must have (table stakes) — ship in v1:**
- Player setup with names and colors (2-6 players)
- Add points with event type labels (road, city, monastery, farm, manual)
- Shared/atomic scoring for majority ties (one action, N entries)
- Score display ranked by total
- Undo last action (complete action with all entries)
- Action history showing grouped entries per action
- Game state machine (setup → playing → final scoring → finished)
- Mobile-friendly touch UI (48px minimum touch targets)
- No account, no login

**Should have (key differentiators) — ship in v1:**
- Visual SVG scoreboard track with real board photo background
- Meeple tokens positioned on correct cells (score_total % 50)
- Token movement animation (step-by-step at ~80ms per step)
- Lap indicator badge (score_total // 50)
- Token stacking when multiple players share a cell

**Also valuable but can ship in v1 or shortly after:**
- Rollback to any past action (beyond single undo)
- Undone actions visible in history (struck through, not deleted)
- Distinct final-scoring phase controls
- Haptic feedback on score entry

**Defer to post-MVP:**
- Expansion-specific event types (add as enum values, low effort)
- Export to JSON
- PWA/offline mode
- Turn tracking
- Any game logic enforcement (deliberately never build this)
- BGG integration, statistics, user accounts, sound effects

### Architecture Approach

The architecture is a server-rendered monolith with three clear layers: Web Routes (thin HTTP handlers), Service Layer (all business logic), and Data Layer (SQLModel + SQLite + Alembic). The browser layer has two distinct concerns: HTMX (declarative partial updates via HTML fragment swaps) and vanilla JS (SVG board animation only). There is no client-side state; the server is the single source of truth.

Every user-visible operation (score, undo, rollback) executes in one database transaction. After any state-changing action, a single POST returns all affected dashboard fragments via `hx-swap-oob` — score table, board tokens, and history in one response, no extra round-trips. Templates are split into full pages and fragments; HTMX endpoints return only fragments, and full-page loads include those same fragments via `{% include %}` to avoid duplication.

**Major components:**
1. **Web Routes** (`app/web/routes.py`) — accept HTTP, call services, render templates, return HTML (full pages or fragments)
2. **Service Layer** (`app/services.py`) — all scoring, undo, rollback, recalculation, and state transitions; pure Python testable without HTTP
3. **Data Layer** (`app/models.py`, `app/db.py`, `alembic/`) — SQLModel schema, SQLite engine with WAL pragmas, Alembic migrations
4. **Jinja2 Templates** (`templates/`) — full pages and HTMX fragments; fragments are reused by both full-page and partial responses
5. **Vanilla JS** (`static/js/`) — reads `data-cell` / `data-prev-cell` attributes from server-rendered SVG tokens, runs animation only
6. **Static Assets** (`static/`) — CSS, JS, board image; served by FastAPI static mount

**Key invariant to preserve:** `player.score_total == SUM(points) FROM score_entries WHERE player_id = X AND is_undone = FALSE`

### Critical Pitfalls

1. **score_total cache diverges from entry log** — Write property-based tests (hypothesis library) running 50+ random add/undo/rollback sequences, asserting cache equals recalculated total after every operation. Set this up in Phase 1 before any undo code is written.

2. **SQLite data loss in Docker from WAL file misconfiguration** — Mount the entire data directory (not just the .db file) as a named volume so WAL sidecar files are included. Force `PRAGMA wal_checkpoint(TRUNCATE)` on graceful shutdown. Smoke test: `docker compose down && docker compose up`, verify data survives.

3. **Alembic fails silently on SQLite schema changes** — Enable `render_as_batch=True` in `alembic/env.py` on day one. Name all constraints explicitly in SQLModel models. Test migrations against file-based SQLite, not just in-memory.

4. **HTMX partial updates leave dashboard inconsistent** — Define a single response-builder function that assembles all OOB fragments (score table + board tokens + history) so nothing is ever forgotten. After every HTMX action, regression tests should compare partial DOM against a full page refresh.

5. **Async/sync mismatch blocks event loop** — Use `def` (not `async def`) for all route handlers that call synchronous SQLAlchemy. FastAPI runs sync handlers in a threadpool automatically.

---

## Implications for Roadmap

Based on combined research, the 5-phase structure from ARCHITECTURE.md is the correct build order. The dependency chain is strict: data model → services → web UI → history/rollback → SVG board → game states.

### Phase 1: Foundation (Data Model, Services, Docker)

**Rationale:** All subsequent phases depend on correct scoring logic. This phase has no HTTP, no templates — just the data layer, service functions, and tests. The three critical pitfalls all manifest here.
**Delivers:** Working `add_score()`, `undo_last()`, `rollback_to()`, `recalculate_score()` with full test coverage; Alembic migration history; Docker environment with persistent SQLite volume.
**Addresses:** Player setup model, score event model, game state machine model.
**Avoids:** Pitfalls 1 (cache divergence), 2 (Docker data loss), 3 (Alembic batch mode), 5 (async/sync), 10 (SQLite locking), 11 (state machine enforcement).
**Research flag:** Standard patterns — no additional research needed.

### Phase 2: Minimal Web UI (Setup + Dashboard + Basic Scoring)

**Rationale:** Delivers the first end-to-end vertical slice. Creates game, adds players, scores points, sees results. HTMX fragment strategy must be established here.
**Delivers:** Setup page (create game, add players), dashboard page (score table, controls, undo), HTMX fragment swaps with OOB updates. First usable version of the app.
**Uses:** FastAPI routes, Jinja2 templates, HTMX `hx-post` / `hx-swap-oob`, jinja2-fragments for template block rendering.
**Avoids:** Pitfall 4 (HTMX inconsistent state), Pitfall 8 (touch targets too small), Pitfall 9 (template duplication).
**Research flag:** Standard patterns — HTMX + FastAPI + Jinja2 is well-documented.

### Phase 3: History and Rollback

**Rationale:** Extends the already-working scoring system. Rollback is a more complex service operation than undo; the foundation should be battle-tested before adding it.
**Delivers:** Chronological action history fragment, rollback to any past action, struck-through undone actions in history, event type labels.
**Addresses:** Differentiator features (rollback, audit trail) that require solid Phase 1 data model to be correct.
**Avoids:** Pitfall 7 (score_before/score_after confusion — show point deltas only, not snapshots).
**Research flag:** Standard patterns.

### Phase 4: SVG Board

**Rationale:** Visually the signature differentiator, but functionally independent of scoring logic. Reads the same `score_total` data already used by the score table. This is a rendering concern, not a data concern, so it can safely be built after the data is solid.
**Delivers:** Server-rendered SVG tokens via Jinja2, CELLS coordinate array in static JS, token movement animation on `htmx:afterSwap`, lap badges, token stacking offset.
**Avoids:** Pitfall 6 (SVG coordinate mapping breaks on different devices — use `preserveAspectRatio="xMidYMid meet"`, map coordinates as percentages, test on 3+ devices), Pitfall 8 (touch targets on board).
**Research flag:** SVG responsive coordinate mapping warrants a focused research spike during planning. The `preserveAspectRatio` approach and percentage-based CELLS mapping need concrete implementation validation before coding starts.

### Phase 5: Game States and Final Scoring

**Rationale:** The core scoring workflow (playing state) works without state transitions. Adding setup/scoring/finished states is an orchestration layer on top of already-working components.
**Delivers:** State machine transitions enforced in service layer, distinct controls for playing vs. final scoring phases, finished state results screen, event type filtering by game phase.
**Addresses:** Game state machine (table stakes), distinct final-scoring phase (differentiator).
**Avoids:** Pitfall 11 (state machine not enforced — central `transition_state()` function with explicit invalid-transition tests), Pitfall 12 (no backup mechanism — implement JSON export here as manual backup).
**Research flag:** Standard patterns.

### Phase Ordering Rationale

- **Data before UI** because every subsequent phase tests against real service behavior. Discovering a flaw in `recalculate_score()` after the web UI is built requires unwinding both layers; discovering it in Phase 1 tests requires unwinding nothing.
- **Core scoring before rollback** because rollback depends on an immutable entry log that must first be proven correct under normal scoring conditions.
- **Web UI before SVG board** because the board reads the same `score_total` values that the score table already renders. Building the board without a working score table means debugging both the data and the rendering simultaneously.
- **SVG board before game states** because the board needs to render correctly in the playing state before final-scoring state adds new event types and transitions.
- **All phases build testably in sequence** — each phase adds a regression test suite that the next phase runs against without modification.

### Research Flags

Phases needing deeper research during planning:

- **Phase 4 (SVG Board):** The coordinate mapping approach (percentage-based vs. pixel-based), `preserveAspectRatio` interaction with the board photo's actual aspect ratio, and the `data-prev-cell` animation timing need a concrete spike or research pass. The board photo dimensions and viewBox setup should be validated before writing the CELLS array.

Phases with standard, well-documented patterns (skip research-phase):

- **Phase 1:** SQLite WAL pragmas, Alembic batch mode, Docker named volumes — all documented with official sources.
- **Phase 2:** FastAPI + Jinja2 + HTMX `hx-swap-oob` — core HTMX feature, documented at htmx.org.
- **Phase 3:** Service layer extension, Jinja2 template blocks — same patterns established in Phase 2.
- **Phase 5:** State machine pattern — standard Python enum + validation function.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All package versions verified on PyPI as of April/May 2026. Dockerfile and pyproject.toml reference configuration is fully specified. |
| Features | MEDIUM | 15+ competitors surveyed via web search; individual app feature details sourced from app store descriptions, not hands-on testing. Gap analysis conclusion is MEDIUM confidence — a niche tool may exist that didn't surface. |
| Architecture | HIGH | Server-rendered monolith + HTMX is a well-established pattern. `hx-swap-oob` is a stable core HTMX feature. Service layer patterns are from official FastAPI/SQLModel docs. Project's own `docs/plan.md` and validated prototypes served as primary sources. |
| Pitfalls | HIGH | 10 of 12 pitfalls sourced from official documentation or real-world incident reports. 2 pitfalls (score_before/score_after confusion, SVG coordinate mapping) are MEDIUM confidence — logical consequences of design choices rather than externally documented patterns. |

**Overall confidence:** HIGH

### Gaps to Address

- **Board photo dimensions:** The CELLS coordinate mapping depends on the actual aspect ratio of the board photo. Before Phase 4, measure the source image and establish the viewBox dimensions. This determines whether percentage-based coordinates will work cleanly or need per-resolution calibration.

- **Competitor feature verification:** Feature comparison table is based on app store descriptions and search snippets. The "shared scoring" and "undo" behaviors of specific competitors were not hands-on verified. This is acceptable — the product is better than what's described, not worse.

- **jinja2-fragments package name:** PITFALLS.md references both `jinja2-fragments` (the library name) and `Jinja2Blocks` (the class). Verify the current PyPI package name and API before Phase 1 template setup.

- **HTMX 4.0 timeline:** STACK.md notes HTMX 4.0 stable is expected early 2027. If the project extends beyond that window, evaluate upgrading. Not a blocking concern for now.

---

## Sources

### Primary (HIGH confidence)

- PyPI package pages for FastAPI, SQLModel, Alembic, Uvicorn, pytest, pydantic-settings — versions verified April–May 2026
- [Alembic batch migrations for SQLite](https://alembic.sqlalchemy.org/en/latest/batch.html) — batch mode configuration
- [FastAPI async/await documentation](https://fastapi.tiangolo.com/async/) — sync vs async route handler behavior
- [HTMX hx-swap-oob documentation](https://htmx.org/attributes/hx-swap-oob/) — multi-target swap pattern
- [SQLite WAL mode](https://sqlite.org/wal.html) — WAL pragma behavior
- [Docker persist data documentation](https://docs.docker.com/get-started/workshop/05_persisting_data/) — named volume configuration
- [jinja2-fragments library](https://github.com/sponsfreixes/jinja2-fragments) — template block rendering
- Project's own `docs/plan.md` and `docs/prototype/` — data model, API design, validated UI

### Secondary (MEDIUM confidence)

- [CarcassonneScorer.com](https://carcassonnescorer.com/) — competitor feature reference
- [Carcassonne Scoreboard Android (Google Play)](https://play.google.com/store/apps/details/Carcassonne_Scoreboard?id=com.Carcassonne_Scoreboard.EDrummer19&hl=en_SG) — competitor feature reference
- [HTMX template fragments essay](https://htmx.org/essays/template-fragments/) — fragment strategy patterns
- [Don't Forget the WAL: SQLite Data Loss in Containers](https://bkiran.com/blog/sqlite-containers-data-loss) — Docker/WAL incident reports
- [SVG coordinate systems — Sara Soueidan](https://www.sarasoueidan.com/blog/svg-coordinate-systems/) — preserveAspectRatio behavior
- [Touch target sizes — Nielsen Norman Group](https://www.nngroup.com/articles/touch-target-size/) — 48px minimum standard
- BGG threads for competitor landscape survey (15+ apps)

### Tertiary (LOW confidence)

- App store descriptions for individual competitor features — not hands-on verified; used only for gap analysis direction

---
*Research completed: 2026-05-01*
*Ready for roadmap: yes*
