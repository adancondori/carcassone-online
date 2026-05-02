"""Tests for scoring service functions.

Tests cover: add_score, undo_last, rollback_to, recalculate_score,
shared scoring, cache consistency, game state transitions, event-type
validation, and finished-state guards.
"""

import random

import pytest

from app.models import ScoreAction, ScoreEntry
from app.services import (
    PLAYING_EVENT_TYPES,
    SCORING_EVENT_TYPES,
    add_score,
    begin_scoring,
    finish_game,
    recalculate_score,
    rollback_to,
    undo_last,
)
from sqlmodel import select


# ---------------------------------------------------------------------------
# add_score tests
# ---------------------------------------------------------------------------


class TestAddScore:
    def test_add_score_single_player(self, session, game_with_players):
        """Adding points to one player updates score_total and creates correct entry."""
        game, (alice, bob) = game_with_players

        action = add_score(
            session,
            game.id,
            [(alice.id, 8)],
            "ROAD_COMPLETED",
            description="Short road",
        )

        session.refresh(alice)
        assert alice.score_total == 8

        entries = session.exec(
            select(ScoreEntry).where(ScoreEntry.action_id == action.id)
        ).all()
        assert len(entries) == 1
        assert entries[0].points == 8
        assert entries[0].score_before == 0
        assert entries[0].score_after == 8

    def test_add_score_shared(self, session, game_with_players):
        """Shared scoring gives points to multiple players from one action."""
        game, (alice, bob) = game_with_players

        action = add_score(
            session,
            game.id,
            [(alice.id, 10), (bob.id, 10)],
            "CITY_COMPLETED",
        )

        session.refresh(alice)
        session.refresh(bob)
        assert alice.score_total == 10
        assert bob.score_total == 10

        entries = session.exec(
            select(ScoreEntry).where(ScoreEntry.action_id == action.id)
        ).all()
        assert len(entries) == 2

    def test_add_score_cumulative(self, session, game_with_players):
        """Successive scores accumulate correctly with accurate score_before."""
        game, (alice, bob) = game_with_players

        add_score(session, game.id, [(alice.id, 8)], "ROAD_COMPLETED")
        action2 = add_score(session, game.id, [(alice.id, 12)], "CITY_COMPLETED")

        session.refresh(alice)
        assert alice.score_total == 20

        entries = session.exec(
            select(ScoreEntry).where(ScoreEntry.action_id == action2.id)
        ).all()
        assert len(entries) == 1
        assert entries[0].score_before == 8
        assert entries[0].score_after == 20

    def test_add_score_invalid_player(self, session, game_with_players):
        """Adding score for nonexistent player raises ValueError."""
        game, _ = game_with_players

        with pytest.raises(ValueError, match="not found"):
            add_score(session, game.id, [(9999, 5)], "MANUAL")


# ---------------------------------------------------------------------------
# undo_last tests
# ---------------------------------------------------------------------------


class TestUndoLast:
    def test_undo_single_action(self, session, game_with_players):
        """Undo reverts the last action, restoring score to previous state."""
        game, (alice, bob) = game_with_players

        add_score(session, game.id, [(alice.id, 8)], "ROAD_COMPLETED")
        add_score(session, game.id, [(alice.id, 12)], "CITY_COMPLETED")

        undone = undo_last(session, game.id)

        session.refresh(alice)
        assert alice.score_total == 8
        assert undone is not None
        assert undone.is_undone is True

    def test_undo_shared_action(self, session, game_with_players):
        """Undoing a shared scoring action reverts all affected players."""
        game, (alice, bob) = game_with_players

        add_score(session, game.id, [(alice.id, 8)], "ROAD_COMPLETED")
        add_score(
            session,
            game.id,
            [(alice.id, 10), (bob.id, 10)],
            "CITY_COMPLETED",
        )

        undo_last(session, game.id)

        session.refresh(alice)
        session.refresh(bob)
        assert alice.score_total == 8
        assert bob.score_total == 0

    def test_undo_empty_game(self, session, game_with_players):
        """Undo with no actions returns None."""
        game, _ = game_with_players

        result = undo_last(session, game.id)
        assert result is None

    def test_undo_already_undone_skipped(self, session, game_with_players):
        """Each undo targets a different action -- already-undone actions are skipped."""
        game, (alice, bob) = game_with_players

        add_score(session, game.id, [(alice.id, 5)], "ROAD_COMPLETED")
        add_score(session, game.id, [(alice.id, 10)], "CITY_COMPLETED")

        first_undone = undo_last(session, game.id)
        second_undone = undo_last(session, game.id)

        # Two different actions were undone
        assert first_undone.id != second_undone.id
        session.refresh(alice)
        assert alice.score_total == 0


# ---------------------------------------------------------------------------
# rollback_to tests
# ---------------------------------------------------------------------------


class TestRollbackTo:
    def test_rollback_to_action(self, session, game_with_players):
        """Rollback marks all actions after target as undone and recalculates."""
        game, (alice, bob) = game_with_players

        a1 = add_score(session, game.id, [(alice.id, 8)], "ROAD_COMPLETED")
        add_score(session, game.id, [(bob.id, 5)], "ROAD_COMPLETED")
        add_score(
            session,
            game.id,
            [(alice.id, 12), (bob.id, 12)],
            "CITY_COMPLETED",
        )

        count = rollback_to(session, game.id, a1.id)

        assert count == 2
        session.refresh(alice)
        session.refresh(bob)
        assert alice.score_total == 8
        assert bob.score_total == 0

    def test_rollback_to_nothing(self, session, game_with_players):
        """Rollback when no actions exist after target returns 0."""
        game, (alice, bob) = game_with_players

        a1 = add_score(session, game.id, [(alice.id, 8)], "ROAD_COMPLETED")

        count = rollback_to(session, game.id, a1.id)
        assert count == 0


# ---------------------------------------------------------------------------
# recalculate_score tests
# ---------------------------------------------------------------------------


class TestRecalculateScore:
    def test_recalculate_matches_normal(self, session, game_with_players):
        """After add_score, recalculate returns the same value as score_total."""
        game, (alice, bob) = game_with_players

        add_score(session, game.id, [(alice.id, 8)], "ROAD_COMPLETED")
        add_score(session, game.id, [(alice.id, 12)], "CITY_COMPLETED")

        result = recalculate_score(session, alice.id)
        session.refresh(alice)
        assert result == 20
        assert alice.score_total == result

    def test_recalculate_with_undone(self, session, game_with_players):
        """Recalculate reflects only active (non-undone) entries."""
        game, (alice, bob) = game_with_players

        add_score(session, game.id, [(alice.id, 8)], "ROAD_COMPLETED")
        a2 = add_score(session, game.id, [(alice.id, 12)], "CITY_COMPLETED")

        # Manually mark action as undone (bypass undo_last)
        a2.is_undone = True
        session.add(a2)
        session.commit()

        result = recalculate_score(session, alice.id)
        session.refresh(alice)
        assert result == 8
        assert alice.score_total == 8

    def test_recalculate_no_entries(self, session, game_with_players):
        """Recalculate returns 0 for a player with no score entries."""
        game, (alice, bob) = game_with_players

        result = recalculate_score(session, alice.id)
        session.refresh(alice)
        assert result == 0
        assert alice.score_total == 0


# ---------------------------------------------------------------------------
# Cache consistency test
# ---------------------------------------------------------------------------


class TestCacheConsistency:
    def test_cache_consistency_random(self, session, game_with_players):
        """After random add/undo operations, score_total always equals recalculate."""
        game, (alice, bob) = game_with_players
        rng = random.Random(42)  # deterministic seed

        for _ in range(20):
            op = rng.choice(["add", "undo"])

            if op == "add":
                # Pick random player(s) and points
                targets = []
                if rng.random() < 0.3:
                    # shared scoring
                    pts = rng.randint(1, 20)
                    targets = [(alice.id, pts), (bob.id, pts)]
                else:
                    player = rng.choice([alice, bob])
                    targets = [(player.id, rng.randint(1, 20))]
                add_score(session, game.id, targets, "MANUAL")
            else:
                undo_last(session, game.id)

            # After every operation, cache must match recalculate
            for player in [alice, bob]:
                session.refresh(player)
                recalc = recalculate_score(session, player.id)
                session.refresh(player)
                assert player.score_total == recalc, (
                    f"Cache mismatch for {player.name}: "
                    f"score_total={player.score_total}, recalculate={recalc}"
                )


# ---------------------------------------------------------------------------
# Game state transition tests
# ---------------------------------------------------------------------------


class TestGameStates:
    """Tests for begin_scoring() and finish_game() state transitions."""

    def test_begin_scoring_from_playing(self, session, game_with_players):
        """begin_scoring transitions a playing game to scoring state."""
        game, _ = game_with_players
        assert game.status == "playing"

        result = begin_scoring(session, game.id)

        assert result.status == "scoring"
        session.refresh(game)
        assert game.status == "scoring"

    def test_begin_scoring_returns_game(self, session, game_with_players):
        """begin_scoring returns the updated Game object."""
        game, _ = game_with_players

        result = begin_scoring(session, game.id)

        assert result.id == game.id

    def test_begin_scoring_rejects_non_playing(self, session, game_with_players):
        """begin_scoring raises ValueError for a non-playing game."""
        game, _ = game_with_players
        # Transition to scoring first
        begin_scoring(session, game.id)

        with pytest.raises(ValueError):
            begin_scoring(session, game.id)

    def test_begin_scoring_rejects_setup(self, session, engine):
        """begin_scoring raises ValueError for a setup game."""
        from app.models import Game

        game = Game(name="Setup Game", status="setup")
        session.add(game)
        session.commit()
        session.refresh(game)

        with pytest.raises(ValueError):
            begin_scoring(session, game.id)

    def test_begin_scoring_game_not_found(self, session):
        """begin_scoring raises ValueError for nonexistent game."""
        with pytest.raises(ValueError, match="not found"):
            begin_scoring(session, 999)

    def test_finish_game_from_scoring(self, session, game_with_players):
        """finish_game transitions a scoring game to finished state."""
        game, _ = game_with_players
        begin_scoring(session, game.id)

        result = finish_game(session, game.id)

        assert result.status == "finished"
        session.refresh(game)
        assert game.status == "finished"

    def test_finish_game_returns_game(self, session, game_with_players):
        """finish_game returns the updated Game object."""
        game, _ = game_with_players
        begin_scoring(session, game.id)

        result = finish_game(session, game.id)

        assert result.id == game.id

    def test_finish_game_from_playing(self, session, game_with_players):
        """finish_game works directly from playing state (skip scoring)."""
        game, _ = game_with_players

        result = finish_game(session, game.id)
        assert result.status == "finished"

    def test_finish_game_rejects_setup(self, session):
        """finish_game raises ValueError for a setup game."""
        from app.services import create_game
        game = create_game(session, "Test")

        with pytest.raises(ValueError):
            finish_game(session, game.id)

    def test_finish_game_rejects_finished(self, session, game_with_players):
        """finish_game raises ValueError for an already finished game."""
        game, _ = game_with_players
        begin_scoring(session, game.id)
        finish_game(session, game.id)

        with pytest.raises(ValueError):
            finish_game(session, game.id)

    def test_finish_game_game_not_found(self, session):
        """finish_game raises ValueError for nonexistent game."""
        with pytest.raises(ValueError, match="not found"):
            finish_game(session, 999)


# ---------------------------------------------------------------------------
# Event type validation tests
# ---------------------------------------------------------------------------


class TestEventTypeValidation:
    """Tests for event_type enforcement in add_score() per game state."""

    # -- Playing state: valid event types --

    def test_playing_accepts_city_completed(self, session, game_with_players):
        """CITY_COMPLETED is accepted during playing state."""
        game, (alice, _) = game_with_players
        action = add_score(session, game.id, [(alice.id, 10)], "CITY_COMPLETED")
        assert action is not None

    def test_playing_accepts_road_completed(self, session, game_with_players):
        """ROAD_COMPLETED is accepted during playing state."""
        game, (alice, _) = game_with_players
        action = add_score(session, game.id, [(alice.id, 5)], "ROAD_COMPLETED")
        assert action is not None

    def test_playing_accepts_monastery_completed(self, session, game_with_players):
        """MONASTERY_COMPLETED is accepted during playing state."""
        game, (alice, _) = game_with_players
        action = add_score(session, game.id, [(alice.id, 9)], "MONASTERY_COMPLETED")
        assert action is not None

    def test_playing_accepts_manual(self, session, game_with_players):
        """MANUAL is accepted during playing state."""
        game, (alice, _) = game_with_players
        action = add_score(session, game.id, [(alice.id, 3)], "MANUAL")
        assert action is not None

    # -- Playing state: rejected event types --

    def test_playing_rejects_city_final(self, session, game_with_players):
        """CITY_FINAL is rejected during playing state."""
        game, (alice, _) = game_with_players
        with pytest.raises(ValueError):
            add_score(session, game.id, [(alice.id, 5)], "CITY_FINAL")

    def test_playing_rejects_road_final(self, session, game_with_players):
        """ROAD_FINAL is rejected during playing state."""
        game, (alice, _) = game_with_players
        with pytest.raises(ValueError):
            add_score(session, game.id, [(alice.id, 5)], "ROAD_FINAL")

    def test_playing_rejects_monastery_final(self, session, game_with_players):
        """MONASTERY_FINAL is rejected during playing state."""
        game, (alice, _) = game_with_players
        with pytest.raises(ValueError):
            add_score(session, game.id, [(alice.id, 5)], "MONASTERY_FINAL")

    def test_playing_rejects_farm_final(self, session, game_with_players):
        """FARM_FINAL is rejected during playing state."""
        game, (alice, _) = game_with_players
        with pytest.raises(ValueError):
            add_score(session, game.id, [(alice.id, 5)], "FARM_FINAL")

    # -- Scoring state: valid event types --

    def test_scoring_accepts_city_final(self, session, game_with_players):
        """CITY_FINAL is accepted during scoring state."""
        game, (alice, _) = game_with_players
        begin_scoring(session, game.id)
        action = add_score(session, game.id, [(alice.id, 10)], "CITY_FINAL")
        assert action is not None

    def test_scoring_accepts_road_final(self, session, game_with_players):
        """ROAD_FINAL is accepted during scoring state."""
        game, (alice, _) = game_with_players
        begin_scoring(session, game.id)
        action = add_score(session, game.id, [(alice.id, 3)], "ROAD_FINAL")
        assert action is not None

    def test_scoring_accepts_monastery_final(self, session, game_with_players):
        """MONASTERY_FINAL is accepted during scoring state."""
        game, (alice, _) = game_with_players
        begin_scoring(session, game.id)
        action = add_score(session, game.id, [(alice.id, 5)], "MONASTERY_FINAL")
        assert action is not None

    def test_scoring_accepts_farm_final(self, session, game_with_players):
        """FARM_FINAL is accepted during scoring state."""
        game, (alice, _) = game_with_players
        begin_scoring(session, game.id)
        action = add_score(session, game.id, [(alice.id, 7)], "FARM_FINAL")
        assert action is not None

    def test_scoring_accepts_manual(self, session, game_with_players):
        """MANUAL is accepted during scoring state."""
        game, (alice, _) = game_with_players
        begin_scoring(session, game.id)
        action = add_score(session, game.id, [(alice.id, 2)], "MANUAL")
        assert action is not None

    # -- Scoring state: rejected event types --

    def test_scoring_rejects_city_completed(self, session, game_with_players):
        """CITY_COMPLETED is rejected during scoring state."""
        game, (alice, _) = game_with_players
        begin_scoring(session, game.id)
        with pytest.raises(ValueError):
            add_score(session, game.id, [(alice.id, 10)], "CITY_COMPLETED")

    def test_scoring_rejects_road_completed(self, session, game_with_players):
        """ROAD_COMPLETED is rejected during scoring state."""
        game, (alice, _) = game_with_players
        begin_scoring(session, game.id)
        with pytest.raises(ValueError):
            add_score(session, game.id, [(alice.id, 5)], "ROAD_COMPLETED")

    def test_scoring_rejects_monastery_completed(self, session, game_with_players):
        """MONASTERY_COMPLETED is rejected during scoring state."""
        game, (alice, _) = game_with_players
        begin_scoring(session, game.id)
        with pytest.raises(ValueError):
            add_score(session, game.id, [(alice.id, 9)], "MONASTERY_COMPLETED")

    # -- Invalid states --

    def test_setup_rejects_scoring(self, session, engine):
        """add_score raises ValueError in setup state."""
        from app.models import Game, Player

        game = Game(name="Setup Game", status="setup")
        session.add(game)
        session.flush()
        player = Player(game_id=game.id, name="Test", color="blue", turn_order=1)
        session.add(player)
        session.commit()
        session.refresh(game)
        session.refresh(player)

        with pytest.raises(ValueError):
            add_score(session, game.id, [(player.id, 5)], "MANUAL")

    def test_finished_rejects_scoring(self, session, game_with_players):
        """add_score raises ValueError in finished state."""
        game, (alice, _) = game_with_players
        begin_scoring(session, game.id)
        finish_game(session, game.id)

        with pytest.raises(ValueError):
            add_score(session, game.id, [(alice.id, 5)], "MANUAL")


# ---------------------------------------------------------------------------
# Finished state guard tests
# ---------------------------------------------------------------------------


class TestFinishedStateGuards:
    """Tests for undo_last/rollback_to rejection in finished state and acceptance in scoring."""

    def test_undo_last_rejects_finished(self, session, game_with_players):
        """undo_last raises ValueError for a finished game."""
        game, (alice, _) = game_with_players
        add_score(session, game.id, [(alice.id, 8)], "ROAD_COMPLETED")
        begin_scoring(session, game.id)
        finish_game(session, game.id)

        with pytest.raises(ValueError):
            undo_last(session, game.id)

    def test_rollback_to_rejects_finished(self, session, game_with_players):
        """rollback_to raises ValueError for a finished game."""
        game, (alice, _) = game_with_players
        a1 = add_score(session, game.id, [(alice.id, 8)], "ROAD_COMPLETED")
        begin_scoring(session, game.id)
        finish_game(session, game.id)

        with pytest.raises(ValueError):
            rollback_to(session, game.id, a1.id)

    def test_undo_last_works_in_scoring(self, session, game_with_players):
        """undo_last succeeds during scoring state."""
        game, (alice, _) = game_with_players
        add_score(session, game.id, [(alice.id, 8)], "ROAD_COMPLETED")
        begin_scoring(session, game.id)

        undone = undo_last(session, game.id)

        assert undone is not None
        assert undone.is_undone is True
        session.refresh(alice)
        assert alice.score_total == 0

    def test_rollback_to_works_in_scoring(self, session, game_with_players):
        """rollback_to succeeds during scoring state."""
        game, (alice, _) = game_with_players
        a1 = add_score(session, game.id, [(alice.id, 8)], "ROAD_COMPLETED")
        add_score(session, game.id, [(alice.id, 12)], "CITY_COMPLETED")
        begin_scoring(session, game.id)

        count = rollback_to(session, game.id, a1.id)

        assert count == 1
        session.refresh(alice)
        assert alice.score_total == 8
