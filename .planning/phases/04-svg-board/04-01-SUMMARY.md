---
phase: 04-svg-board
plan: 01
subsystem: web-ui/board
tags: [svg, htmx, oob, meeple, jinja2]

dependency-graph:
  requires: [02-02]
  provides: [svg-board, board-oob-fragment, build-board-context]
  affects: [04-02]

tech-stack:
  added: []
  patterns:
    - Server-side SVG rendering via Jinja2 loops (no client-side JS for board)
    - 5-fragment OOB pattern (score_table + controls + action_bar + history + board)
    - build_board_context helper for cell grouping and stacking offsets

key-files:
  created:
    - app/static/images/carcassonneok.jpg
  modified:
    - app/templates/dashboard.html
    - app/static/css/style.css
    - app/web/dependencies.py
    - app/web/routes.py

decisions:
  - id: "04-01-01"
    decision: "Server-side SVG rendering with Jinja2 loops, no client-side JS"
    rationale: "Consistent with app architecture; board updates via OOB swap like all other fragments"
  - id: "04-01-02"
    decision: "BOARD_CELLS as module constant in dependencies.py, build_board_context as helper"
    rationale: "Clean separation; route just calls build_board_context(players) and passes result to template"
  - id: "04-01-03"
    decision: "Board as 5th OOB fragment in _render_dashboard_fragments"
    rationale: "Extends existing OOB pattern; board tokens update atomically with score table"

metrics:
  duration: 3min
  completed: 2026-05-01
---

# Phase 4 Plan 1: Board SVG Implementation Summary

**SVG scoring board with server-rendered meeple tokens, stacking offsets, lap badges, and HTMX OOB live updates — all via Jinja2, no client-side JS.**

## Performance

- **Duration:** 3 min
- **Tasks:** 2/2
- **Files modified:** 5

## Accomplishments
- Board photo copied to static assets and served from /static/images/
- SVG board block with meeple-shaped tokens rendered server-side via Jinja2 loops
- Stacking offsets prevent token overlap when multiple players share a cell
- Lap badges (x1, x2...) appear on tokens for players past cell 49
- Board updates live via HTMX OOB as 5th fragment alongside score table, controls, action bar, and history
- CSS ported from prototype: board wrapper, token shadows, badge styling

## Task Commits

1. **Task 1: Board image and SVG board template block** - `883f119` (feat)
2. **Task 2: Board data computation and OOB wiring** - `ba5f2fe` (feat)

## Files Created/Modified
- `app/static/images/carcassonneok.jpg` - Board photo from sources
- `app/templates/dashboard.html` - Added {% block board %} with SVG, meeple tokens, lap badges
- `app/static/css/style.css` - Board wrapper, token, badge CSS ported from prototype
- `app/web/dependencies.py` - BOARD_CELLS (50 coords), _stack_offset, build_board_context
- `app/web/routes.py` - Board OOB fragment, board_cells in all dashboard contexts

## Decisions Made

| ID | Decision | Rationale |
|----|----------|-----------|
| 04-01-01 | Server-side SVG rendering via Jinja2 | Consistent with app architecture; OOB swaps |
| 04-01-02 | BOARD_CELLS + build_board_context in dependencies.py | Clean separation from routes |
| 04-01-03 | Board as 5th OOB fragment | Extends existing pattern; atomic updates |

## Deviations from Plan

None -- plan executed exactly as written.

## Verification Results

- All 56 existing tests pass (no regressions)
- BOARD_CELLS has 50 entries
- build_board_context([]) returns {}

## Next Phase Readiness

Plan 04-02 (integration tests and visual verification) can proceed immediately. Board template, routes, and OOB wiring are complete.
