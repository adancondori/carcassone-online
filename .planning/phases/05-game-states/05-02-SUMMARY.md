---
phase: 05-game-states
plan: 02
subsystem: web-layer
tags: [state-transitions, conditional-ui, finished-state, htmx-oob, integration-tests]

dependency_graph:
  requires: [05-01, 02-01, 02-02]
  provides: [begin-scoring-route, finish-game-route, state-conditional-dashboard, finished-results-view]
  affects: []

tech_stack:
  added: []
  patterns: [state-conditional-template-rendering, dynamic-event-type-filtering, transition-oob-fragment]

file_tracking:
  key_files:
    created: []
    modified: [app/web/routes.py, app/web/dependencies.py, app/templates/dashboard.html, app/static/css/style.css, tests/test_web.py]

decisions:
  - id: "05-02-01"
    description: "PLAYING_EVENT_TYPE_LABELS and SCORING_EVENT_TYPE_LABELS as filtered dicts from EVENT_TYPE_LABELS"
    rationale: "Template loop over active_event_types renders correct radio buttons per state without template logic"
  - id: "05-02-02"
    description: "Transition block as 6th OOB fragment in _render_dashboard_fragments"
    rationale: "Transition button area must update when scoring/undo changes state context"

metrics:
  duration: 4min
  completed: 2026-05-02
---

# Phase 5 Plan 2: Web Layer Game State Integration Summary

State transition routes (begin-scoring, finish) with PRG pattern, state-conditional dashboard (dynamic event types, transition buttons, finished results banner), and 18 integration tests.

## What Was Done

### Task 1: Transition routes and state-conditional dashboard template
- Added `begin_scoring_route` and `finish_game_route` POST routes with PRG 303 redirect pattern
- Added `PLAYING_EVENT_TYPE_LABELS` and `SCORING_EVENT_TYPE_LABELS` filtered constants in dependencies.py
- Made dashboard header status dynamic: En juego / Puntuacion final / Finalizada
- Replaced hardcoded event type radio buttons with Jinja2 loop over `active_event_types`
- Added transition button section: "Puntuacion final" (playing) / "Terminar partida" (scoring) with confirm() dialogs
- Wrapped controls and action_bar content in `game.status != 'finished'` conditionals
- Added results banner for finished state: "Partida finalizada", winner display, "Nueva partida" link
- Updated rollback button conditional to also check `game.status != 'finished'`
- Added transition as 6th OOB fragment in `_render_dashboard_fragments()`
- Added CSS for btn-transition, btn-begin-scoring, btn-finish, results-banner, btn-new-game
- All 41 existing web tests pass
- Commit: `cf0d8ea`

### Task 2: Integration tests for game states
- Added `begin_scoring()` and `finish_game()` test helpers
- Added `TestGameStates` class with 18 tests:
  - 4 state transition tests (redirect, status text)
  - 3 event type filtering tests (playing/scoring types, MANUAL in both)
  - 6 finished state tests (no controls, no undo, results banner, new game link, score table, no rollback)
  - 3 transition button tests (per-state presence/absence)
  - 2 scoring enforcement tests (final types accepted, completed types rejected in scoring)
- Full suite: 116 tests pass (was 98, added 18)
- Commit: `74724a5`

## Decisions Made

| ID | Decision | Rationale |
|----|----------|-----------|
| 05-02-01 | Filtered event type label dicts for template use | Template loops over active_event_types to render correct radio buttons per game state |
| 05-02-02 | Transition block as 6th OOB fragment | Ensures transition buttons update when HTMX fragment responses change game context |

## Deviations from Plan

None -- plan executed exactly as written.

## Test Results

```
59 passed in 0.82s (test_web.py)
116 passed in 0.98s (full suite)
```

## Next Phase Readiness

This completes Phase 5 (Game States) and the entire project roadmap. All 12 plans across 5 phases are complete. The application now supports the full game lifecycle: setup, playing (with completed event types), final scoring (with final event types), and finished (read-only results view).
