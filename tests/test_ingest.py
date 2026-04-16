"""
Tests for the lyrics ingestion module.

Note: Some tests mock the stanza NLP pipeline to avoid downloading
models during testing. Integration tests with real NLP would be separate.
"""
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestParseMetadata:
    """Test metadata extraction from lyrics files."""

    def test_parses_artist_and_title(self):
        from slovo.ingest import _parse_metadata

        lines = [
            "# Artist: BoomBox",
            "# Title: Врятуй",
            "",
            "Перший рядок",
            "Другий рядок",
        ]
        artist, title, content = _parse_metadata(lines)
        assert artist == "BoomBox"
        assert title == "Врятуй"
        assert content == ["Перший рядок", "Другий рядок"]

    def test_defaults_to_unknown(self):
        from slovo.ingest import _parse_metadata

        lines = ["Рядок без метаданих"]
        artist, title, content = _parse_metadata(lines)
        assert artist == "Unknown"
        assert title == "Unknown"

    def test_skips_section_markers(self):
        from slovo.ingest import _parse_metadata

        lines = [
            "# Artist: Test",
            "# Title: Song",
            "# [Приспів]",
            "Рядок приспіву",
            "# [Куплет]",
            "Рядок куплету",
        ]
        artist, title, content = _parse_metadata(lines)
        # Section markers like "[Приспів]" should be skipped
        assert "# [Приспів]" not in content
        assert content == ["Рядок приспіву", "Рядок куплету"]

    def test_handles_whitespace(self):
        from slovo.ingest import _parse_metadata

        lines = [
            "# Artist:   BoomBox  ",
            "# Title:   Врятуй  ",
            "  ",
            "Рядок  ",
        ]
        artist, title, content = _parse_metadata(lines)
        assert artist == "BoomBox"
        assert title == "Врятуй"


class TestIsCyrillic:
    """Test Cyrillic text detection."""

    def test_detects_ukrainian_text(self):
        from slovo.ingest import _is_cyrillic

        assert _is_cyrillic("Привіт") is True
        assert _is_cyrillic("їжак") is True
        assert _is_cyrillic("МІСТО") is True

    def test_rejects_latin_only(self):
        from slovo.ingest import _is_cyrillic

        assert _is_cyrillic("Hello") is False
        assert _is_cyrillic("123") is False

    def test_mixed_content(self):
        from slovo.ingest import _is_cyrillic

        # Mixed is still Cyrillic if it contains Cyrillic
        assert _is_cyrillic("Hello Київ") is True


class TestStopLemmas:
    """Test that common words are filtered out."""

    def test_common_words_excluded(self):
        from slovo.ingest import STOP_LEMMAS

        # Function words should be in stop list
        assert "і" in STOP_LEMMAS
        assert "та" in STOP_LEMMAS
        assert "що" in STOP_LEMMAS
        assert "бути" in STOP_LEMMAS


class TestTokenizeLine:
    """Test line tokenization with mocked NLP."""

    def test_extracts_content_words(self):
        from slovo.ingest import _tokenize_line

        # Create a mock NLP pipeline
        mock_nlp = MagicMock()

        # Mock stanza document structure
        mock_word1 = MagicMock()
        mock_word1.upos = "NOUN"
        mock_word1.lemma = "місто"
        mock_word1.text = "місто"

        mock_word2 = MagicMock()
        mock_word2.upos = "VERB"
        mock_word2.lemma = "спати"
        mock_word2.text = "спить"

        mock_word3 = MagicMock()
        mock_word3.upos = "ADP"  # Preposition - should be filtered
        mock_word3.lemma = "в"
        mock_word3.text = "в"

        mock_sentence = MagicMock()
        mock_sentence.words = [mock_word1, mock_word2, mock_word3]

        mock_doc = MagicMock()
        mock_doc.sentences = [mock_sentence]

        mock_nlp.return_value = mock_doc

        tokens = _tokenize_line("Місто спить в ночі", mock_nlp)

        # Should only include NOUN and VERB
        lemmas = [t["lemma"] for t in tokens]
        assert "місто" in lemmas
        assert "спати" in lemmas
        assert "в" not in lemmas  # Preposition filtered

    def test_filters_short_lemmas(self):
        from slovo.ingest import _tokenize_line

        mock_nlp = MagicMock()

        mock_word = MagicMock()
        mock_word.upos = "NOUN"
        mock_word.lemma = "я"  # Single letter
        mock_word.text = "я"

        mock_sentence = MagicMock()
        mock_sentence.words = [mock_word]

        mock_doc = MagicMock()
        mock_doc.sentences = [mock_sentence]
        mock_nlp.return_value = mock_doc

        tokens = _tokenize_line("Я", mock_nlp)
        assert len(tokens) == 0  # Single letter filtered


class TestIngestFile:
    """Test file ingestion with mocked dependencies."""

    def test_skips_already_ingested(self, mock_mongo_client, tmp_lyrics_file):
        from slovo.db import songs_col
        from slovo.ingest import ingest_file

        # Mark file as already ingested
        songs_col().insert_one({
            "filepath": str(tmp_lyrics_file),
            "artist": "Test",
            "title": "Song",
        })

        result = ingest_file(tmp_lyrics_file, force=False)
        assert result["skipped"] is True

    def test_force_reingests(self, mock_mongo_client, tmp_lyrics_file):
        from slovo.db import songs_col
        from slovo.ingest import ingest_file

        # Mark file as already ingested
        songs_col().insert_one({
            "filepath": str(tmp_lyrics_file),
            "artist": "Test",
            "title": "Song",
        })

        # Mock the NLP pipeline to avoid downloading models
        with patch("slovo.ingest.get_pipeline") as mock_get_pipeline, \
             patch("slovo.ingest._translate_line", return_value="translated"):

            mock_nlp = MagicMock()
            mock_word = MagicMock()
            mock_word.upos = "NOUN"
            mock_word.lemma = "тест"
            mock_word.text = "тест"

            mock_sentence = MagicMock()
            mock_sentence.words = [mock_word]

            mock_doc = MagicMock()
            mock_doc.sentences = [mock_sentence]
            mock_nlp.return_value = mock_doc

            mock_get_pipeline.return_value = mock_nlp

            result = ingest_file(tmp_lyrics_file, force=True)
            assert result["skipped"] is False

    def test_raises_for_missing_file(self, mock_mongo_client):
        from slovo.ingest import ingest_file

        with pytest.raises(FileNotFoundError):
            ingest_file("/nonexistent/file.txt")

    def test_records_song_metadata(self, mock_mongo_client, tmp_lyrics_file):
        from slovo.db import songs_col
        from slovo.ingest import ingest_file

        with patch("slovo.ingest.get_pipeline") as mock_get_pipeline, \
             patch("slovo.ingest._translate_line", return_value="translated"):

            mock_nlp = MagicMock()
            mock_word = MagicMock()
            mock_word.upos = "NOUN"
            mock_word.lemma = "ранок"
            mock_word.text = "ранок"

            mock_sentence = MagicMock()
            mock_sentence.words = [mock_word]

            mock_doc = MagicMock()
            mock_doc.sentences = [mock_sentence]
            mock_nlp.return_value = mock_doc

            mock_get_pipeline.return_value = mock_nlp

            ingest_file(tmp_lyrics_file)

            # Check song was recorded
            song = songs_col().find_one({"filepath": str(tmp_lyrics_file)})
            assert song is not None
            assert song["artist"] == "Test Artist"
            assert song["title"] == "Test Song"
            assert "ingested_at" in song


class TestIngestDirectory:
    """Test directory ingestion."""

    def test_ingests_all_txt_files(self, mock_mongo_client, tmp_path):
        from slovo.ingest import ingest_directory

        # Create multiple lyrics files
        (tmp_path / "song1.txt").write_text(
            "# Artist: A\n# Title: One\nТекст", encoding="utf-8"
        )
        (tmp_path / "song2.txt").write_text(
            "# Artist: B\n# Title: Two\nТекст", encoding="utf-8"
        )
        (tmp_path / "not_lyrics.md").write_text("# Readme", encoding="utf-8")

        with patch("slovo.ingest.get_pipeline") as mock_get_pipeline, \
             patch("slovo.ingest._translate_line", return_value="text"):

            mock_nlp = MagicMock()
            mock_word = MagicMock()
            mock_word.upos = "NOUN"
            mock_word.lemma = "текст"
            mock_word.text = "текст"

            mock_sentence = MagicMock()
            mock_sentence.words = [mock_word]

            mock_doc = MagicMock()
            mock_doc.sentences = [mock_sentence]
            mock_nlp.return_value = mock_doc

            mock_get_pipeline.return_value = mock_nlp

            results = ingest_directory(tmp_path)

            # Should process only .txt files
            assert len(results) == 2

    def test_returns_empty_for_no_txt(self, mock_mongo_client, tmp_path):
        from slovo.ingest import ingest_directory

        (tmp_path / "readme.md").write_text("# Readme", encoding="utf-8")

        results = ingest_directory(tmp_path)
        assert results == []


class TestExampleLineStorage:
    """Test that example lines are stored correctly."""

    def test_stores_up_to_max_lines(self, mock_mongo_client, tmp_path):
        from slovo.db import words_col
        from slovo.ingest import MAX_EXAMPLE_LINES, ingest_file

        # Create lyrics with many lines containing the same word
        lines = ["# Artist: Test", "# Title: Song"]
        for i in range(10):
            lines.append(f"Рядок {i} з словом тест")

        lyrics_file = tmp_path / "test.txt"
        lyrics_file.write_text("\n".join(lines), encoding="utf-8")

        with patch("slovo.ingest.get_pipeline") as mock_get_pipeline, \
             patch("slovo.ingest._translate_line", return_value="translated"):

            mock_nlp = MagicMock()

            def process_line(line):
                mock_word = MagicMock()
                mock_word.upos = "NOUN"
                mock_word.lemma = "тест"
                mock_word.text = "тест"

                mock_sentence = MagicMock()
                mock_sentence.words = [mock_word]

                mock_doc = MagicMock()
                mock_doc.sentences = [mock_sentence]
                return mock_doc

            mock_nlp.side_effect = process_line
            mock_get_pipeline.return_value = mock_nlp

            ingest_file(lyrics_file)

            word = words_col().find_one({"lemma": "тест"})
            assert word is not None
            assert len(word["example_lines"]) <= MAX_EXAMPLE_LINES


class TestTranslitInIngestion:
    """Test that transliteration is applied to stored lines."""

    def test_lines_include_translit(self, mock_mongo_client, tmp_path):
        from slovo.db import words_col
        from slovo.ingest import ingest_file

        lyrics = "# Artist: Test\n# Title: Song\n\nМісто спить"
        lyrics_file = tmp_path / "test.txt"
        lyrics_file.write_text(lyrics, encoding="utf-8")

        with patch("slovo.ingest.get_pipeline") as mock_get_pipeline, \
             patch("slovo.ingest._translate_line", return_value="The city sleeps"):

            mock_nlp = MagicMock()
            mock_word = MagicMock()
            mock_word.upos = "NOUN"
            mock_word.lemma = "місто"
            mock_word.text = "місто"

            mock_sentence = MagicMock()
            mock_sentence.words = [mock_word]

            mock_doc = MagicMock()
            mock_doc.sentences = [mock_sentence]
            mock_nlp.return_value = mock_doc

            mock_get_pipeline.return_value = mock_nlp

            ingest_file(lyrics_file)

            word = words_col().find_one({"lemma": "місто"})
            assert word is not None
            assert len(word["example_lines"]) > 0
            line = word["example_lines"][0]
            assert "translit" in line
            # Translit should contain Latin characters
            assert any(c.isascii() and c.isalpha() for c in line["translit"])
