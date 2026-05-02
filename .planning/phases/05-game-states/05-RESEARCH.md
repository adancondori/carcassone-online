# Phase 5: Game States - Research

**Researched:** 2026-05-01
**Domain:** Application state machine, UI conditional rendering
**Confidence:** HIGH

## Summary

Phase 5 implements a game lifecycle state machine (setup -> playing -> scoring -> finished) with enforcement at the service and UI layers. This is an application-logic phase, not a library/framework integration -- all the tools are already in the stack.

The critical finding is that **most of the data model infrastructure already exists**: the `Game.status` field with its CHECK constraint already supports all four states, `start_game()` handles setup->playing, and the event types are already split into "completed" and "final" categories in both the DB constraint and `EVENT_TYPE_LABELS`. What's missing is: (a) two new transition functions (playing->scoring, scoring->finished), (b) event-type validation in `add_score()` based on game state, (c) UI that adapts the available controls per state, and (d) a read-only finished screen.

**Primary recommendation:** Implement as three layers -- service functions enforce state transitions and event-type filtering, routes check game state before allowing mutations, and templates conditionally render controls based on `game.status`. No new database columns or migrations needed.

## Standard Stack

### Core

No new libraries needed. This phase uses existing stack components:

| Component | Already In Place | Purpose for Phase 5 |
|-----------|-----------------|---------------------|
| Game.status field | Yes (models.py) | Stores current state with CHECK constraint |
| CHECK constraint | Yes (`'setup', 'playing', 'scoring', 'finished'`) | DB-level validation of valid states |
| EVENT_TYPE_LABELS | Yes (dependencies.py) | Labels already categorized by completed/final |
| start_game() | Yes (services.py) | Existing setup->playing transition pattern |
| Jinja2 conditionals | Yes (templates) | `{% if game.status == 'playing' %}` for UI switching |
| HTMX OOB fragments | Yes (routes.py) | Fragment pattern extends naturally |

### Supporting

No additional libraries or tools required.

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Simple string status + if/elif | Python Enum for states | Enum is cleaner for code but the status field is already a string in the DB and throughout the codebase; converting adds migration and refactoring cost for no Phase 5 benefit |
| Manual state checks | python-statemachine library | Overkill for 4 linear states; adds dependency for what amounts to 3 if-statements |
| Server-side event type filtering | Client-side JS filtering | Server-side is authoritative; JS can show/hide for UX but service must enforce |

## Architecture Patterns

### Pattern 1: State-Grouped Event Types (Confidence: HIGH)

Define which event types are valid in each game state as constants, then validate in `add_score()`.

**Source:** Derived from existing codebase patterns (event_type CHECK constraint + EVENT_TYPE_LABELS)

```python
# In services.py (or models.py alongside BOARD_SIZE)
PLAYING_EVENT_TYPES = {
    "ROAD_COMPLETED", "CITY_COMPLETED", "MONASTERY_COMPLETED", "MANUAL"
}
SCORING_EVENT_TYPES = {
    "ROAD_FINAL", "CITY_FINAL", "MONASTERY_FINAL", "FARM_FINAL", "MANUAL"
}
```

**Why constants, not function lookups:** These sets are fixed by Carcassonne rules. Hardcoding them as frozensets is simpler and faster than any dynamic approach. MANUAL appears in both because manual adjustments are valid at any scoring stage.

### Pattern 2: Transition Functions Following start_game() Pattern (Confidence: HIGH)

The existing `start_game()` shows the pattern: validate current state, check preconditions, update status, commit.

```python
def begin_scoring(session: Session, game_id: int) -> Game:
    """Transition from playing to scoring (final scoring phase)."""
    game = session.get(Game, game_id)
    if game.status != "playing":
        raise ValueError("Can only begin scoring from playing state")
    game.status = "scoring"
    session.commit()
    session.refresh(game)
    return game

def finish_game(session: Session, game_id: int) -> Game:
    """Transition from scoring to finished."""
    game = session.get(Game, game_id)
    if game.status != "scoring":
        raise ValueError("Can only finish a game from scoring state")
    game.status = "finished"
    session.commit()
    session.refresh(game)
    return game
```

**Key design choice:** These are separate functions (not a generic `transition(game_id, new_state)`) because:
1. Each transition may have different preconditions (e.g., `begin_scoring` could warn about unscored structures)
2. Follows existing pattern established by `start_game()`
3. Makes the callsite readable: `begin_scoring(session, game_id)` vs `transition(session, game_id, "scoring")`

### Pattern 3: Event Type Validation in add_score() (Confidence: HIGH)

The `add_score()` function must validate that the event_type is allowed for the current game state. This is the enforcement layer.

```python
def add_score(session, game_id, player_points, event_type, description=None):
    game = session.get(Game, game_id)
    if game is None:
        raise ValueError(f"Game {game_id} not found")

    # State-based event type validation
    if game.status == "playing" and event_type not in PLAYING_EVENT_TYPES:
        raise ValueError(f"Event type '{event_type}' not allowed during playing phase")
    elif game.status == "scoring" and event_type not in SCORING_EVENT_TYPES:
        raise ValueError(f"Event type '{event_type}' not allowed during scoring phase")
    elif game.status in ("setup", "finished"):
        raise ValueError(f"Cannot score in '{game.status}' state")

    # ... existing logic
```

**Important:** This validation goes in the service layer, not just the UI. The UI controls which buttons appear, but the service is the authority.

### Pattern 4: Template Conditional Controls (Confidence: HIGH)

The dashboard template switches which event type radio buttons are shown based on `game.status`. The same Jinja2 conditional pattern used for `{% if oob %}` extends naturally.

```html
<!-- Event type buttons vary by game state -->
<div class="type-buttons">
    {% if game.status == 'playing' %}
        <label class="type-btn active">
            <input type="radio" name="event_type" value="CITY_COMPLETED" checked>
            Ciudad
        </label>
        <label class="type-btn">
            <input type="radio" name="event_type" value="ROAD_COMPLETED">
            Camino
        </label>
        <label class="type-btn">
            <input type="radio" name="event_type" value="MONASTERY_COMPLETED">
            Monasterio
        </label>
    {% elif game.status == 'scoring' %}
        <label class="type-btn active">
            <input type="radio" name="event_type" value="CITY_FINAL" checked>
            Ciudad
        </label>
        <label class="type-btn">
            <input type="radio" name="event_type" value="ROAD_FINAL">
            Camino
        </label>
        <label class="type-btn">
            <input type="radio" name="event_type" value="MONASTERY_FINAL">
            Monasterio
        </label>
        <label class="type-btn">
            <input type="radio" name="event_type" value="FARM_FINAL">
            Granja
        </label>
    {% endif %}
    <!-- MANUAL always available in both playing and scoring -->
    {% if game.status in ['playing', 'scoring'] %}
        <label class="type-btn">
            <input type="radio" name="event_type" value="MANUAL">
            Manual
        </label>
    {% endif %}
</div>
```

### Pattern 5: Finished State as Read-Only View (Confidence: HIGH)

When `game.status == 'finished'`, the dashboard shows only the final ranking without any controls, scoring form, or undo/rollback buttons. This could be:

1. **Same template with conditionals** -- wrap controls/action_bar in `{% if game.status != 'finished' %}`, add a "results" block shown only when finished
2. **Separate template** -- `finished.html` extending base.html with just the ranking table

**Recommendation:** Same template with conditionals. The score table, history, and board (Phase 4) should all still display -- only the interactive controls are removed. A new "final ranking" header/section replaces the controls area.

### Pattern 6: State Transition UI (Confidence: HIGH)

The user needs buttons to trigger state transitions:
- **"Puntuacion final" button** on the dashboard during `playing` state -- triggers playing->scoring
- **"Terminar partida" button** on the dashboard during `scoring` state -- triggers scoring->finished

These are POST routes following the PRG pattern (303 redirect back to dashboard), identical to `/games/{id}/start`.

```python
@router.post("/games/{game_id}/begin-scoring")
def begin_scoring_route(game_id, session=Depends(get_session)):
    try:
        begin_scoring(session, game_id)
    except ValueError:
        pass
    return RedirectResponse(url=f"/games/{game_id}", status_code=303)
```

**Placement in UI:** The transition buttons should be prominent and distinct from scoring controls. The "Puntuacion final" button indicates the game is ending and switches to final scoring mode. The "Terminar partida" button finalizes everything.

### Anti-Patterns to Avoid

- **Client-only enforcement:** Do NOT rely solely on hiding UI buttons to enforce state rules. The service layer must validate. A user could submit a form with an invalid event_type via browser dev tools.
- **Generic state machine library:** The state graph is trivially linear (4 states, 3 transitions). A library adds complexity with zero benefit.
- **Backward transitions:** The requirements explicitly say "no going backward." Do not implement scoring->playing or finished->scoring. If a user made a mistake by transitioning too early, they should undo scores or rollback, not revert the state.
- **Status field on ScoreAction:** Do not add a "phase" column to ScoreAction to track which state it was created in. The event_type itself encodes this (COMPLETED = playing, FINAL = scoring).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Event type categorization | Runtime string parsing to detect "COMPLETED" vs "FINAL" | Static set constants (PLAYING_EVENT_TYPES, SCORING_EVENT_TYPES) | Explicit is better than implicit; no fragile string matching |
| State validation | Inline if/elif in every route | Centralized check in `add_score()` + separate `validate_game_state()` if needed | Single source of truth for state rules |

**Key insight:** This phase is almost entirely application logic. There are no libraries to integrate -- just careful placement of validation and conditional rendering using tools already in the stack.

## Common Pitfalls

### Pitfall 1: Forgetting to Guard undo_last and rollback_to in Finished State
**What goes wrong:** User in finished state can still hit undo/rollback via direct request, modifying a "read-only" game.
**Why it happens:** The undo/rollback service functions don't check game state -- they were written before states existed.
**How to avoid:** Add game state check at the top of `undo_last()` and `rollback_to()`:
```python
game = session.get(Game, game_id)
if game.status == "finished":
    raise ValueError("Cannot modify a finished game")
```
**Warning signs:** Test for undo in finished state passes when it should raise.

### Pitfall 2: OOB Fragments Not Updating After State Transition
**What goes wrong:** User clicks "Puntuacion final" (playing->scoring), page redirects, but the controls still show "playing" event types because the fragment cache wasn't refreshed.
**Why it happens:** PRG redirect loads the full page via GET, but if there's a stale HTMX fragment somewhere, controls may be wrong.
**How to avoid:** State transitions use PRG (full page redirect via 303), which forces a complete page load. The GET handler for the dashboard reads `game.status` fresh from DB and renders the correct controls. This naturally works correctly -- the risk is only if you try to return HTMX fragments from the transition route instead of redirecting.

### Pitfall 3: MANUAL Event Type Dual Membership
**What goes wrong:** MANUAL is valid in both playing and scoring states. If the validation logic uses exclusive sets, MANUAL might be rejected in one state.
**Why it happens:** Copy-paste error or overly strict set definitions.
**How to avoid:** Ensure MANUAL is in BOTH `PLAYING_EVENT_TYPES` and `SCORING_EVENT_TYPES`. Unit test that MANUAL is accepted in both states.

### Pitfall 4: Dashboard Route Not Handling All States
**What goes wrong:** GET `/games/{id}` only handles "setup" (redirect) and implicitly "playing". After adding "scoring" and "finished", the route might render incorrectly.
**Why it happens:** The current `game_dashboard` route assumes any non-setup game is in playing state.
**How to avoid:** The route should handle all states:
- `setup` -> redirect to `/games/{id}/setup` (already done)
- `playing` -> dashboard with completed event types
- `scoring` -> dashboard with final event types
- `finished` -> dashboard with read-only results view

The template conditionals handle playing/scoring/finished differentiation, so the route itself just needs to pass `game.status` to the template (which it already does via `game_state.game`).

### Pitfall 5: Undo During Scoring State Might Need to Revert State
**What goes wrong:** User transitions to scoring, scores some final points, then realizes they need to go back to playing. There's no backward transition.
**Why it happens:** The requirements say "no going backward" but real game scenarios may need flexibility.
**How to avoid:** This is a **design decision, not a bug**. The requirements are clear: no backward transitions. The user can undo/rollback individual scoring actions, but the state machine only moves forward. If this becomes a usability issue, it's a future enhancement, not a Phase 5 concern. Document this clearly in the UI (e.g., confirmation dialog on "Puntuacion final").

### Pitfall 6: Missing Alembic Migration for Schema Changes
**What goes wrong:** Developer expects a migration is needed and creates an empty/broken one.
**Why it happens:** Muscle memory from Phases 1-2 where migrations were required.
**How to avoid:** **No migration is needed for Phase 5.** The Game.status CHECK constraint already includes all four states (`'setup', 'playing', 'scoring', 'finished'`). The event_type constraint already includes all event types. No new columns or tables are added. Verify by running `alembic check` or `alembic revision --autogenerate` -- it should produce no changes.

## Code Examples

### State Transition Service Functions

```python
# services.py -- new functions following start_game() pattern

PLAYING_EVENT_TYPES = frozenset({
    "ROAD_COMPLETED", "CITY_COMPLETED", "MONASTERY_COMPLETED", "MANUAL"
})
SCORING_EVENT_TYPES = frozenset({
    "ROAD_FINAL", "CITY_FINAL", "MONASTERY_FINAL", "FARM_FINAL", "MANUAL"
})

def begin_scoring(session: Session, game_id: int) -> Game:
    """Transition game from playing to scoring (final scoring phase)."""
    game = session.get(Game, game_id)
    if game is None:
        raise ValueError(f"Game {game_id} not found")
    if game.status != "playing":
        raise ValueError("Can only begin scoring from playing state")
    game.status = "scoring"
    session.commit()
    session.refresh(game)
    return game

def finish_game(session: Session, game_id: int) -> Game:
    """Transition game from scoring to finished."""
    game = session.get(Game, game_id)
    if game is None:
        raise ValueError(f"Game {game_id} not found")
    if game.status != "scoring":
        raise ValueError("Can only finish a game from scoring state")
    game.status = "finished"
    session.commit()
    session.refresh(game)
    return game
```

### Event Type Validation in add_score()

```python
def add_score(session, game_id, player_points, event_type, description=None):
    game = session.get(Game, game_id)
    if game is None:
        raise ValueError(f"Game {game_id} not found")
    if game.status == "playing" and event_type not in PLAYING_EVENT_TYPES:
        raise ValueError(f"Event type '{event_type}' not allowed in playing state")
    if game.status == "scoring" and event_type not in SCORING_EVENT_TYPES:
        raise ValueError(f"Event type '{event_type}' not allowed in scoring state")
    if game.status not in ("playing", "scoring"):
        raise ValueError(f"Cannot add scores in '{game.status}' state")
    # ... rest of existing logic unchanged
```

### Finished State Guard on Undo/Rollback

```python
def undo_last(session, game_id):
    game = session.get(Game, game_id)
    if game is None:
        raise ValueError(f"Game {game_id} not found")
    if game.status == "finished":
        raise ValueError("Cannot undo in a finished game")
    # ... rest of existing logic

def rollback_to(session, game_id, action_id):
    game = session.get(Game, game_id)
    if game is None:
        raise ValueError(f"Game {game_id} not found")
    if game.status == "finished":
        raise ValueError("Cannot rollback in a finished game")
    # ... rest of existing logic
```

### Transition Routes

```python
@router.post("/games/{game_id}/begin-scoring")
def begin_scoring_route(game_id: int, session: Session = Depends(get_session)):
    """Transition from playing to final scoring phase."""
    try:
        begin_scoring(session, game_id)
    except ValueError:
        pass
    return RedirectResponse(url=f"/games/{game_id}", status_code=303)

@router.post("/games/{game_id}/finish")
def finish_game_route(game_id: int, session: Session = Depends(get_session)):
    """Transition from scoring to finished state."""
    try:
        finish_game(session, game_id)
    except ValueError:
        pass
    return RedirectResponse(url=f"/games/{game_id}", status_code=303)
```

### Template Status Display

```html
<div class="header-status">
    {% if game.status == 'playing' %}En juego{% endif %}
    {% if game.status == 'scoring' %}Puntuacion final{% endif %}
    {% if game.status == 'finished' %}Finalizada{% endif %}
</div>
```

### Template Conditional for Finished State

```html
{% if game.status != 'finished' %}
    {# Controls, action bar, scoring form #}
    {% block controls %}...{% endblock %}
    {% block action_bar %}...{% endblock %}
{% else %}
    {# Read-only results view #}
    <div class="results-banner">
        <h2>Partida finalizada</h2>
        {# Winner announcement, final ranking shown via score table above #}
    </div>
{% endif %}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| No game states (always "playing") | Four-state lifecycle | Phase 1 (schema ready) | Phase 5 adds enforcement layer on existing schema |

**Deprecated/outdated:**
- Nothing deprecated. The schema was forward-designed in Phase 1 to support all four states.

## Open Questions

1. **Should "Begin Scoring" require confirmation?**
   - What we know: Transitioning to scoring limits available event types (no more completed structures). This is significant.
   - What's unclear: Whether users will accidentally hit the button.
   - Recommendation: Add an `hx-confirm` or a browser confirm dialog on the "Puntuacion final" button, similar to rollback confirmation. Low-cost safety measure.

2. **Should undo/rollback be allowed during "scoring" state?**
   - What we know: The requirements say finished is read-only, but don't explicitly address undo during scoring.
   - What's unclear: Whether users should be able to undo playing-phase actions while in scoring state.
   - Recommendation: Allow undo/rollback during both playing and scoring states. Only finished is truly locked. Users may realize a game-phase score was wrong during final scoring.

3. **Should the finished screen have a "New Game" button?**
   - What we know: The requirements mention "final ranking" but don't specify navigation from finished state.
   - What's unclear: Whether to link back to `/games/new` from the results screen.
   - Recommendation: Yes, add a "Nueva partida" link/button on the finished screen. Simple UX improvement with no downside.

4. **What happens if game has zero scoring actions and user transitions to scoring/finished?**
   - What we know: No precondition check exists (unlike start_game which requires >= 2 players).
   - What's unclear: Whether this is a valid scenario.
   - Recommendation: Allow it. A game could legitimately have zero scores before final scoring. Don't over-constrain.

## Sources

### Primary (HIGH confidence)
- Existing codebase (`app/models.py`, `app/services.py`, `app/web/routes.py`, `app/templates/dashboard.html`) -- all patterns derived from code already written and tested
- `alembic/versions/531e052bb60d_initial_schema.py` -- confirms CHECK constraint already supports all 4 states
- `app/web/dependencies.py` -- EVENT_TYPE_LABELS already categorize completed vs final

### Secondary (MEDIUM confidence)
- Phase 3 plans (`03-01-PLAN.md`, `03-02-PLAN.md`) -- Phase 5 depends on Phase 3 being complete; history/rollback patterns inform how state guards integrate

### Tertiary (LOW confidence)
- None. This phase is entirely application logic within the existing stack.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new libraries; everything exists in codebase
- Architecture: HIGH -- patterns derived directly from existing code (start_game, add_score, template conditionals)
- Pitfalls: HIGH -- pitfalls identified from reading the actual code and spotting guard-check gaps

**Research date:** 2026-05-01
**Valid until:** No expiry (application logic, not library-dependent)
