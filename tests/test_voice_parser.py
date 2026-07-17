"""Tests for the voice command parser (plan v2, fase 1).

The parser is pure Python: text in, VoiceCommand out. All grammar rules
from docs/plan_v2.md live here. No I/O, no game state — resolve_event_type
receives the game status explicitly.
"""

import pytest

from app.voice.parser import (
    ParseError,
    VoiceCommand,
    parse_command,
    resolve_event_type,
)


# ---------------------------------------------------------------------------
# Basic commands
# ---------------------------------------------------------------------------


class TestParseBasics:
    def test_simple_add(self):
        """'agrega 5 puntos al rojo' → +5 rojo, sin tipo."""
        cmd = parse_command("agrega 5 puntos al rojo")
        assert cmd.intent == "add_score"
        assert cmd.entries == [("rojo", 5)]
        assert cmd.event_word is None

    def test_verb_is_optional(self):
        """'5 al rojo' funciona sin verbo."""
        cmd = parse_command("5 al rojo")
        assert cmd.entries == [("rojo", 5)]

    def test_puntos_keyword_is_optional(self):
        cmd = parse_command("agrega 5 al rojo")
        assert cmd.entries == [("rojo", 5)]

    def test_shared_amount_multiple_colors(self):
        """'suma 5 puntos rojo, amarillo' → ambos reciben 5 (compartido)."""
        cmd = parse_command("suma 5 puntos rojo, amarillo")
        assert cmd.entries == [("rojo", 5), ("amarillo", 5)]

    def test_shared_with_y_connector(self):
        cmd = parse_command("ciudad 8 al rojo y al amarillo")
        assert cmd.entries == [("rojo", 8), ("amarillo", 8)]
        assert cmd.event_word == "ciudad"

    def test_multi_group_distinct_amounts(self):
        """'suma 5 al rojo y 20 al negro' → montos distintos, una acción."""
        cmd = parse_command("suma 5 al rojo y 20 al negro")
        assert cmd.entries == [("rojo", 5), ("negro", 20)]

    def test_multi_group_with_repeated_verb(self):
        """Ejemplo del plan original: verbo repetido por grupo."""
        cmd = parse_command("agrega 5 puntos al rojo y agrega 20 puntos al negro")
        assert cmd.entries == [("rojo", 5), ("negro", 20)]

    def test_subtract_verb_negates(self):
        """'quita 3 al verde' → −3 verde."""
        cmd = parse_command("quita 3 al verde")
        assert cmd.entries == [("verde", -3)]

    def test_resta_verb_negates(self):
        cmd = parse_command("resta 10 al negro")
        assert cmd.entries == [("negro", -10)]

    def test_case_accents_and_punctuation_normalized(self):
        cmd = parse_command("Añade 5 al Rojo.")
        assert cmd.entries == [("rojo", 5)]

    def test_colors_first_order(self):
        """Orden alternativo de la gramática: destinos cantidad."""
        cmd = parse_command("al rojo 5 puntos")
        assert cmd.entries == [("rojo", 5)]

    def test_all_six_colors_recognized(self):
        cmd = parse_command("agrega 2 al rojo, azul, verde, amarillo, negro y rosa")
        assert cmd.entries == [
            ("rojo", 2), ("azul", 2), ("verde", 2),
            ("amarillo", 2), ("negro", 2), ("rosa", 2),
        ]


# ---------------------------------------------------------------------------
# Event type words
# ---------------------------------------------------------------------------


class TestEventWords:
    def test_camino(self):
        cmd = parse_command("camino 4 azul")
        assert cmd.event_word == "camino"
        assert cmd.entries == [("azul", 4)]

    def test_monasterio(self):
        cmd = parse_command("monasterio 9 al rosa")
        assert cmd.event_word == "monasterio"

    def test_granja(self):
        cmd = parse_command("granja 9 rosa")
        assert cmd.event_word == "granja"

    def test_event_word_after_verb(self):
        cmd = parse_command("agrega ciudad 8 al rojo")
        assert cmd.event_word == "ciudad"


# ---------------------------------------------------------------------------
# Numbers as words (Whisper often transcribes digits as words)
# ---------------------------------------------------------------------------


class TestNumberWords:
    @pytest.mark.parametrize("text,expected", [
        ("agrega cinco al rojo", 5),
        ("agrega uno al rojo", 1),
        ("agrega un punto al rojo", 1),
        ("agrega diez al rojo", 10),
        ("agrega quince al rojo", 15),
        ("agrega dieciséis al rojo", 16),
        ("agrega veinte al rojo", 20),
        ("agrega veintiuno al rojo", 21),
        ("agrega veintinueve al rojo", 29),
        ("agrega treinta al rojo", 30),
        ("agrega treinta y uno al rojo", 31),
        ("agrega sesenta y uno al rojo", 61),
        ("agrega noventa y nueve al rojo", 99),
    ])
    def test_number_words(self, text, expected):
        cmd = parse_command(text)
        assert cmd.entries == [("rojo", expected)]

    def test_word_number_in_second_group(self):
        cmd = parse_command("cinco al rojo y veinte al negro")
        assert cmd.entries == [("rojo", 5), ("negro", 20)]

    def test_camino_cuatro_azul(self):
        """Ejemplo del plan."""
        cmd = parse_command("camino cuatro azul")
        assert cmd.event_word == "camino"
        assert cmd.entries == [("azul", 4)]


# ---------------------------------------------------------------------------
# Errors (legibles, nunca interpretación creativa)
# ---------------------------------------------------------------------------


class TestParseErrors:
    def test_empty_text(self):
        with pytest.raises(ParseError):
            parse_command("")

    def test_missing_amount(self):
        with pytest.raises(ParseError, match="cantidad"):
            parse_command("agrega puntos al rojo")

    def test_missing_color(self):
        with pytest.raises(ParseError, match="color"):
            parse_command("agrega 5 puntos")

    def test_unknown_color(self):
        with pytest.raises(ParseError, match="morado"):
            parse_command("agrega 5 al morado")

    def test_duplicate_color_rejected(self):
        """Un color no puede repetirse (constraint único por acción en DB)."""
        with pytest.raises(ParseError, match="rojo"):
            parse_command("5 al rojo y 3 al rojo")

    def test_zero_amount_rejected(self):
        with pytest.raises(ParseError, match="mayor"):
            parse_command("agrega 0 al rojo")

    def test_gibberish(self):
        with pytest.raises(ParseError):
            parse_command("hola qué tal cómo estás")

    def test_amount_above_limit_rejected(self):
        with pytest.raises(ParseError):
            parse_command("agrega 5000 al rojo")


# ---------------------------------------------------------------------------
# Event type resolution by game state (regla 3 del plan)
# ---------------------------------------------------------------------------


class TestResolveEventType:
    def test_no_word_defaults_to_manual(self):
        assert resolve_event_type(None, "playing") == "MANUAL"
        assert resolve_event_type(None, "scoring") == "MANUAL"

    @pytest.mark.parametrize("word,status,expected", [
        ("camino", "playing", "ROAD_COMPLETED"),
        ("camino", "scoring", "ROAD_FINAL"),
        ("ciudad", "playing", "CITY_COMPLETED"),
        ("ciudad", "scoring", "CITY_FINAL"),
        ("monasterio", "playing", "MONASTERY_COMPLETED"),
        ("monasterio", "scoring", "MONASTERY_FINAL"),
        ("granja", "scoring", "FARM_FINAL"),
    ])
    def test_word_maps_by_status(self, word, status, expected):
        assert resolve_event_type(word, status) == expected

    def test_granja_invalid_during_playing(self):
        with pytest.raises(ParseError, match="[Gg]ranja"):
            resolve_event_type("granja", "playing")

    def test_negative_forces_manual(self):
        """Regla 2: quita/resta siempre es MANUAL, aunque digan un tipo."""
        assert resolve_event_type("ciudad", "playing", negative=True) == "MANUAL"

    @pytest.mark.parametrize("status", ["setup", "finished"])
    def test_invalid_game_status(self, status):
        with pytest.raises(ParseError):
            resolve_event_type("ciudad", status)


# ---------------------------------------------------------------------------
# VoiceCommand shape
# ---------------------------------------------------------------------------


class TestVoiceCommand:
    def test_intent_field_present(self):
        """El diseño extensible: todo comando declara su intent."""
        cmd = parse_command("5 al rojo")
        assert isinstance(cmd, VoiceCommand)
        assert cmd.intent == "add_score"
