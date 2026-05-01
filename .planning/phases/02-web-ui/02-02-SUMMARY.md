---
phase: 02-web-ui
plan: 02
subsystem: ui
tags: [htmx, jinja2, oob-swap, scoring, undo, javascript]

# Dependency graph
requires:
  - phase: 02-01
    provides: web infrastructure, template engine with Jinja2Blocks, base.html, CSS, PLAYER_COLORS
  - phase: 01-02
    provides: add_score, undo_last, get_game_state service functions
provides:
  - Scoring dashboard with HTMX-driven score table, controls, and undo
  - Multi-fragment OOB response pattern for score/undo routes
  - Controls.js for ephemeral UI state management
affects: [02-03, 03-history, 04-svg-board]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "HTMX OOB multi-fragment: primary target + hx-swap-oob for secondary targets"
    - "_render_dashboard_fragments() helper for DRY fragment rendering"
    - "initControls() idempotent re-initialization after OOB swaps"

key-files:
  created:
    - app/templates/dashboard.html
    - app/static/js/controls.js
  modified:
    - app/web/routes.py
    - app/static/css/style.css

key-decisions:
  - "OOB pattern: score_table as primary target (no oob attr) + controls/action_bar as oob=true"
  - "controls.js uses vanilla JS with initControls() re-bound on htmx:afterSwap and htmx:oobAfterSwap"
  - "Touch targets enforced at 48px minimum via CSS min-height on player-chip, type-btn, point-btn"

patterns-established:
  - "_render_dashboard_fragments(): shared helper for multi-fragment HTMX responses"
  - "oob context variable toggles hx-swap-oob attribute rendering per block"
  - "Annotated[list[int], Form()] for multi-value checkbox form fields in FastAPI"

# Metrics
duration: 5min
completed: 2026-05-01
---

# Phase 2 Plan 2: Scoring Dashboard Summary

**HTMX scoring dashboard with OOB multi-fragment responses for score table, controls reset, and undo button state**

## Performance

- **Duration:** 5 min
- **Started:** 2026-05-01T23:49:00Z
- **Completed:** 2026-05-01T23:54:00Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Full scoring dashboard with ranked score table showing player name, color dot, score, cell (score%50), and lap (score//50)
- HTMX-driven scoring: POST /score returns 3 fragments (score_table primary + controls OOB + action_bar OOB) in one response
- Undo via POST /undo returns the same multi-fragment pattern, reverts scores, and auto-disables button when empty
- Controls.js manages all ephemeral UI state: player chip toggling, point selection, dynamic submit label, automatic re-init after OOB swaps

## Task Commits

Each task was committed atomically:

1. **Task 1: Dashboard template, scoring routes, and undo with HTMX OOB fragments** - `1e596e8` (feat)
2. **Task 2: Controls JavaScript for ephemeral UI state** - `c0be015` (feat)

## Files Created/Modified
- `app/templates/dashboard.html` - Dashboard template with named blocks: score_table, controls, action_bar for HTMX fragment rendering
- `app/static/js/controls.js` - Vanilla JS for ephemeral UI state: player chips, point buttons, custom input, submit validation
- `app/web/routes.py` - Dashboard GET, score POST, undo POST routes with _render_dashboard_fragments() helper
- `app/static/css/style.css` - Touch target fixes: min-height 48px on player-chip, type-btn; height 48px on point-btn

## Decisions Made
- Used old-style TemplateResponse call (`"template.html", {"request": request, ...}`) for consistency with existing codebase, with `block_name=` as keyword arg
- `_render_dashboard_fragments()` helper function extracts shared fragment rendering logic between score and undo routes
- `oob` context variable (False for primary target, True for OOB targets) controls whether `hx-swap-oob="true"` attribute is rendered in each block
- `all_players` sorted by turn_order for controls (consistent chip order), `players` sorted by score for table (ranking)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Enforced 48px minimum touch targets on interactive elements**
- **Found during:** Task 2 (controls.js verification)
- **Issue:** Player chips (~32px), type buttons (~36px), and point buttons (44px) were below the 48px mobile touch target minimum
- **Fix:** Added min-height: 48px to .player-chip and .type-btn; changed .point-btn and .point-custom input height from 44px to 48px
- **Files modified:** app/static/css/style.css
- **Verification:** CSS values confirmed >= 48px for all interactive elements
- **Committed in:** c0be015 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 missing critical)
**Impact on plan:** Touch target fix was explicitly called for in the plan as a conditional action. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Scoring dashboard fully functional, ready for 02-03 (end game / final scoring UI)
- History panel and rollback UI deferred to Phase 3
- SVG board integration deferred to Phase 4

---
*Phase: 02-web-ui*
*Completed: 2026-05-01*
