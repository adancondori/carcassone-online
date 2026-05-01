"""Tests for scoring service functions.

Tests cover: add_score, undo_last, rollback_to, recalculate_score,
shared scoring, cache consistency, and edge cases.
"""

import random

import pytest

from app.models import ScoreAction, ScoreEntry
from app.services import add_score, recalculate_score, rollback_to, undo_last
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
