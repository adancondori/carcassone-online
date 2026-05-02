---
phase: 03-history-and-rollback
plan: 01
subsystem: web-ui/history
tags: [htmx, oob, rollback, history, jinja2]

dependency-graph:
  requires: [02-02]
  provides: [history-panel, rollback-route, oob-history-fragment]
  affects: [03-02, 05-01]

tech-stack:
  added: []
  patterns:
    - ActionDetail dataclass for template-ready action data
    - 4-fragment OOB pattern (score_table + controls + action_bar + history)

key-files:
  created: []
  modified:
    - app/services.py
    - app/web/dependencies.py
    - app/web/routes.py
    - app/templates/dashboard.html
    - app/static/css/style.css

decisions:
  - id: "03-01-01"
    decision: "ActionDetail dataclass with pre-resolved player names/colors"
    rationale: "Template gets simple dicts instead of needing player lookup; keeps Jinja2 logic minimal"
  - id: "03-01-02"
    decision: "History as 4th OOB fragment in _render_dashboard_fragments"
    rationale: "Consistent with existing OOB pattern; history updates atomically with score_table, controls, and action_bar"
  - id: "03-01-03"
    decision: "hx-confirm on rollback but not on undo"
    rationale: "Undo reverses one action (low risk); rollback can undo many actions at once (confirmation appropriate)"

metrics:
  duration: 2min
  completed: 2026-05-01
---

# Phase 3 Plan 1: History Panel UI, Rollback Route, and CSS Summary

Interactive history panel below the action bar showing all scoring actions with rollback capability, updating via OOB alongside score_table, controls, and action_bar.

## One-liner

History panel with per-action rollback via HTMX OOB, ActionDetail dataclass for template data, and CSS ported from prototype.

## What Was Done

### Task 1: Extend GameState, add history block, rollback route, and OOB wiring
- Added `ActionDetail` dataclass to `app/services.py` holding a ScoreAction with pre-resolved player name/color/points dicts
- Extended `GameState` with `action_details: list[ActionDetail]` field
- Updated `get_game_state` to load all actions (active + undone) with entries and build ActionDetail list
- Added `EVENT_TYPE_LABELS` mapping to `app/web/dependencies.py` for display-friendly Spanish event names
- Added `{% block history %}` to `dashboard.html` with reverse-chronological action list, rollback buttons, and hx-confirm
- Added `POST /games/{id}/rollback` route to `app/web/routes.py` calling `rollback_to()` then `_render_dashboard_fragments()`
- Added history as 4th OOB fragment in `_render_dashboard_fragments`
- Passed `action_details` and `EVENT_TYPE_LABELS` to both `game_dashboard` and `_render_dashboard_fragments` contexts

### Task 2: Add history CSS styles
- Ported history panel styles from prototype to `app/static/css/style.css`
- History card, header, scrollable list, item layout with number/content/rollback columns
- Undone items: `opacity: 0.35` + `text-decoration: line-through`
- Rollback button: minimal border style with accent-gold hover
- Custom webkit scrollbar for history list overflow

## Decisions Made

| ID | Decision | Rationale |
|----|----------|-----------|
| 03-01-01 | ActionDetail dataclass with pre-resolved player names/colors | Template gets simple dicts; keeps Jinja2 logic minimal |
| 03-01-02 | History as 4th OOB fragment in _render_dashboard_fragments | Consistent with existing OOB pattern; atomic updates |
| 03-01-03 | hx-confirm on rollback but not undo | Undo = 1 action (low risk); rollback = many (needs confirmation) |

## Deviations from Plan

None -- plan executed exactly as written.

## Verification Results

- All 45 existing tests pass (no regressions)
- No new test failures introduced

## Commits

| Hash | Message |
|------|---------|
| 7ed52d8 | feat(03-01): add history panel, rollback route, and OOB wiring |
| e022e03 | feat(03-01): add history panel CSS styles |

## Next Phase Readiness

Plan 03-02 (integration tests for history and rollback) can proceed immediately. All routes, templates, and OOB fragments are in place.
