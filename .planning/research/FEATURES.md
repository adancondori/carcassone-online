# Feature Landscape

**Domain:** Board game scoring tracker (Carcassonne-specific, web-based)
**Researched:** 2026-05-01
**Overall confidence:** MEDIUM — based on WebSearch survey of ~15 competing apps/tools, cross-referenced across multiple sources. WebFetch was unavailable for deep-dive verification.

## Competitive Landscape Summary

The Carcassonne scoring tool space splits into three tiers:

1. **Generic score keepers** (ScorePal, Scory, Keep Score, Score Pad, Scorecard.gg) — track numbers for any game. No Carcassonne-specific logic. Table stakes features: add/subtract points, player names/colors, history.
2. **Carcassonne-specific apps** (Carcassonne Scoreboard Android, Carcassonne Score Counter iOS, CarcassonneScorer.com, CarcaScorer) — know about event types (road, city, monastery, farm), expansions, and scoring rules. Some have visual tracks.
3. **Streaming/tournament tools** (TrackScore.online) — OBS overlays with real-time scoring, meeple tracking, turn indicators. Designed for broadcast, not table use.

No existing web app combines a visual SVG scoreboard track (replicating the physical board) with event-sourced undo/rollback and mobile-first design. This is the gap.

---

## Table Stakes

Features users expect from any scoring tracker. Missing any of these and the app feels broken or incomplete compared to alternatives.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Player setup (2-6 players)** | Every competitor supports this. Carcassonne base game is 2-5, expansions go to 6. | Low | Name + color assignment. Enforce unique colors per game. |
| **Add points to a player** | Fundamental purpose of the app. Every competitor does this. | Low | Quick-tap buttons (+1, +2, +3, etc.) plus custom input. |
| **Score display / leaderboard** | Users need to see current standings at a glance. All competitors show this. | Low | Ranked table with player name, color, total score. |
| **Undo last action** | Present in Carcassonne Scoreboard (Android), Score Anything, and most modern score apps. Users will accidentally enter wrong values. | Low | Undo the most recent scoring action completely. |
| **Scoring event types** | Carcassonne-specific apps (Scoreboard Android, CarcassonneScorer.com) categorize by road/city/monastery/farm. Users expect this from a Carcassonne-focused tool. | Low | Label each scoring action with its event type. |
| **Mobile-friendly UI** | Used at the game table on a phone. All modern score apps are mobile-first or responsive. | Medium | Touch targets, no tiny buttons, readable in ambient light. |
| **No account required** | Scorecard.gg, ScoreApp, and most casual score trackers emphasize zero-friction start. Requiring login for a table-side tool is a dealbreaker. | Low | No login, no registration. Just open and play. |
| **Shared/multi-player scoring** | Carcassonne's majority-tie rule means one event awards points to multiple players simultaneously. The Android Scoreboard app handles this. | Medium | One action, N entries. Must be atomic (all or nothing). |
| **Game state machine** | Carcassonne has distinct phases: setup, playing (completed structures), final scoring (incomplete + farms), finished. CarcassonneScorer.com distinguishes end-game scoring. | Low | Controls which event types are available in each phase. |
| **Action history / log** | Carcassonne Scoreboard (Android) has a "Log" feature. Score Anything shows chronological scoresheet. Users need to verify what happened. | Medium | Chronological list of actions, grouped by event. Shows who scored what. |

---

## Differentiators

Features that set this product apart from competitors. Not expected, but create competitive advantage when present.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Visual SVG scoreboard track** | No existing web app replicates the physical 50-cell Carcassonne track with tokens. The iOS app has a visual circle but it's native-only. Using the real board photo as background creates authentic table feel. | High | SVG with viewBox, real board photo background, 50 mapped cell positions. Core differentiator. |
| **Meeple tokens on track** | Colored meeple tokens positioned on correct cells. Physical board feel in digital form. No web competitor does this. | Medium | Derive cell from `score_total % 50`. Position SVG elements. |
| **Token movement animation** | Step-by-step animation along the track when points are scored. "Juicy" feedback that competitors lack. | Medium | Animate through intermediate cells at ~80ms per step. Depends on visual track. |
| **Token stacking (overlap handling)** | When multiple players share a cell, tokens fan out radially so all remain visible. Physical board has this problem too. | Low | Offset calculation based on count of tokens at same cell. |
| **Lap indicator on tokens** | Badge showing x1, x2, x3 for unlimited laps. Physical game uses stacking meeple blocks for this. | Low | Derive from `score_total // 50`. Display as badge on token. |
| **Rollback to any past action** | Goes beyond single undo. Users can rewind to any point in game history. No Carcassonne-specific competitor offers this (Android app only has undo/redo). | Medium | Mark all actions after target as undone. Recalculate affected scores. |
| **Event-sourced action model** | Score truth is derived from active entries, not a mutable counter. Makes undo/rollback safe and auditable. | Medium | `score_actions` + `score_entries` pattern. Recalculate on undo. |
| **Undone actions visible in history** | Struck-through but still visible in the log. Full audit trail. No competitor shows this. | Low | Visual styling only. Depends on action history. |
| **Distinct final-scoring phase** | Separate UI controls for end-game scoring (incomplete structures, farms). CarcassonneScorer.com does this but as a different paradigm (calculator, not tracker). | Low | Filter available event types by game state. |
| **Haptic feedback on score entry** | Mobile vibration on successful score registration. Modern UX expectation for touch apps, but no board game scorer does it well. | Low | `navigator.vibrate()` API. Single line of code, big UX impact. |
| **Dockerized self-hosting** | Run on local network at a game cafe or club. MeepleStats does this for game tracking, but no Carcassonne scorer does. | Low | Already planned. `docker compose up` and go. |

---

## Anti-Features

Features to deliberately NOT build. Common mistakes in this domain that add complexity without value for the target use case.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| **Game logic / rule enforcement** | The app is a scorer, not a game engine. Validating tile placement, structure completion, or follower rules adds massive complexity with no value. The user at the table knows what happened. CarcassonneScorer.com tries to be a calculator and it creates friction. | Accept user input as-is. Label the event type, record the points. Trust the player. |
| **Multiplayer networking (multi-device)** | Adds WebSocket/sync complexity for a use case that doesn't need it. One phone at the table is the design. The Android Scoreboard app is single-device and nobody complains. | Single device, single session. Keep it simple. |
| **User accounts / authentication** | Scorecard.gg's #1 selling point is "no account needed." Adding auth for a casual table-side tool is friction that kills adoption. | No login. Open the URL and start a game. |
| **BGG integration / cloud sync** | BGStats does this well and has 16 languages + years of data. Competing on stats/sync is losing. | Focus on in-game experience, not post-game analytics. Users who want stats already use BGStats. |
| **Game statistics / analytics** | Win rates, play counts, score distributions are a different product (BGStats, NemeStats). Building this dilutes focus on the core scoring experience. | Maybe export game data as JSON for users who want to analyze elsewhere. |
| **Turn tracking (v1)** | TrackScore.online tracks turns for streaming. At a physical table, players know whose turn it is. Adds UI clutter for minimal value. | Defer to post-MVP. Can be added without data model changes. |
| **Expansion-specific rule logic** | The Android Scoreboard app toggles expansions to change UI. But since we don't enforce rules, expansion "support" is just more event types. Shipping 20 event types in v1 is scope creep. | Start with base game event types. Add expansion types as simple enum additions later. |
| **Sound effects** | Tempting for "juiciness" but annoying in a noisy game-table environment. Users will mute immediately. | Haptic feedback is better: silent, personal, and doesn't disturb the table. |
| **Score hiding / suspense mode** | Scory offers hidden scores. In Carcassonne the physical board is visible to all players. Hidden scores contradict the game's nature. | Always show all scores. Matches the physical experience. |
| **Random player selector / dice** | Keep Score has this. It's feature bloat for a Carcassonne scorer. Players already have a seating order. | Out of scope. Not scoring-related. |
| **Timer** | ScorePal and BGStats have game timers. In a casual Carcassonne game at a table, nobody times anything. | Out of scope. Not scoring-related. |
| **PWA / installable app** | Tempting for offline use, but adds service worker complexity. The app is used on local network (home WiFi or hotspot) where connectivity is reliable. Over-engineering for v1. | Defer. Can be added later as enhancement without architecture changes. |

---

## Feature Dependencies

```
Player Setup (2-6 players)
  |
  v
Add Points + Event Types + Shared Scoring
  |
  v
Score Display / Leaderboard -------> Visual SVG Track
  |                                      |
  v                                      v
Action History / Log                Meeple Tokens on Track
  |                                      |
  v                                      v
Undo Last Action                   Token Movement Animation
  |                                      |
  v                                      v
Rollback to Any Action             Token Stacking + Lap Badge
  |
  v
Game State Machine (setup -> playing -> scoring -> finished)
  |
  v
Final Scoring Phase (distinct event types)

Independent:
- Haptic Feedback (can be added anytime)
- Dockerized Deployment (infrastructure, parallel track)
- Undone Actions Visible in History (styling on top of history)
```

Key dependency insight: The visual SVG track is the signature differentiator but depends on basic scoring working first. It should be Phase 3 (after core scoring and history/rollback), matching the existing plan in `docs/plan.md`.

---

## MVP Recommendation

For MVP, prioritize all table stakes plus the one differentiator that defines the product:

### Must ship (table stakes):
1. Player setup with names and colors (2-6 players)
2. Add points with event type labels (road, city, monastery, farm, manual)
3. Shared scoring for majority ties (one action, multiple players)
4. Score display / leaderboard ranked by score
5. Undo last action (complete action with all entries)
6. Action history showing grouped entries per action
7. Game state machine (setup -> playing -> scoring -> finished)
8. Mobile-friendly layout
9. No account required

### Ship in MVP (key differentiator):
10. Visual SVG scoreboard track with meeple tokens
11. Token movement animation
12. Lap indicator

### Defer to post-MVP:
- **Rollback to any action**: Nice to have but undo covers 90% of correction needs. Add in Phase 2.
- **Haptic feedback**: Low complexity, but distraction during core build. Add when polish pass happens.
- **Final scoring phase (distinct UI)**: Can work with just the state machine filtering event types. Dedicated UI can come later.
- **Export to JSON**: Post-MVP convenience feature.
- **Turn tracking**: Explicitly out of scope per PROJECT.md.
- **Expansion event types**: Add as enum values when needed.
- **PWA / offline**: Only if real users request it.

---

## Competitor Quick Reference

| App | Platform | Visual Track | Event Types | Undo | Shared Scoring | Expansions | Free |
|-----|----------|-------------|-------------|------|---------------|------------|------|
| Carcassonne Scoreboard (Android) | Android | No | Yes | Yes (undo/redo) | Unclear | 7 expansions | Yes |
| Carcassonne Score Counter (iOS) | iOS | Visual circle | Basic | Reset only | Unclear | No | Yes |
| CarcassonneScorer.com | Web | No | Yes (calculator) | No | Yes (shared features) | All main + mini | Yes |
| CarcaScorer (GitHub) | Web | No | Basic counter | No | No | No | Yes |
| TrackScore.online | Web (OBS) | No (overlay) | Yes | Unclear | Yes | No | Yes |
| ScoreApp.nl | Web (PWA) | No | Generic | Yes | No | N/A | Yes |
| Scorecard.gg | Web | No | Generic sheets | Unclear | No | N/A | Yes |
| **This project** | **Web** | **Yes (SVG + photo)** | **Yes** | **Yes (undo + rollback)** | **Yes (atomic)** | **Base game** | **Yes** |

The combination of visual SVG track + event-sourced undo/rollback + atomic shared scoring + mobile-first web is unoccupied in the market.

---

## Sources

- [Carcassonne Scoreboard (Android) - Google Play](https://play.google.com/store/apps/details/Carcassonne_Scoreboard?id=com.Carcassonne_Scoreboard.EDrummer19&hl=en_SG)
- [Carcassonne Score Counter (iOS) - App Store](https://apps.apple.com/us/app/carcassonne-score-counter/id6480453456)
- [CarcassonneScorer.com](https://carcassonnescorer.com/)
- [CarcaScorer - GitHub](https://github.com/magicznyleszek/carcascorer)
- [TrackScore.online Carcassonne Scoreboard](https://trackscore.online/carcassonne-scoreboard)
- [Scorecard.gg - BGG thread](https://boardgamegeek.com/thread/3189910/i-made-a-free-scoring-web-app-for-board-games-call)
- [ScoreApp.nl](https://www.scoreapp.nl/en)
- [BGStats App](https://www.bgstatsapp.com/)
- [MeepleStats - BGG thread](https://boardgamegeek.com/thread/3457987/meeplestats-self-hosted-board-game-tracking-app-op)
- [Board Game Scoring Apps - BGG discussion](https://boardgamegeek.com/thread/2224193/board-game-scoring-apps)
- [5 Score-Keeping Apps Reviewed - Denexa Games](https://www.denexa.com/blog/5-scorekeeping-apps-reviewed/)
- [Game Scoring App Discussion - BGG](https://boardgamegeek.com/thread/1883155/game-scoring-app-whats-best-and-most-practical)
- [Carcassonne Scoring Board (GitHub)](https://github.com/NikolaBreznjak/carcassonne-scoring-board)
- [Board Buddy - Hacker News](https://news.ycombinator.com/item?id=43925474)

**Confidence notes:** Feature categorization is based on surveying 15+ competing apps across web, iOS, and Android. Individual app feature details are LOW-MEDIUM confidence (sourced from app store descriptions and search snippets, not hands-on testing). The "gap analysis" conclusion (no web app combines visual track + event-sourced undo + mobile-first) is MEDIUM confidence — it's possible a niche tool exists that didn't surface in search, but the pattern across results is consistent.
