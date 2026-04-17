"""
Tests for slovo/genius.py — Genius API service for song search and lyrics.
"""
import os
from unittest.mock import MagicMock, patch

import pytest
import requests


class TestGeniusServiceInit:
    """Tests for GeniusService initialization."""

    def test_init_with_token_parameter(self):
        """Should accept token as parameter."""
        from slovo.genius import GeniusService

        service = GeniusService(access_token="test_token")
        assert service.access_token == "test_token"
        assert service.headers["Authorization"] == "Bearer test_token"

    def test_init_with_env_variable(self):
        """Should read token from environment."""
        with patch.dict(os.environ, {"GENIUS_CLIENT_ACCESS_TOKEN": "env_token"}):
            from slovo.genius import GeniusService

            service = GeniusService()
            assert service.access_token == "env_token"

    def test_init_without_token_raises(self):
        """Should raise ValueError when no token provided."""
        with patch.dict(os.environ, {"GENIUS_CLIENT_ACCESS_TOKEN": ""}, clear=False):
            from slovo.genius import GeniusService

            with pytest.raises(ValueError, match="access token is required"):
                GeniusService()


class TestSearchSongs:
    """Tests for GeniusService.search_songs method."""

    def test_search_songs_success(self):
        """Should return list of song dicts."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "response": {
                "hits": [
                    {
                        "result": {
                            "id": 123,
                            "title": "Test Song",
                            "primary_artist": {"name": "Test Artist"},
                            "url": "https://genius.com/test-song",
                        }
                    },
                    {
                        "result": {
                            "id": 456,
                            "title": "Another Song",
                            "primary_artist": {"name": "Another Artist"},
                            "url": "https://genius.com/another-song",
                        }
                    },
                ]
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_response):
            from slovo.genius import GeniusService

            service = GeniusService(access_token="test")
            songs = service.search_songs("test query")

            assert len(songs) == 2
            assert songs[0]["id"] == 123
            assert songs[0]["title"] == "Test Song"
            assert songs[0]["artist"] == "Test Artist"
            assert songs[0]["url"] == "https://genius.com/test-song"

    def test_search_songs_respects_limit(self):
        """Should limit results to max_results."""
        hits = [
            {
                "result": {
                    "id": i,
                    "title": f"Song {i}",
                    "primary_artist": {"name": "Artist"},
                    "url": f"https://genius.com/song-{i}",
                }
            }
            for i in range(20)
        ]
        mock_response = MagicMock()
        mock_response.json.return_value = {"response": {"hits": hits}}
        mock_response.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_response):
            from slovo.genius import GeniusService

            service = GeniusService(access_token="test")
            songs = service.search_songs("test", max_results=5)

            assert len(songs) == 5

    def test_search_songs_empty_results(self):
        """Should return empty list when no results."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"response": {"hits": []}}
        mock_response.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_response):
            from slovo.genius import GeniusService

            service = GeniusService(access_token="test")
            songs = service.search_songs("nonexistent query")

            assert songs == []

    def test_search_songs_api_error(self):
        """Should raise HTTPError on API failure."""
        with patch("requests.get", side_effect=requests.RequestException("API error")):
            from slovo.genius import GeniusService

            service = GeniusService(access_token="test")
            with pytest.raises(requests.HTTPError, match="search request failed"):
                service.search_songs("test")

    def test_search_songs_unexpected_response(self):
        """Should raise RuntimeError on unexpected response format."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"unexpected": "format"}
        mock_response.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_response):
            from slovo.genius import GeniusService

            service = GeniusService(access_token="test")
            with pytest.raises(RuntimeError, match="Unexpected response format"):
                service.search_songs("test")


class TestGetSong:
    """Tests for GeniusService.get_song method."""

    def test_get_song_success(self):
        """Should return song dict with lyrics."""
        api_response = MagicMock()
        api_response.json.return_value = {
            "response": {
                "song": {
                    "id": 123,
                    "title": "Test Song",
                    "primary_artist": {"name": "Test Artist"},
                    "url": "https://genius.com/test-song-lyrics",
                    "release_date_for_display": "January 1, 2020",
                }
            }
        }
        api_response.raise_for_status = MagicMock()

        scrape_response = MagicMock()
        scrape_response.text = """
        <html>
        <div data-lyrics-container="true">
            First verse line<br/>
            Second verse line
        </div>
        </html>
        """
        scrape_response.raise_for_status = MagicMock()

        with patch("requests.get", side_effect=[api_response, scrape_response]):
            from slovo.genius import GeniusService

            service = GeniusService(access_token="test")
            song = service.get_song(123)

            assert song["id"] == 123
            assert song["title"] == "Test Song"
            assert song["artist"] == "Test Artist"
            assert "First verse line" in song["lyrics"]
            assert song["release_date"] == "January 1, 2020"

    def test_get_song_api_error(self):
        """Should raise HTTPError on API failure."""
        with patch("requests.get", side_effect=requests.RequestException("API error")):
            from slovo.genius import GeniusService

            service = GeniusService(access_token="test")
            with pytest.raises(requests.HTTPError, match="song request failed"):
                service.get_song(123)


class TestScrapeLyrics:
    """Tests for GeniusService.scrape_lyrics method."""

    def test_scrape_lyrics_data_container(self):
        """Should find lyrics in data-lyrics-container div."""
        mock_response = MagicMock()
        mock_response.text = """
        <html>
        <div data-lyrics-container="true">
            First line<br/>
            Second line
        </div>
        </html>
        """
        mock_response.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_response):
            from slovo.genius import GeniusService

            service = GeniusService(access_token="test")
            lyrics = service.scrape_lyrics("https://genius.com/test")

            assert "First line" in lyrics
            assert "Second line" in lyrics

    def test_scrape_lyrics_class_container(self):
        """Should find lyrics in class-based container."""
        mock_response = MagicMock()
        mock_response.text = """
        <html>
        <div class="Lyrics__Container-sc-1ynbvzw">
            Verse one<br/>
            Verse two
        </div>
        </html>
        """
        mock_response.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_response):
            from slovo.genius import GeniusService

            service = GeniusService(access_token="test")
            lyrics = service.scrape_lyrics("https://genius.com/test")

            assert "Verse one" in lyrics
            assert "Verse two" in lyrics

    def test_scrape_lyrics_removes_markers(self):
        """Should remove [Verse], [Chorus] markers."""
        mock_response = MagicMock()
        mock_response.text = """
        <html>
        <div data-lyrics-container="true">
            [Verse 1]
            First line
            [Chorus]
            Chorus line
        </div>
        </html>
        """
        mock_response.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_response):
            from slovo.genius import GeniusService

            service = GeniusService(access_token="test")
            lyrics = service.scrape_lyrics("https://genius.com/test")

            assert "[Verse 1]" not in lyrics
            assert "[Chorus]" not in lyrics
            assert "First line" in lyrics
            assert "Chorus line" in lyrics

    def test_scrape_lyrics_removes_embed(self):
        """Should remove Embed text."""
        mock_response = MagicMock()
        mock_response.text = """
        <html>
        <div data-lyrics-container="true">
            Song lyrics here
            Embed
        </div>
        </html>
        """
        mock_response.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_response):
            from slovo.genius import GeniusService

            service = GeniusService(access_token="test")
            lyrics = service.scrape_lyrics("https://genius.com/test")

            assert "Embed" not in lyrics
            assert "Song lyrics here" in lyrics

    def test_scrape_lyrics_no_container(self):
        """Should raise RuntimeError when no lyrics container found."""
        mock_response = MagicMock()
        mock_response.text = "<html><body>No lyrics here</body></html>"
        mock_response.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_response):
            from slovo.genius import GeniusService

            service = GeniusService(access_token="test")
            with pytest.raises(RuntimeError, match="Could not find lyrics"):
                service.scrape_lyrics("https://genius.com/test")

    def test_scrape_lyrics_request_error(self):
        """Should raise HTTPError on request failure."""
        with patch("requests.get", side_effect=requests.RequestException("Network error")):
            from slovo.genius import GeniusService

            service = GeniusService(access_token="test")
            with pytest.raises(requests.HTTPError, match="Failed to fetch lyrics"):
                service.scrape_lyrics("https://genius.com/test")


class TestCleanLyrics:
    """Tests for the private _clean_lyrics method."""

    def test_clean_lyrics_normalizes_newlines(self):
        """Should reduce excessive newlines."""
        from slovo.genius import GeniusService

        service = GeniusService(access_token="test")

        dirty = "Line one\n\n\n\n\nLine two\n\n\n\n\n\nLine three"
        clean = service._clean_lyrics(dirty)

        assert "\n\n\n" not in clean
        assert "Line one" in clean
        assert "Line two" in clean
        assert "Line three" in clean

    def test_clean_lyrics_strips_whitespace(self):
        """Should strip leading/trailing whitespace."""
        from slovo.genius import GeniusService

        service = GeniusService(access_token="test")

        dirty = "   \n\n  Lyrics here  \n\n   "
        clean = service._clean_lyrics(dirty)

        assert clean == "Lyrics here"
