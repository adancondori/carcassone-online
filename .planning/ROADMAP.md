# Roadmap: Carcassonne Scoreboard

## Overview

Deliver a mobile-first web scoreboard for Carcassonne in 5 phases, building from proven data foundations upward. Phase 1 establishes the data model, service layer, and infrastructure without any HTTP -- validating the three critical pitfalls (score_total cache, SQLite WAL in Docker, Alembic batch mode) before any UI code exists. Phases 2-3 layer on the web interface and history/rollback. Phase 4 adds the signature SVG board. Phase 5 wires up game state transitions as orchestration on top of working components.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Foundation** - Data model, service layer, Docker, and test infrastructure
- [x] **Phase 2: Web UI** - Setup page, dashboard, scoring controls, and HTMX fragment strategy
- [ ] **Phase 3: History and Rollback** - Action history display, rollback to any point, undo visibility
- [ ] **Phase 4: SVG Board** - Visual scoring track with meeple tokens, laps, and stacking
- [ ] **Phase 5: Game States** - State machine transitions, final scoring phase, finished screen

## Phase Details

### Phase 1: Foundation
**Goal**: The scoring engine works correctly and is proven by tests -- data model, service functions, and infrastructure are solid before any HTTP code is written
**Depends on**: Nothing (first phase)
**Requirements**: INFRA-01, INFRA-02, INFRA-03, INFRA-04, INFRA-05
**Success Criteria** (what must be TRUE):
  1. `docker compose up --build` starts the application and SQLite database persists across container restarts
  2. SQLModel models (Game, Player, ScoreAction, ScoreEntry) exist with all constraints, and Alembic migration runs with batch mode enabled
  3. `add_score()` correctly updates player.score_total and creates action+entries atomically for both single-player and shared scoring
  4. `undo_last()` and `rollback_to()` recalculate scores from active entries (not from score_before), and recalculated totals always match the cache
  5. pytest suite passes covering models (current_cell, lap), services (add, undo, rollback, shared scoring, recalculate), and property-based tests for cache consistency
**Plans**: 3 plans

Plans:
- [ ] 01-01-PLAN.md — Project structure, models, DB layer, and model tests
- [ ] 01-02-PLAN.md — Service functions (add_score, undo, rollback, recalculate) via TDD
- [ ] 01-03-PLAN.md — Alembic migrations, FastAPI app shell, and Docker configuration

### Phase 2: Web UI
**Goal**: Users can create a game, add players, score points, and see results in a browser -- the first end-to-end playable version
**Depends on**: Phase 1
**Requirements**: SETUP-01, SETUP-02, SETUP-03, SETUP-04, SETUP-05, SCORE-01, SCORE-02, SCORE-03, SCORE-04, SCORE-05, SCORE-06, DISPLAY-01, DISPLAY-02, DISPLAY-04
**Success Criteria** (what must be TRUE):
  1. User can create a new game, add 2-6 players with unique names and colors, remove a player, and start the game
  2. User can select one or multiple players, choose an event type, enter points (quick-tap or custom), add an optional note, and submit a scoring action
  3. Score table updates via HTMX without page reload, showing all players ranked by total score with name, color, score, cell, and lap
  4. Undo button reverses the last complete scoring action (including shared actions) and the score table reflects the corrected totals immediately
  5. Dashboard is usable on a mobile phone screen (touch targets >= 48px, no horizontal scroll)
**Plans**: 3 plans

Plans:
- [ ] 02-01-PLAN.md — Web infrastructure, template engine, static files, CSS, and setup page (create game, add/remove players, start)
- [ ] 02-02-PLAN.md — Scoring dashboard with HTMX fragments, scoring controls, undo, and controls.js
- [ ] 02-03-PLAN.md — Web integration tests and visual verification checkpoint

### Phase 3: History and Rollback
**Goal**: Users can see the full scoring history and roll back to any previous point in the game
**Depends on**: Phase 2
**Requirements**: UNDO-01, UNDO-02, UNDO-03, UNDO-04, DISPLAY-03
**Success Criteria** (what must be TRUE):
  1. Action history displays all scoring actions in chronological order, grouped by action with event type and all affected players (e.g., "City: Adam +12, Pablo +12")
  2. User can tap any past action to rollback, and all subsequent actions are marked undone with scores recalculated
  3. Undone actions remain visible in the history list but are visually struck through
  4. History updates via HTMX alongside the score table after every score, undo, or rollback operation (OOB fragment consistency)
**Plans**: 2 plans

Plans:
- [ ] 03-01-PLAN.md — History panel UI, rollback route, OOB wiring, and CSS styles
- [ ] 03-02-PLAN.md — Integration tests for history display and rollback

### Phase 4: SVG Board
**Goal**: Users see their meeple tokens moving around a visual replica of the physical Carcassonne scoring track
**Depends on**: Phase 2
**Requirements**: BOARD-01, BOARD-02, BOARD-03, BOARD-04, BOARD-05
**Success Criteria** (what must be TRUE):
  1. SVG board displays the real Carcassonne scoring track photo as background with 50 mapped cell positions
  2. Each player has a meeple-shaped token positioned on the correct cell (score_total % 50)
  3. When multiple players share a cell, tokens stack with radial offset so all are visible
  4. Lap badge (x1, x2, x3...) appears on tokens for players who have passed cell 49
  5. Board is responsive on mobile phones -- scales correctly without horizontal scroll or clipped tokens
**Plans**: 2 plans

Plans:
- [ ] 04-01-PLAN.md — Board SVG implementation: image, template block, CSS, OOB wiring, and token rendering
- [ ] 04-02-PLAN.md — Integration tests for board and visual verification checkpoint

### Phase 5: Game States
**Goal**: The game follows a clear lifecycle from setup through final scoring to a finished results screen
**Depends on**: Phase 2, Phase 3
**Requirements**: STATE-01, STATE-02, STATE-03, STATE-04
**Success Criteria** (what must be TRUE):
  1. Game transitions through setup -> playing -> scoring -> finished, and transitions are enforced (no going backward)
  2. In playing state, only completed-structure event types (road/city/monastery completed + manual) are available
  3. In scoring state, only final event types (road/city/monastery final + farm final + manual) are available
  4. Finished state shows final ranking and is read-only -- no scoring or undo actions are possible
**Plans**: 2 plans

Plans:
- [ ] 05-01-PLAN.md — Service layer: state transition functions, event-type constants and validation, finished-state guards (TDD)
- [ ] 05-02-PLAN.md — Web layer: transition routes, state-conditional dashboard UI, finished results view, integration tests

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5
Note: Phase 3 and Phase 4 are independent after Phase 2; they could execute in either order.

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation | 3/3 | Complete | 2026-05-01 |
| 2. Web UI | 3/3 | Complete | 2026-05-01 |
| 3. History and Rollback | 0/2 | Not started | - |
| 4. SVG Board | 0/TBD | Not started | - |
| 5. Game States | 0/2 | Not started | - |
