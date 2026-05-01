# Carcassonne Scoreboard

## What This Is

A web-based scoring tracker for the board game Carcassonne. Replaces the physical scoreboard with an interactive digital version that tracks scores, supports undo/rollback, and shows a visual board with meeple tokens. Designed mobile-first for use at the game table on a phone or tablet.

**This is NOT a Carcassonne game implementation** — only the scoring component. The user decides what to score; the app records and visualizes it.

## Core Value

Players can accurately track scores during a Carcassonne game with undo capability, so mistakes at the table are never permanent.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Create and configure a game session with 2-6 players
- [ ] Assign unique colors and names to each player
- [ ] Register scoring actions with event type (road, city, monastery, farm, manual)
- [ ] Support shared scoring: multiple players score from one action (majority tie rule)
- [ ] All scoring is atomic: one action with N entries, one transaction
- [ ] Undo the last scoring action completely (all entries in the action)
- [ ] Rollback to any previous action (undo all subsequent actions)
- [ ] Score recalculation from active entries as source of truth (not mutable cache)
- [ ] Visual SVG board with 50 cells (0-49) using real board photo as background
- [ ] Meeple tokens positioned on correct cells with stacking when overlapping
- [ ] Lap indicator (x1, x2, x3...) for unlimited laps
- [ ] Score table showing all players ranked by score
- [ ] Action history showing grouped entries per action, with undone actions visually struck through
- [ ] Game state machine: setup -> playing -> scoring -> finished
- [ ] Distinguish scoring during game (completed structures) vs final scoring (incomplete + farms)
- [ ] Dashboard usable on mobile (phone at the game table)
- [ ] Dockerized deployment with single `docker compose up`

### Out of Scope

- Game logic (tile placement, follower rules, structure completion) — user decides what to score
- Multiplayer networking (multiple devices) — single device at the table
- User accounts / authentication — no login needed
- Expansion rules in v1 (Inns & Cathedrals, Traders & Builders, Abbot) — add as event types later
- Turn tracking in v1 — convenience feature, not core scoring
- Export/import in v1 — deferred to later phase

## Context

- **Game rules reference**: Complete Annotated Rules (CAR) v6.4, stored at `docs/rules.pdf`
- **Board photo**: `sources/carcassonneok.jpg` — clean photo of the physical scoring track
- **Board coordinates**: 50 cell positions mapped from `sources/carcassonneok-point.jpg` with red dots marking each cell center
- **UI prototype**: `docs/prototype/dashboard.html` and `docs/prototype/setup.html` — fully interactive HTML prototypes validated by the user, with Carcassonne Plus blue/gold color palette
- **Detailed plan**: `docs/plan.md` — comprehensive technical plan with data model, API design, service logic, and phased development strategy
- **Scoring rules summary**:
  - During game: road (1pt/tile), city (2pt/segment + 2pt/shield), monastery (9pt)
  - Final: road (1pt/tile), city (1pt/segment + 1pt/shield), monastery (1pt + neighbors), farm (3pt/completed adjacent city)
  - Majority tie: all tied players get full points (CAR p.12)
  - Scoreboard: 50-cell track, unlimited laps (CAR p.14)

## Constraints

- **Stack**: FastAPI (Python) + Jinja2 + HTMX + JS vanilla + SQLite + SQLModel + Alembic + Docker
- **Database**: SQLite (zero config, sufficient for ~100 rows/game). Migration path to PostgreSQL via connection string change.
- **Data model**: `score_actions` (what happened) + `score_entries` (who was affected). Undo/rollback operates on actions, not individual entries. `player.score_total` is a cache; truth is SUM of active entries.
- **Frontend**: Server-driven with HTMX. No SPA, no build step, no npm. JS vanilla only for SVG board and animations.
- **Responsive**: Mobile-first, usable on phone at the game table. SVG board with `preserveAspectRatio="none"` and viewBox 600x420.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| score_actions + score_entries (not flat events) | Shared scoring is one logical event affecting N players. Undo/rollback must operate on the whole action atomically. | — Pending |
| score_total as cache, recalculate on undo | Prevents data corruption from partial undo. O(N) with N~100 entries per game. | — Pending |
| SQLite over MySQL | Zero config, no DB container, sufficient for this data volume. | — Pending |
| HTMX over SPA | Server-driven UI, no build step, simpler stack. JS only for SVG board. | — Pending |
| Real board photo as SVG background | Authentic look, coordinates mapped from physical board. | ✓ Good |
| Carcassonne Plus blue/gold palette | Matches official branding, validated by user. | ✓ Good |

---
*Last updated: 2026-05-01 after initialization*
