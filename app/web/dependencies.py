"""Shared web dependencies: template engine, color constants."""

from jinja2_fragments.fastapi import Jinja2Blocks

# Template engine with fragment support for future HTMX partial rendering.
templates = Jinja2Blocks(directory="app/templates")

# Carcassonne player colors (meeple colors).
# Keys match the Player.color field values stored in the database.
PLAYER_COLORS = {
    "blue":   {"name": "Azul",     "hex": "#0055BF"},
    "red":    {"name": "Rojo",     "hex": "#CC0000"},
    "green":  {"name": "Verde",    "hex": "#237F23"},
    "yellow": {"name": "Amarillo", "hex": "#F2CD00"},
    "black":  {"name": "Negro",    "hex": "#1A1A1A"},
    "pink":   {"name": "Rosa",     "hex": "#FF69B4"},
}
