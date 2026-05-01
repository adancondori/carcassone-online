# Domain Pitfalls

**Domain:** Board game scoring web app (Carcassonne scoreboard)
**Stack:** FastAPI + SQLite + HTMX + Jinja2 + SQLModel + Docker
**Researched:** 2026-05-01

---

## Critical Pitfalls

Mistakes that cause data loss, corruption, or require rewrites.

### Pitfall 1: score_total Cache Diverges from Entry Source of Truth

**Severity:** CRITICAL
**What goes wrong:** `player.score_total` (mutable cache) drifts out of sync with `SUM(score_entries.points WHERE is_undone=FALSE)`. This happens when add_score updates the cache but a crash/error occurs before commit, when undo/rollback code paths forget to recalculate, or when a new code path modifies entries without updating the cache.
**Why it happens:** Two sources of truth exist by design. The cache is an optimization for the happy path, but every write path must maintain both or they diverge. Event sourcing lite has fewer safeguards than full event sourcing because there is no automatic projection rebuild mechanism.
**Consequences:** Players see wrong scores. The board shows meeples on wrong cells. Undo appears to "not work" because the cache shows a different value than the recalculated one. Trust in the app is destroyed.
**Warning signs:**
- Unit test for `recalculate_score()` returns a different value than `player.score_total` after a sequence of add/undo/add operations
- Any code path that writes to `score_entries` without also calling `recalculate_score()` or updating `score_total`
- Missing transaction boundaries (partial commits)
**Prevention:**
1. Always recalculate from entries on undo/rollback (the plan already does this -- good)
2. Add a DB-level CHECK or application-level assertion that runs `recalculate_score()` after every commit in tests
3. Write a "consistency check" test that runs 50+ random add/undo/rollback sequences and asserts cache == recalculated after every operation
4. Consider making `score_total` a computed property in the API response layer (calculate on read) and only cache in the DB column for query convenience
**Detection:** Automated property-based tests (hypothesis library) generating random score/undo/rollback sequences
**Phase:** Phase 1 (must be correct from day one -- this is the core data model)
**Confidence:** HIGH (this is a well-known event sourcing pitfall documented extensively)

### Pitfall 2: SQLite Data Loss in Docker from Volume Misconfiguration

**Severity:** CRITICAL
**What goes wrong:** SQLite database file disappears or reverts to an earlier state after `docker compose down && docker compose up` or container rebuild. Data written during a session is lost entirely.
**Why it happens:** Three common causes:
1. Database path inside the container does not match the volume mount target
2. Using an anonymous volume instead of a named volume (anonymous volumes are not reused after `docker compose down`)
3. WAL mode creates `-wal` and `-shm` sidecar files; if only the `.db` file is persisted but the WAL files are on the container filesystem, uncommitted WAL data is lost on container stop
**Consequences:** Complete loss of game data. Users lose in-progress and completed games.
**Warning signs:**
- `docker compose down && docker compose up` loses data
- Database file size is unexpectedly small after restart
- `.db-wal` and `.db-shm` files exist alongside the `.db` file but are not in the mounted volume
**Prevention:**
1. Mount the entire data *directory* (not just the `.db` file) as a named volume or bind mount so WAL files are included
2. The current plan mounts `db_data:/code/data` which is correct -- verify DATABASE_URL writes to `/code/data/carcassonne.db`
3. Add a smoke test: `docker compose down && docker compose up`, verify data survives
4. Force WAL checkpoint on graceful shutdown (PRAGMA wal_checkpoint(TRUNCATE)) to flush WAL into the main database file
5. Never bind-mount the `.db` file directly; always mount the parent directory
**Detection:** Manual test during Phase 1: create a game, stop Docker, restart, verify game exists
**Phase:** Phase 1 (Docker setup is in scope)
**Confidence:** HIGH (real-world data loss reports from n8n, Shlink, and other projects confirm this)

### Pitfall 3: Alembic Migrations Fail Silently on SQLite Schema Changes

**Severity:** CRITICAL
**What goes wrong:** SQLite does not support most ALTER TABLE operations (drop column, rename column with constraints, add/drop constraints). Alembic autogenerate creates migration scripts that work on PostgreSQL but fail or silently skip operations on SQLite. CHECK constraints and unnamed UNIQUE constraints are particularly problematic -- they may be silently dropped during migration.
**Why it happens:** SQLite's ALTER TABLE only supports ADD COLUMN and RENAME COLUMN. For any other change, Alembic must use "batch mode" which recreates the entire table, copies data, and drops the old one. Batch mode is not enabled by default.
**Consequences:** Schema migrations appear to succeed but constraints are missing. Data integrity violations go undetected. Migrating to production with missing CHECK constraints means invalid event_type values can be inserted.
**Warning signs:**
- Migration script contains `op.drop_constraint()`, `op.alter_column()`, or `op.drop_column()` without `with op.batch_alter_table()` wrapper
- Running `alembic upgrade head` produces no errors but schema inspection shows missing constraints
- Tests pass with in-memory SQLite but fail with file-based SQLite
**Prevention:**
1. Enable batch mode in `alembic/env.py`: `context.configure(..., render_as_batch=True)`
2. Name ALL constraints explicitly in SQLModel models (unnamed constraints cannot be targeted by batch operations)
3. After every migration, run a schema validation test that checks all expected constraints exist
4. Test migrations against a file-based SQLite database, not just in-memory
**Detection:** Schema inspection tests; `PRAGMA table_info()` and `PRAGMA index_list()` checks after migration
**Phase:** Phase 1 (Alembic setup is in scope)
**Confidence:** HIGH (Alembic official documentation explicitly documents this limitation)

---

## Moderate Pitfalls

Mistakes that cause bugs, poor UX, or technical debt requiring significant rework.

### Pitfall 4: HTMX Partial Updates Leave Dashboard in Inconsistent State

**Severity:** MODERATE
**What goes wrong:** After scoring, the server updates the score table but forgets to also update the board SVG (meeple positions), the history panel, or the lap indicators. The user sees updated scores in the table but meeples are on old positions. Or after undo, the history shows the action as undone but the score table still shows old values.
**Why it happens:** HTMX partial updates only swap the targeted element. When one action affects multiple dashboard sections (score table, SVG board, history, controls), each must be explicitly updated via `hx-swap-oob` or by targeting a common parent. It is easy to add a new dashboard section and forget to include it in the OOB swap list.
**Consequences:** Dashboard shows contradictory information. Users do not trust the scores. They refresh the page to "fix" it, which works but defeats the purpose of HTMX partial updates.
**Warning signs:**
- Pressing F5/refresh changes what the user sees (stale partial state was visible)
- New dashboard sections are added but not included in score/undo response templates
- OOB swap IDs do not match element IDs in the page (silent failure -- HTMX does not warn)
**Prevention:**
1. Define a clear "update contract": every scoring/undo endpoint returns ALL affected fragments via OOB swaps
2. Create a single response builder function that assembles all fragments (score table, board, history) so nothing is forgotten
3. Use `jinja2-fragments` (Jinja2Blocks) to render individual template blocks from the same template, keeping full-page and partial responses in sync
4. Test: after every HTMX action, compare the partial-updated DOM against a full page refresh
5. Consider returning the entire dashboard content area as one swap for simplicity (small page, not a performance concern)
**Detection:** Selenium/Playwright test that scores, checks all sections, undoes, checks all sections again
**Phase:** Phase 1 (HTMX setup) and Phase 3 (SVG board adds another section to keep in sync)
**Confidence:** HIGH (HTMX OOB documentation and community discussions confirm this pattern)

### Pitfall 5: Async/Sync Mismatch Blocks FastAPI Event Loop

**Severity:** MODERATE
**What goes wrong:** Using `async def` for route handlers while performing synchronous SQLite/SQLAlchemy operations blocks the FastAPI event loop. Under concurrent requests (even just 2-3 simultaneous users refreshing), the app becomes unresponsive.
**Why it happens:** SQLite and synchronous SQLAlchemy are blocking I/O. If the route handler is `async def`, FastAPI runs it directly on the event loop. A blocking database call in an `async def` function freezes the entire event loop until the query completes. With `def` (non-async), FastAPI automatically runs the handler in a thread pool, avoiding the block.
**Consequences:** App freezes momentarily under any concurrent access. Scores appear to "hang" for seconds. Particularly noticeable during rapid scoring sequences at the game table.
**Warning signs:**
- Route handlers are declared as `async def` but call synchronous SQLAlchemy session methods
- Response times spike when two browser tabs are open simultaneously
- No `await` statements inside `async def` handlers (indicates sync operations in async context)
**Prevention:**
1. Use `def` (not `async def`) for all route handlers that perform synchronous database operations. FastAPI will run them in a threadpool automatically.
2. Alternatively, use `run_in_threadpool()` for database calls within `async def` handlers
3. Add a linting rule or code review checklist: "no `async def` routes with synchronous DB calls"
4. For this project's scale (single device, single user), the impact is low -- but getting it right from the start prevents confusion later
**Detection:** Load test with 3-5 concurrent requests; response time should not degrade
**Phase:** Phase 1 (route handler setup)
**Confidence:** HIGH (FastAPI official docs explicitly document this behavior)

### Pitfall 6: SVG Coordinate Mapping Breaks on Different Devices

**Severity:** MODERATE
**What goes wrong:** Meeple positions are mapped from a photo of the physical board at specific pixel coordinates. On different screen sizes, aspect ratios, or when the SVG scales, meeples appear offset from their expected cell positions. Touch targets for cells do not align with the visual board.
**Why it happens:** Multiple failure modes:
1. viewBox aspect ratio does not match the board photo aspect ratio, causing `preserveAspectRatio` to add padding or crop
2. Coordinates are mapped in absolute pixels from the source image but the SVG renders at a different size
3. The plan specifies `preserveAspectRatio="none"` which stretches the image, distorting coordinates non-uniformly on non-matching aspect ratios
**Consequences:** Meeples appear between cells or on wrong cells. The app looks broken on certain phones. Touch interaction with the board is impossible if targets are misaligned.
**Warning signs:**
- Meeples look correct on the developer's screen but offset on a different phone
- Board photo appears stretched or squished
- Cell positions were mapped at one resolution and tested only at that resolution
**Prevention:**
1. Use `preserveAspectRatio="xMidYMid meet"` (not `"none"`) to maintain aspect ratio
2. Map cell coordinates as percentages of the viewBox, not as absolute pixels
3. Test on at least 3 different screen sizes/aspect ratios during Phase 3
4. Add a debug mode that renders cell position dots over the board for visual verification
5. Use the actual viewBox dimensions when mapping coordinates from the source photo
**Detection:** Visual regression test or manual verification on 3+ devices/screen sizes
**Phase:** Phase 3 (SVG board implementation)
**Confidence:** MEDIUM (based on SVG responsive design best practices and the project's specific design choices)

### Pitfall 7: score_before/score_after Denormalization Creates Phantom Inconsistencies

**Severity:** MODERATE
**What goes wrong:** The `score_entries` table stores `score_before` and `score_after` alongside `points`. After undo/rollback, these snapshot values become historically inaccurate because they reflected the state at the time of the original action, which has since been undone. Code that reads `score_before`/`score_after` from undone entries will see values that contradict the current score timeline.
**Why it happens:** `score_before` and `score_after` are denormalized snapshots. They are correct at write time but become stale relative to the current state after undo/rollback changes the effective timeline. They remain correct as "what was the score at the moment this entry was originally created" but misleading if interpreted as "what would the score be if we replayed to this point."
**Consequences:** Displaying `score_before`/`score_after` in the history panel after undo/rollback shows values that do not add up. Users see "Score: 8 -> 20" for an entry, but the player's current score is 0 because earlier entries were also undone. Debugging score discrepancies becomes confusing.
**Warning signs:**
- History UI shows `score_before`/`score_after` values that do not form a consistent chain after undo operations
- Developer confusion about whether these fields represent "original timeline" or "current timeline"
**Prevention:**
1. Document clearly: `score_before`/`score_after` are original-timeline snapshots, never rewritten
2. In the history UI, show only `points` (the delta), not absolute score snapshots, for undone entries
3. Consider whether `score_before`/`score_after` are needed at all -- `points` plus the action ordering provides the same information via recalculation
4. If kept, never use them for score calculation logic; always use `SUM(points)` from active entries
**Detection:** Test that adds 3 actions, undoes the middle one (via rollback), and verifies history display logic handles the snapshot gap correctly
**Phase:** Phase 2 (history display) and Phase 1 (data model design)
**Confidence:** MEDIUM (logical consequence of the denormalization design; less commonly documented)

### Pitfall 8: Touch Target Sizes Too Small on Mobile Board

**Severity:** MODERATE
**What goes wrong:** Score input buttons, player selection toggles, and board cells are too small for reliable finger tapping on a phone screen at the game table. Users mis-tap adjacent buttons, entering wrong scores or selecting wrong players.
**Why it happens:** Designing on a desktop monitor with mouse precision. Elements that are easy to click with a mouse are impossible to tap reliably with fingers. The average fingertip is 1.6-2 cm wide; interactive elements need to be at least 44-48px (CSS px) with 8px spacing.
**Consequences:** Frustration during gameplay. Scoring errors from mis-taps. Users abandon the app and go back to the physical scoreboard.
**Warning signs:**
- Prototype looks fine on desktop browser but buttons feel tiny on actual phone
- Users consistently tap the wrong score button or select the wrong player
- Point value buttons (+1, +2, +3, etc.) are packed tightly together
**Prevention:**
1. Design all interactive elements at minimum 48x48 CSS pixels with 8px gaps
2. Use CSS `@media (any-pointer: coarse)` to increase touch target sizes on touch devices
3. Place primary controls (score buttons, player selection) in the bottom half of the screen (thumb zone)
4. Test on a real phone from day one, not just browser DevTools
5. The prototypes already exist -- validate touch target sizes against the 48px minimum
**Detection:** Manual testing on a real phone; CSS audit of all interactive elements
**Phase:** Phase 1 (controls design) and Phase 3 (SVG board interaction)
**Confidence:** HIGH (well-established UX research from Nielsen Norman Group and platform guidelines)

---

## Minor Pitfalls

Mistakes that cause annoyance, minor bugs, or unnecessary complexity but are easily fixable.

### Pitfall 9: Template Duplication Between Full Page and HTMX Partials

**Severity:** MINOR
**What goes wrong:** The same UI component (e.g., score table) is defined twice: once in the full-page template and once as a standalone partial for HTMX responses. When one is updated, the other is forgotten, leading to visual inconsistencies.
**Why it happens:** Without a template fragment strategy, the natural approach is to create separate template files for partials. These diverge from the main template over time.
**Prevention:**
1. Use `jinja2-fragments` library (Jinja2Blocks) to render individual `{% block %}` sections from the main template
2. Define each dashboard section as a named block in `dashboard.html`
3. For HTMX responses, render only the specific block(s) needed
4. Full page renders the complete template; partials render individual blocks from the SAME template
**Phase:** Phase 1 (template architecture)
**Confidence:** HIGH (jinja2-fragments library exists specifically for this purpose)

### Pitfall 10: SQLite "Database is Locked" Under Concurrent Access

**Severity:** MINOR (for this project's single-user use case)
**What goes wrong:** Multiple simultaneous requests (e.g., two HTMX requests fired in quick succession) cause SQLite to return "database is locked" errors because SQLite allows only one writer at a time.
**Why it happens:** SQLAlchemy's default connection pooling can create multiple connections. If two requests try to write simultaneously (e.g., rapid button clicks), the second one gets a lock error. Without WAL mode and `busy_timeout`, the error is immediate rather than retried.
**Consequences:** Occasional "500 Internal Server Error" during rapid scoring. Score action may not be saved.
**Prevention:**
1. Enable WAL mode at startup: `PRAGMA journal_mode=WAL`
2. Set `busy_timeout`: `PRAGMA busy_timeout=5000` (wait up to 5 seconds for lock)
3. Use `NullPool` or `StaticPool` with SQLAlchemy to limit to a single connection (sufficient for single-user)
4. Configure via SQLAlchemy connect_args: `{"check_same_thread": False}` for SQLite with FastAPI
**Phase:** Phase 1 (database configuration)
**Confidence:** HIGH (SQLite and SQLAlchemy documentation confirm this)

### Pitfall 11: Game State Machine Transitions Not Enforced

**Severity:** MINOR
**What goes wrong:** The game status progresses `setup -> playing -> scoring -> finished`, but without enforcement, API calls can transition in invalid directions (e.g., `finished -> playing`) or actions can be performed in wrong states (e.g., adding players during `playing`).
**Why it happens:** State machine logic is documented but not enforced in code. Each endpoint independently checks status, and some forget to check. New endpoints added later may skip the check entirely.
**Consequences:** Invalid game states. Players added mid-game. Scoring happens on finished games.
**Prevention:**
1. Create a single `transition_state(game, new_status)` function that validates the transition
2. Add a decorator or dependency that validates game status for each endpoint category
3. Test every invalid transition explicitly: `finished -> playing`, `playing -> setup`, etc.
4. Use an enum for status values (not raw strings) so invalid values are caught at the type level
**Phase:** Phase 1 (game model) and Phase 4 (scoring/finished states)
**Confidence:** HIGH (standard state machine pattern)

### Pitfall 12: No Backup/Recovery for In-Progress Games

**Severity:** MINOR (for personal use; MODERATE if others use it)
**What goes wrong:** A Docker volume is accidentally deleted, the host machine crashes, or a bad migration corrupts the database. All game history is lost with no way to recover.
**Why it happens:** SQLite single-file database means one file to lose. No automated backup mechanism exists.
**Consequences:** Loss of in-progress or historical game data.
**Prevention:**
1. Add a simple backup script that copies the database file periodically
2. Use SQLite's `.backup` command (safe to run while app is active, handles WAL correctly)
3. Implement game export to JSON (planned for Phase 4) as a manual backup option
4. Consider a pre-shutdown hook in Docker that creates a backup before container stops
**Phase:** Phase 4 (export) or post-MVP
**Confidence:** HIGH (standard operational concern)

---

## Phase-Specific Warnings

| Phase | Likely Pitfall | Severity | Mitigation |
|-------|---------------|----------|------------|
| **Phase 1: Basic Game** | score_total cache divergence (#1) | CRITICAL | Property-based tests with random add/undo sequences |
| **Phase 1: Basic Game** | Docker volume data loss (#2) | CRITICAL | Mount data directory, smoke test restart |
| **Phase 1: Basic Game** | Alembic batch mode not enabled (#3) | CRITICAL | Set `render_as_batch=True` in env.py, name all constraints |
| **Phase 1: Basic Game** | Async/sync mismatch (#5) | MODERATE | Use `def` for all DB-touching routes |
| **Phase 1: Basic Game** | Template duplication (#9) | MINOR | Use jinja2-fragments from the start |
| **Phase 1: Basic Game** | SQLite locking (#10) | MINOR | Enable WAL + busy_timeout at startup |
| **Phase 1: Basic Game** | Touch target sizes (#8) | MODERATE | Design at 48px minimum, test on real phone |
| **Phase 2: History** | score_before/score_after confusion (#7) | MODERATE | Show only point deltas in history, document snapshot semantics |
| **Phase 2: History** | HTMX stale state (#4) | MODERATE | OOB swaps for all sections, single response builder |
| **Phase 3: SVG Board** | Coordinate mapping breaks (#6) | MODERATE | Use viewBox-relative coords, test on 3+ devices |
| **Phase 3: SVG Board** | Touch targets on board (#8) | MODERATE | Debug overlay for cell positions, verify on phone |
| **Phase 4: Final Scoring** | State machine not enforced (#11) | MINOR | Central transition function, test invalid transitions |
| **Phase 4: Final Scoring** | No backup mechanism (#12) | MINOR | Implement JSON export as manual backup |

---

## Meta-Pitfall: Overengineering for Single-User Scale

**What goes wrong:** Spending time on problems that do not exist at this project's scale: caching layers, read replicas, message queues, WebSocket real-time sync, elaborate retry mechanisms.
**Why it matters:** This is a single-device, single-user app used at a game table. The database will have ~100 rows per game. The only concurrent user is the same person tapping twice quickly.
**Prevention:** Build the simplest correct thing. Optimize only when a real problem is measured. The event sourcing lite pattern (score_actions + score_entries) is already the right level of sophistication for undo/rollback. Do not add more infrastructure.

---

## Sources

- [Alembic Batch Migrations for SQLite](https://alembic.sqlalchemy.org/en/latest/batch.html) -- HIGH confidence
- [FastAPI Concurrency and async/await](https://fastapi.tiangolo.com/async/) -- HIGH confidence
- [SQLite WAL Mode](https://sqlite.org/wal.html) -- HIGH confidence
- [Don't Forget the WAL: SQLite Data Loss in Containers](https://bkiran.com/blog/sqlite-containers-data-loss) -- HIGH confidence
- [HTMX hx-swap-oob Documentation](https://htmx.org/attributes/hx-swap-oob/) -- HIGH confidence
- [HTMX Template Fragments Essay](https://htmx.org/essays/template-fragments/) -- HIGH confidence
- [jinja2-fragments Library](https://github.com/sponsfreixes/jinja2-fragments) -- HIGH confidence
- [Touch Target Sizes - Nielsen Norman Group](https://www.nngroup.com/articles/touch-target-size/) -- HIGH confidence
- [SVG Coordinate Systems - Sara Soueidan](https://www.sarasoueidan.com/blog/svg-coordinate-systems/) -- HIGH confidence
- [Docker Persist the DB](https://docs.docker.com/get-started/workshop/05_persisting_data/) -- HIGH confidence
- [Event Sourcing Pitfalls](https://innovecs.com/blog/event-sourcing-101-when-to-use-and-how-to-avoid-pitfalls/) -- MEDIUM confidence
- [FastAPI Performance Mistakes](https://dev.to/igorbenav/fastapi-mistakes-that-kill-your-performance-2b8k) -- MEDIUM confidence
- [SQLAlchemy Database is Locked with SQLite](https://copyprogramming.com/howto/sqlalchemy-and-sqlite-database-is-locked) -- MEDIUM confidence
