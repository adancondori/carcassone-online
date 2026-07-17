"""Voice command orchestration (plan v2, fase 4).

Takes an already-transcribed text, runs it through the parser, validates
against the game's players, applies the score via services.add_score
(inheriting every validation there), and records the outcome in voice_log.

Never raises for a bad command — every failure path returns a VoiceOutcome
with a user-facing message and is persisted to voice_log.
"""

import json
from dataclasses import dataclass, field

from sqlmodel import Session, select

from app.models import Game, Player, VoiceLog
from app.services import add_score
from app.voice.parser import ParseError, parse_command, resolve_event_type

# Grammar colors (Spanish) -> Player.color keys stored in the DB (English).
COLOR_KEYS = {
    "rojo": "red", "azul": "blue", "verde": "green",
    "amarillo": "yellow", "negro": "black", "rosa": "pink",
}


@dataclass
class VoiceOutcome:
    """Result of processing one voice command, ready for the toast."""
    kind: str                    # "success" | "error"
    status: str                  # voice_log status value
    message: str
    transcript: str
    entries: list[dict] = field(default_factory=list)  # {name, color, points}
    event_type: str | None = None


def _log(
    session: Session,
    game_id: int,
    outcome: VoiceOutcome,
    duration_ms: int,
    action_id: int | None = None,
    parsed: str | None = None,
) -> None:
    session.add(VoiceLog(
        game_id=game_id,
        transcript=outcome.transcript,
        parsed=parsed,
        status=outcome.status,
        error_detail=None if outcome.kind == "success" else outcome.message,
        action_id=action_id,
        duration_ms=duration_ms,
    ))
    session.commit()


def process_voice_command(
    session: Session, game_id: int, transcript: str, duration_ms: int = 0
) -> VoiceOutcome:
    """Interpret and apply a transcribed voice command against a game.

    The game must exist (callers 404 otherwise). Always returns a
    VoiceOutcome and logs it; never raises for a bad command.
    """
    transcript = transcript.strip()
    if not transcript:
        outcome = VoiceOutcome(
            kind="error", status="empty_audio",
            message="No escuché nada, intenta de nuevo",
            transcript=transcript,
        )
        _log(session, game_id, outcome, duration_ms)
        return outcome

    try:
        command = parse_command(transcript)
    except ParseError as exc:
        outcome = VoiceOutcome(
            kind="error", status="parse_error",
            message=f"No entendí: ‹{transcript}› — {exc}",
            transcript=transcript,
        )
        _log(session, game_id, outcome, duration_ms)
        return outcome

    game = session.get(Game, game_id)
    players_by_color = {
        p.color: p
        for p in session.exec(select(Player).where(Player.game_id == game_id))
    }

    try:
        player_points: list[tuple[int, int]] = []
        toast_entries: list[dict] = []
        for spanish_color, points in command.entries:
            color_key = COLOR_KEYS[spanish_color]
            player = players_by_color.get(color_key)
            if player is None:
                raise ParseError(
                    f"No hay jugador de color {spanish_color} en esta partida"
                )
            player_points.append((player.id, points))
            toast_entries.append(
                {"name": player.name, "color": color_key, "points": points}
            )

        negative = any(points < 0 for _, points in command.entries)
        event_type = resolve_event_type(
            command.event_word, game.status, negative=negative
        )

        action = add_score(
            session, game_id, player_points, event_type,
            description="(voz)",
        )
    except (ParseError, ValueError) as exc:
        session.rollback()
        outcome = VoiceOutcome(
            kind="error", status="validation_error",
            message=str(exc), transcript=transcript,
        )
        _log(session, game_id, outcome, duration_ms)
        return outcome

    outcome = VoiceOutcome(
        kind="success", status="applied",
        message="", transcript=transcript,
        entries=toast_entries, event_type=event_type,
    )
    _log(
        session, game_id, outcome, duration_ms,
        action_id=action.id,
        parsed=json.dumps(
            {"entries": command.entries, "event_type": event_type},
            ensure_ascii=False,
        ),
    )
    return outcome
