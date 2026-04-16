"""
Tests for the word-of-the-day selection module.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest


class TestPickWord:
    """Test word selection logic."""

    def test_picks_highest_frequency_word(self, mock_mongo_client):
        from slovo.db import words_col
        from slovo.wod import pick_word

        col = words_col()
        col.insert_many([
            {"lemma": "рідкий", "known": False, "frequency": 1, "shown_at": None},
            {"lemma": "частий", "known": False, "frequency": 10, "shown_at": None},
            {"lemma": "середній", "known": False, "frequency": 5, "shown_at": None},
        ])

        word = pick_word()
        assert word is not None
        assert word["lemma"] == "частий"

    def test_excludes_known_words(self, mock_mongo_client):
        from slovo.db import words_col
        from slovo.wod import pick_word

        col = words_col()
        col.insert_many([
            {"lemma": "знаю", "known": True, "frequency": 100, "shown_at": None},
            {"lemma": "нове", "known": False, "frequency": 1, "shown_at": None},
        ])

        word = pick_word()
        assert word is not None
        assert word["lemma"] == "нове"

    def test_respects_cooldown(self, mock_mongo_client):
        from slovo.db import words_col
        from slovo.wod import COOLDOWN_DAYS, pick_word

        col = words_col()
        now = datetime.now(timezone.utc)

        col.insert_many([
            {
                "lemma": "недавно",
                "known": False,
                "frequency": 100,
                "shown_at": now - timedelta(days=5),  # Within cooldown
            },
            {
                "lemma": "давно",
                "known": False,
                "frequency": 1,
                "shown_at": now - timedelta(days=COOLDOWN_DAYS + 1),  # Past cooldown
            },
        ])

        word = pick_word()
        assert word is not None
        assert word["lemma"] == "давно"

    def test_filters_by_pos(self, mock_mongo_client):
        from slovo.db import words_col
        from slovo.wod import pick_word

        col = words_col()
        col.insert_many([
            {"lemma": "іменник", "pos": "NOUN", "known": False, "frequency": 5, "shown_at": None},
            {"lemma": "дієслово", "pos": "VERB", "known": False, "frequency": 10, "shown_at": None},
        ])

        word = pick_word(pos_filter="NOUN")
        assert word is not None
        assert word["pos"] == "NOUN"

    def test_filters_by_min_frequency(self, mock_mongo_client):
        from slovo.db import words_col
        from slovo.wod import pick_word

        col = words_col()
        col.insert_many([
            {"lemma": "рідкий", "known": False, "frequency": 1, "shown_at": None},
            {"lemma": "частий", "known": False, "frequency": 5, "shown_at": None},
        ])

        word = pick_word(min_frequency=3)
        assert word is not None
        assert word["lemma"] == "частий"

    def test_filters_by_artist(self, mock_mongo_client):
        from slovo.db import words_col
        from slovo.wod import pick_word

        col = words_col()
        col.insert_many([
            {
                "lemma": "бумбокс",
                "songs": ["BoomBox - Song1"],
                "known": False,
                "frequency": 5,
                "shown_at": None,
            },
            {
                "lemma": "інший",
                "songs": ["Re-Read - Song2"],
                "known": False,
                "frequency": 10,
                "shown_at": None,
            },
        ])

        word = pick_word(artist_filter="BoomBox")
        assert word is not None
        assert word["lemma"] == "бумбокс"

    def test_returns_none_when_no_eligible_words(self, mock_mongo_client):
        from slovo.db import words_col
        from slovo.wod import pick_word

        col = words_col()
        col.insert_many([
            {"lemma": "знаю", "known": True, "frequency": 10, "shown_at": None},
        ])

        word = pick_word()
        assert word is None


class TestPickExampleLine:
    """Test example line selection."""

    def test_returns_line_with_translation(self, mock_mongo_client, sample_word_doc):
        from slovo.wod import pick_example_line

        line = pick_example_line(sample_word_doc)
        assert line is not None
        assert "cyrillic" in line
        assert "translation" in line

    def test_returns_none_for_no_lines(self, mock_mongo_client):
        from slovo.wod import pick_example_line

        word_doc = {"lemma": "тест", "example_lines": []}
        line = pick_example_line(word_doc)
        assert line is None

    def test_prefers_translated_lines(self, mock_mongo_client):
        from slovo.wod import pick_example_line

        word_doc = {
            "lemma": "тест",
            "example_lines": [
                {"cyrillic": "No translation", "translation": ""},
                {"cyrillic": "Has translation", "translation": "Has translation"},
            ],
        }

        # Run multiple times to check preference
        for _ in range(5):
            line = pick_example_line(word_doc)
            # Should always pick the one with translation when available
            assert line["translation"] == "Has translation"


class TestRecordShown:
    """Test recording word-of-the-day history."""

    def test_updates_shown_at(self, mock_mongo_client, sample_word_doc):
        from slovo.db import words_col
        from slovo.wod import record_shown

        col = words_col()
        result = col.insert_one(sample_word_doc)
        sample_word_doc["_id"] = result.inserted_id

        record_shown(sample_word_doc, "city", None)

        updated = col.find_one({"_id": result.inserted_id})
        assert updated["shown_at"] is not None

    def test_adds_history_entry(self, mock_mongo_client, sample_word_doc):
        from slovo.db import history_col, words_col
        from slovo.wod import record_shown

        wcol = words_col()
        result = wcol.insert_one(sample_word_doc)
        sample_word_doc["_id"] = result.inserted_id

        example_line = sample_word_doc["example_lines"][0]
        record_shown(sample_word_doc, "city", example_line)

        hcol = history_col()
        entry = hcol.find_one({"lemma": "місто"})
        assert entry is not None
        assert entry["translation"] == "city"
        assert entry["example_line"] == example_line


class TestMarkKnown:
    """Test marking words as known."""

    def test_marks_existing_word(self, mock_mongo_client, sample_word_doc):
        from slovo.db import words_col
        from slovo.wod import mark_known

        col = words_col()
        col.insert_one(sample_word_doc)

        result = mark_known("місто")
        assert result is True

        word = col.find_one({"lemma": "місто"})
        assert word["known"] is True

    def test_returns_false_for_missing_word(self, mock_mongo_client):
        from slovo.wod import mark_known

        result = mark_known("неіснуюче")
        assert result is False


class TestSetTranslation:
    """Test setting custom translations."""

    def test_sets_translation(self, mock_mongo_client, sample_word_doc):
        from slovo.db import words_col
        from slovo.wod import set_translation

        col = words_col()
        col.insert_one(sample_word_doc)

        result = set_translation("місто", "urban area")
        assert result is True

        word = col.find_one({"lemma": "місто"})
        assert word["translation"] == "urban area"

    def test_returns_false_for_missing_word(self, mock_mongo_client):
        from slovo.wod import set_translation

        result = set_translation("неіснуюче", "nothing")
        assert result is False


class TestSetNote:
    """Test adding notes to words."""

    def test_sets_note(self, mock_mongo_client, sample_word_doc):
        from slovo.db import words_col
        from slovo.wod import set_note

        col = words_col()
        col.insert_one(sample_word_doc)

        result = set_note("місто", "Neuter noun, locative: місті")
        assert result is True

        word = col.find_one({"lemma": "місто"})
        assert word["notes"] == "Neuter noun, locative: місті"


class TestGetStats:
    """Test corpus statistics."""

    def test_returns_counts(self, mock_mongo_client):
        from slovo.db import words_col
        from slovo.wod import get_stats

        col = words_col()
        now = datetime.now(timezone.utc)
        col.insert_many([
            {"lemma": "знаю", "known": True, "shown_at": now, "pos": "VERB", "frequency": 5},
            {"lemma": "бачив", "known": False, "shown_at": now, "pos": "VERB", "frequency": 3},
            {"lemma": "нове", "known": False, "shown_at": None, "pos": "ADJ", "frequency": 1},
        ])

        stats = get_stats()
        assert stats["total"] == 3
        assert stats["known"] == 1
        assert stats["seen_not_known"] == 1
        assert stats["untouched"] == 1


class TestGetHistory:
    """Test retrieving word-of-the-day history."""

    def test_returns_recent_entries(self, mock_mongo_client):
        from datetime import datetime, timedelta, timezone

        from slovo.db import history_col
        from slovo.wod import get_history

        col = history_col()
        now = datetime.now(timezone.utc)

        col.insert_many([
            {"lemma": "перший", "shown_at": now - timedelta(days=2)},
            {"lemma": "другий", "shown_at": now - timedelta(days=1)},
            {"lemma": "третій", "shown_at": now},
        ])

        history = get_history(limit=2)
        assert len(history) == 2
        assert history[0]["lemma"] == "третій"


class TestGetOrTranslate:
    """Test translation fetching with caching."""

    def test_returns_existing_translation(self, mock_mongo_client, sample_word_doc):
        from slovo.wod import get_or_translate

        result = get_or_translate(sample_word_doc)
        assert result == "city, town"

    def test_fetches_translation_when_missing(self, mock_mongo_client):
        from slovo.db import words_col
        from slovo.wod import get_or_translate

        col = words_col()
        word_doc = {
            "lemma": "кава",
            "translation": None,
            "pos": "NOUN",
            "frequency": 1,
            "known": False,
        }
        result = col.insert_one(word_doc)
        word_doc["_id"] = result.inserted_id

        with patch("slovo.wod._fetch_translation", return_value="coffee"):
            translation = get_or_translate(word_doc)
            assert translation == "coffee"

            # Check it was persisted
            updated = col.find_one({"_id": result.inserted_id})
            assert updated["translation"] == "coffee"
