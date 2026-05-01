---
phase: 01-foundation
plan: 02
subsystem: database
tags: [sqlmodel, sqlalchemy, scoring, undo, rollback, tdd, pytest]

# Dependency graph
requires:
  - phase: 01-foundation (01-01)
    provides: "Game, Player, ScoreAction, ScoreEntry models with constraints"
provides:
  - "add_score service: atomic multi-player scoring with ScoreEntries"
  - "undo_last service: soft-undo last action with score recalculation"
  - "rollback_to service: batch undo after a given action"
  - "recalculate_score service: SUM of active entries as source of truth"
  - "14 service tests including cache consistency property test"
affects: [01-foundation-03, 02-htmx-ui]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Service functions take Session as first arg for explicit transaction control"
    - "recalculate_score as source of truth: undo/rollback always recalculate from entries"
    - "add_score uses fast-path cache update; undo/rollback use safe-path recalculation"
    - "func.coalesce(func.sum(...), 0) for null-safe aggregation"
    - "session.flush() after recalculate to persist before potential refresh"

key-files:
  created:
    - app/services.py
    - tests/test_services.py
  modified: []

key-decisions:
  - "recalculate_score flushes after update to ensure consistency when called standalone"
  - "No refactor phase needed -- implementation followed RESEARCH.md patterns directly"

patterns-established:
  - "TDD RED-GREEN cycle: stub with NotImplementedError, write all tests, then implement"
  - "Cache consistency test: random add/undo loop verifies score_total == recalculate after each op"
  - "Service layer is pure functions, no class -- session passed explicitly"

# Metrics
duration: 3min
completed: 2026-05-01
---

# Phase 01 Plan 02: Scoring Service Layer Summary

**TDD-driven scoring engine with add/undo/rollback/recalculate, shared scoring support, and cache consistency proven by random operation sequences**

## Performance

- **Duration:** 3 min
- **Started:** 2026-05-01T23:30:03Z
- **Completed:** 2026-05-01T23:33:32Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- 4 core service functions implemented with TDD (RED then GREEN)
- Shared scoring: multiple players scored from single action
- Score cache consistency proven: 20-iteration random add/undo loop verifies score_total == recalculate_score after every operation
- 14 service tests + 11 model tests = 25 total, all passing

## Task Commits

Each task was committed atomically:

1. **Task 1: RED -- Write failing tests** - `63b9688` (test)
2. **Task 2: GREEN -- Implement services** - `f777e02` (feat)

_TDD plan: 2 commits (test + feat). No refactor phase needed._

## Files Created/Modified
- `app/services.py` - Core scoring service: add_score, undo_last, rollback_to, recalculate_score (159 lines)
- `tests/test_services.py` - 14 tests covering all service functions, edge cases, shared scoring, and cache consistency (271 lines)

## Decisions Made
- **recalculate_score flushes after update:** Without `session.flush()`, a subsequent `session.refresh()` would reload stale data from the DB. Flush ensures the updated score_total is written before any caller refreshes the object.
- **No refactor phase:** Implementation matched RESEARCH.md patterns closely enough that no cleanup was warranted.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] recalculate_score needed session.flush() after updating score_total**
- **Found during:** Task 2 (GREEN phase)
- **Issue:** `test_recalculate_with_undone` failed because `recalculate_score` updated `player.score_total` in Python but didn't flush to DB. When `session.refresh(alice)` was called, it reloaded the stale DB value.
- **Fix:** Added `session.flush()` after setting `player.score_total = total`
- **Files modified:** app/services.py
- **Verification:** All 14 tests pass including the failing test
- **Committed in:** f777e02 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Essential for correctness. Without flush, standalone recalculate_score calls would appear to work but DB state would be stale until next commit.

## Issues Encountered
None -- implementation followed RESEARCH.md patterns and all tests passed after the flush fix.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Service layer complete and proven by tests
- Ready for 01-03 (Alembic migrations + Docker) which needs models and services in place
- Ready for Phase 2 (HTMX UI) which will call these service functions from route handlers

---
*Phase: 01-foundation*
*Completed: 2026-05-01*
