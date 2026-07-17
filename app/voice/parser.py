"""Voice command parser for Carcassonne Scoreboard (plan v2).

Pure Python: text in, VoiceCommand out. No I/O and no game state — the
game status is passed explicitly to resolve_event_type().

Grammar (docs/plan_v2.md):

    comando  := [verbo] grupo ( ("y" | ",") grupo )*
    grupo    := [tipo] cantidad ["puntos"] destinos
              | destinos cantidad ["puntos"]
    verbo    := agrega | añade | suma | anota | pon | quita | resta
    cantidad := dígitos | palabras numéricas (0-99)
    destinos := ["al"|"a la"|"a"|"para"] color ( ("y"|",") ["al"] color )*
    color    := rojo | azul | verde | amarillo | negro | rosa
    tipo     := camino | ciudad | monasterio | granja
"""

from dataclasses import dataclass


class ParseError(ValueError):
    """A voice command that doesn't fit the grammar. Message is user-facing."""


@dataclass
class VoiceCommand:
    """Structured interpretation of a voice command.

    intent is always "add_score" in v1; the field exists so future intents
    (undo by voice, state changes) extend the pipeline without redesign.
    """
    intent: str
    entries: list[tuple[str, int]]  # ordered (color, points)
    event_word: str | None          # camino | ciudad | monasterio | granja


COLORS = frozenset({"rojo", "azul", "verde", "amarillo", "negro", "rosa"})

POSITIVE_VERBS = frozenset({"agrega", "añade", "suma", "anota", "pon"})
NEGATIVE_VERBS = frozenset({"quita", "resta"})

# Event word -> (event type in playing, event type in scoring)
EVENT_WORD_MAP = {
    "camino": ("ROAD_COMPLETED", "ROAD_FINAL"),
    "ciudad": ("CITY_COMPLETED", "CITY_FINAL"),
    "monasterio": ("MONASTERY_COMPLETED", "MONASTERY_FINAL"),
    "granja": (None, "FARM_FINAL"),  # None: invalid during playing
}

# Words that carry no meaning and are skipped between meaningful tokens.
FILLER_WORDS = frozenset({
    "al", "a", "la", "el", "los", "las", "para", "puntos", "punto",
    "y", ",",
})

MAX_POINTS = 999

_UNITS = {
    "cero": 0, "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3,
    "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9,
}
_TEENS_AND_TWENTIES = {
    "diez": 10, "once": 11, "doce": 12, "trece": 13, "catorce": 14,
    "quince": 15, "dieciseis": 16, "diecisiete": 17, "dieciocho": 18,
    "diecinueve": 19, "veinte": 20, "veintiun": 21, "veintiuno": 21,
    "veintidos": 22, "veintitres": 23, "veinticuatro": 24,
    "veinticinco": 25, "veintiseis": 26, "veintisiete": 27,
    "veintiocho": 28, "veintinueve": 29,
}
_TENS = {
    "treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60,
    "setenta": 70, "ochenta": 80, "noventa": 90,
}

_ACCENT_MAP = str.maketrans("áéíóúü", "aeiouu")
_PUNCTUATION = ".,;:!?¡¿"


def _normalize(text: str) -> list[str]:
    """Lowercase, strip accents (keeping ñ) and punctuation, split to tokens."""
    text = text.lower().translate(_ACCENT_MAP)
    for ch in _PUNCTUATION:
        text = text.replace(ch, " ")
    return text.split()


class _GroupBuilder:
    """Accumulates one grammar group: amount + colors + sign."""

    def __init__(self, sign: int = 1):
        self.amount: int | None = None
        self.colors: list[str] = []
        self.sign = sign

    @property
    def is_complete(self) -> bool:
        return self.amount is not None and bool(self.colors)

    @property
    def is_empty(self) -> bool:
        return self.amount is None and not self.colors

    def close(self) -> tuple[int, list[str]]:
        if self.amount is None:
            raise ParseError("Falta la cantidad de puntos")
        if not self.colors:
            raise ParseError("Falta el color del jugador")
        if self.amount == 0:
            raise ParseError("La cantidad debe ser mayor que 0")
        if self.amount > MAX_POINTS:
            raise ParseError(
                f"La cantidad {self.amount} es demasiado grande (máximo {MAX_POINTS})"
            )
        return (self.amount * self.sign, self.colors)


def _consume_number(tokens: list[str], i: int) -> tuple[int, int] | None:
    """Try to read a number starting at tokens[i].

    Returns (value, next_index) or None if tokens[i] is not a number.
    Handles digits, number words, and 'treinta y uno' style compounds.
    """
    token = tokens[i]
    if token.isdigit():
        return (int(token), i + 1)
    if token in _UNITS:
        return (_UNITS[token], i + 1)
    if token in _TEENS_AND_TWENTIES:
        return (_TEENS_AND_TWENTIES[token], i + 1)
    if token in _TENS:
        value = _TENS[token]
        # 'treinta y uno': tens + 'y' + unit
        if (
            i + 2 < len(tokens)
            and tokens[i + 1] == "y"
            and tokens[i + 2] in _UNITS
            and _UNITS[tokens[i + 2]] > 0
        ):
            return (value + _UNITS[tokens[i + 2]], i + 3)
        return (value, i + 1)
    return None


def parse_command(text: str) -> VoiceCommand:
    """Parse a Spanish voice command into a VoiceCommand.

    Raises:
        ParseError: with a user-facing Spanish message when the text
            doesn't fit the grammar. Never guesses.
    """
    tokens = _normalize(text)
    if not tokens:
        raise ParseError("No escuché ningún comando")

    groups: list[tuple[int, list[str]]] = []
    event_word: str | None = None
    group = _GroupBuilder()

    i = 0
    while i < len(tokens):
        token = tokens[i]

        number = _consume_number(tokens, i)
        if number is not None:
            value, next_i = number
            if group.amount is not None:
                if not group.is_complete:
                    raise ParseError("Escuché dos cantidades seguidas")
                # New group with a fresh amount ('... y 20 al negro'),
                # inheriting the sign ('quita 3 al rojo y 2 al verde').
                groups.append(group.close())
                group = _GroupBuilder(sign=group.sign)
            group.amount = value
            i = next_i
            continue

        if token in POSITIVE_VERBS or token in NEGATIVE_VERBS:
            sign = -1 if token in NEGATIVE_VERBS else 1
            if group.is_complete:
                groups.append(group.close())
                group = _GroupBuilder(sign=sign)
            elif group.is_empty:
                group.sign = sign
            else:
                raise ParseError(f"No entendí el verbo '{token}' a mitad del comando")
            i += 1
            continue

        if token in EVENT_WORD_MAP:
            if event_word is not None and event_word != token:
                raise ParseError(
                    f"Escuché dos tipos distintos: '{event_word}' y '{token}'"
                )
            event_word = token
            i += 1
            continue

        if token in COLORS:
            group.colors.append(token)
            i += 1
            continue

        if token in FILLER_WORDS:
            i += 1
            continue

        raise ParseError(f"No reconozco '{token}'")

    groups.append(group.close())

    entries: list[tuple[str, int]] = []
    seen: set[str] = set()
    for points, colors in groups:
        for color in colors:
            if color in seen:
                raise ParseError(f"El color {color} aparece más de una vez")
            seen.add(color)
            entries.append((color, points))

    return VoiceCommand(intent="add_score", entries=entries, event_word=event_word)


def resolve_event_type(
    event_word: str | None, game_status: str, negative: bool = False
) -> str:
    """Map an event word to a concrete event type given the game state.

    Rule 2: corrections (negative points) are always MANUAL.
    Rule 3: the same word maps to *_COMPLETED in playing, *_FINAL in scoring.

    Raises:
        ParseError: if the game state doesn't allow scoring, or the word
            isn't valid in this state (granja during playing).
    """
    if game_status not in ("playing", "scoring"):
        raise ParseError(f"No se puede puntuar en estado '{game_status}'")
    if negative or event_word is None:
        return "MANUAL"

    playing_type, scoring_type = EVENT_WORD_MAP[event_word]
    resolved = playing_type if game_status == "playing" else scoring_type
    if resolved is None:
        raise ParseError("Granja solo vale en puntuación final")
    return resolved
