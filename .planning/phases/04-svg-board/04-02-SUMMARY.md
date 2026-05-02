---
phase: 04-svg-board
plan: 02
subsystem: testing/board
tags: [pytest, integration-tests, visual-verification, board]

dependency-graph:
  requires: [04-01]
  provides: [board-tests, calibrated-coordinates]
  affects: []

tech-stack:
  added: []
  patterns: []

key-files:
  created: []
  modified:
    - tests/test_web.py
    - app/web/dependencies.py

decisions:
  - id: "04-02-01"
    decision: "Recalibrated all 50 BOARD_CELLS from red-dot reference image using automated detection"
    rationale: "Original prototype coordinates were misaligned; user provided reference image with red dots at cell centers"
  - id: "04-02-02"
    decision: "Cells 36 and 37 manually corrected after visual verification"
    rationale: "Automated detection placed 37 on roof tiles instead of scoring track"

metrics:
  duration: 5min
  completed: 2026-05-01
---

# Phase 4 Plan 2: Board Integration Tests & Visual Verification Summary

**10 board tests added, all 50 cell coordinates recalibrated from reference image with red-dot markers, visual checkpoint approved.**

## Performance

- **Duration:** 5 min
- **Tasks:** 2/2
- **Files modified:** 2

## Accomplishments
- 10 new tests: build_board_context unit tests (empty, single player, lap, stacking, cells 36-37) + integration tests (dashboard GET, score POST OOB, undo POST OOB, lap badge)
- All 50 BOARD_CELLS recalibrated using automated red-dot detection from reference image
- Cells 36 and 37 manually corrected after visual verification
- Visual checkpoint passed: tokens align with board, stacking works, lap badges display

## Task Commits

1. **Task 1: Board integration tests** - `41800c9` (test)
2. **Task 2: Visual verification + coordinate fix** - `c46ebcf` (fix)

## Files Created/Modified
- `tests/test_web.py` - 10 new tests in TestBoardContext and TestBoardIntegration classes
- `app/web/dependencies.py` - All 50 BOARD_CELLS recalibrated from reference image

## Decisions Made

| ID | Decision | Rationale |
|----|----------|-----------|
| 04-02-01 | Recalibrated coordinates from red-dot reference image | Original prototype coords were misaligned |
| 04-02-02 | Cells 36-37 manually corrected | Automated detection placed 37 on buildings, not track |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] All 50 cell coordinates were misaligned with board photo**
- **Found during:** Task 2 (visual verification checkpoint)
- **Issue:** Original prototype coordinates didn't match actual cell positions on the board photo
- **Fix:** Automated red-dot detection from reference image + manual correction for cells 36-37
- **Files modified:** app/web/dependencies.py, tests/test_web.py
- **Verification:** Visual inspection confirmed all 50 numbers align with board cells

**Total deviations:** 1 auto-fixed (coordinate recalibration)

## Issues Encountered

None.

## Next Phase Readiness

Phase 4 complete. All board features working and tested. Ready for Phase 5 (Game States).
