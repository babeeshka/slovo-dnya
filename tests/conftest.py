"""
Shared pytest fixtures for slovo-dnya tests.

Uses mongomock to provide an in-memory MongoDB for testing without
requiring a real database connection.
"""
import os
from unittest.mock import patch

import mongomock
import pytest


@pytest.fixture(autouse=True)
def mock_env():
    """Set test environment variables for all tests."""
    env_vars = {
        "MONGODB_URI": "mongodb://localhost:27017",
        "MONGODB_DB": "slovo_test",
        "NOTIFY_METHOD": "print",
    }
    with patch.dict(os.environ, env_vars, clear=False):
        yield


@pytest.fixture
def mock_mongo_client():
    """
    Provide a mongomock client that behaves like pymongo.

    This replaces the real MongoClient with an in-memory mock,
    so tests don't need a running MongoDB instance.
    """
    client = mongomock.MongoClient()
    with patch("slovo.db.get_client", return_value=client):
        # Clear the lru_cache so our mock is used
        from slovo.db import get_client
        get_client.cache_clear()
        yield client
        # Clean up after test
        client.close()
        get_client.cache_clear()


@pytest.fixture
def test_db(mock_mongo_client):
    """Get the test database from the mock client."""
    return mock_mongo_client["slovo_test"]


@pytest.fixture
def words_collection(test_db):
    """Get the words collection from the test database."""
    return test_db["words"]


@pytest.fixture
def songs_collection(test_db):
    """Get the songs collection from the test database."""
    return test_db["songs"]


@pytest.fixture
def history_collection(test_db):
    """Get the history collection from the test database."""
    return test_db["history"]


@pytest.fixture
def sample_word_doc():
    """A sample word document matching the schema."""
    return {
        "lemma": "місто",
        "pos": "NOUN",
        "frequency": 4,
        "songs": ["BoomBox - Врятуй", "Re-Read - Ніч"],
        "known": False,
        "translation": "city, town",
        "shown_at": None,
        "notes": "",
        "example_lines": [
            {
                "cyrillic": "Місяць світить над тихим містом",
                "translit": "Misiats svityt nad tykhym mistom",
                "translation": "The moon shines over the quiet city",
                "song": "Зразок - Вечірнє місто",
            }
        ],
    }


@pytest.fixture
def sample_lyrics_content():
    """Sample lyrics file content for testing ingestion."""
    return """# Artist: Test Artist
# Title: Test Song

Ранок приходить тихо і повільно
Місто прокидається навколо
Серце моє б'ється дуже рівно
"""


@pytest.fixture
def tmp_lyrics_file(tmp_path, sample_lyrics_content):
    """Create a temporary lyrics file for testing."""
    lyrics_file = tmp_path / "test_song.txt"
    lyrics_file.write_text(sample_lyrics_content, encoding="utf-8")
    return lyrics_file
