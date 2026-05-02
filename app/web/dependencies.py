"""Shared web dependencies: template engine, color constants, label maps."""

import math
from collections import defaultdict

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

# Display-friendly labels for scoring event types.
EVENT_TYPE_LABELS = {
    "ROAD_COMPLETED": "Camino",
    "CITY_COMPLETED": "Ciudad",
    "MONASTERY_COMPLETED": "Monasterio",
    "ROAD_FINAL": "Camino (final)",
    "CITY_FINAL": "Ciudad (final)",
    "MONASTERY_FINAL": "Monasterio (final)",
    "FARM_FINAL": "Granja",
    "MANUAL": "Manual",
}

# Carcassonne scoring track cell coordinates (50 cells, 0-49).
# Mapped from board photo at viewBox 0 0 600 420.
BOARD_CELLS = [
    (540, 352),  # 0
    (444, 360),  # 1
    (387, 360),  # 2
    (330, 363),  # 3
    (276, 367),  # 4
    (226, 366),  # 5
    (167, 366),  # 6
    (106, 371),  # 7
    (62,  338),  # 8
    (47,  285),  # 9
    (39,  233),  # 10
    (39,  181),  # 11
    (39,  129),  # 12
    (47,  76),   # 13
    (85,  53),   # 14
    (135, 43),   # 15
    (179, 40),   # 16
    (229, 43),   # 17
    (273, 43),   # 18
    (318, 43),   # 19
    (363, 43),   # 20
    (412, 37),   # 21
    (455, 34),   # 22
    (500, 37),   # 23
    (549, 40),   # 24
    (566, 86),   # 25
    (559, 123),  # 26
    (500, 126),  # 27
    (459, 126),  # 28
    (421, 129),  # 29
    (382, 134),  # 30
    (339, 134),  # 31
    (298, 137),  # 32
    (249, 137),  # 33
    (212, 134),  # 34
    (173, 137),  # 35
    (135, 156),  # 36 — matches printed track at this pixel
    (119, 190),  # 37
    (142, 225),  # 38
    (190, 233),  # 39
    (226, 236),  # 40
    (263, 233),  # 41
    (303, 225),  # 42
    (349, 228),  # 43
    (391, 228),  # 44
    (434, 225),  # 45
    (475, 222),  # 46
    (516, 215),  # 47
    (556, 233),  # 48
    (552, 278),  # 49
]


def _stack_offset(index: int, total: int) -> tuple[float, float]:
    """Compute radial stacking offset for overlapping tokens on a cell."""
    if total == 1:
        return (0.0, 0.0)
    angle = (2 * math.pi * index) / total - math.pi / 2
    radius = 13.0 if total <= 3 else 15.0
    return (math.cos(angle) * radius, math.sin(angle) * radius)


def build_board_context(players: list) -> dict:
    """Build board_cells dict for the SVG board template.

    Groups players by cell (score_total % 50), computes stacking offsets,
    and returns {cell_num: [{"cx", "cy", "hex", "color", "initial", "lap"}, ...]}.
    """
    if not players:
        return {}

    # Group players by cell number
    cell_groups: dict[int, list] = defaultdict(list)
    for player in players:
        cell = player.score_total % 50
        cell_groups[cell].append(player)

    result: dict[int, list[dict]] = {}
    for cell_num, cell_players in cell_groups.items():
        base_x, base_y = BOARD_CELLS[cell_num]
        total = len(cell_players)
        tokens = []
        for idx, player in enumerate(cell_players):
            dx, dy = _stack_offset(idx, total)
            tokens.append({
                "cx": base_x + dx,
                "cy": base_y + dy,
                "hex": PLAYER_COLORS[player.color]["hex"],
                "color": player.color,
                "initial": player.name[0],
                "lap": player.score_total // 50,
            })
        result[cell_num] = tokens

    return result
