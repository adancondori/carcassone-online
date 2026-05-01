# Carcassonne Scoreboard

Sistema web para controlar la puntuacion de partidas de Carcassonne.
**Solo el tablero de puntuacion** — no implementa el juego, solo registra y visualiza puntos.

---

## 1. Objetivo

Crear un tablero web interactivo que replique el scoreboard fisico de Carcassonne:
circuito de casillas 0-49 que se recorre multiples vueltas, con hasta 6 jugadores,
historial de movimientos, undo/rollback por accion completa, y tipos de puntuacion
del juego base.

Referencia: el tablero fisico (ver `sources/IMG_20210617_152518.jpg.webp`) muestra
un circuito serpenteante numerado 0-49. Las reglas oficiales (CAR v6.4, pag. 14)
confirman: "a track of fifty fields that can be lapped many times."

---

## 2. Stack

| Capa          | Tecnologia                        | Justificacion                                           |
| ------------- | --------------------------------- | ------------------------------------------------------- |
| Backend       | FastAPI                           | Async, tipado, ideal para API + templates                |
| Frontend      | Jinja2 + HTMX + JS vanilla       | Server-driven UI, sin build step, interactividad con HTMX |
| Base de datos | SQLite                            | Zero config, archivo local, suficiente para ~100 rows/partida |
| ORM           | SQLModel                          | Modelos compartidos entre Pydantic y SQLAlchemy           |
| Migraciones   | Alembic                           | Versionado de esquema                                    |
| Tests         | pytest                            | TDD desde el inicio                                      |
| Contenedor    | Docker + Docker Compose           | Entorno reproducible                                     |

> **Nota sobre SQLite vs MySQL**: Para un scoreboard de mesa con decenas de rows
> por partida, SQLite es mas que suficiente y elimina la complejidad de un servidor
> de BD separado. Si en el futuro se necesita acceso concurrente desde multiples
> dispositivos, migrar a PostgreSQL/MySQL es un cambio de connection string.

---

## 3. Reglas de puntuacion (juego base)

Basado en el CAR v6.4 (Complete Annotated Rules). El scoreboard no valida si una
estructura esta completa — eso lo decide el jugador. El sistema solo necesita saber:
**quien gano cuantos puntos y por que razon.**

### Durante la partida (estructuras completadas)

| Tipo                    | Puntos                                          |
| ----------------------- | ----------------------------------------------- |
| Camino completado       | 1 punto por tile del camino                     |
| Ciudad completada       | 2 puntos por segmento + 2 puntos por escudo     |
| Monasterio completado   | 9 puntos (1 por tile: el monasterio + 8 vecinos)|

### Al final de la partida (estructuras incompletas + granjas)

| Tipo                    | Puntos                                          |
| ----------------------- | ----------------------------------------------- |
| Camino incompleto       | 1 punto por tile                                |
| Ciudad incompleta       | 1 punto por segmento + 1 punto por escudo       |
| Monasterio incompleto   | 1 punto por tile (monasterio + vecinos)         |
| Granja (campo)          | 3 puntos por ciudad completada adyacente        |

### Regla de empate en mayoria

Cuando multiples jugadores comparten mayoria de seguidores en una estructura,
**todos** reciben los puntos completos (CAR pag. 12). El sistema debe permitir
asignar los mismos puntos a multiples jugadores en una sola accion.

### Tipos de evento en el sistema

```
ROAD_COMPLETED        # camino completado durante la partida
CITY_COMPLETED        # ciudad completada durante la partida
MONASTERY_COMPLETED   # monasterio completado durante la partida
ROAD_FINAL            # camino incompleto al final
CITY_FINAL            # ciudad incompleta al final
MONASTERY_FINAL       # monasterio incompleto al final
FARM_FINAL            # granja al final de la partida
MANUAL                # ajuste manual libre
```

> **Fuera de alcance del MVP**: expansiones como Inns & Cathedrals, Traders & Builders,
> Abbot/jardines, etc. Se pueden agregar como tipos de evento adicionales despues.

---

## 4. Modelo conceptual: accion de puntuacion

### El problema

En Carcassonne, un momento de puntuacion en la mesa puede afectar a multiples
jugadores (empate en mayoria: todos reciben los puntos completos). Este es un
**unico evento logico** que produce **multiples cambios de puntaje**.

Si el modelo trata cada cambio de puntaje como un evento independiente, el
undo/rollback se rompe: deshacer "el ultimo evento" deshace solo uno de los
cambios, dejando el tablero en un estado que nunca existio en la mesa.

### La solucion: score_actions + score_entries

```
score_action  = "que paso en la mesa"     (1 por momento de puntuacion)
score_entry   = "a quien le afecto"       (1 por jugador afectado)
```

- **Undo** deshace la ultima `score_action` completa (todas sus entries).
- **Rollback** deshace todas las acciones posteriores a una accion dada.
- **Atomicidad**: una accion con todas sus entries se escribe en una sola transaccion.

### Fuente de verdad

`player.score_total` es un **cache** que se actualiza transaccionalmente junto con
las entries. La fuente de verdad autoritativa es la suma de entries activas:

```
score_total = SUM(points) FROM score_entries
              WHERE player_id = X
              AND score_action.is_undone = FALSE
```

En operaciones normales (sumar puntos), se actualiza `score_total` directamente
por rendimiento. En undo/rollback, se **recalcula desde entries activas** como
medida de seguridad contra inconsistencias.

---

## 5. Modelo de datos

3 tablas core + constraints de integridad.

### Tabla `games`

```sql
CREATE TABLE games (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'setup'
                CHECK (status IN ('setup', 'playing', 'scoring', 'finished')),
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### Tabla `players`

```sql
CREATE TABLE players (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id     INTEGER NOT NULL REFERENCES games(id),
    name        TEXT NOT NULL,
    color       TEXT NOT NULL,
    score_total INTEGER NOT NULL DEFAULT 0,
    turn_order  INTEGER NOT NULL CHECK (turn_order BETWEEN 1 AND 6),
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (game_id, color),
    UNIQUE (game_id, turn_order),
    UNIQUE (game_id, name)
);
```

`current_cell` = `score_total % 50` (derivado, no almacenado)
`lap` = `score_total // 50` (derivado, no almacenado)

### Tabla `score_actions`

Una fila por cada momento de puntuacion en la mesa.

```sql
CREATE TABLE score_actions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id     INTEGER NOT NULL REFERENCES games(id),
    event_type  TEXT NOT NULL
                CHECK (event_type IN (
                    'ROAD_COMPLETED', 'CITY_COMPLETED', 'MONASTERY_COMPLETED',
                    'ROAD_FINAL', 'CITY_FINAL', 'MONASTERY_FINAL',
                    'FARM_FINAL', 'MANUAL'
                )),
    description TEXT,             -- nota opcional ("ciudad grande del norte")
    is_undone   BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### Tabla `score_entries`

Una fila por cada jugador afectado por una accion.

```sql
CREATE TABLE score_entries (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    action_id       INTEGER NOT NULL REFERENCES score_actions(id),
    player_id       INTEGER NOT NULL REFERENCES players(id),
    points          INTEGER NOT NULL,
    score_before    INTEGER NOT NULL,
    score_after     INTEGER NOT NULL,

    UNIQUE (action_id, player_id)  -- un jugador no puntua dos veces en la misma accion
);
```

### Invariantes

- Max 6 jugadores por partida (CHECK + validacion en servicio).
- Color, turn_order y nombre unicos por partida.
- `score_entries.score_after` = `score_entries.score_before + score_entries.points`.
- Una accion siempre tiene al menos 1 entry.
- Undo/rollback opera sobre acciones completas, nunca sobre entries individuales.

---

## 6. Estructura del proyecto

```
carcassonne-scoreboard/
  app/
    __init__.py
    main.py               # FastAPI app, startup
    config.py             # settings desde env vars
    models.py             # SQLModel: Game, Player, ScoreAction, ScoreEntry
    db.py                 # engine, session, create_tables
    services.py           # logica: puntuar, undo, rollback, recalcular
    api/
      __init__.py
      games.py            # endpoints de partidas
      players.py          # endpoints de jugadores
      scores.py           # endpoints de puntuacion
    web/
      __init__.py
      routes.py           # rutas HTML (dashboard, setup)
    templates/
      base.html
      setup.html          # crear partida y registrar jugadores
      dashboard.html      # tablero principal
      components/
        board.html        # tablero visual SVG
        scoretable.html   # tabla de puntuaciones
        controls.html     # botones de puntuacion
        history.html      # historial de acciones
    static/
      css/
        style.css
        board.css
      js/
        board.js          # animacion, coordenadas SVG
        controls.js       # interaccion con botones

  tests/
    __init__.py
    conftest.py           # fixtures: db en memoria, factories
    test_models.py        # Player.current_cell, Player.lap
    test_services.py      # puntuar, undo, rollback, compartida, recalcular
    test_api.py           # endpoints HTTP

  alembic/
  alembic.ini
  docker-compose.yml
  Dockerfile
  pyproject.toml
  .env
```

---

## 7. Logica de negocio

### Player (modelo)

```python
BOARD_SIZE = 50

class Player(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    game_id: int = Field(foreign_key="games.id")
    name: str
    color: str
    score_total: int = 0
    turn_order: int

    @property
    def current_cell(self) -> int:
        return self.score_total % BOARD_SIZE

    @property
    def lap(self) -> int:
        return self.score_total // BOARD_SIZE
```

### Registrar puntuacion

Una sola funcion para 1 o N jugadores. Una transaccion, un commit.

```python
def add_score(
    session,
    game_id: int,
    player_points: list[tuple[int, int]],  # [(player_id, points), ...]
    event_type: str,
    description: str | None = None,
) -> ScoreAction:
    """
    Registra una accion de puntuacion que afecta a uno o mas jugadores.
    Todo se escribe en una sola transaccion.

    Ejemplo un jugador:   add_score(s, 1, [(player_id, 8)], "CITY_COMPLETED")
    Ejemplo compartida:   add_score(s, 1, [(p1, 6), (p2, 6)], "CITY_COMPLETED")
    """
    action = ScoreAction(
        game_id=game_id,
        event_type=event_type,
        description=description,
    )
    session.add(action)
    session.flush()  # obtener action.id sin commit

    for player_id, points in player_points:
        player = session.get(Player, player_id)
        score_before = player.score_total
        player.score_total += points
        entry = ScoreEntry(
            action_id=action.id,
            player_id=player_id,
            points=points,
            score_before=score_before,
            score_after=player.score_total,
        )
        session.add(entry)

    session.commit()
    return action
```

### Undo (deshacer ultima accion completa)

```python
def undo_last(session, game_id: int) -> ScoreAction | None:
    """Deshace la ultima accion activa de la partida, incluyendo todas sus entries."""
    last_action = get_last_active_action(session, game_id)
    if not last_action:
        return None

    last_action.is_undone = True

    # Recalcular score de cada jugador afectado desde entries activas
    affected_player_ids = {e.player_id for e in last_action.entries}
    for pid in affected_player_ids:
        recalculate_score(session, pid)

    session.commit()
    return last_action
```

### Rollback (deshacer hasta una accion dada)

```python
def rollback_to(session, game_id: int, action_id: int) -> int:
    """Deshace todas las acciones posteriores a action_id. Retorna cantidad deshechas."""
    actions = get_actions_after(session, game_id, action_id)
    if not actions:
        return 0

    affected_player_ids = set()
    for action in actions:
        action.is_undone = True
        for entry in action.entries:
            affected_player_ids.add(entry.player_id)

    # Recalcular todos los jugadores afectados de una vez
    for pid in affected_player_ids:
        recalculate_score(session, pid)

    session.commit()
    return len(actions)
```

### Recalcular score desde entries (fuente de verdad)

```python
def recalculate_score(session, player_id: int) -> int:
    """
    Recalcula score_total de un jugador sumando sus entries activas.
    Usa esto despues de undo/rollback para garantizar consistencia.
    """
    total = (
        session.query(func.coalesce(func.sum(ScoreEntry.points), 0))
        .join(ScoreAction)
        .where(ScoreEntry.player_id == player_id)
        .where(ScoreAction.is_undone == False)
        .scalar()
    )
    player = session.get(Player, player_id)
    player.score_total = total
    return total
```

---

## 8. API REST

```
POST   /api/games                     crear partida
GET    /api/games/{id}                estado de la partida con jugadores
PATCH  /api/games/{id}                cambiar status (playing -> scoring -> finished)

POST   /api/games/{id}/players        agregar jugador (max 6, solo en setup)
DELETE /api/games/{id}/players/{pid}   quitar jugador (solo en setup)

POST   /api/games/{id}/score          registrar accion de puntuacion (1 o N jugadores)
POST   /api/games/{id}/undo           deshacer ultima accion completa
POST   /api/games/{id}/rollback       rollback hasta una accion especifica
GET    /api/games/{id}/history        historial de acciones con sus entries
```

### Ejemplo de request para score

```json
// Un jugador
{
    "event_type": "CITY_COMPLETED",
    "entries": [{"player_id": 1, "points": 10}],
    "description": "ciudad grande del norte"
}

// Puntuacion compartida (empate)
{
    "event_type": "CITY_COMPLETED",
    "entries": [
        {"player_id": 1, "points": 10},
        {"player_id": 3, "points": 10}
    ],
    "description": "ciudad compartida"
}
```

---

## 9. Dashboard web

### Layout principal (mobile-first)

```
+------------------------------------------+
|  CARCASSONNE SCOREBOARD       [Partida X] |
+------------------------------------------+
|                                          |
|  [ Tablero visual SVG 0-49 ]            |
|  fichas de colores en sus casillas       |
|  badge de vuelta junto a la ficha        |
|                                          |
+------------------------------------------+
|  Jugador | Score | Casilla | Vuelta     |
|    Adan  |   53  |    3    |   x1       |
|    Pablo |  152  |    2    |   x3       |
|    Maria |   28  |   28    |   --       |
+------------------------------------------+
|  Tipo: [Camino] [Ciudad] [Monasterio]   |
|  Pts:  [+1][+2][+3][+4][+5][+8][+10]   |
|        [Otro: ___]                       |
|  Jugadores: [Adan] [Pablo] (multi-sel)  |
|  Nota:  [________________]               |
|  [  ANOTAR PUNTOS  ]                     |
+------------------------------------------+
|  [Undo ultima accion] [Terminar partida]|
+------------------------------------------+
|  Historial:                              |
|  #3 Ciudad: Adan +12, Pablo +12 (desh.) |
|  #2 Camino: Pablo +5                     |
|  #1 Ciudad: Adan +8                      |
+------------------------------------------+
```

Cambios clave vs plan anterior:

- **Seleccion multi-jugador**: para puntuacion compartida, el usuario selecciona
  multiples jugadores antes de anotar. Esto produce una sola accion con N entries.
- **Historial muestra acciones** (no entries individuales): "#3 Ciudad: Adan +12,
  Pablo +12" es una linea, no dos.
- **Vuelta como badge generico**: "x1", "x2", "x3"... no limitado a "50/100".
- **Sin indicador de turno en el MVP**: los turnos son conveniencia, no scoring.
  Se puede agregar despues sin cambiar el modelo de datos.

### Tablero visual (SVG con coordenadas relativas)

El tablero se renderiza como SVG con viewBox fijo. Las coordenadas de las casillas
se definen como porcentajes del viewBox, no como pixeles absolutos. Esto lo hace
responsive sin JavaScript adicional.

```html
<svg viewBox="0 0 1000 700" class="scoreboard">
  <!-- Fondo del tablero -->
  <image href="/static/images/board-bg.png" width="1000" height="700" />

  <!-- Casillas como posiciones porcentuales del viewBox -->
  <!-- Las coordenadas se mapean de la foto del tablero real -->
</svg>
```

```javascript
// Coordenadas relativas al viewBox (0-1000, 0-700)
const CELLS = [
    { x: 925, y: 640 },  // casilla 0 (abajo-derecha)
    { x: 845, y: 640 },  // casilla 1
    // ... 50 posiciones mapeadas del tablero real
];

function animateMove(playerId, fromCell, toCell) {
    const token = document.getElementById(`token-${playerId}`);
    let current = fromCell;
    const steps = [];

    // Calcular el recorrido paso a paso
    let c = fromCell;
    while (c !== toCell) {
        c = (c + 1) % 50;
        steps.push(c);
    }

    let i = 0;
    function step() {
        if (i >= steps.length) return;
        const pos = CELLS[steps[i]];
        token.setAttribute("cx", pos.x);
        token.setAttribute("cy", pos.y);
        i++;
        setTimeout(step, 80);  // 80ms entre casillas
    }
    step();
}
```

### Stacking de fichas

Cuando multiples jugadores estan en la misma casilla, las fichas se posicionan
con un offset radial para que todas sean visibles:

```javascript
function getStackOffset(index, total) {
    if (total === 1) return { dx: 0, dy: 0 };
    const angle = (2 * Math.PI * index) / total;
    const radius = 12;
    return { dx: Math.cos(angle) * radius, dy: Math.sin(angle) * radius };
}
```

---

## 10. Colores por defecto

Los 6 colores del juego base (48 seguidores en 6 colores, CAR pag. 7):

```python
DEFAULT_COLORS = [
    {"name": "blue",   "hex": "#0055BF"},
    {"name": "red",    "hex": "#CC0000"},
    {"name": "green",  "hex": "#237F23"},
    {"name": "yellow", "hex": "#F2CD00"},
    {"name": "black",  "hex": "#1A1A1A"},
    {"name": "pink",   "hex": "#FF69B4"},
]
```

---

## 11. Estrategia de undo/rollback

Nunca se borran acciones ni entries fisicamente. Toda operacion es auditable.

**Undo**: marca la ultima `score_action` activa como `is_undone = true`.
Recalcula `score_total` de todos los jugadores afectados desde entries activas.

**Rollback**: dada una `score_action` objetivo, marca como `is_undone` todas
las acciones posteriores. Recalcula todos los jugadores afectados.

```
Ejemplo:
  Accion 1 (ciudad):   Adan +8                    -> Adan=8
  Accion 2 (camino):   Pablo +5                   -> Pablo=5
  Accion 3 (ciudad):   Adan +12, Pablo +12        -> Adan=20, Pablo=17

  Undo:
    Accion 3 -> is_undone
    Recalcular Adan: SUM(entries activas) = 8     -> Adan=8
    Recalcular Pablo: SUM(entries activas) = 5    -> Pablo=5

  Rollback a accion 1:
    Accion 2 -> is_undone
    Accion 3 -> is_undone (ya estaba)
    Recalcular Adan = 8, Pablo = 0

  Resultado: acciones 2 y 3 visibles en historial pero tachadas.
```

### Por que recalcular en vez de usar score_before

Con acciones agrupadas y undo/rollback parciales, revertir `score_before` entry
por entry puede generar inconsistencias si el orden de reversion no es perfecto.
Recalcular desde entries activas es O(N) donde N ~ decenas de entries por partida,
y elimina toda posibilidad de corrupcion.

---

## 12. Estados de la partida

```
setup -> playing -> scoring -> finished
```

- **setup**: se agregan/quitan jugadores, se asignan nombres y colores.
- **playing**: partida en curso. Tipos de evento: *_COMPLETED y MANUAL.
- **scoring**: puntuacion final. Tipos de evento: *_FINAL, FARM_FINAL y MANUAL.
  El dashboard puede mostrar controles especificos para esta fase.
- **finished**: partida terminada. Solo lectura.

Transiciones validas solo hacia adelante. No se puede volver de `playing` a `setup`.

---

## 13. Docker

### docker-compose.yml

```yaml
services:
  web:
    build: .
    container_name: carcassonne_web
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
    ports:
      - "8000:8000"
    volumes:
      - .:/code
      - db_data:/code/data
    env_file:
      - .env

volumes:
  db_data:
```

### Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /code

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY pyproject.toml .
RUN pip install --upgrade pip && pip install -e ".[dev]"

COPY . .

EXPOSE 8000
```

### .env

```env
APP_NAME=Carcassonne Scoreboard
DATABASE_URL=sqlite:///data/carcassonne.db
```

---

## 14. Fases de desarrollo

Cada fase entrega valor usable de punta a punta (vertical slicing).

### Fase 1 — Partida basica funcional

**Meta**: crear partida, agregar jugadores, sumar puntos, deshacer, ver en navegador.

- Modelos SQLModel: Game, Player, ScoreAction, ScoreEntry
- DB SQLite + Alembic migration inicial con CHECK/UNIQUE constraints
- Servicio: `add_score()`, `undo_last()`, `recalculate_score()`
- Endpoints: crear partida, agregar jugador, registrar puntuacion, undo, ver estado
- Dashboard basico: setup + tabla de puntuaciones + botones de puntos + undo
- HTMX para actualizacion sin reload
- Seleccion multi-jugador para puntuacion compartida
- Tests: modelos, servicio (incluyendo undo de accion compartida), endpoints
- Docker Compose funcional

**Entregable**: `docker compose up`, abrir navegador, crear partida, jugar.

### Fase 2 — Historial, rollback, tipos de puntuacion

- Historial visual de acciones (agrupado: "Ciudad: Adan +12, Pablo +12")
- Rollback a cualquier accion anterior con confirmacion
- Acciones deshechas visibles pero tachadas
- Tipos de puntuacion como etiqueta: camino, ciudad, monasterio
- Notas opcionales en cada accion

### Fase 3 — Tablero visual SVG

- Tablero de 50 casillas con layout serpenteante (SVG, coordenadas relativas)
- Fichas de color posicionadas en su casilla
- Animacion paso a paso al sumar puntos
- Badge de vuelta generico (x1, x2, x3...)
- Stacking visual cuando multiples jugadores comparten casilla
- Responsive nativo por SVG viewBox

### Fase 4 — Puntuacion final y fin de partida

- Estado "scoring": tipos de evento finales (incompletos + granjas)
- Estado "finished": pantalla de resultados con ranking final
- Exportar partida a JSON

### Fase 5 — Mejoras opcionales (post-MVP)

- Turnos: indicador de turno actual, boton "siguiente turno"
- Importar partida desde JSON
- Tipos de evento de expansiones: Inns & Cathedrals, Traders & Builders, Abbot
- Configuracion por partida: seleccionar que expansiones estan activas

---

## 15. Tests

```bash
# Ejecutar todos los tests
docker compose exec web pytest

# Solo tests de un modulo
docker compose exec web pytest tests/test_services.py -v

# Con coverage
docker compose exec web pytest --cov=app
```

### Tests clave

```python
# tests/test_models.py

def test_player_cell_and_lap():
    player = Player(name="Adan", color="blue", score_total=53, turn_order=1, game_id=1)
    assert player.current_cell == 3
    assert player.lap == 1

def test_player_at_zero():
    player = Player(name="Adan", color="blue", score_total=0, turn_order=1, game_id=1)
    assert player.current_cell == 0
    assert player.lap == 0

def test_player_three_laps():
    player = Player(name="Adan", color="blue", score_total=152, turn_order=1, game_id=1)
    assert player.current_cell == 2
    assert player.lap == 3


# tests/test_services.py

def test_add_score_single_player(db_session, game_with_players):
    game, players = game_with_players
    action = add_score(db_session, game.id, [(players[0].id, 8)], "CITY_COMPLETED")
    assert len(action.entries) == 1
    assert players[0].score_total == 8
    assert action.entries[0].score_before == 0
    assert action.entries[0].score_after == 8

def test_add_score_shared(db_session, game_with_players):
    """Empate en mayoria: ambos jugadores reciben puntos completos."""
    game, players = game_with_players
    action = add_score(
        db_session, game.id,
        [(players[0].id, 10), (players[1].id, 10)],
        "CITY_COMPLETED",
        description="ciudad compartida",
    )
    assert len(action.entries) == 2
    assert players[0].score_total == 10
    assert players[1].score_total == 10

def test_undo_single_action(db_session, game_with_players):
    game, players = game_with_players
    add_score(db_session, game.id, [(players[0].id, 8)], "ROAD_COMPLETED")
    add_score(db_session, game.id, [(players[0].id, 12)], "CITY_COMPLETED")
    undone = undo_last(db_session, game.id)
    assert undone.event_type == "CITY_COMPLETED"
    assert players[0].score_total == 8  # recalculado desde entries activas

def test_undo_shared_action(db_session, game_with_players):
    """Undo de accion compartida revierte ambos jugadores."""
    game, players = game_with_players
    add_score(db_session, game.id, [(players[0].id, 8)], "ROAD_COMPLETED")
    add_score(
        db_session, game.id,
        [(players[0].id, 10), (players[1].id, 10)],
        "CITY_COMPLETED",
    )
    assert players[0].score_total == 18
    assert players[1].score_total == 10

    undo_last(db_session, game.id)
    assert players[0].score_total == 8   # solo queda el camino
    assert players[1].score_total == 0   # todo revertido

def test_undo_empty_game(db_session, game_with_players):
    game, _ = game_with_players
    assert undo_last(db_session, game.id) is None

def test_rollback_to_action(db_session, game_with_players):
    game, players = game_with_players
    a1 = add_score(db_session, game.id, [(players[0].id, 8)], "ROAD_COMPLETED")
    add_score(db_session, game.id, [(players[1].id, 5)], "ROAD_COMPLETED")
    add_score(
        db_session, game.id,
        [(players[0].id, 12), (players[1].id, 12)],
        "CITY_COMPLETED",
    )
    count = rollback_to(db_session, game.id, a1.id)
    assert count == 2
    assert players[0].score_total == 8
    assert players[1].score_total == 0

def test_recalculate_matches_score_total(db_session, game_with_players):
    """Despues de operaciones normales, recalculate confirma consistencia."""
    game, players = game_with_players
    add_score(db_session, game.id, [(players[0].id, 8)], "ROAD_COMPLETED")
    add_score(db_session, game.id, [(players[0].id, 12)], "CITY_COMPLETED")
    assert recalculate_score(db_session, players[0].id) == 20
    assert players[0].score_total == 20

def test_max_6_players(db_session, game):
    for i in range(6):
        add_player(db_session, game.id, f"Player{i}")
    with pytest.raises(ValueError):
        add_player(db_session, game.id, "Player7")

def test_unique_color_per_game(db_session, game):
    add_player(db_session, game.id, "Adan", color="blue")
    with pytest.raises(IntegrityError):
        add_player(db_session, game.id, "Pablo", color="blue")
```

---

## 16. Comandos

```bash
# Levantar el proyecto
docker compose up --build

# Ejecutar tests
docker compose exec web pytest

# Crear migracion
docker compose exec web alembic revision --autogenerate -m "descripcion"

# Aplicar migraciones
docker compose exec web alembic upgrade head
```

---

## 17. Requerimiento formal

> Desarrollar un tablero de puntuacion web para Carcassonne, dockerizado con
> FastAPI y SQLite. Soporta hasta 6 jugadores con circuito visual de 50 casillas
> (0-49), vueltas ilimitadas, tablero SVG responsive, tipos de puntuacion del
> juego base (camino, ciudad, monasterio, granja), puntuacion compartida por
> empate en mayoria como accion atomica, historial de acciones, undo y rollback
> por accion completa con recalculo desde entries.
>
> Diseño mobile-first para uso en la mesa de juego. TDD con pytest.
> Fases verticales: cada fase entrega funcionalidad usable.
