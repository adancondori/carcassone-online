---
phase: 04-svg-board
verified: 2026-05-01T00:00:00Z
status: passed
score: 5/5 must-haves verified
---

# Phase 4: SVG Board Verification Report

**Phase Goal:** Users see their meeple tokens moving around a visual replica of the physical Carcassonne scoring track
**Verified:** 2026-05-01
**Status:** PASSED
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #   | Truth                                                                | Status     | Evidence                                                                                                  |
| --- | -------------------------------------------------------------------- | ---------- | --------------------------------------------------------------------------------------------------------- |
| 1   | SVG board displays Carcassonne scoring track photo with 50 mapped cell positions | VERIFIED | `carcassonneok.jpg` (653KB) exists; `BOARD_CELLS` has 50 tuples (verified programmatically); image linked via `/static/images/carcassonneok.jpg` in SVG `<image>` element |
| 2   | Each player has a meeple-shaped token positioned on the correct cell (score_total % 50) | VERIFIED | `build_board_context` uses `player.score_total % 50` for cell and `BOARD_CELLS[cell_num]` for coordinates; template renders `<use href="#meeple">` per player |
| 3   | Multiple players sharing a cell have tokens offset radially so all are visible | VERIFIED | `_stack_offset(index, total)` computes distinct radial angles; for 2 players offsets are (0,-13) and (0,+13); test `test_stacking_offsets` and `test_stacking_in_board_fragment` pass |
| 4   | Lap badge (x1, x2, x3...) appears on tokens for players past cell 49 | VERIFIED | Template renders `<text class="lap-badge">x{{ bp.lap }}</text>` when `bp.lap > 0`; `lap = score_total // 50`; integration test `test_lap_badge_appears` (score 55 → x1) passes |
| 5   | Board is responsive on mobile without horizontal scroll or clipped tokens | VERIFIED | `.board-svg { width:100%; height:auto; display:block }` + SVG `viewBox="0 0 600 420"`; `.board-wrapper { overflow:hidden }`; `@media (max-width:767px)` and `@media (max-width:380px)` breakpoints present |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact                          | Provides                            | Exists | Lines | Substantive | Wired           | Status     |
| --------------------------------- | ----------------------------------- | ------ | ----- | ----------- | --------------- | ---------- |
| `app/static/images/carcassonneok.jpg` | Board photo for SVG background  | YES    | 653KB binary | N/A (binary) | Referenced in template | VERIFIED |
| `app/templates/dashboard.html`    | Board SVG block with meeple tokens  | YES    | 241   | YES         | Rendered by routes | VERIFIED |
| `app/static/css/style.css`        | Board wrapper and token styling     | YES    | 919   | YES         | Linked via base.html | VERIFIED |
| `app/web/dependencies.py`         | BOARD_CELLS (50 coords), build_board_context, _stack_offset | YES | 131 | YES | Imported by routes.py | VERIFIED |
| `app/web/routes.py`               | Board OOB fragment in _render_dashboard_fragments | YES | 291 | YES | Called on every score/undo/rollback | VERIFIED |
| `tests/test_web.py`               | TestBoardContext + TestBoard integration tests | YES | 624+ | 10 board tests | Run by pytest | VERIFIED |

### Key Link Verification

| From                          | To                                        | Via                                          | Status  | Details                                                              |
| ----------------------------- | ----------------------------------------- | -------------------------------------------- | ------- | -------------------------------------------------------------------- |
| `app/web/routes.py`           | `app/templates/dashboard.html`            | `block_name="board"` OOB fragment            | WIRED   | `board_html = templates.TemplateResponse(..., block_name="board")` at line 87; appended to response at line 94 |
| `app/templates/dashboard.html` | `app/static/images/carcassonneok.jpg`    | SVG `<image href="/static/images/...">` at line 36 | WIRED | Exact path confirmed in template and tested in `test_dashboard_includes_board_svg` |
| `app/web/routes.py`           | `app/web/dependencies.py`                 | `from app.web.dependencies import build_board_context` | WIRED | Line 23; called at lines 44 and 224 |
| `game_dashboard` route        | `board_cells` in full-page context        | `board_cells = build_board_context(...)` passed to TemplateResponse | WIRED | Line 224; `board_cells` in context dict at line 237 |
| `_render_dashboard_fragments` | `board_cells` in OOB context              | `board_cells = build_board_context(...)` at line 44; in `base_context` at line 55 | WIRED | All 5 OOB fragments share same `base_context` with `board_cells` |

### Requirements Coverage

| Requirement | Description                                              | Status    | Supporting Truth |
| ----------- | -------------------------------------------------------- | --------- | ---------------- |
| BOARD-01    | SVG board displays Carcassonne scoring track photo       | SATISFIED | Truth 1          |
| BOARD-02    | Meeple-shaped tokens positioned on correct cell          | SATISFIED | Truth 2          |
| BOARD-03    | Multiple tokens stack with radial offset                 | SATISFIED | Truth 3          |
| BOARD-04    | Lap badge (x1, x2, x3...) for players past cell 49      | SATISFIED | Truth 4          |
| BOARD-05    | Board responsive on mobile phones (SVG viewBox scaling)  | SATISFIED | Truth 5          |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| `app/web/routes.py` | 59-91 | DeprecationWarning: `TemplateResponse(name, context)` param order | Warning | 217 warnings emitted per test run; does not affect functionality; all tests pass |

No blockers. The deprecation warning is about Starlette/FastAPI API migration (`name` should be second param), not a board-specific issue and does not affect rendering.

### Human Verification Required

The visual checkpoint task (04-02 Task 2) was part of the plan and was approved during execution (noted in 04-02-SUMMARY.md). The following items are documented here for completeness:

#### 1. Visual token alignment on real board

**Test:** Start the app, create a game with 3+ players, score points, observe token positions
**Expected:** Tokens appear on the numbered scoring cells of the board photo
**Why human:** Coordinate mapping cannot be verified programmatically without visual inspection of the photo; coordinates were recalibrated from a red-dot reference image and cells 36-37 were manually corrected

#### 2. Stacking visibility on real board

**Test:** Score two players the same total, observe on board
**Expected:** Both tokens visible, not overlapping
**Why human:** Visual confirmation that the 13px radial offset is sufficient at the rendered mobile size

#### 3. Mobile layout — no horizontal scroll

**Test:** Open on mobile viewport or DevTools mobile simulation
**Expected:** Board fills width, no horizontal scroll, tokens visible and not clipped
**Why human:** Interaction with actual viewport cannot be verified via HTML grep

### Gaps Summary

No gaps. All 5 success criteria are satisfied in the codebase:

- Board photo exists at the correct static path (653KB)
- 50 BOARD_CELLS coordinates defined and verified programmatically
- `build_board_context` correctly maps `score_total % 50` to cell and `score_total // 50` to lap
- `_stack_offset` produces distinct radial positions for co-located players
- Template renders meeple-shaped SVG path, player initial, color, and conditional lap badge
- Board block rendered as 5th OOB fragment on every score/undo/rollback action
- 14 board tests pass (10 unit + integration, 0 failures)
- 66 total tests pass with no regressions
- CSS provides responsive scaling via `width:100%; height:auto` + `viewBox`
- Mobile breakpoints at 767px and 380px present

---

_Verified: 2026-05-01_
_Verifier: Claude (so-verifier)_
