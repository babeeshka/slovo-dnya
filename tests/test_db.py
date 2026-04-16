"""
Tests for the database module.

Uses mongomock to test without a real MongoDB connection.
"""
import pytest


class TestDatabaseConnection:
    """Test database connection and collection accessors."""

    def test_words_collection_accessible(self, mock_mongo_client):
        from slovo.db import words_col

        col = words_col()
        assert col is not None
        assert col.name == "words"

    def test_songs_collection_accessible(self, mock_mongo_client):
        from slovo.db import songs_col

        col = songs_col()
        assert col is not None
        assert col.name == "songs"

    def test_history_collection_accessible(self, mock_mongo_client):
        from slovo.db import history_col

        col = history_col()
        assert col is not None
        assert col.name == "history"


class TestWordsCollection:
    """Test words collection operations."""

    def test_insert_word(self, mock_mongo_client, sample_word_doc):
        from slovo.db import words_col

        col = words_col()
        result = col.insert_one(sample_word_doc)
        assert result.inserted_id is not None

    def test_find_word_by_lemma(self, mock_mongo_client, sample_word_doc):
        from slovo.db import words_col

        col = words_col()
        col.insert_one(sample_word_doc)

        found = col.find_one({"lemma": "місто"})
        assert found is not None
        assert found["lemma"] == "місто"
        assert found["pos"] == "NOUN"

    def test_update_word_frequency(self, mock_mongo_client, sample_word_doc):
        from slovo.db import words_col

        col = words_col()
        col.insert_one(sample_word_doc)

        col.update_one({"lemma": "місто"}, {"$inc": {"frequency": 2}})

        found = col.find_one({"lemma": "місто"})
        assert found["frequency"] == 6  # 4 + 2

    def test_mark_word_known(self, mock_mongo_client, sample_word_doc):
        from slovo.db import words_col

        col = words_col()
        col.insert_one(sample_word_doc)

        col.update_one({"lemma": "місто"}, {"$set": {"known": True}})

        found = col.find_one({"lemma": "місто"})
        assert found["known"] is True

    def test_add_example_line(self, mock_mongo_client, sample_word_doc):
        from slovo.db import words_col

        col = words_col()
        col.insert_one(sample_word_doc)

        new_line = {
            "cyrillic": "Нова лінія",
            "translit": "Nova liniia",
            "translation": "New line",
            "song": "Test - Song",
        }
        col.update_one(
            {"lemma": "місто"}, {"$push": {"example_lines": new_line}}
        )

        found = col.find_one({"lemma": "місто"})
        assert len(found["example_lines"]) == 2


class TestSongsCollection:
    """Test songs collection operations."""

    def test_insert_song(self, mock_mongo_client):
        from slovo.db import songs_col

        col = songs_col()
        song = {
            "artist": "BoomBox",
            "title": "Врятуй",
            "filepath": "/path/to/file.txt",
            "word_count": 50,
            "line_count": 20,
        }
        result = col.insert_one(song)
        assert result.inserted_id is not None

    def test_find_song_by_filepath(self, mock_mongo_client):
        from slovo.db import songs_col

        col = songs_col()
        song = {
            "artist": "BoomBox",
            "title": "Врятуй",
            "filepath": "/path/to/file.txt",
            "word_count": 50,
            "line_count": 20,
        }
        col.insert_one(song)

        found = col.find_one({"filepath": "/path/to/file.txt"})
        assert found is not None
        assert found["artist"] == "BoomBox"


class TestHistoryCollection:
    """Test history collection operations."""

    def test_insert_history_entry(self, mock_mongo_client):
        from datetime import datetime, timezone

        from slovo.db import history_col

        col = history_col()
        entry = {
            "lemma": "кава",
            "pos": "NOUN",
            "translation": "coffee",
            "example_line": {
                "cyrillic": "Я п'ю каву",
                "translit": "Ya piu kavu",
                "translation": "I drink coffee",
                "song": "Test - Song",
            },
            "shown_at": datetime.now(timezone.utc),
        }
        result = col.insert_one(entry)
        assert result.inserted_id is not None

    def test_history_sorted_by_date(self, mock_mongo_client):
        from datetime import datetime, timedelta, timezone

        from slovo.db import history_col

        col = history_col()
        now = datetime.now(timezone.utc)

        entries = [
            {"lemma": "перший", "shown_at": now - timedelta(days=2)},
            {"lemma": "другий", "shown_at": now - timedelta(days=1)},
            {"lemma": "третій", "shown_at": now},
        ]
        col.insert_many(entries)

        # Get most recent first
        results = list(col.find({}).sort("shown_at", -1))
        assert results[0]["lemma"] == "третій"
        assert results[2]["lemma"] == "перший"


class TestQueryPatterns:
    """Test common query patterns used by the application."""

    def test_find_unknown_words(self, mock_mongo_client):
        from slovo.db import words_col

        col = words_col()
        col.insert_many([
            {"lemma": "слово", "known": False, "frequency": 5},
            {"lemma": "знати", "known": True, "frequency": 3},
            {"lemma": "нове", "known": False, "frequency": 1},
        ])

        unknown = list(col.find({"known": False}))
        assert len(unknown) == 2

    def test_find_words_by_frequency(self, mock_mongo_client):
        from slovo.db import words_col

        col = words_col()
        col.insert_many([
            {"lemma": "рідкий", "frequency": 1},
            {"lemma": "частий", "frequency": 10},
            {"lemma": "середній", "frequency": 5},
        ])

        # Words with frequency >= 5
        frequent = list(col.find({"frequency": {"$gte": 5}}))
        assert len(frequent) == 2

    def test_find_words_by_artist_regex(self, mock_mongo_client):
        from slovo.db import words_col

        col = words_col()
        col.insert_many([
            {"lemma": "один", "songs": ["BoomBox - Song1"]},
            {"lemma": "два", "songs": ["Re-Read - Song2"]},
            {"lemma": "три", "songs": ["BoomBox - Song3", "Other - Song4"]},
        ])

        # Words from BoomBox songs
        boombox = list(
            col.find({"songs": {"$regex": "BoomBox", "$options": "i"}})
        )
        assert len(boombox) == 2

    def test_aggregate_pos_counts(self, mock_mongo_client):
        from slovo.db import words_col

        col = words_col()
        col.insert_many([
            {"lemma": "іменник1", "pos": "NOUN"},
            {"lemma": "іменник2", "pos": "NOUN"},
            {"lemma": "дієслово", "pos": "VERB"},
        ])

        pipeline = [
            {"$group": {"_id": "$pos", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]
        results = list(col.aggregate(pipeline))
        assert len(results) == 2
        assert results[0]["_id"] == "NOUN"
        assert results[0]["count"] == 2
