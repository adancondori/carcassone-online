# Carcassonne Scoreboard

Marcador digital para el juego de mesa Carcassonne. Reemplaza el tablero fisico de puntuacion con una version interactiva que registra puntos, soporta deshacer/rollback, y muestra un tablero SVG con fichas de meeple en tiempo real.

Disenado mobile-first para usar en la mesa de juego desde un telefono o tablet.

**Esto NO es una implementacion del juego Carcassonne** -- solo el componente de puntuacion. El usuario decide que puntuar; la app lo registra y visualiza.

## Funcionalidades

### Gestion de partidas
- Crear partidas con nombre personalizado
- Agregar 2-6 jugadores con nombres unicos y colores de meeple
- Dashboard principal con estadisticas globales, top ganadores, y partidas recientes

### Puntuacion
- Seleccion de uno o multiples jugadores (puntuacion compartida para empates de mayoria)
- Tipos de evento: Ciudad, Camino, Monasterio, Manual
- Botones rapidos (+1 a +10) o puntuacion personalizada
- Nota opcional por accion (ej: "ciudad del norte")
- Todas las acciones son atomicas: una transaccion por accion

### Tablero SVG
- Replica visual del tablero de puntuacion fisico de Carcassonne
- Fichas con forma de meeple posicionadas en la casilla correcta (score % 50)
- Apilamiento radial cuando multiples jugadores comparten casilla
- Insignia de vuelta (x1, x2, x3...) para jugadores que superan la casilla 49
- Actualizacion en tiempo real via HTMX OOB

### Historial y Rollback
- Historial completo de acciones en orden cronologico inverso
- Cada entrada muestra tipo de evento, jugadores afectados y puntos
- Rollback a cualquier accion anterior (todas las posteriores se marcan como deshechas)
- Acciones deshechas permanecen visibles pero tachadas
- Deshacer la ultima accion con un solo boton

### Estados de juego
- Maquina de estados: configuracion -> en juego -> puntuacion final -> finalizada
- En juego: solo tipos de estructura completada (camino/ciudad/monasterio + manual)
- Puntuacion final: solo tipos finales (camino/ciudad/monasterio final + granja + manual)
- Estado finalizado: pantalla de resultados con ranking, solo lectura

### Interfaz
- Mobile-first: touch targets >= 48px, sin scroll horizontal
- Actualizaciones sin recarga via HTMX (score table, controles, historial, tablero, barra de transicion)
- Tema oscuro inspirado en la caja de Carcassonne

## Stack tecnico

| Componente | Tecnologia |
|-----------|-----------|
| Backend | Python 3.12, FastAPI |
| Base de datos | SQLite (WAL mode) + SQLModel ORM |
| Migraciones | Alembic (batch mode para SQLite) |
| Templates | Jinja2 + jinja2-fragments |
| Interactividad | HTMX (OOB swaps, sin JS frameworks) |
| Frontend | CSS custom (sin frameworks), SVG server-side |
| Testing | pytest (117 tests) |
| Deploy | Docker + docker-compose |

## Instalacion

### Con Docker (recomendado)

```bash
git clone git@github.com:adancondori/carcassone-online.git
cd carcassonne-scoreboard
docker compose up --build
```

Abrir http://localhost:8000

### Sin Docker

Requisitos: Python 3.12+

```bash
git clone git@github.com:adancondori/carcassone-online.git
cd carcassonne-scoreboard

# Crear entorno virtual
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# Instalar dependencias
pip install -e ".[dev]"

# Crear directorio de datos
mkdir -p data

# Ejecutar migraciones
alembic upgrade head

# Iniciar servidor
uvicorn app.main:app --reload --port 8000
```

Abrir http://localhost:8000

## Tests

```bash
# Todos los tests
pytest

# Con detalle
pytest -v

# Solo tests de servicios
pytest tests/test_services.py

# Solo tests web
pytest tests/test_web.py
```

## Estructura del proyecto

```
app/
  main.py              # FastAPI app, lifespan, health check
  models.py            # SQLModel: Game, Player, ScoreAction, ScoreEntry
  services.py          # Logica de negocio: scoring, undo, rollback, estados
  db.py                # Engine, session, SQLite pragmas
  config.py            # Settings via pydantic-settings
  web/
    routes.py          # Rutas HTTP: setup, dashboard, scoring, transiciones
    dependencies.py    # Templates, colores, labels, coordenadas del tablero
  templates/
    base.html          # Layout base con HTMX
    home.html          # Dashboard principal con estadisticas
    setup.html         # Pagina de configuracion de partida
    dashboard.html     # Tablero de juego con bloques OOB
  static/
    css/style.css      # Estilos unificados
    js/controls.js     # UI efimera para formulario de puntuacion
    images/            # Foto del tablero de Carcassonne
tests/
  conftest.py          # Fixtures: engine in-memory, session, client
  test_models.py       # Tests de modelos (current_cell, lap)
  test_services.py     # Tests de servicios (scoring, undo, rollback, estados)
  test_web.py          # Tests de integracion web (setup, scoring, historial, tablero, estados)
```

## Modelo de datos

```
Game (id, name, status, created_at)
  |
  +-- Player (id, game_id, name, color, score_total, turn_order)
  |
  +-- ScoreAction (id, game_id, event_type, description, is_undone, created_at)
        |
        +-- ScoreEntry (id, action_id, player_id, points, score_before, score_after)
```

- `score_total` es un cache que se recalcula desde entries activas en cada undo/rollback
- `is_undone` marca acciones deshechas sin borrarlas (auditabilidad)
- Una accion puede tener multiples entries (puntuacion compartida)

## Uso

1. Abrir http://localhost:8000
2. Click en "Nueva partida"
3. Nombrar la partida y agregar 2-6 jugadores
4. "Iniciar partida" abre el tablero de juego
5. Seleccionar jugador(es), tipo de evento, puntos, y "Anotar puntos"
6. El tablero SVG y la tabla de scores se actualizan en tiempo real
7. Usar "Deshacer" para revertir la ultima accion, o tap en el historial para rollback
8. "Puntuacion final" cambia a tipos de evento finales (granjas, estructuras incompletas)
9. "Terminar partida" muestra el ranking final

## Licencia

MIT
