---
phase: 02-web-ui
plan: 01
subsystem: ui
tags: [fastapi, jinja2, htmx, css, templates, forms]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: SQLModel models (Game, Player), database layer, FastAPI shell
provides:
  - Jinja2Blocks template engine with HTMX CDN
  - Static file serving at /static/
  - Merged CSS from both validated prototypes
  - PLAYER_COLORS constant and COLOR_HEX_MAP
  - GameState dataclass and get_game_state() helper
  - Game lifecycle services: create_game, add_player, remove_player, start_game
  - Complete setup page with PRG-pattern routes
  - Dashboard stub template for post-start redirect
affects: [02-02-dashboard, 02-03-htmx, 04-svg-board]

# Tech tracking
tech-stack:
  added: [jinja2-fragments~=1.12.0, python-multipart>=0.0.18]
  patterns: [PRG (Post-Redirect-Get), Jinja2 template inheritance, sync route handlers]

key-files:
  created:
    - app/web/__init__.py
    - app/web/dependencies.py
    - app/web/routes.py
    - app/templates/base.html
    - app/templates/setup.html
    - app/templates/dashboard_stub.html
    - app/static/css/style.css
  modified:
    - pyproject.toml
    - app/main.py
    - app/services.py

key-decisions:
  - "PLAYER_COLORS in web/dependencies.py, COLOR_HEX_MAP in services.py to avoid circular imports"
  - "All routes use sync def (not async def) for sync SQLModel sessions"
  - "PRG pattern with 303 redirects for all POST routes"
  - "Dashboard header uses .header-dashboard class to avoid collision with setup .header"
  - "GameState sorts players by score_total DESC for dashboard; setup sorts by turn_order"

patterns-established:
  - "PRG pattern: POST routes return RedirectResponse(status_code=303)"
  - "Template context always includes PLAYER_COLORS dict for color lookups"
  - "Service functions raise ValueError for invalid operations; routes catch silently and redirect"
  - "Template inheritance: all pages extend base.html"

# Metrics
duration: 5min
completed: 2026-05-01
---

# Phase 2 Plan 1: Web Infrastructure & Setup Page Summary

**Jinja2Blocks template engine with HTMX CDN, merged prototype CSS, and complete setup page for game creation and player management**

## Performance

- **Duration:** 5 min
- **Started:** 2026-05-01T23:41:36Z
- **Completed:** 2026-05-01T23:46:57Z
- **Tasks:** 2
- **Files modified:** 10

## Accomplishments
- Wired Jinja2Blocks template engine with HTMX CDN into FastAPI app
- Extracted and merged CSS from both validated prototypes into unified stylesheet
- Implemented complete setup flow: create game, add/remove players (with color selector), start game
- Added game lifecycle service functions (create_game, add_player, remove_player, start_game)
- Added get_game_state() helper returning ranked players and action count

## Task Commits

Each task was committed atomically:

1. **Task 1: Web infrastructure** - `803e6ca` (feat)
2. **Task 2: Setup page routes and template** - `40f7ea5` (feat)

## Files Created/Modified
- `pyproject.toml` - Added jinja2-fragments and python-multipart dependencies
- `app/main.py` - Mounted static files, included web router
- `app/services.py` - Added GameState, get_game_state, create_game, add_player, remove_player, start_game
- `app/web/__init__.py` - Web package init
- `app/web/dependencies.py` - Jinja2Blocks templates instance, PLAYER_COLORS constant
- `app/web/routes.py` - 7 routes for setup flow and dashboard stub
- `app/templates/base.html` - HTML skeleton with HTMX CDN and CSS link
- `app/templates/setup.html` - Setup page with game name form, color selector, player list
- `app/templates/dashboard_stub.html` - Placeholder dashboard for started games
- `app/static/css/style.css` - Complete CSS merged from both prototype files

## Decisions Made
- PLAYER_COLORS defined in web/dependencies.py for template access; COLOR_HEX_MAP duplicated in services.py to avoid circular imports
- All POST routes use PRG pattern with 303 status codes as recommended by research
- Setup page uses radio buttons with hidden input for color selection (server-side form, no HTMX yet)
- Dashboard header given distinct class .header-dashboard to coexist with setup .header styles
- Service errors caught silently in routes and redirect back to setup (user sees current state)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Port 8001 was busy during verification; switched to 8002/8003 for testing

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Template engine, static files, and CSS all working -- dashboard plan (02-02) can build directly on this
- GameState helper and PLAYER_COLORS ready for dashboard template
- All 25 Phase 1 tests still passing (no regressions)
- Dashboard stub template placeholder ready to be replaced in 02-02

---
*Phase: 02-web-ui*
*Completed: 2026-05-01*
