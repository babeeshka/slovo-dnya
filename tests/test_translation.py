"""
Tests for slovo/translation.py — Google Translate API service with fallback.
"""
import os
from unittest.mock import MagicMock, patch

import pytest


class TestTranslationService:
    """Tests for TranslationService class."""

    def test_service_init_with_api_key(self):
        """Service should use API when key is available."""
        with patch.dict(os.environ, {"GOOGLE_TRANSLATE_API_KEY": "test_key"}):
            from slovo.translation import TranslationService

            service = TranslationService()
            assert service.use_api is True
            assert service.api_key == "test_key"
            assert service.client is not None

    def test_service_init_without_api_key(self):
        """Service should fall back to deep-translator when no API key."""
        with patch.dict(os.environ, {"GOOGLE_TRANSLATE_API_KEY": ""}, clear=False):
            from slovo.translation import TranslationService

            service = TranslationService()
            assert service.use_api is False
            assert service.client is None
            assert service.fallback_translator is not None

    def test_detect_part_of_speech_verb(self):
        """Should detect verbs from -ти ending."""
        from slovo.translation import TranslationService

        service = TranslationService()
        result = service._detect_part_of_speech("говорити")
        assert result.get("part_of_speech") == "verb"

        result = service._detect_part_of_speech("бачити")
        assert result.get("part_of_speech") == "verb"

    def test_detect_part_of_speech_adjective(self):
        """Should detect adjectives from -ий/-ій endings."""
        from slovo.translation import TranslationService

        service = TranslationService()
        result = service._detect_part_of_speech("гарний")
        assert result.get("part_of_speech") == "adjective"

        result = service._detect_part_of_speech("синій")
        assert result.get("part_of_speech") == "adjective"

    def test_detect_part_of_speech_adverb(self):
        """Should detect adverbs from -но/-ко endings."""
        from slovo.translation import TranslationService

        service = TranslationService()
        result = service._detect_part_of_speech("добре")
        # 'добре' doesn't end in -но/-ко
        assert result.get("part_of_speech") is None

        result = service._detect_part_of_speech("швидко")
        assert result.get("part_of_speech") == "adverb"

    def test_detect_part_of_speech_skips_phrases(self):
        """Should not detect POS for multi-word phrases."""
        from slovo.translation import TranslationService

        service = TranslationService()
        result = service._detect_part_of_speech("добрий день")
        assert result == {}

    def test_detect_formality_formal(self):
        """Should detect formal pronouns."""
        from slovo.translation import TranslationService

        service = TranslationService()
        result = service._detect_formality("Як ви поживаєте")
        assert result.get("formality") == "formal"

    def test_detect_formality_informal(self):
        """Should detect informal pronouns."""
        from slovo.translation import TranslationService

        service = TranslationService()
        result = service._detect_formality("Як ти себе почуваєш")
        assert result.get("formality") == "informal"

    def test_detect_formality_neutral(self):
        """Should return empty dict for neutral text."""
        from slovo.translation import TranslationService

        service = TranslationService()
        result = service._detect_formality("Погода сьогодні гарна")
        assert result == {}

    def test_translate_empty_text_raises(self):
        """Should raise ValueError for empty text."""
        from slovo.translation import TranslationService

        service = TranslationService()
        with pytest.raises(ValueError, match="cannot be empty"):
            service.translate("")

        with pytest.raises(ValueError, match="cannot be empty"):
            service.translate("   ")

    def test_translate_batch_empty_list(self):
        """Should return empty list for empty input."""
        from slovo.translation import TranslationService

        service = TranslationService()
        result = service.translate_batch([])
        assert result == []


class TestTranslationWithMockedAPI:
    """Tests that mock the external API calls."""

    def test_translate_with_api_success(self):
        """Should use Google API when key is available."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": {
                "translations": [
                    {
                        "translatedText": "hello",
                        "detectedSourceLanguage": "uk",
                    }
                ]
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch.dict(os.environ, {"GOOGLE_TRANSLATE_API_KEY": "test_key"}):
            with patch("httpx.Client") as MockClient:
                mock_client = MagicMock()
                mock_client.get.return_value = mock_response
                MockClient.return_value = mock_client

                from slovo.translation import TranslationService

                service = TranslationService()
                result = service.translate("привіт")

                assert result["translation"] == "hello"
                assert result["provider"] == "google_api"
                assert result["detected_language"] == "uk"

    def test_translate_fallback_when_no_api_key(self):
        """Should use deep-translator when no API key."""
        with patch.dict(os.environ, {"GOOGLE_TRANSLATE_API_KEY": ""}):
            with patch("deep_translator.GoogleTranslator.translate", return_value="hello"):
                from slovo.translation import TranslationService

                service = TranslationService()
                result = service.translate("привіт")

                assert result["translation"] == "hello"
                assert result["provider"] == "deep_translator"

    def test_translate_batch_with_errors(self):
        """Should include error info for failed translations in batch."""
        with patch.dict(os.environ, {"GOOGLE_TRANSLATE_API_KEY": ""}):
            with patch(
                "deep_translator.GoogleTranslator.translate",
                side_effect=[RuntimeError("API error"), "world"],
            ):
                from slovo.translation import TranslationService

                service = TranslationService()
                results = service.translate_batch(["привіт", "світ"])

                # First should have error
                assert "error" in results[0]
                # Second should succeed
                assert results[1]["translation"] == "world"


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def test_translate_function(self):
        """Should use singleton service."""
        with patch.dict(os.environ, {"GOOGLE_TRANSLATE_API_KEY": ""}):
            with patch("deep_translator.GoogleTranslator.translate", return_value="hello"):
                from slovo import translation

                # Clear singleton
                translation._service = None

                result = translation.translate("привіт")
                assert result["translation"] == "hello"

    def test_translate_batch_function(self):
        """Should use singleton service for batch."""
        with patch.dict(os.environ, {"GOOGLE_TRANSLATE_API_KEY": ""}):
            with patch(
                "deep_translator.GoogleTranslator.translate",
                side_effect=["hello", "world"],
            ):
                from slovo import translation

                # Clear singleton
                translation._service = None

                results = translation.translate_batch(["привіт", "світ"])
                assert len(results) == 2
                assert results[0]["translation"] == "hello"
                assert results[1]["translation"] == "world"
