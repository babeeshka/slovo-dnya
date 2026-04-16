"""
Tests for the FastAPI REST endpoints.

Uses TestClient from Starlette and mongomock for database mocking.
"""
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(mock_mongo_client):
    """Create a test client with mocked database."""
    from slovo.api import app

    return TestClient(app)


@pytest.fixture
def populated_db(mock_mongo_client):
    """Populate the test database with sample data."""
    from slovo.db import history_col, songs_col, words_col

    words_col().insert_many([
        {
            "lemma": "місто",
            "pos": "NOUN",
            "frequency": 10,
            "songs": ["Artist A - Song 1"],
            "known": False,
            "translation": "city",
            "shown_at": None,
            "notes": "",
            "example_lines": [
                {
                    "cyrillic": "Місто спить",
                    "translit": "Misto spyt",
                    "translation": "The city sleeps",
                    "song": "Artist A - Song 1",
                }
            ],
        },
        {
            "lemma": "вода",
            "pos": "NOUN",
            "frequency": 5,
            "songs": ["Artist B - Song 2"],
            "known": True,
            "translation": "water",
            "shown_at": datetime(2024, 1, 1, tzinfo=timezone.utc),
            "notes": "Feminine noun",
            "example_lines": [],
        },
        {
            "lemma": "йти",
            "pos": "VERB",
            "frequency": 8,
            "songs": ["Artist A - Song 1", "Artist C - Song 3"],
            "known": False,
            "translation": "to go",
            "shown_at": None,
            "notes": "",
            "example_lines": [],
        },
    ])

    songs_col().insert_many([
        {
            "artist": "Artist A",
            "title": "Song 1",
            "filepath": "/path/to/song1.txt",
            "word_count": 50,
            "line_count": 20,
            "ingested_at": datetime(2024, 1, 15, tzinfo=timezone.utc),
        },
        {
            "artist": "Artist B",
            "title": "Song 2",
            "filepath": "/path/to/song2.txt",
            "word_count": 30,
            "line_count": 15,
            "ingested_at": datetime(2024, 1, 10, tzinfo=timezone.utc),
        },
    ])

    history_col().insert_many([
        {
            "lemma": "слово",
            "pos": "NOUN",
            "translation": "word",
            "example_line": None,
            "shown_at": datetime(2024, 1, 20, tzinfo=timezone.utc),
        },
    ])

    return mock_mongo_client


class TestHealthCheck:
    """Test the health check endpoint."""

    def test_health_check(self, client):
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "slovo-dnya"


class TestListWords:
    """Test the word listing endpoint."""

    def test_list_all_words(self, client, populated_db):
        response = client.get("/words")
        assert response.status_code == 200
        words = response.json()
        assert len(words) == 3

    def test_filter_by_pos(self, client, populated_db):
        response = client.get("/words?pos=NOUN")
        assert response.status_code == 200
        words = response.json()
        assert len(words) == 2
        assert all(w["pos"] == "NOUN" for w in words)

    def test_filter_unknown_only(self, client, populated_db):
        response = client.get("/words?unknown_only=true")
        assert response.status_code == 200
        words = response.json()
        assert len(words) == 2
        assert all(w["known"] is False for w in words)

    def test_filter_by_artist(self, client, populated_db):
        response = client.get("/words?artist=Artist%20A")
        assert response.status_code == 200
        words = response.json()
        assert len(words) == 2  # місто and йти

    def test_filter_by_min_freq(self, client, populated_db):
        response = client.get("/words?min_freq=8")
        assert response.status_code == 200
        words = response.json()
        assert len(words) == 2  # місто (10) and йти (8)

    def test_pagination(self, client, populated_db):
        # Get first 2
        response = client.get("/words?limit=2")
        assert response.status_code == 200
        words = response.json()
        assert len(words) == 2

        # Get with offset
        response = client.get("/words?limit=2&offset=2")
        words = response.json()
        assert len(words) == 1

    def test_sorted_by_frequency(self, client, populated_db):
        response = client.get("/words")
        words = response.json()
        frequencies = [w["frequency"] for w in words]
        assert frequencies == sorted(frequencies, reverse=True)


class TestGetWord:
    """Test getting a single word's details."""

    def test_get_existing_word(self, client, populated_db):
        response = client.get("/words/місто")
        assert response.status_code == 200
        word = response.json()
        assert word["lemma"] == "місто"
        assert word["pos"] == "NOUN"
        assert word["translation"] == "city"
        assert len(word["example_lines"]) == 1

    def test_get_nonexistent_word(self, client, populated_db):
        response = client.get("/words/nonexistent")
        assert response.status_code == 404

    def test_case_insensitive_lookup(self, client, populated_db):
        response = client.get("/words/МІСТО")
        assert response.status_code == 200
        assert response.json()["lemma"] == "місто"


class TestMarkKnown:
    """Test marking words as known."""

    def test_mark_existing_word(self, client, populated_db):
        response = client.post("/words/місто/known")
        assert response.status_code == 200
        assert response.json()["message"] == "Word marked as known"

        # Verify it was updated
        from slovo.db import words_col

        word = words_col().find_one({"lemma": "місто"})
        assert word["known"] is True

    def test_mark_nonexistent_word(self, client, populated_db):
        response = client.post("/words/nonexistent/known")
        assert response.status_code == 404


class TestSetTranslation:
    """Test setting custom translations."""

    def test_set_translation(self, client, populated_db):
        response = client.post(
            "/words/місто/translation",
            json={"translation": "urban area"},
        )
        assert response.status_code == 200

        from slovo.db import words_col

        word = words_col().find_one({"lemma": "місто"})
        assert word["translation"] == "urban area"

    def test_set_translation_nonexistent(self, client, populated_db):
        response = client.post(
            "/words/nonexistent/translation",
            json={"translation": "test"},
        )
        assert response.status_code == 404


class TestSetNote:
    """Test adding notes to words."""

    def test_set_note(self, client, populated_db):
        response = client.post(
            "/words/місто/note",
            json={"note": "Neuter noun"},
        )
        assert response.status_code == 200

        from slovo.db import words_col

        word = words_col().find_one({"lemma": "місто"})
        assert word["notes"] == "Neuter noun"


class TestWodEndpoints:
    """Test word-of-the-day endpoints."""

    def test_get_wod_preview(self, client, populated_db):
        response = client.get("/wod")
        assert response.status_code == 200
        wod = response.json()

        # Should return highest frequency unknown word
        assert wod is not None
        assert wod["lemma"] == "місто"
        assert wod["translation"] == "city"

    def test_get_wod_with_pos_filter(self, client, populated_db):
        response = client.get("/wod?pos=VERB")
        assert response.status_code == 200
        wod = response.json()
        assert wod["lemma"] == "йти"

    def test_get_wod_preview_does_not_record(self, client, populated_db):
        from slovo.db import history_col

        initial_count = history_col().count_documents({})

        client.get("/wod")

        assert history_col().count_documents({}) == initial_count

    def test_post_wod_records_history(self, client, populated_db):
        from slovo.db import history_col, words_col

        initial_count = history_col().count_documents({})

        response = client.post("/wod")
        assert response.status_code == 200

        # History should have new entry
        assert history_col().count_documents({}) == initial_count + 1

        # Word should have shown_at set
        word = words_col().find_one({"lemma": "місто"})
        assert word["shown_at"] is not None

    def test_wod_returns_none_when_no_eligible(self, client, mock_mongo_client):
        # Empty database
        response = client.get("/wod")
        assert response.status_code == 200
        assert response.json() is None


class TestStats:
    """Test statistics endpoint."""

    def test_get_stats(self, client, populated_db):
        response = client.get("/stats")
        assert response.status_code == 200
        stats = response.json()

        assert stats["total"] == 3
        assert stats["known"] == 1
        assert "pos_breakdown" in stats
        assert "top_unknown" in stats


class TestHistory:
    """Test history endpoint."""

    def test_get_history(self, client, populated_db):
        response = client.get("/history")
        assert response.status_code == 200
        history = response.json()
        assert len(history) >= 1
        assert history[0]["lemma"] == "слово"

    def test_history_limit(self, client, populated_db):
        response = client.get("/history?limit=1")
        history = response.json()
        assert len(history) == 1


class TestSongs:
    """Test songs listing endpoint."""

    def test_list_songs(self, client, populated_db):
        response = client.get("/songs")
        assert response.status_code == 200
        songs = response.json()
        assert len(songs) == 2

    def test_filter_songs_by_artist(self, client, populated_db):
        response = client.get("/songs?artist=Artist%20A")
        songs = response.json()
        assert len(songs) == 1
        assert songs[0]["artist"] == "Artist A"

    def test_songs_sorted_by_date(self, client, populated_db):
        response = client.get("/songs")
        songs = response.json()
        # Most recent first
        assert songs[0]["title"] == "Song 1"
