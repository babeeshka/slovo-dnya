"""
Tests for slovo/study.py — Spaced repetition system.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest


class TestCalculateNextReview:
    """Tests for SM-2 algorithm calculations."""

    def test_quality_must_be_in_range(self):
        """Quality must be between 0 and 5."""
        from slovo.study import calculate_next_review

        with pytest.raises(ValueError, match="must be between 0 and 5"):
            calculate_next_review(quality=-1, current_ease_factor=2.5, current_interval=0, review_count=0)

        with pytest.raises(ValueError, match="must be between 0 and 5"):
            calculate_next_review(quality=6, current_ease_factor=2.5, current_interval=0, review_count=0)

    def test_failed_recall_resets_interval(self):
        """Quality < 3 should reset interval to 0."""
        from slovo.study import calculate_next_review

        ease, interval, _ = calculate_next_review(
            quality=2, current_ease_factor=2.5, current_interval=10, review_count=5
        )
        assert interval == 0

    def test_first_success_interval_is_one_day(self):
        """First successful review (quality >= 3) should set interval to 1 day."""
        from slovo.study import calculate_next_review

        ease, interval, _ = calculate_next_review(
            quality=4, current_ease_factor=2.5, current_interval=0, review_count=0
        )
        assert interval == 1

    def test_second_success_interval_is_six_days(self):
        """Second successful review should set interval to 6 days."""
        from slovo.study import calculate_next_review

        ease, interval, _ = calculate_next_review(
            quality=4, current_ease_factor=2.5, current_interval=1, review_count=1
        )
        assert interval == 6

    def test_subsequent_reviews_multiply_interval(self):
        """After second review, interval = previous * ease_factor."""
        from slovo.study import calculate_next_review

        ease, interval, _ = calculate_next_review(
            quality=4, current_ease_factor=2.5, current_interval=6, review_count=2
        )
        assert interval == int(6 * 2.5)  # 15 days

    def test_ease_factor_increases_on_perfect_recall(self):
        """Quality 5 should increase ease factor."""
        from slovo.study import calculate_next_review

        ease, _, _ = calculate_next_review(
            quality=5, current_ease_factor=2.5, current_interval=6, review_count=2
        )
        assert ease > 2.5

    def test_ease_factor_decreases_on_hard_recall(self):
        """Quality 3 should decrease ease factor."""
        from slovo.study import calculate_next_review

        ease, _, _ = calculate_next_review(
            quality=3, current_ease_factor=2.5, current_interval=6, review_count=2
        )
        assert ease < 2.5

    def test_ease_factor_minimum(self):
        """Ease factor should not go below 1.3."""
        from slovo.study import calculate_next_review

        ease, _, _ = calculate_next_review(
            quality=0, current_ease_factor=1.3, current_interval=0, review_count=0
        )
        assert ease >= 1.3

    def test_next_review_date_is_in_future(self):
        """Next review date should be in the future."""
        from slovo.study import calculate_next_review

        _, interval, next_review = calculate_next_review(
            quality=4, current_ease_factor=2.5, current_interval=1, review_count=1
        )
        now = datetime.now(timezone.utc)
        assert next_review > now


class TestRecordReview:
    """Tests for recording reviews in database."""

    def test_record_review_updates_database(self, mock_mongo_client):
        """Recording a review should update the word document."""
        from slovo.db import words_col
        from slovo.study import record_review

        words_col().insert_one({
            "lemma": "тест",
            "pos": "NOUN",
            "frequency": 1,
            "known": False,
        })

        result = record_review("тест", quality=4)

        assert result["lemma"] == "тест"
        assert result["quality"] == 4
        assert result["review_count"] == 1
        assert result["interval"] == 1  # First review

        # Verify database was updated
        word = words_col().find_one({"lemma": "тест"})
        assert word["review_count"] == 1
        assert word["ease_factor"] is not None
        assert word["next_review"] is not None

    def test_record_review_increments_count(self, mock_mongo_client):
        """Each review should increment review_count."""
        from slovo.db import words_col
        from slovo.study import record_review

        words_col().insert_one({
            "lemma": "тест",
            "review_count": 2,
            "ease_factor": 2.5,
            "interval": 6,
        })

        result = record_review("тест", quality=5)
        assert result["review_count"] == 3

    def test_record_review_not_found(self, mock_mongo_client):
        """Should raise error for non-existent word."""
        from slovo.study import record_review

        with pytest.raises(RuntimeError, match="not found"):
            record_review("неіснуючий", quality=4)

    def test_record_review_invalid_quality(self, mock_mongo_client):
        """Should raise error for invalid quality."""
        from slovo.study import record_review

        with pytest.raises(ValueError, match="must be between 0 and 5"):
            record_review("тест", quality=10)


class TestGetDueWords:
    """Tests for getting words due for review."""

    def test_get_due_words_never_reviewed(self, mock_mongo_client):
        """Words never reviewed should be due."""
        from slovo.db import words_col
        from slovo.study import get_due_words

        words_col().insert_many([
            {"lemma": "один", "known": False},
            {"lemma": "два", "known": False, "next_review": None},
        ])

        due = get_due_words(limit=10)
        assert len(due) == 2

    def test_get_due_words_past_review_date(self, mock_mongo_client):
        """Words with past review date should be due."""
        from slovo.db import words_col
        from slovo.study import get_due_words

        past = datetime.now(timezone.utc) - timedelta(days=1)
        words_col().insert_one({
            "lemma": "тест",
            "known": False,
            "next_review": past,
        })

        due = get_due_words(limit=10)
        assert len(due) == 1

    def test_get_due_words_excludes_future(self, mock_mongo_client):
        """Words with future review date should not be due."""
        from slovo.db import words_col
        from slovo.study import get_due_words

        future = datetime.now(timezone.utc) + timedelta(days=7)
        words_col().insert_one({
            "lemma": "тест",
            "known": False,
            "next_review": future,
        })

        due = get_due_words(limit=10)
        assert len(due) == 0

    def test_get_due_words_excludes_known(self, mock_mongo_client):
        """Words marked as known should not be due."""
        from slovo.db import words_col
        from slovo.study import get_due_words

        words_col().insert_one({
            "lemma": "тест",
            "known": True,
        })

        due = get_due_words(limit=10)
        assert len(due) == 0

    def test_get_due_words_respects_limit(self, mock_mongo_client):
        """Should respect the limit parameter."""
        from slovo.db import words_col
        from slovo.study import get_due_words

        for i in range(20):
            words_col().insert_one({"lemma": f"слово{i}", "known": False})

        due = get_due_words(limit=5)
        assert len(due) == 5


class TestGetStudyStats:
    """Tests for study statistics."""

    def test_get_study_stats_counts(self, mock_mongo_client):
        """Should return correct word counts."""
        from slovo.db import words_col
        from slovo.study import get_study_stats

        now = datetime.now(timezone.utc)
        words_col().insert_many([
            {"lemma": "один", "known": False},  # Due (never reviewed)
            {"lemma": "два", "known": False, "review_count": 1, "next_review": now - timedelta(days=1)},  # Due + learning
            {"lemma": "три", "known": True},  # Known
            {"lemma": "чотири", "known": False, "next_review": now + timedelta(days=7)},  # Not due
        ])

        stats = get_study_stats()

        assert stats["total_words"] == 4
        assert stats["words_due"] == 2  # один and два


class TestGetWordStudyData:
    """Tests for getting word study data."""

    def test_get_word_study_data_exists(self, mock_mongo_client):
        """Should return study data for existing word."""
        from slovo.db import words_col
        from slovo.study import get_word_study_data

        words_col().insert_one({
            "lemma": "тест",
            "translation": "test",
            "pos": "NOUN",
            "ease_factor": 2.6,
            "interval": 10,
            "review_count": 5,
        })

        data = get_word_study_data("тест")

        assert data["lemma"] == "тест"
        assert data["ease_factor"] == 2.6
        assert data["interval"] == 10
        assert data["review_count"] == 5

    def test_get_word_study_data_defaults(self, mock_mongo_client):
        """Should return defaults for word without study data."""
        from slovo.db import words_col
        from slovo.study import get_word_study_data

        words_col().insert_one({
            "lemma": "новий",
            "translation": "new",
        })

        data = get_word_study_data("новий")

        assert data["lemma"] == "новий"
        assert data["ease_factor"] == 2.5  # Default
        assert data["interval"] == 0
        assert data["review_count"] == 0

    def test_get_word_study_data_not_found(self, mock_mongo_client):
        """Should return None for non-existent word."""
        from slovo.study import get_word_study_data

        data = get_word_study_data("неіснуючий")
        assert data is None
