---
phase: 03-history-and-rollback
plan: 02
subsystem: testing/integration
tags: [pytest, htmx, oob, rollback, history, integration-tests]

dependency-graph:
  requires: [03-01]
  provides: [history-rollback-test-coverage, phase-3-requirements-verification]
  affects: [04-01]

tech-stack:
  added: []
  patterns:
    - post_rollback and get_action_ids test helpers for rollback route testing
    - HTML section extraction for targeted assertion of OOB fragment content

key-files:
  created: []
  modified:
    - tests/test_web.py

decisions:
  - id: "03-02-01"
    decision: "Query ScoreAction table via get_action_ids helper for rollback test action IDs"
    rationale: "Action IDs are auto-generated; querying DB is the only reliable way to get them for rollback calls"
  - id: "03-02-02"
    decision: "Extract history section from response for targeted undone-class assertions"
    rationale: "Avoid false positives from 'undone' appearing in non-history parts of the response"

metrics:
  duration: 2min
  completed: 2026-05-01
---

# Phase 3 Plan 2: History and Rollback Integration Tests Summary

11 integration tests verifying history OOB fragment, event type labels, rollback score recalculation, and undone CSS class marking across score/undo/rollback responses.

## One-liner

Integration tests for history panel OOB fragment and rollback route covering UNDO-01 through UNDO-04 and DISPLAY-03.

## What Was Done

### Task 1: Add history and rollback integration tests
- Added `post_rollback` helper: POSTs to `/games/{id}/rollback` with `action_id` and HTMX header
- Added `get_action_ids` helper: queries ScoreAction table ordered by id for reliable action ID lookup
- Added import of `ScoreAction` from `app.models`
- Added `TestHistory` class with 6 tests:
  - `test_score_response_includes_history` -- verifies `id="history"` and `hx-swap-oob="true"` in score response
  - `test_history_shows_event_type_label` -- verifies "Ciudad" and "Camino" labels appear for respective event types
  - `test_history_shows_player_names_and_points` -- verifies "Alice" and "+8" appear in history
  - `test_history_shows_shared_scoring` -- verifies both "Alice" and "Bob" with "+12" for shared action
  - `test_undo_marks_action_as_undone_in_history` -- verifies `undone` class present after undo
  - `test_dashboard_full_page_includes_history` -- verifies full page GET includes history div with action details
- Added `TestRollback` class with 5 tests:
  - `test_rollback_returns_fragments` -- verifies 200, no DOCTYPE, has OOB attributes
  - `test_rollback_reverts_scores` -- verifies Alice=8 after rollback (not 18 or 0)
  - `test_rollback_marks_subsequent_actions_undone` -- verifies actions 2,3 have undone class, action 1 does not
  - `test_rollback_shared_action` -- verifies both players show 10 after rollback to shared action
  - `test_rollback_nothing_when_last_action` -- verifies no-op rollback keeps scores unchanged

## Decisions Made

| ID | Decision | Rationale |
|----|----------|-----------|
| 03-02-01 | Query ScoreAction table via get_action_ids helper | Action IDs are auto-generated; DB query is only reliable source |
| 03-02-02 | Extract history section for targeted undone-class assertions | Avoids false positives from 'undone' in non-history response parts |

## Deviations from Plan

None -- plan executed exactly as written.

## Verification Results

- `python -m pytest tests/ -x -q`: 56 passed (45 existing + 11 new)
- `python -m pytest tests/test_web.py::TestHistory -v`: 6/6 passed
- `python -m pytest tests/test_web.py::TestRollback -v`: 5/5 passed
- No existing tests modified or broken

## Commits

| Hash | Message |
|------|---------|
| f9fe6a9 | test(03-02): add history and rollback integration tests |

## Next Phase Readiness

Phase 3 is complete. All UNDO-01 through UNDO-04 and DISPLAY-03 requirements are covered by tests. Phase 4 (SVG Board) can proceed independently.
