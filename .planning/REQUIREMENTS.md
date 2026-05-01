# Requirements: Carcassonne Scoreboard

**Defined:** 2026-05-01
**Core Value:** Players can accurately track scores during a Carcassonne game with undo capability, so mistakes at the table are never permanent.

## v1 Requirements

### Game Setup (SETUP)

- [ ] **SETUP-01**: User can create a new game session with a name
- [ ] **SETUP-02**: User can add 2-6 players with unique names
- [ ] **SETUP-03**: Each player is assigned a unique color from the 6 Carcassonne base colors
- [ ] **SETUP-04**: User can remove a player during setup
- [ ] **SETUP-05**: Game transitions from setup to playing when user starts the game

### Scoring (SCORE)

- [ ] **SCORE-01**: User can add points to a selected player with quick-tap buttons (+1 to +10) or custom input
- [ ] **SCORE-02**: Each scoring action is labeled with an event type (road, city, monastery, manual)
- [ ] **SCORE-03**: User can score multiple players in one action (shared scoring for majority ties)
- [ ] **SCORE-04**: All entries in a shared scoring action are written atomically (one transaction)
- [ ] **SCORE-05**: Optional text note can be attached to any scoring action
- [ ] **SCORE-06**: player.score_total is updated transactionally but recalculated from active entries on undo/rollback

### Undo & Rollback (UNDO)

- [ ] **UNDO-01**: User can undo the last scoring action (all entries in the action are reversed)
- [ ] **UNDO-02**: User can rollback to any previous action (all subsequent actions are marked undone)
- [ ] **UNDO-03**: Undone actions remain visible in history (struck through) for auditability
- [ ] **UNDO-04**: Undo/rollback recalculates affected player scores from active entries (not from score_before)

### Visual Board (BOARD)

- [ ] **BOARD-01**: SVG board displays the real Carcassonne scoring track photo as background
- [ ] **BOARD-02**: Meeple-shaped tokens are positioned on the correct cell for each player
- [ ] **BOARD-03**: Multiple tokens on the same cell stack with radial offset for visibility
- [ ] **BOARD-04**: Lap badge (x1, x2, x3...) displayed on tokens for players past cell 49
- [ ] **BOARD-05**: Board is responsive and usable on mobile phones (SVG viewBox scaling)

### Score Display (DISPLAY)

- [ ] **DISPLAY-01**: Score table shows all players ranked by total score
- [ ] **DISPLAY-02**: Each row shows player name, color dot, total score, current cell, and lap
- [ ] **DISPLAY-03**: Action history shows grouped entries per action with event type and player details
- [ ] **DISPLAY-04**: HTMX updates score table, board tokens, and history without page reload

### Game States (STATE)

- [ ] **STATE-01**: Game follows state machine: setup -> playing -> scoring -> finished
- [ ] **STATE-02**: In playing state, available event types are: road/city/monastery completed + manual
- [ ] **STATE-03**: In scoring state, available event types are: road/city/monastery final + farm final + manual
- [ ] **STATE-04**: Finished state is read-only with final ranking

### Infrastructure (INFRA)

- [ ] **INFRA-01**: Project runs with `docker compose up --build`
- [ ] **INFRA-02**: SQLite database with Alembic migrations (batch mode enabled)
- [ ] **INFRA-03**: SQLite foreign_keys pragma enabled per connection + WAL mode
- [ ] **INFRA-04**: pytest test suite covering models, services, and API endpoints
- [ ] **INFRA-05**: FastAPI serves both API endpoints and Jinja2 HTML templates

## v2 Requirements

### Optional Features

- **OPT-01**: Turn tracking — indicator of current player, next-turn button
- **OPT-02**: Export game to JSON
- **OPT-03**: Import game from JSON
- **OPT-04**: Token movement animation step-by-step along the track
- **OPT-05**: Haptic feedback on score entry (navigator.vibrate)
- **OPT-06**: Expansion event types (Inns & Cathedrals, Traders & Builders, Abbot)
- **OPT-07**: Per-game expansion configuration (select active expansions)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Game logic / rule enforcement | App is a scorer, not a game engine. User decides what to score. |
| Multiplayer networking | Single device at the table. Adds WebSocket complexity for no value. |
| User accounts / auth | Zero-friction start. No login needed for table-side tool. |
| BGG integration / cloud sync | Different product (BGStats). Focus on in-game experience. |
| Statistics / analytics | Different product. Maybe export JSON for external analysis. |
| Sound effects | Annoying at game table. Haptic feedback is better. |
| PWA / installable app | Over-engineering for v1. Can add later. |
| Score hiding | Contradicts physical Carcassonne (board visible to all). |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| SETUP-01 | Phase 1 | Pending |
| SETUP-02 | Phase 1 | Pending |
| SETUP-03 | Phase 1 | Pending |
| SETUP-04 | Phase 1 | Pending |
| SETUP-05 | Phase 1 | Pending |
| SCORE-01 | Phase 1 | Pending |
| SCORE-02 | Phase 1 | Pending |
| SCORE-03 | Phase 1 | Pending |
| SCORE-04 | Phase 1 | Pending |
| SCORE-05 | Phase 1 | Pending |
| SCORE-06 | Phase 1 | Pending |
| UNDO-01 | Phase 2 | Pending |
| UNDO-02 | Phase 2 | Pending |
| UNDO-03 | Phase 2 | Pending |
| UNDO-04 | Phase 2 | Pending |
| DISPLAY-01 | Phase 1 | Pending |
| DISPLAY-02 | Phase 1 | Pending |
| DISPLAY-03 | Phase 2 | Pending |
| DISPLAY-04 | Phase 2 | Pending |
| BOARD-01 | Phase 3 | Pending |
| BOARD-02 | Phase 3 | Pending |
| BOARD-03 | Phase 3 | Pending |
| BOARD-04 | Phase 3 | Pending |
| BOARD-05 | Phase 3 | Pending |
| STATE-01 | Phase 4 | Pending |
| STATE-02 | Phase 4 | Pending |
| STATE-03 | Phase 4 | Pending |
| STATE-04 | Phase 4 | Pending |
| INFRA-01 | Phase 1 | Pending |
| INFRA-02 | Phase 1 | Pending |
| INFRA-03 | Phase 1 | Pending |
| INFRA-04 | Phase 1 | Pending |
| INFRA-05 | Phase 1 | Pending |

**Coverage:**
- v1 requirements: 33 total
- Mapped to phases: 33
- Unmapped: 0

---
*Requirements defined: 2026-05-01*
*Last updated: 2026-05-01 after research synthesis*
