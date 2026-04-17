"""
Tests for export functionality.

Tests CSV, JSON, and Anki export formats.
"""
import csv
import json
from pathlib import Path

import pytest


@pytest.fixture
def export_words_data(mock_mongo_client):
    """Populate database with test words for export testing."""
    from slovo.db import words_col

    words_col().insert_many([
        {
            "lemma": "привіт",
            "pos": "NOUN",
            "frequency": 15,
            "translation": "hello; greeting",
            "known": False,
            "notes": "",
            "example_lines": [
                {
                    "cyrillic": "Привіт, як справи?",
                    "translit": "Pryvit, yak spravy?",
                    "translation": "Hello, how are you?",
                    "song": "Test Song 1",
                }
            ],
        },
        {
            "lemma": "місто",
            "pos": "NOUN",
            "frequency": 10,
            "translation": "city, town",
            "known": False,
            "notes": "",
            "example_lines": [
                {
                    "cyrillic": "Місяць світить над тихим містом",
                    "translit": "Misiats svityt nad tykhym mistom",
                    "translation": "The moon shines over the quiet city",
                    "song": "Test Song 2",
                }
            ],
        },
        {
            "lemma": "вода",
            "pos": "NOUN",
            "frequency": 8,
            "translation": "water",
            "known": True,
            "notes": "Feminine noun",
            "example_lines": [],
        },
        {
            "lemma": "йти",
            "pos": "VERB",
            "frequency": 12,
            "translation": "to go",
            "known": False,
            "notes": "",
            "example_lines": [
                {
                    "cyrillic": "Я йду додому",
                    "translit": "Ya ydu dodomu",
                    "translation": "I am going home",
                    "song": "Test Song 3",
                }
            ],
        },
    ])

    return mock_mongo_client


class TestCsvExport:
    """Test CSV export functionality."""

    def test_export_csv_all_words(self, tmp_path, export_words_data):
        """Test exporting all words to CSV."""
        from typer.testing import CliRunner
        from slovo.cli import app

        runner = CliRunner()
        output_file = tmp_path / "test_export.csv"

        result = runner.invoke(app, ["export", "--output", str(output_file), "--format", "csv"])

        assert result.exit_code == 0
        assert output_file.exists()

        with open(output_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 4
        assert rows[0]["lemma"] == "привіт"  # Sorted by frequency desc

    def test_export_csv_unknown_only(self, tmp_path, export_words_data):
        """Test exporting only unknown words to CSV."""
        from typer.testing import CliRunner
        from slovo.cli import app

        runner = CliRunner()
        output_file = tmp_path / "test_unknown.csv"

        result = runner.invoke(app, ["export", "--output", str(output_file), "--format", "csv", "--unknown"])

        assert result.exit_code == 0
        assert output_file.exists()

        with open(output_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 3  # Should exclude "вода" (known=True)
        assert all(row["known"] == "False" for row in rows)


class TestJsonExport:
    """Test JSON export functionality."""

    def test_export_json_all_words(self, tmp_path, export_words_data):
        """Test exporting all words to JSON."""
        from typer.testing import CliRunner
        from slovo.cli import app

        runner = CliRunner()
        output_file = tmp_path / "test_export.json"

        result = runner.invoke(app, ["export", "--output", str(output_file), "--format", "json"])

        assert result.exit_code == 0
        assert output_file.exists()

        with open(output_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert len(data) == 4
        assert data[0]["lemma"] == "привіт"

    def test_export_json_by_pos(self, tmp_path, export_words_data):
        """Test filtering by POS in JSON export."""
        from typer.testing import CliRunner
        from slovo.cli import app

        runner = CliRunner()
        output_file = tmp_path / "test_nouns.json"

        result = runner.invoke(app, ["export", "--output", str(output_file), "--format", "json", "--pos", "NOUN"])

        assert result.exit_code == 0

        with open(output_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert len(data) == 3
        assert all(w["pos"] == "NOUN" for w in data)


class TestAnkiExport:
    """Test Anki export functionality."""

    def test_export_anki_basic_format(self, tmp_path, export_words_data):
        """Test basic Anki export format with tab-separated values."""
        from typer.testing import CliRunner
        from slovo.cli import app

        runner = CliRunner()
        output_file = tmp_path / "test_anki.txt"

        result = runner.invoke(app, ["export", "--output", str(output_file), "--format", "anki"])

        assert result.exit_code == 0
        assert output_file.exists()

        with open(output_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

        assert len(lines) == 4

    def test_export_anki_front_format(self, tmp_path, export_words_data):
        """Test Anki front side format: word (transliteration)."""
        from typer.testing import CliRunner
        from slovo.cli import app

        runner = CliRunner()
        output_file = tmp_path / "test_anki.txt"

        result = runner.invoke(app, ["export", "--output", str(output_file), "--format", "anki"])

        with open(output_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # Check first card for "привіт"
        parts = lines[0].strip().split("\t")
        front = parts[0]

        assert "привіт" in front
        assert "pryvit" in front.lower()
        assert "(" in front and ")" in front

    def test_export_anki_back_format(self, tmp_path, export_words_data):
        """Test Anki back side format: translation [POS] "example"."""
        from typer.testing import CliRunner
        from slovo.cli import app

        runner = CliRunner()
        output_file = tmp_path / "test_anki.txt"

        result = runner.invoke(app, ["export", "--output", str(output_file), "--format", "anki"])

        with open(output_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # Check first card for "привіт"
        parts = lines[0].strip().split("\t")
        back = parts[1]

        assert "hello" in back.lower() or "greeting" in back.lower()
        assert "[NOUN]" in back
        assert "Привіт" in back  # Example sentence should be included

    def test_export_anki_with_example_sentence(self, tmp_path, export_words_data):
        """Test that example sentences are included in Anki cards."""
        from typer.testing import CliRunner
        from slovo.cli import app

        runner = CliRunner()
        output_file = tmp_path / "test_anki.txt"

        result = runner.invoke(app, ["export", "--output", str(output_file), "--format", "anki"])

        with open(output_file, "r", encoding="utf-8") as f:
            content = f.read()

        # місто should have its example
        assert "Місяць світить над тихим містом" in content

    def test_export_anki_without_example_sentence(self, tmp_path, export_words_data):
        """Test Anki export handles words without example sentences."""
        from typer.testing import CliRunner
        from slovo.cli import app

        runner = CliRunner()
        output_file = tmp_path / "test_anki.txt"

        result = runner.invoke(app, ["export", "--output", str(output_file), "--format", "anki"])

        with open(output_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # Find "вода" which has no example lines
        voda_line = [line for line in lines if "вода" in line][0]
        parts = voda_line.strip().split("\t")

        assert len(parts) == 2
        front, back = parts

        assert "вода" in front
        assert "water" in back.lower()
        assert "[NOUN]" in back
        # Should not have quotes (no example)
        assert back.count('"') == 0

    def test_export_anki_unknown_only(self, tmp_path, export_words_data):
        """Test Anki export with unknown-only filter."""
        from typer.testing import CliRunner
        from slovo.cli import app

        runner = CliRunner()
        output_file = tmp_path / "test_anki_unknown.txt"

        result = runner.invoke(app, ["export", "--output", str(output_file), "--format", "anki", "--unknown"])

        assert result.exit_code == 0

        with open(output_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

        assert len(lines) == 3  # Should exclude "вода" (known=True)
        content = "\n".join(lines)
        assert "вода" not in content

    def test_export_anki_pos_filter(self, tmp_path, export_words_data):
        """Test Anki export with POS filter."""
        from typer.testing import CliRunner
        from slovo.cli import app

        runner = CliRunner()
        output_file = tmp_path / "test_anki_verbs.txt"

        result = runner.invoke(app, ["export", "--output", str(output_file), "--format", "anki", "--pos", "VERB"])

        assert result.exit_code == 0

        with open(output_file, "r", encoding="utf-8") as f:
            lines = f.readlines()

        assert len(lines) == 1
        assert "йти" in lines[0]
        assert "[VERB]" in lines[0]

    def test_export_anki_default_filename(self, tmp_path, export_words_data, monkeypatch):
        """Test that Anki export uses .txt extension by default."""
        from typer.testing import CliRunner
        from slovo.cli import app

        runner = CliRunner()

        # Change to tmp_path so the file is created there
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["export", "--format", "anki"])

        assert result.exit_code == 0
        assert "vocabulary.txt" in result.stdout

        output_file = tmp_path / "vocabulary.txt"
        assert output_file.exists()


class TestExportEdgeCases:
    """Test edge cases and error handling."""

    def test_export_invalid_format(self, tmp_path, export_words_data):
        """Test that invalid format raises error."""
        from typer.testing import CliRunner
        from slovo.cli import app

        runner = CliRunner()
        output_file = tmp_path / "test.xyz"

        result = runner.invoke(app, ["export", "--output", str(output_file), "--format", "invalid"])

        assert result.exit_code == 1
        assert "Unknown format" in result.stdout

    def test_export_no_matching_words(self, tmp_path, export_words_data):
        """Test export when no words match the filter."""
        from typer.testing import CliRunner
        from slovo.cli import app

        runner = CliRunner()
        output_file = tmp_path / "test_empty.csv"

        result = runner.invoke(app, ["export", "--output", str(output_file), "--format", "csv", "--pos", "ADJ"])

        assert result.exit_code == 0
        assert "No words match that filter" in result.stdout
        assert not output_file.exists()
