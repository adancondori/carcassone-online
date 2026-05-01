"""Web routes for Carcassonne Scoreboard setup and game management."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from app.db import get_session
from app.services import (
    add_player,
    create_game,
    get_game_state,
    remove_player,
    start_game,
)
from app.web.dependencies import PLAYER_COLORS, templates

router = APIRouter()


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


@router.get("/games/{game_id}")
def game_dashboard(
    request: Request,
    game_id: int,
    session: Session = Depends(get_session),
):
    """Game dashboard page (stub -- full implementation in 02-02)."""
    game_state = get_game_state(session, game_id)

    # If still in setup, redirect there
    if game_state.game.status == "setup":
        return RedirectResponse(
            url=f"/games/{game_id}/setup", status_code=303
        )

    return templates.TemplateResponse(
        "dashboard_stub.html",
        {
            "request": request,
            "game": game_state.game,
            "players": game_state.players,
            "PLAYER_COLORS": PLAYER_COLORS,
            "has_actions": game_state.action_count > 0,
        },
    )
