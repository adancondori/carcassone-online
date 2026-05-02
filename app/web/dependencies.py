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
    (528, 361),  # 0
    (438, 365),  # 1
    (360, 370),  # 2
    (294, 365),  # 3
    (228, 349),  # 4
    (162, 336),  # 5
    (108, 349),  # 6
    (72,  353),  # 7
    (48,  323),  # 8
    (24,  290),  # 9
    (30,  239),  # 10
    (24,  193),  # 11
    (30,  143),  # 12
    (36,  80),   # 13
    (42,  25),   # 14
    (78,  17),   # 15
    (126, 17),   # 16
    (168, 17),   # 17
    (216, 21),   # 18
    (258, 21),   # 19
    (312, 21),   # 20
    (360, 17),   # 21
    (408, 17),   # 22
    (456, 17),   # 23
    (516, 17),   # 24
    (546, 55),   # 25
    (552, 97),   # 26
    (534, 139),  # 27
    (468, 139),  # 28
    (408, 134),  # 29
    (348, 126),  # 30
    (300, 118),  # 31
    (258, 118),  # 32
    (216, 113),  # 33
    (168, 109),  # 34
    (132, 109),  # 35
    (108, 130),  # 36
    (78,  155),  # 37
    (102, 206),  # 38
    (144, 210),  # 39
    (192, 218),  # 40
    (228, 218),  # 41
    (276, 218),  # 42
    (318, 218),  # 43
    (360, 218),  # 44
    (402, 210),  # 45
    (444, 210),  # 46
    (492, 193),  # 47
    (510, 214),  # 48
    (498, 256),  # 49
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
