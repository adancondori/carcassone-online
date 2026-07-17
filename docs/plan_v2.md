# Plan v2 — Puntuación por voz y modo mesa

> **Estado: APROBADO** (2026-07-17). Pendiente: iniciar Fase 1 (parser).

## Problema

En la práctica, anotar puntos durante la partida es lento: hay que
seleccionar jugadores, tipo de evento y puntos manualmente en la pantalla.
Eso interrumpe el ritmo del juego en la mesa.

## Objetivo

Anotar puntos hablando: el usuario mantiene presionado un control
(tecla espacio en laptop, botón de micrófono en el teléfono), dice
"agrega 5 puntos al rojo y al negro", y los puntos se aplican de inmediato
con la interpretación visible y deshacer a un toque. Complementado con un
**modo mesa**: marcador gigante a pantalla completa para dejar el dispositivo
visible mientras se juega, controlado solo por voz.

**Métrica de éxito**: anotar una puntuación típica toma < 5 segundos de
principio a fin, y una interpretación errónea se corrige con un solo
tap o Cmd+Z.

## Decisiones

| Decisión | Elección | Rationale |
|----------|----------|-----------|
| Motor de voz (resuelve la sección "Search") | **faster-whisper local** (server-side, dentro del contenedor Docker) | Privado (el audio nunca sale de casa), sin costo por uso, funciona sin internet. A cambio: modelo en el contenedor y latencia de CPU. |
| Dispositivos | **Ambos**: espacio (laptop) y enter para confirmar y finalizar + botón mantener-presionado (teléfono) | La app es mobile-first; la tecla espacio cubre laptop. |
| Confirmación | **Aplicar directo** + toast con interpretación + Deshacer visible | El undo atómico ya existe; confirmar cada comando mataría la velocidad ("lo más práctico posible"). |
| Tipo de evento | **Opcional en la frase**, default `MANUAL` | "Ciudad 8 al rojo" → historial rico; "5 al rojo" → funciona igual. |
| Parsing | **Server-side, Python puro** (sin LLM, sin dependencias) | Determinista, barato, 100% testeable con TDD — el estilo de este proyecto. |
| Identificador de jugador | **El color** (rojo, azul, verde, amarillo, negro, rosa) | Canónico, corto, ya es único por partida (constraint en DB). |
| Rehacer (Cmd+Shift+Z) | **Nuevo servicio `redo_last`** que reactiva acciones deshechas | Hoy solo existe undo/rollback; rehacer requiere lógica nueva (ver abajo). |
| HTTPS en LAN | **mkcert** (certificado local montado en uvicorn) | Sin contenedor extra ni reverse proxy; un comando genera el cert confiable para la LAN. |

## Arquitectura

```
[Navegador]                         [FastAPI]
push-to-talk (espacio / botón mic)
  └─ MediaRecorder graba clip
       └─ POST /games/{id}/voice ──► transcriber.py (faster-whisper)
          (multipart, audio blob)        └─ texto transcrito
                                      parser.py (gramática pura)
                                         └─ VoiceCommand | ParseError
                                      services.add_score()  ◄── reutiliza TODAS
                                         └─ ScoreAction+Entries   las validaciones
                                      voice_log (auditoría)
          fragmentos HTMX + toast ◄── _render_dashboard_fragments()
```

Módulos nuevos, cada uno con una sola responsabilidad:

- `app/voice/parser.py` — texto → `VoiceCommand` estructurado. Python puro,
  sin I/O. Aquí vive toda la gramática.
- `app/voice/transcriber.py` — audio bytes → texto. Envuelve faster-whisper
  (modelo singleton, carga perezosa). Inyectable como dependencia para
  poder simularlo en tests.
- `app/services.py` — nueva función `redo_last` (rehacer).
- `app/models.py` — nueva tabla `voice_log`.
- `app/web/routes.py` — rutas nuevas: `POST /games/{id}/voice`,
  `POST /games/{id}/redo`.
- `app/static/js/voice.js` — captura de audio, shortcuts y estados de UI.

### Escalabilidad y robustez (diseño para futuras mejoras)

La arquitectura define **seams** (costuras) explícitos: puntos donde mañana
se puede crecer o reemplazar piezas sin reescribir el resto.

1. **Motor de voz intercambiable (puerto/adaptador).** `Transcriber` es un
   Protocol de Python (`transcribe(audio: bytes) -> str`);
   `FasterWhisperTranscriber` es solo la implementación v1, elegida por
   `voice_engine` en Settings. Cambiar a Whisper API, Vosk o un motor GPU
   = escribir una clase nueva + cambiar config. Parser, rutas y tests no se
   enteran (los tests ya inyectan un transcriber falso por dependency
   override).
2. **Intents extensibles.** El parser no devuelve "puntos" sino
   `VoiceCommand(intent="add_score", ...)` y el endpoint despacha por
   intent. v1 tiene un solo intent, pero agregar "deshacer por voz" o
   "pasar a puntuación final" mañana = un intent nuevo + su handler, sin
   tocar el pipeline de audio ni la gramática existente.
3. **Vocabulario como datos, no como código.** Tipos de evento, colores y
   verbos viven en mapas/frozensets (el patrón actual de `services.py`).
   Las expansiones del juego (Posadas y Catedrales, etc. — ya previstas en
   PROJECT.md como event types futuros) se agregan como entradas de datos
   más una migración del CHECK constraint.
4. **Protección del servidor.** Límite de tamaño del clip (~1MB ≈ 15s),
   semáforo que serializa las transcripciones (CPU-bound: una a la vez),
   rutas sync en threadpool (el patrón que el proyecto ya usa). El endpoint
   **nunca** propaga un 500 por audio malo: toda falla termina tipificada
   en `voice_log` y como toast legible.
5. **Camino de crecimiento sin reescritura.** El transcriber es el único
   componente pesado y nada más lo conoce: su interfaz es el punto exacto
   para extraerlo a un worker/cola o moverlo a GPU si algún día hace falta.
   La DB ya migra a PostgreSQL cambiando el connection string. El contrato
   HTMX de fragmentos no cambia con nada de esto.
6. **Observabilidad.** `voice_log` guarda `duration_ms` por comando para
   detectar degradación; los rechazos van al logger del servidor (patrón
   `logger.warning` ya establecido); `/health` reporta el estado del modelo
   (`{"status": "ok", "whisper": "loaded" | "cold"}`).

**Deliberadamente fuera (YAGNI):** colas de mensajes, microservicios,
websockets. La escala real es una mesa de juego; los seams anteriores
garantizan que, si eso cambia, se crece sin reescribir.

## Gramática de comandos

### Forma general

```
comando  := [verbo] grupo ( ("y" | ",") grupo )*
grupo    := [tipo] cantidad ["puntos"] destinos
          | destinos cantidad ["puntos"]
verbo    := agrega | añade | suma | anota | pon | quita | resta
cantidad := dígitos ("5") | palabras ("cinco", "veintiuno", "sesenta y uno")
destinos := ["al" | "a la" | "a" | "para"] color ( ("y" | ",") ["al"] color )*
color    := rojo | azul | verde | amarillo | negro | rosa
tipo     := camino | ciudad | monasterio | granja
```

### Reglas (para evitar la explosión de combinaciones)

1. **El color es el único identificador de jugador.** Nunca nombres.
2. **`quita`/`resta` genera puntos negativos** y siempre se registra como
   `MANUAL` (es una corrección, no un evento del juego).
3. **El tipo se mapea según el estado de la partida**: "camino" en estado
   `playing` → `ROAD_COMPLETED`; en `scoring` → `ROAD_FINAL`. "Granja" solo
   es válida en `scoring` (`add_score` ya rechaza tipos inválidos por estado).
4. **Una frase = una acción** (un `ScoreAction`). Varios grupos con montos
   distintos generan entries distintos dentro de la misma acción — el modelo
   actual ya lo soporta.
5. **Cantidad compartida**: si un grupo tiene varios colores, todos reciben
   el mismo monto (regla de mayoría empatada de Carcassonne).
6. Lo que no calce con la gramática → error legible, nunca interpretación
   "creativa".

### Ejemplos

| Frase | Resultado |
|-------|-----------|
| "agrega 5 puntos al rojo" | +5 rojo, MANUAL |
| "ciudad 8 al rojo y al amarillo" | +8 rojo, +8 amarillo, CITY_COMPLETED (compartida) |
| "suma 5 al rojo y 20 al negro" | +5 rojo, +20 negro, una sola acción MANUAL |
| "camino cuatro azul" | +4 azul, ROAD_COMPLETED |
| "quita 3 al verde" | −3 verde, MANUAL |
| "granja 9 rosa" (en scoring) | +9 rosa, FARM_FINAL |
| "granja 9 rosa" (en playing) | Error: "Granja solo vale en puntuación final" |
| "agrega puntos al morado" | Error: "No hay jugador de color morado en esta partida" |

## Rehacer (redo)

Semántica de `redo_last`, consistente con el undo existente:

- Solo son **rehacibles** las acciones deshechas con `id` mayor que la
  última acción activa (es decir, la "pila" de undos recientes).
- `redo_last` reactiva la rehacible de menor `id` (el orden natural:
  undo, undo, redo, redo vuelve al estado original).
- **Anotar algo nuevo invalida el redo** (comportamiento estándar de
  cualquier editor): las acciones deshechas anteriores dejan de ser
  rehacibles porque quedan detrás de la nueva acción.
- Recalcula puntajes desde entries, igual que undo/rollback.
- Bloqueado en estado `finished`.

## Modelo de datos

Nueva tabla `voice_log` (cubre los tres logs del plan original: texto
escuchado, puntuación aplicada y errores):

```
voice_log
├── id            PK
├── game_id       FK → game.id
├── transcript    str            (texto que devolvió Whisper)
├── parsed        str | None     (JSON del VoiceCommand interpretado)
├── status        str            CHECK: applied | parse_error |
│                                validation_error | empty_audio
├── error_detail  str | None
├── action_id     FK → score_action.id | None  (si se aplicó)
├── duration_ms   int            (latencia total, para calibrar)
└── created_at    datetime
```

Migración Alembic con batch mode, como las existentes.

## API

- `POST /games/{game_id}/voice` — multipart con campo `audio` (blob del
  MediaRecorder). Siempre responde 200 con los fragmentos HTMX de siempre
  **más un fragmento de toast** con la interpretación o el error:
  - Éxito: "🎤 +5 Rojo, +5 Amarillo — Camino" (con los meeple-dots del tema).
  - Error de parsing: transcript + motivo: "No entendí: ‹agrega puntos
    rojo› — falta la cantidad".
  - Silencio: "No escuché nada, intenta de nuevo".
- `POST /games/{game_id}/redo` — rehace la última acción deshecha y devuelve
  los mismos fragmentos (patrón idéntico a `/undo`).

## UI / UX

### Entrada manual vs voz (sección "Botón" del plan original)

Toggle en el panel de controles con dos pestañas: **Manual** (los controles
actuales) y **Voz** (botón de micrófono grande + últimas interpretaciones).
El modo se recuerda en `localStorage`. La voz también funciona desde el modo
manual vía tecla espacio — el toggle solo cambia qué se ve.

### Push-to-talk

- **Laptop**: mantener **espacio** = grabar; soltar (o **Enter**) = finalizar
  y enviar. Se ignora si el foco está en un input o textarea. **Esc** cancela
  la grabación sin enviar.
- **Teléfono**: botón de micrófono grande, mantener presionado
  (touchstart/touchend). Mínimo 48px.
- Estados visibles con los tokens del tema pastel: pill "🎤 Escuchando…"
  (miel) → "Procesando…" (salvia) → toast resultado (hoja/arcilla).

### Modo mesa (sección "FrontEnd" del plan original)

Botón "Modo mesa" en el dashboard → vista a pantalla completa
(Fullscreen API) pensada para dejar el dispositivo apoyado en la mesa:

```
┌─────────────────────────────────────────────┐
│   ● Rojo      ● Azul     ● Amarillo  ● Negro │
│    45          38           52         29    │
│   (♟ casilla 45 ×0)  ...                     │
│                                              │
│              [ 🎤 mantener para hablar ]     │
└─────────────────────────────────────────────┘
```

- Puntajes gigantes (Fredoka), un panel por jugador con su color de meeple,
  ordenados por puntaje; se actualiza con los mismos swaps OOB de HTMX.
- El botón/tecla de voz sigue activo — es el modo "solo mirar y hablar".
- **Screen Wake Lock API** para que la pantalla no se apague en la mesa.
- Salir: botón ✕ o Esc.

### Shortcuts (sección "Shortcuts" del plan original)

| Tecla | Acción |
|-------|--------|
| `Espacio` (mantener) | Grabar comando de voz |
| `Enter` | Finalizar y enviar la grabación en curso |
| `Esc` | Cancelar grabación sin enviar / salir del modo mesa |
| `Cmd/Ctrl + Z` | Deshacer última acción |
| `Cmd/Ctrl + Shift + Z` | Rehacer acción deshecha |

Los shortcuts se ignoran cuando el foco está en un campo de texto (para no
pelear con el undo nativo del navegador).

## Configuración e infra (todo Dockerizado)

- En `Settings` (config.py): `whisper_model` (default `"small"`),
  `whisper_device` (`"cpu"`), `whisper_compute` (`"int8"`),
  `voice_language` (`"es"`).
- Transcripción con `vad_filter=True` (evita alucinaciones en silencio) e
  `initial_prompt` con el vocabulario del dominio ("puntos, camino, ciudad,
  monasterio, granja, rojo, azul, verde, amarillo, negro, rosa").
- Docker: `faster-whisper` en la imagen; volumen para el cache del modelo
  (`~/.cache/huggingface`) para no re-descargar ~250MB en cada build.
- El modelo `small` int8 da buen español con ~2s por clip corto en CPU
  moderna; `base` como fallback si la latencia molesta.

## Riesgos y mitigaciones

| Riesgo | Mitigación |
|--------|------------|
| **`getUserMedia` exige HTTPS fuera de localhost** — el teléfono por LAN no podrá usar el micrófono con `http://192.168.x.x`. Es el bloqueante n.º 1 del caso de uso principal. (Wake Lock también lo requiere.) | **Decidido: mkcert.** Certificado local montado en uvicorn (`--ssl-keyfile/--ssl-certfile`) vía docker-compose; instalar la CA de mkcert en el teléfono una sola vez. |
| Latencia de Whisper en CPU | Clips cortos por diseño (push-to-talk), modelo `small` int8, VAD. Mostrar "Procesando…" para que la espera sea legible. |
| Whisper transcribe números como palabras ("sesenta y uno") | El parser normaliza palabras numéricas 0–99 además de dígitos. |
| Confusión rojo/rosa u otras palabras cercanas | `initial_prompt` con vocabulario + revisar `voice_log` para calibrar. El toast + Cmd+Z hace que el costo de un error sea mínimo. |
| Formatos de audio distintos por navegador (Chrome: webm/opus, Safari: mp4/aac) | faster-whisper decodifica ambos vía PyAV. Probar en ambos navegadores en la fase de verificación. |
| Ruido de la mesa activando grabación | No hay activación por sonido: solo push-to-talk explícito. |

## Fases de implementación

1. **Parser (TDD, sin I/O)** — gramática completa, números en palabras,
   colores→jugadores, tipos por estado, multi-grupo, verbos de resta,
   errores legibles. La fase con más casos borde; barata de probar
   exhaustivamente porque es Python puro.
2. **Redo + shortcuts de servicio (TDD)** — `redo_last` con su semántica de
   pila, ruta `/redo`, tests. Independiente de la voz; entrega valor sola.
3. **Transcriber + config** — wrapper de faster-whisper con carga perezosa,
   settings, Docker (dependencia + volumen de cache), prueba con fixture de
   audio corto (marcada `slow`, opcional en CI).
4. **Endpoint de voz + voice_log + migración** — ruta multipart, integración
   parser→`add_score`, logging de todos los resultados, fragmento de toast,
   tests de integración con transcriber simulado (dependency override, el
   mismo patrón de los tests web actuales).
5. **Frontend voz** — `voice.js` (MediaRecorder, push-to-talk, estados),
   botón mic móvil, toggle Manual/Voz, shortcuts Cmd+Z / Cmd+Shift+Z,
   estilos con los tokens pastel.
6. **Modo mesa** — vista fullscreen de puntajes gigantes, Wake Lock,
   integración con voz.
7. **Infra HTTPS + calibración real** — mkcert para LAN (cert montado en el
   contenedor, CA instalada en el teléfono), probar en teléfono real en
   Chrome y Safari, revisar `voice_log` y ajustar gramática e
   `initial_prompt`.

Las fases 1–4 son testeables sin micrófono ni navegador; 5–7 requieren
verificación manual en dispositivo real. La fase 2 puede adelantarse o
posponerse sin bloquear nada.

## Fuera de alcance (v1)

- Activación por palabra clave ("oye Carcassonne") — solo push-to-talk.
- Comandos de voz que no sean puntuación (deshacer por voz, cambiar estado).
- Nombres de jugadores en la gramática — solo colores.
- Otros idiomas — solo español.
- Panel de administración de logs — `voice_log` se consulta por SQL/futuro.
