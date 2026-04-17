"""
genius.py -- Genius API service for song search and lyrics extraction.

Provides GeniusService class for:
  - Searching songs via Genius API
  - Fetching song metadata
  - Scraping and cleaning lyrics from Genius web pages

Environment variables required:
  - GENIUS_CLIENT_ACCESS_TOKEN
"""
import os
import re
from typing import Optional

import requests
from bs4 import BeautifulSoup


class GeniusService:
    """Service for interacting with the Genius API and scraping lyrics."""

    def __init__(self, access_token: Optional[str] = None):
        """
        Initialize Genius service.

        Args:
            access_token: Genius API access token. If not provided, reads from
                         GENIUS_CLIENT_ACCESS_TOKEN environment variable.

        Raises:
            ValueError: If access token is not provided and not found in environment.
        """
        self.access_token = access_token or os.getenv("GENIUS_CLIENT_ACCESS_TOKEN")
        if not self.access_token:
            raise ValueError(
                "Genius API access token is required. "
                "Set GENIUS_CLIENT_ACCESS_TOKEN environment variable or pass access_token parameter."
            )

        self.base_url = "https://api.genius.com"
        self.headers = {"Authorization": f"Bearer {self.access_token}"}

    def search_songs(self, query: str, max_results: int = 10) -> list[dict]:
        """
        Search for songs on Genius.

        Args:
            query: Search query (artist name, song title, or both)
            max_results: Maximum number of results to return (default: 10)

        Returns:
            List of song dicts with keys: id, title, artist, url

        Raises:
            requests.HTTPError: If API request fails
            RuntimeError: If response format is unexpected
        """
        url = f"{self.base_url}/search"
        params = {"q": query}

        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            response.raise_for_status()
        except requests.RequestException as e:
            raise requests.HTTPError(
                f"Genius API search request failed for query '{query}': {e}"
            ) from e

        try:
            data = response.json()
            hits = data["response"]["hits"]
        except (KeyError, ValueError) as e:
            raise RuntimeError(
                f"Unexpected response format from Genius API: {e}"
            ) from e

        songs = []
        for hit in hits[:max_results]:
            try:
                result = hit["result"]
                songs.append({
                    "id": result["id"],
                    "title": result["title"],
                    "artist": result["primary_artist"]["name"],
                    "url": result["url"],
                })
            except KeyError as e:
                raise RuntimeError(
                    f"Missing expected field in Genius API response: {e}"
                ) from e

        return songs

    def get_song(self, song_id: int) -> dict:
        """
        Get detailed song information including metadata and lyrics.

        Args:
            song_id: Genius song ID

        Returns:
            Dict with keys: id, title, artist, url, lyrics, release_date

        Raises:
            requests.HTTPError: If API request or lyrics scraping fails
            RuntimeError: If response format is unexpected
        """
        url = f"{self.base_url}/songs/{song_id}"

        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
        except requests.RequestException as e:
            raise requests.HTTPError(
                f"Genius API song request failed for ID {song_id}: {e}"
            ) from e

        try:
            data = response.json()
            song = data["response"]["song"]
        except (KeyError, ValueError) as e:
            raise RuntimeError(
                f"Unexpected response format from Genius API: {e}"
            ) from e

        song_url = song.get("url")
        if not song_url:
            raise RuntimeError(f"No URL found for song ID {song_id}")

        lyrics = self.scrape_lyrics(song_url)

        return {
            "id": song["id"],
            "title": song["title"],
            "artist": song["primary_artist"]["name"],
            "url": song_url,
            "lyrics": lyrics,
            "release_date": song.get("release_date_for_display", "Unknown"),
        }

    def scrape_lyrics(self, url: str) -> str:
        """
        Scrape and clean lyrics from a Genius song page.

        Args:
            url: URL of Genius song page

        Returns:
            Cleaned lyrics text

        Raises:
            requests.HTTPError: If page request fails
            RuntimeError: If lyrics cannot be found on page
        """
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
        except requests.RequestException as e:
            raise requests.HTTPError(
                f"Failed to fetch lyrics from {url}: {e}"
            ) from e

        soup = BeautifulSoup(response.text, "html.parser")

        lyrics_selectors = [
            'div[class*="Lyrics__Container"]',
            'div[class*="lyrics"]',
            'div[data-lyrics-container="true"]',
        ]

        lyrics_divs = None
        for selector in lyrics_selectors:
            lyrics_divs = soup.select(selector)
            if lyrics_divs:
                break

        if not lyrics_divs:
            raise RuntimeError(f"Could not find lyrics on page: {url}")

        lyrics_parts = []
        for div in lyrics_divs:
            for br in div.find_all("br"):
                br.replace_with("\n")

            text = div.get_text(separator="\n")
            lyrics_parts.append(text)

        lyrics = "\n".join(lyrics_parts)

        lyrics = self._clean_lyrics(lyrics)

        return lyrics

    def _clean_lyrics(self, lyrics: str) -> str:
        """
        Clean lyrics text by removing markers and formatting artifacts.

        Args:
            lyrics: Raw lyrics text

        Returns:
            Cleaned lyrics text
        """
        lyrics = re.sub(r"\[.*?\]", "", lyrics)

        lyrics = re.sub(r"\bEmbed\b", "", lyrics, flags=re.IGNORECASE)

        lyrics = re.sub(r"\n{3,}", "\n\n", lyrics)

        lyrics = lyrics.strip()

        return lyrics
