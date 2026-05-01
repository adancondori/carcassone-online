# Phase 2: Web UI - Research

**Researched:** 2026-05-01
**Domain:** FastAPI + Jinja2 + HTMX server-rendered web UI with partial fragment updates
**Confidence:** HIGH

## Summary

Phase 2 transforms the Phase 1 foundation (models, services, DB, tests) into the first end-to-end playable web application. The core challenge is implementing the HTMX fragment swap pattern correctly: a single POST (score, undo) must return multiple HTML fragments that update the score table and controls simultaneously without a full page reload.

The stack is well-established: FastAPI's built-in `Jinja2Templates` handles server-side rendering, HTMX's `hx-swap-oob` attribute enables multi-region updates from a single response, and `jinja2-fragments` (via `Jinja2Blocks`) eliminates template duplication by rendering individual `{% block %}` sections from the same template used for full page loads.

The critical architectural decision is using `hx-swap-oob` for multi-fragment responses rather than separate HTMX requests per UI section. This ensures the score table and controls always reflect the same database state, avoiding visual inconsistencies.

**Primary recommendation:** Use `jinja2-fragments` `Jinja2Blocks` as a drop-in replacement for FastAPI's `Jinja2Templates`. Define each dashboard section (score table, controls, action bar) as a named `{% block %}` in `dashboard.html`. For full page loads, render the complete template. For HTMX POST responses, render the primary target block plus OOB blocks in a single response, assembled via HTMLResponse string concatenation.

## Standard Stack

### Core (already in Phase 1)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | ~=0.136.1 | Web framework, routes, dependency injection | Already installed in Phase 1 |
| Jinja2 | >=3.1.6 (transitive) | Server-side HTML templating | Pulled in by FastAPI/Starlette |
| HTMX | 2.0.10 (CDN) | Browser-side partial page updates via HTML | No npm, no build step, CDN script tag |
| Vanilla JS | ES2022+ | Ephemeral UI state (selected players, points) | Only for scoring form interactivity |

### New Dependencies for Phase 2

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| jinja2-fragments | ~=1.12.0 | Render individual template blocks for HTMX partial responses | Eliminates template duplication between full pages and fragments. Drop-in replacement for Jinja2Templates. |
| python-multipart | >=0.0.18 | Parse form POST data in FastAPI | Required by FastAPI for `Form()` parameter extraction. May already be installed in Phase 1 -- verify. |

### Dependencies to Verify from Phase 1

Phase 1 plan lists `jinja2` as a dependency but does NOT list `python-multipart`. The STACK.md research includes `python-multipart>=0.0.18` in the pyproject.toml example. Phase 2 must verify this dependency exists or add it.

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| jinja2-fragments | Separate fragment template files | Works but violates DRY -- same HTML defined in dashboard.html AND in fragments/score_table.html. Divergence over time is guaranteed. |
| jinja2-fragments | fasthx or fastapi-htmx libraries | Add decorator abstraction over FastAPI's built-in templates. For a 5-route web app, the abstraction adds complexity without benefit. |
| hx-swap-oob (multi-fragment) | Separate HTMX requests per section | Multiple HTTP round-trips, multiple DB queries, visual inconsistency between fragments during update window. |
| HTMLResponse concatenation | hx-select-oob on client side | Client-side OOB selection requires the response to contain all content and htmx selects from it. Less explicit than server-side OOB attributes. |

**Installation:**
```bash
# Add to pyproject.toml dependencies
pip install jinja2-fragments~=1.12.0 python-multipart>=0.0.18
```

## Architecture Patterns

### Recommended Project Structure (Phase 2 additions)

```
app/
  main.py                 # Add template engine, static files mount, include routers
  models.py               # (from Phase 1 -- no changes)
  services.py             # (from Phase 1 -- no changes)
  db.py                   # (from Phase 1 -- no changes)
  web/
    __init__.py
    routes.py             # Web routes: setup page, dashboard, score, undo
    dependencies.py       # Shared dependencies: get_session, get_game_or_404
  templates/
    base.html             # HTML skeleton: <head>, CSS, HTMX script, body wrapper
    setup.html            # Full page: game creation + player management (extends base)
    dashboard.html        # Full page: scoring dashboard (extends base, defines blocks)
    fragments/
      score_update.html   # Multi-fragment OOB response assembler for score/undo
  static/
    css/
      style.css           # Extracted from prototype CSS (CSS variables, responsive)
    js/
      controls.js         # Ephemeral UI state for scoring form (player selection, point selection)
```

### Pattern 1: Jinja2Blocks for Full Page + Fragment Rendering

**What:** Replace `Jinja2Templates` with `Jinja2Blocks` from jinja2-fragments. Define each dashboard section as a named block. Full page loads render the complete template; HTMX responses render individual blocks.

**When to use:** Every route that serves HTML.

**Example:**

```python
# app/web/routes.py
from jinja2_fragments.fastapi import Jinja2Blocks

templates = Jinja2Blocks(directory="app/templates")

@router.get("/games/{game_id}")
def dashboard(request: Request, game_id: int, session: Session = Depends(get_session)):
    game_state = get_game_state(session, game_id)
    return templates.TemplateResponse(
        request, "dashboard.html",
        {"game": game_state.game, "players": game_state.players}
    )
```

```html
<!-- app/templates/dashboard.html -->
{% extends "base.html" %}

{% block content %}
<div class="main-workspace">
  <div class="main-column">
    {% block score_table %}
    <div id="score-table" class="score-table-wrapper">
      <table class="score-table">
        <!-- score table rows -->
      </table>
    </div>
    {% endblock %}
  </div>

  {% block controls %}
  <div id="controls" class="controls">
    <!-- scoring controls form -->
  </div>
  {% endblock %}
</div>

{% block action_bar %}
<div id="action-bar" class="action-bar">
  <!-- undo button, etc. -->
</div>
{% endblock %}
{% endblock %}
```

**Source:** [jinja2-fragments FastAPI integration docs](https://github.com/sponsfreixes/jinja2-fragments) (verified via Context7)

### Pattern 2: Multi-Fragment OOB Response for Score/Undo

**What:** A single POST to `/games/{id}/score` returns the primary target (score table) plus out-of-band fragments (controls reset, action bar update). HTMX swaps the primary target normally and swaps OOB fragments by matching element IDs.

**When to use:** Every mutating endpoint (score, undo) that needs to update multiple dashboard sections.

**Example:**

```python
# app/web/routes.py
from fastapi.responses import HTMLResponse

@router.post("/games/{game_id}/score")
def score_action(request: Request, game_id: int, session: Session = Depends(get_session)):
    form = await request.form()
    # ... parse form, call add_score service ...
    game_state = get_game_state(session, game_id)
    context = {"request": request, "game": game_state.game, "players": game_state.players}

    # Render primary target: score table
    score_table_html = templates.TemplateResponse(
        request, "dashboard.html", context, block_name="score_table"
    ).body.decode()

    # Render OOB fragment: action bar (undo button state may change)
    action_bar_html = templates.TemplateResponse(
        request, "dashboard.html", context, block_name="action_bar"
    ).body.decode()

    # Concatenate: primary + OOB fragments
    # The OOB fragment needs hx-swap-oob="true" attribute
    combined = score_table_html + action_bar_html
    return HTMLResponse(content=combined)
```

**Important OOB detail:** The OOB fragment elements must have `hx-swap-oob="true"` in their HTML and an `id` matching the target element in the page. This can be set in the template block itself:

```html
{% block action_bar %}
<div id="action-bar" class="action-bar" {% if oob %}hx-swap-oob="true"{% endif %}>
  <!-- content -->
</div>
{% endblock %}
```

Pass `oob=True` in context when rendering for HTMX responses, `oob=False` (or omit) for full page loads.

**Source:** [HTMX hx-swap-oob documentation](https://htmx.org/attributes/hx-swap-oob/) (verified via Context7)

### Pattern 3: HX-Request Header Detection

**What:** Check for the `HX-Request` header to determine whether to return a full page or fragments. Useful for the dashboard GET route to support both initial page load and HTMX-driven navigation.

**When to use:** Routes that serve both full pages and partial updates from the same URL.

**Example:**

```python
@router.get("/games/{game_id}")
def dashboard(request: Request, game_id: int, session: Session = Depends(get_session)):
    game_state = get_game_state(session, game_id)
    context = {"request": request, "game": game_state.game, "players": game_state.players}

    if request.headers.get("HX-Request"):
        # HTMX request: return only the content block
        return templates.TemplateResponse(
            request, "dashboard.html", context, block_name="content"
        )
    # Normal request: return full page
    return templates.TemplateResponse(request, "dashboard.html", context)
```

**Source:** [HTMX request headers](https://htmx.org/docs/) -- `HX-Request` is always "true" for HTMX-initiated requests (verified via Context7)

### Pattern 4: Thin Routes, Fat Services

**What:** Route handlers parse form data, call service functions, build template context, and return HTML. Zero business logic in routes. Zero database queries in routes (except via services).

**When to use:** Every route.

**Example:**

```python
@router.post("/games/{game_id}/score")
def score_action(
    game_id: int,
    request: Request,
    player_ids: list[int] = Form(...),
    points: int = Form(...),
    event_type: str = Form(...),
    description: str = Form(None),
    session: Session = Depends(get_session),
):
    player_points = [(pid, points) for pid in player_ids]
    add_score(session, game_id, player_points, event_type, description)
    game_state = get_game_state(session, game_id)
    # render and return fragments...
```

### Pattern 5: Form POST with HTMX from Dashboard Controls

**What:** The scoring form uses `hx-post` to submit to the server. The form serializes selected players, points, event type, and optional note as form data. HTMX swaps the response fragments into the DOM.

**When to use:** The scoring controls section of the dashboard.

**Example:**

```html
<form id="score-form"
      hx-post="/games/{{ game.id }}/score"
      hx-target="#score-table"
      hx-swap="outerHTML">

  <!-- Player selection (checkboxes) -->
  {% for player in players %}
  <label class="player-chip">
    <input type="checkbox" name="player_ids" value="{{ player.id }}">
    <span class="chip-dot" style="background:{{ player.color_hex }}"></span>
    {{ player.name }}
  </label>
  {% endfor %}

  <!-- Event type (radio buttons) -->
  <input type="radio" name="event_type" value="CITY_COMPLETED" checked> Ciudad
  <input type="radio" name="event_type" value="ROAD_COMPLETED"> Camino
  <!-- ... -->

  <!-- Points (radio or hidden input set by JS) -->
  <input type="hidden" name="points" id="points-input" value="">

  <!-- Note -->
  <input type="text" name="description" placeholder="Nota opcional">

  <button type="submit">Anotar puntos</button>
</form>
```

**Key detail:** The point buttons (+1, +2, +3, etc.) are NOT submit buttons. They are JS-driven toggles that set the hidden `points` input value. Only the "Anotar puntos" submit button triggers the `hx-post`.

**Source:** [HTMX hx-post documentation](https://htmx.org/attributes/hx-post/) (verified via Context7)

### Anti-Patterns to Avoid

- **Client-side state duplication:** The prototype (`dashboard.html`) maintains a full JS state object (`let state = {...}`). The real app must NOT replicate this. Server is the single source of truth. The only client-side "state" is ephemeral UI state: which players are selected, which point button is active, which event type is chosen. This resets after each submission.

- **Separate JSON API + HTML routes:** Do NOT build `/api/games/{id}/score` (JSON) alongside `/games/{id}/score` (HTML). Only HTML routes exist in Phase 2. JSON API is YAGNI.

- **Fat templates with business logic:** Templates must NOT calculate scores, sort players, or validate input. All derived values (current_cell, lap, ranking) are computed in Python and passed as ready-to-render context.

- **Individual HTMX requests per fragment:** Do NOT fire three separate requests to update score table, controls, and action bar. Use `hx-swap-oob` for single-request multi-fragment updates.

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Template fragment rendering | Custom template splitting into separate files | jinja2-fragments `Jinja2Blocks` with `block_name` | Keeps full page and fragment rendering in sync from the same template. Eliminates drift between duplicate templates. |
| Form data parsing | Manual `request.body()` parsing | FastAPI `Form()` + python-multipart | Type-safe, validated form parameter extraction. Handles multipart encoding automatically. |
| Static file serving | Custom file serving routes | FastAPI `StaticFiles` mount | Built-in, caching headers, proper MIME types. |
| CSS responsive layout | Custom media query framework | CSS Grid + Flexbox + existing prototype CSS | The prototypes already have working responsive CSS. Extract and reuse. |
| HTMX CDN inclusion | Self-hosting HTMX | `<script src="https://unpkg.com/htmx.org@2.0.10">` | Pinned version, no build step, CDN caching. |

**Key insight:** The prototypes (`docs/prototype/setup.html` and `docs/prototype/dashboard.html`) contain production-ready CSS and interaction patterns. Extract the CSS variables, layout styles, and component styles from the prototypes rather than redesigning from scratch.

## Common Pitfalls

### Pitfall 1: OOB Fragment ID Mismatch

**What goes wrong:** The `id` attribute on the OOB fragment in the server response does not match the `id` of the element in the page DOM. HTMX silently ignores the OOB swap -- no error, no warning, no update.
**Why it happens:** Typo in template, or the element ID was changed in one place but not the other. HTMX does not log a warning when an OOB target is not found.
**How to avoid:** Define element IDs as Jinja2 variables or constants. Use the SAME template block for both full page and fragment rendering (this is why jinja2-fragments matters). Add integration tests that verify OOB elements are present in responses and match page DOM IDs.
**Warning signs:** After scoring, the score table updates but the action bar does not. Page refresh fixes it.

### Pitfall 2: Form POST Returns Full Page Instead of Fragment

**What goes wrong:** The scoring form submits via `hx-post` but the route returns a full `dashboard.html` page instead of just the score table fragment. HTMX replaces the target with an entire HTML document, breaking the layout.
**Why it happens:** Route does not check for HTMX request, or does not use `block_name` parameter, or the `hx-target` is wrong.
**How to avoid:** Mutating endpoints (POST score, POST undo) should ALWAYS return fragments, never full pages. Non-mutating endpoints (GET dashboard) return full page by default, fragments when HX-Request header is present.
**Warning signs:** After scoring, the page "flashes" or the entire page content appears inside the score table div.

### Pitfall 3: `async def` with Sync DB Calls Blocks Event Loop

**What goes wrong:** Route handlers declared as `async def` call synchronous SQLAlchemy/SQLModel session methods, blocking the FastAPI event loop.
**Why it happens:** Default habit of using `async def` in FastAPI.
**How to avoid:** Use `def` (not `async def`) for ALL route handlers that perform synchronous database operations. FastAPI automatically runs sync handlers in a thread pool. This is explicitly documented in FastAPI's concurrency docs.
**Warning signs:** Response times spike when multiple requests arrive simultaneously (even just 2-3).

### Pitfall 4: Form Data Requires python-multipart

**What goes wrong:** FastAPI raises `RuntimeError: Form data requires "python-multipart" to be installed` when a route uses `Form()` parameters.
**Why it happens:** `python-multipart` is not a transitive dependency of FastAPI -- it must be explicitly installed.
**How to avoid:** Ensure `python-multipart>=0.0.18` is in pyproject.toml dependencies. Verify early by testing a form POST route.
**Warning signs:** Runtime error on first form submission attempt.

### Pitfall 5: Scoring Form State Not Reset After Submission

**What goes wrong:** After submitting a score, the player selection checkboxes, point buttons, and event type selection remain in their previous state. The user accidentally submits the same score again.
**Why it happens:** HTMX swaps only the targeted elements. The form controls are outside the swap target and retain their DOM state.
**How to avoid:** Either: (a) include the controls form in the OOB swap response (reset it server-side), or (b) use `HX-Trigger` response header to fire a client-side reset event, or (c) make the form itself the HTMX target and return a fresh empty form. Option (a) is recommended for this project because it follows the server-as-truth pattern.
**Warning signs:** Users submit duplicate scores.

### Pitfall 6: Setup Page Player Management Without HTMX

**What goes wrong:** The setup page (create game, add/remove players) tries to use HTMX for everything, but player management during setup is better handled with standard form POSTs and redirects because the page state is simpler.
**Why it happens:** Over-applying HTMX to pages where traditional form submission works fine.
**How to avoid:** For the setup page, use standard POST + redirect (PRG pattern). HTMX is valuable for the dashboard where partial updates avoid losing the user's position/context. Setup is a linear flow where full page reloads are fine. Alternatively, use HTMX with `hx-post` and swap the player list only, which also works well.
**Warning signs:** Overcomplicated setup page with many HTMX attributes that could be a simple form.

## Code Examples

Verified patterns from official sources:

### FastAPI + Jinja2Blocks Setup

```python
# app/main.py
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from jinja2_fragments.fastapi import Jinja2Blocks

app = FastAPI(title="Carcassonne Scoreboard")

# Static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Templates
templates = Jinja2Blocks(directory="app/templates")
```

Source: [jinja2-fragments README](https://github.com/sponsfreixes/jinja2-fragments) (verified via Context7, HIGH confidence)

### HTMX OOB Multi-Fragment Response

```python
# Assembling multiple fragments in one response
from fastapi.responses import HTMLResponse

def render_score_update(request, templates, context):
    """Render score table + OOB action bar as a single response."""
    # Primary target: score table (swapped via hx-target)
    context_primary = {**context, "oob": False}
    score_html = templates.TemplateResponse(
        request, "dashboard.html", context_primary, block_name="score_table"
    ).body.decode()

    # OOB: action bar (swapped via hx-swap-oob="true" on the element)
    context_oob = {**context, "oob": True}
    action_bar_html = templates.TemplateResponse(
        request, "dashboard.html", context_oob, block_name="action_bar"
    ).body.decode()

    return HTMLResponse(content=score_html + action_bar_html)
```

Source: Pattern derived from [HTMX hx-swap-oob docs](https://htmx.org/attributes/hx-swap-oob/) + [jinja2-fragments block_name](https://github.com/sponsfreixes/jinja2-fragments) (HIGH confidence)

### Dashboard Template with Named Blocks

```html
<!-- app/templates/dashboard.html -->
{% extends "base.html" %}
{% block content %}

<div class="container">
  <div class="header">
    <div class="header-title">Carcassonne</div>
    <div class="header-game">{{ game.name }}</div>
  </div>

  <div class="main-workspace">
    <div class="main-column">
      {% block score_table %}
      <div id="score-table" class="score-table-wrapper"
           {% if oob %}hx-swap-oob="true"{% endif %}>
        <table class="score-table">
          <thead>
            <tr>
              <th colspan="2">Jugador</th>
              <th>Score</th>
              <th>Casilla</th>
              <th>Vuelta</th>
            </tr>
          </thead>
          <tbody>
            {% for player in players %}
            <tr>
              <td><span class="player-dot" style="background:{{ player.color_hex }}"></span></td>
              <td>{{ player.name }}</td>
              <td class="score-value">{{ player.score_total }}</td>
              <td class="cell-value">{{ player.current_cell }}</td>
              <td class="lap-value">{{ "x" ~ player.lap if player.lap > 0 else "--" }}</td>
            </tr>
            {% endfor %}
          </tbody>
        </table>
      </div>
      {% endblock %}
    </div>

    {% block controls %}
    <div id="controls" class="controls"
         {% if oob %}hx-swap-oob="true"{% endif %}>
      <form id="score-form"
            hx-post="/games/{{ game.id }}/score"
            hx-target="#score-table"
            hx-swap="outerHTML">
        <!-- player chips, event type, points, note, submit button -->
      </form>
    </div>
    {% endblock %}
  </div>

  {% block action_bar %}
  <div id="action-bar" class="action-bar"
       {% if oob %}hx-swap-oob="true"{% endif %}>
    <button hx-post="/games/{{ game.id }}/undo"
            hx-target="#score-table"
            hx-swap="outerHTML"
            {% if not has_actions %}disabled{% endif %}>
      Deshacer
    </button>
  </div>
  {% endblock %}

</div>
{% endblock %}
```

Source: Pattern derived from prototype (`docs/prototype/dashboard.html`) + HTMX OOB pattern (HIGH confidence)

### Testing HTMX Endpoints

```python
# tests/test_web.py
from fastapi.testclient import TestClient

def test_score_returns_fragments(client, game_with_players):
    """POST score should return HTML fragments, not full page."""
    game, players = game_with_players
    response = client.post(
        f"/games/{game.id}/score",
        data={
            "player_ids": [players[0].id],
            "points": 8,
            "event_type": "CITY_COMPLETED",
        },
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert "<!DOCTYPE html>" not in response.text  # Not a full page
    assert "score-table" in response.text           # Contains score table
    assert players[0].name in response.text         # Contains player name

def test_score_updates_score_total(client, game_with_players):
    """After scoring, the HTML contains the updated score."""
    game, players = game_with_players
    response = client.post(
        f"/games/{game.id}/score",
        data={
            "player_ids": [players[0].id],
            "points": 12,
            "event_type": "ROAD_COMPLETED",
        },
        headers={"HX-Request": "true"},
    )
    assert "12" in response.text  # Updated score visible

def test_undo_returns_fragments_with_oob(client, game_with_players):
    """POST undo should return score table + OOB action bar."""
    game, players = game_with_players
    # First score something
    client.post(f"/games/{game.id}/score", data={
        "player_ids": [players[0].id], "points": 8, "event_type": "CITY_COMPLETED",
    }, headers={"HX-Request": "true"})

    # Then undo
    response = client.post(
        f"/games/{game.id}/undo",
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    assert "hx-swap-oob" in response.text  # OOB fragment present

def test_dashboard_full_page_without_htmx_header(client, game_with_players):
    """GET dashboard without HX-Request returns full HTML page."""
    game, _ = game_with_players
    response = client.get(f"/games/{game.id}")
    assert response.status_code == 200
    assert "<!DOCTYPE html>" in response.text or "<html" in response.text
```

Source: Pattern derived from [FastAPI testing docs](https://fastapi.tiangolo.com/tutorial/testing/) (HIGH confidence)

### Setup Page: Create Game and Add Players

```python
# app/web/routes.py
@router.get("/games/new")
def setup_page(request: Request):
    return templates.TemplateResponse(request, "setup.html", {
        "colors": PLAYER_COLORS,
    })

@router.post("/games")
def create_game(
    request: Request,
    name: str = Form(...),
    session: Session = Depends(get_session),
):
    game = create_game_service(session, name)
    return RedirectResponse(url=f"/games/{game.id}/setup", status_code=303)

@router.post("/games/{game_id}/players")
def add_player(
    request: Request,
    game_id: int,
    name: str = Form(...),
    color: str = Form(...),
    session: Session = Depends(get_session),
):
    add_player_service(session, game_id, name, color)
    # Redirect back to setup page (PRG pattern)
    return RedirectResponse(url=f"/games/{game_id}/setup", status_code=303)

@router.post("/games/{game_id}/start")
def start_game(
    game_id: int,
    session: Session = Depends(get_session),
):
    start_game_service(session, game_id)  # transitions setup -> playing
    return RedirectResponse(url=f"/games/{game_id}", status_code=303)
```

Source: FastAPI form handling docs + PRG pattern (HIGH confidence)

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Separate fragment files for HTMX | jinja2-fragments renders blocks from same template | jinja2-fragments 1.0 (2023), FastAPI support since 1.9.0 (2025-04-20) | Eliminates template duplication, single source of truth |
| `Jinja2Templates` from FastAPI | `Jinja2Blocks` from jinja2-fragments (drop-in replacement) | jinja2-fragments 1.9.0 | Same API, adds `block_name` parameter |
| `async def` routes with sync DB | `def` routes (FastAPI threadpool) | Always been the recommendation, commonly misunderstood | Prevents event loop blocking with SQLite |
| Manual form parsing | `Form()` with python-multipart | FastAPI best practice since 0.x | Type-safe form parameter extraction |

**Deprecated/outdated:**
- `FastAPI.on_event("startup")`: Use `lifespan` context manager instead (already done in Phase 1)
- `TemplateResponse(name, {"request": request})`: Old signature. New signature is `TemplateResponse(request, name, context)` (changed in Starlette 0.29+, supported by jinja2-fragments since 1.9.0)

## Open Questions

Things that couldn't be fully resolved:

1. **`block_names` (plural) support in FastAPI**
   - What we know: Flask has `render_blocks(template, ["header", "content"])` for multi-block rendering. Starlette documentation mentions `block_names` parameter. FastAPI examples only show `block_name` (singular).
   - What's unclear: Whether FastAPI's `Jinja2Blocks.TemplateResponse` supports `block_names` (plural) as a parameter for rendering multiple blocks in one call.
   - Recommendation: Use the proven approach of rendering individual blocks separately via `block_name` and concatenating with `HTMLResponse`. This is explicit, works today, and avoids depending on undocumented FastAPI-specific behavior. If `block_names` is confirmed to work, it's a minor simplification.

2. **Service layer `get_game_state()` function**
   - What we know: Routes need a "GameState" object containing game, sorted players, and action count (for undo button enable/disable). Phase 1 services provide `add_score`, `undo_last`, `rollback_to`, `recalculate_score` but no aggregation function.
   - What's unclear: Whether Phase 1 will have created a `get_game_state()` helper or if Phase 2 needs to add it.
   - Recommendation: Phase 2 should plan to add `get_game_state(session, game_id) -> GameState` as a service function that loads game + players sorted by score + action count. This is a query helper, not business logic.

3. **Player color hex mapping**
   - What we know: Phase 1 models store color as a string ("blue", "red", etc.). Templates need the hex value ("#0055BF") for rendering color dots.
   - What's unclear: Where the color name -> hex mapping lives (model property, template filter, or constants module).
   - Recommendation: Add a `PLAYER_COLORS` dict constant in models.py (or a shared constants module) and a `color_hex` property on the Player model that looks up the hex value. Alternatively, use a Jinja2 custom filter.

4. **Setup page: HTMX or PRG pattern?**
   - What we know: The prototype uses client-side JS for player management. The real app needs server-side state.
   - What's unclear: Whether the setup page should use HTMX for inline player add/remove or standard POST-Redirect-GET.
   - Recommendation: HTMX is a good fit here too -- `hx-post` to add a player, swap the player list, keeps the page responsive without full reloads. But PRG is simpler and perfectly adequate. Either approach works; the planner should choose one.

## Sources

### Primary (HIGH confidence)

- [jinja2-fragments on GitHub](https://github.com/sponsfreixes/jinja2-fragments) -- FastAPI integration via `Jinja2Blocks`, `block_name` parameter, version 1.12.0 (April 2026). Verified via Context7 `/sponsfreixes/jinja2-fragments`.
- [HTMX hx-swap-oob](https://htmx.org/attributes/hx-swap-oob/) -- Out-of-band swap documentation, core HTMX 2.x feature. Verified via Context7 `/bigskysoftware/htmx`.
- [HTMX hx-post](https://htmx.org/attributes/hx-post/) -- Form submission via POST, hx-target, hx-swap. Verified via Context7.
- [HTMX request/response headers](https://htmx.org/docs/) -- HX-Request, HX-Trigger headers. Verified via Context7.
- [FastAPI templates documentation](https://fastapi.tiangolo.com/advanced/templates/) -- Jinja2Templates, TemplateResponse, StaticFiles. Verified via Context7 `/websites/fastapi_tiangolo`.
- [FastAPI testing documentation](https://fastapi.tiangolo.com/tutorial/testing/) -- TestClient usage, request headers, form data.
- [FastAPI form data](https://fastapi.tiangolo.com/tutorial/request-forms/) -- `Form()` dependency, python-multipart requirement.

### Secondary (MEDIUM confidence)

- [FastAPI + HTMX: The No-Build Full-Stack (Blake Crosley)](https://blakecrosley.com/guides/fastapi-htmx) -- OOB pattern example, template structure, HX-Request detection. Verified pattern via official HTMX docs.
- [Using HTMX with FastAPI (TestDriven.io)](https://testdriven.io/blog/fastapi-htmx/) -- Form handling, HX-Request header detection pattern. Verified via official FastAPI docs.
- [FastAPI + HTMX patterns (johal.in)](https://johal.in/htmx-fastapi-patterns-hypermedia-driven-single-page-applications-2025/) -- Architecture validation for server-rendered HTMX apps.

### Tertiary (LOW confidence)

- None -- all findings verified with primary or secondary sources.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries verified via Context7 and PyPI, versions confirmed current
- Architecture: HIGH -- HTMX OOB pattern and jinja2-fragments integration verified via official documentation
- Pitfalls: HIGH -- async/sync mismatch, OOB ID mismatch, form reset documented in official sources
- Code examples: HIGH -- derived from official docs and verified prototypes

**Research date:** 2026-05-01
**Valid until:** 2026-06-01 (stable libraries, low churn rate)
