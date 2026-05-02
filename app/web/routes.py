"""Web routes for Carcassonne Scoreboard setup and game management."""

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session

from app.db import get_session
from app.services import (
    add_player,
    add_score,
    create_game,
    get_game_state,
    remove_player,
    rollback_to,
    start_game,
    undo_last,
)
from app.web.dependencies import EVENT_TYPE_LABELS, PLAYER_COLORS, templates

router = APIRouter()


# ── Helpers ──────────────────────────────────────────────────


def _render_dashboard_fragments(
    request: Request, session: Session, game_id: int
) -> HTMLResponse:
    """Render score_table + OOB controls + OOB action_bar as a single response.

    Used by both score and undo routes to return multi-fragment HTMX updates.
    The primary target is the score_table (no oob attribute). Controls and
    action_bar are out-of-band swaps (oob=True).
    """
    game_state = get_game_state(session, game_id)
    all_players = sorted(game_state.players, key=lambda p: p.turn_order)

    base_context = {
        "request": request,
        "game": game_state.game,
        "players": game_state.players,
        "all_players": all_players,
        "PLAYER_COLORS": PLAYER_COLORS,
        "EVENT_TYPE_LABELS": EVENT_TYPE_LABELS,
        "action_details": game_state.action_details,
        "has_actions": game_state.action_count > 0,
    }

    # Primary target: score table (no oob attribute)
    score_html = templates.TemplateResponse(
        "dashboard.html",
        {**base_context, "oob": False},
        block_name="score_table",
    ).body.decode()

    # OOB: controls (resets form to clean state)
    controls_html = templates.TemplateResponse(
        "dashboard.html",
        {**base_context, "oob": True},
        block_name="controls",
    ).body.decode()

    # OOB: action bar (undo button enabled/disabled state)
    action_bar_html = templates.TemplateResponse(
        "dashboard.html",
        {**base_context, "oob": True},
        block_name="action_bar",
    ).body.decode()

    # OOB: history (action list with rollback buttons)
    history_html = templates.TemplateResponse(
        "dashboard.html",
        {**base_context, "oob": True},
        block_name="history",
    ).body.decode()

    return HTMLResponse(content=score_html + controls_html + action_bar_html + history_html)


# ── Setup routes ─────────────────────────────────────────────


@router.get("/games/new")
def new_game_page(request: Request):
    """Render the setup page with the game name form."""
    return templates.TemplateResponse(
        "setup.html",
        {
            "request": request,
            "game": None,
            "players": [],
            "available_colors": PLAYER_COLORS,
            "PLAYER_COLORS": PLAYER_COLORS,
            "error": None,
        },
    )


@router.post("/games")
def create_game_route(
    name: str = Form(...),
    session: Session = Depends(get_session),
):
    """Create a new game and redirect to its setup page."""
    game = create_game(session, name)
    return RedirectResponse(url=f"/games/{game.id}/setup", status_code=303)


@router.get("/games/{game_id}/setup")
def setup_page(
    request: Request,
    game_id: int,
    session: Session = Depends(get_session),
):
    """Render the setup page with player management for an existing game."""
    game_state = get_game_state(session, game_id)

    # If game is no longer in setup, redirect to dashboard
    if game_state.game.status != "setup":
        return RedirectResponse(url=f"/games/{game_id}", status_code=303)

    # Sort players by turn_order for setup display (not by score)
    players_by_order = sorted(game_state.players, key=lambda p: p.turn_order)

    taken_colors = {p.color for p in players_by_order}
    available_colors = {
        k: v for k, v in PLAYER_COLORS.items() if k not in taken_colors
    }

    return templates.TemplateResponse(
        "setup.html",
        {
            "request": request,
            "game": game_state.game,
            "players": players_by_order,
            "available_colors": available_colors,
            "PLAYER_COLORS": PLAYER_COLORS,
            "error": None,
        },
    )


@router.post("/games/{game_id}/players")
def add_player_route(
    game_id: int,
    name: str = Form(...),
    color: str = Form(...),
    session: Session = Depends(get_session),
):
    """Add a player to the game and redirect back to setup."""
    try:
        add_player(session, game_id, name, color)
    except ValueError:
        pass  # Constraint violations handled by redirect back to setup
    return RedirectResponse(url=f"/games/{game_id}/setup", status_code=303)


@router.post("/games/{game_id}/players/{player_id}/delete")
def delete_player_route(
    game_id: int,
    player_id: int,
    session: Session = Depends(get_session),
):
    """Remove a player from the game and redirect back to setup."""
    try:
        remove_player(session, game_id, player_id)
    except ValueError:
        pass  # Player already removed or game not in setup
    return RedirectResponse(url=f"/games/{game_id}/setup", status_code=303)


@router.post("/games/{game_id}/start")
def start_game_route(
    game_id: int,
    session: Session = Depends(get_session),
):
    """Start the game and redirect to the dashboard."""
    try:
        start_game(session, game_id)
    except ValueError:
        return RedirectResponse(
            url=f"/games/{game_id}/setup", status_code=303
        )
    return RedirectResponse(url=f"/games/{game_id}", status_code=303)


# ── Dashboard routes ─────────────────────────────────────────


@router.get("/games/{game_id}")
def game_dashboard(
    request: Request,
    game_id: int,
    session: Session = Depends(get_session),
):
    """Render the full game dashboard page."""
    game_state = get_game_state(session, game_id)

    # If still in setup, redirect there
    if game_state.game.status == "setup":
        return RedirectResponse(
            url=f"/games/{game_id}/setup", status_code=303
        )

    all_players = sorted(game_state.players, key=lambda p: p.turn_order)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "game": game_state.game,
            "players": game_state.players,
            "all_players": all_players,
            "PLAYER_COLORS": PLAYER_COLORS,
            "EVENT_TYPE_LABELS": EVENT_TYPE_LABELS,
            "action_details": game_state.action_details,
            "has_actions": game_state.action_count > 0,
            "oob": False,
        },
    )


@router.post("/games/{game_id}/score")
def score_action(
    request: Request,
    game_id: int,
    player_ids: Annotated[list[int], Form()],
    points: int = Form(...),
    event_type: str = Form(...),
    description: str = Form(None),
    session: Session = Depends(get_session),
):
    """Score points for selected players and return HTMX fragments."""
    try:
        player_points = [(pid, points) for pid in player_ids]
        add_score(session, game_id, player_points, event_type, description)
    except ValueError:
        pass  # Service errors handled silently; fragments show current state

    return _render_dashboard_fragments(request, session, game_id)


@router.post("/games/{game_id}/undo")
def undo_action(
    request: Request,
    game_id: int,
    session: Session = Depends(get_session),
):
    """Undo the last scoring action and return HTMX fragments."""
    try:
        undo_last(session, game_id)
    except ValueError:
        pass  # No active actions to undo; fragments show current state

    return _render_dashboard_fragments(request, session, game_id)


@router.post("/games/{game_id}/rollback")
def rollback_action(
    request: Request,
    game_id: int,
    action_id: int = Form(...),
    session: Session = Depends(get_session),
):
    """Rollback to a specific action and return HTMX fragments."""
    try:
        rollback_to(session, game_id, action_id)
    except ValueError:
        pass  # Invalid action_id; fragments show current state

    return _render_dashboard_fragments(request, session, game_id)
