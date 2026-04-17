"""
translation.py — Google Translate API service with deep-translator fallback.

Primary: Google Translate API v2 via httpx
Fallback: deep-translator GoogleTranslator when API unavailable or fails

Returns rich metadata including provider, part-of-speech detection, and formality.
"""
import os
from functools import lru_cache
from typing import Optional

import httpx
from deep_translator import GoogleTranslator
from dotenv import load_dotenv

load_dotenv()


class TranslationService:
    """
    Translation service with Google Translate API primary and deep-translator fallback.

    Features:
    - Google Translate API v2 as primary provider
    - deep-translator as fallback when API key not available
    - LRU cache for performance
    - Ukrainian part-of-speech detection from word endings
    - Formality detection from pronouns
    """

    def __init__(self):
        self.api_key = os.getenv("GOOGLE_TRANSLATE_API_KEY")
        self.use_api = bool(self.api_key)
        self.client = httpx.Client(timeout=10.0) if self.use_api else None
        self.fallback_translator = GoogleTranslator(source="uk", target="en")

    @lru_cache(maxsize=1000)
    def _cached_translate_api(self, text: str, source: str, target: str) -> dict:
        """Cached Google Translate API call."""
        url = "https://translation.googleapis.com/language/translate/v2"
        params = {
            "key": self.api_key,
            "q": text,
            "source": source,
            "target": target,
            "format": "text",
        }

        response = self.client.get(url, params=params)
        response.raise_for_status()

        data = response.json()
        translations = data.get("data", {}).get("translations", [])
        if not translations:
            raise ValueError(f"Google Translate API returned no translations for: {text}")

        first = translations[0]
        translation_text = first.get("translatedText", "")
        detected_lang = first.get("detectedSourceLanguage", source)

        return {
            "translation": translation_text,
            "detected_language": detected_lang,
            "provider": "google_api",
        }

    def _translate_api(self, text: str, source: str, target: str) -> dict:
        """Translate using Google Translate API v2."""
        if not self.api_key:
            raise RuntimeError(
                "GOOGLE_TRANSLATE_API_KEY not set in environment. "
                "Obtain a key from Google Cloud Console and add to .env"
            )

        try:
            result = self._cached_translate_api(text, source, target)

            # Add linguistic analysis
            result.update(self._detect_part_of_speech(text))
            result.update(self._detect_formality(text))

            return result

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 400:
                raise ValueError(f"Invalid translation request: {e.response.text}")
            elif e.response.status_code == 403:
                raise RuntimeError(
                    "Google Translate API key invalid or quota exceeded. "
                    f"Check your API key and billing settings. Details: {e.response.text}"
                )
            else:
                raise RuntimeError(f"Google Translate API HTTP error {e.response.status_code}: {e.response.text}")

        except httpx.RequestError as e:
            raise RuntimeError(f"Google Translate API network error: {e}")

    def _translate_fallback(self, text: str, source: str, target: str) -> dict:
        """Translate using deep-translator as fallback."""
        try:
            # deep-translator uses different source/target codes
            self.fallback_translator.source = source
            self.fallback_translator.target = target

            translation_text = self.fallback_translator.translate(text)

            if not translation_text:
                raise ValueError(f"deep-translator returned empty translation for: {text}")

            result = {
                "translation": translation_text,
                "detected_language": source,
                "provider": "deep_translator",
            }

            # Add linguistic analysis
            result.update(self._detect_part_of_speech(text))
            result.update(self._detect_formality(text))

            return result

        except Exception as e:
            raise RuntimeError(f"deep-translator fallback error: {e}")

    def _detect_part_of_speech(self, text: str) -> dict:
        """
        Detect part-of-speech from Ukrainian word endings.

        Ukrainian verb infinitives typically end in: -ти, -ать, -ять, -ить, -сти
        Adjectives: -ий, -ій, -а, -е, -і (with context)
        Adverbs: -но, -ко

        Returns dict with optional part_of_speech key.
        """
        word = text.strip().lower()

        # Skip multi-word phrases
        if " " in word:
            return {}

        # Verb endings (infinitives and conjugated forms)
        verb_endings = ["ти", "ать", "ять", "ить", "еть", "оть", "сти", "сь"]
        if any(word.endswith(ending) for ending in verb_endings):
            return {"part_of_speech": "verb"}

        # Adjective endings (masculine nominative)
        adj_endings = ["ий", "ій", "ой"]
        if any(word.endswith(ending) for ending in adj_endings):
            return {"part_of_speech": "adjective"}

        # Adverb endings
        adv_endings = ["но", "ко"]
        if len(word) > 3 and any(word.endswith(ending) for ending in adv_endings):
            # Avoid false positives from short words
            return {"part_of_speech": "adverb"}

        # No clear indicator
        return {}

    def _detect_formality(self, text: str) -> dict:
        """
        Detect formality from Ukrainian pronouns.

        Formal: ви, вас, ваш, вами, вам
        Informal: ти, твій, тебе, тобі, тобою

        Returns dict with optional formality key.
        """
        text_lower = text.lower()

        formal_pronouns = ["ви", "вас", "ваш", "вами", "вам"]
        informal_pronouns = ["ти", "твій", "тебе", "тобі", "тобою"]

        # Check for word boundaries to avoid substring matches
        words = text_lower.split()

        if any(pronoun in words for pronoun in formal_pronouns):
            return {"formality": "formal"}
        elif any(pronoun in words for pronoun in informal_pronouns):
            return {"formality": "informal"}

        return {}

    def translate(self, text: str, source: str = "uk", target: str = "en") -> dict:
        """
        Translate text from source to target language.

        Args:
            text: Text to translate
            source: Source language code (default: uk for Ukrainian)
            target: Target language code (default: en for English)

        Returns:
            dict with keys:
                - translation: str — translated text
                - provider: str — google_api | deep_translator
                - detected_language: str — detected source language
                - part_of_speech: str (optional) — verb | adjective | adverb
                - formality: str (optional) — formal | informal

        Raises:
            RuntimeError: On translation failure with specific error details
        """
        if not text or not text.strip():
            raise ValueError("Translation text cannot be empty")

        # Try Google Translate API first if key is available
        if self.use_api:
            try:
                return self._translate_api(text, source, target)
            except Exception as api_error:
                # Fall back to deep-translator
                try:
                    result = self._translate_fallback(text, source, target)
                    # Note the fallback in the result
                    result["fallback_reason"] = str(api_error)
                    return result
                except Exception as fallback_error:
                    raise RuntimeError(
                        f"Translation failed with both providers. "
                        f"API error: {api_error}. Fallback error: {fallback_error}"
                    )
        else:
            # No API key, use deep-translator directly
            return self._translate_fallback(text, source, target)

    def translate_batch(self, texts: list[str], source: str = "uk", target: str = "en") -> list[dict]:
        """
        Translate multiple texts efficiently.

        Args:
            texts: List of texts to translate
            source: Source language code
            target: Target language code

        Returns:
            list of translation result dicts (same format as translate())
        """
        if not texts:
            return []

        results = []
        for text in texts:
            try:
                result = self.translate(text, source, target)
                results.append(result)
            except Exception as e:
                # Include partial results with error information
                results.append({
                    "translation": "",
                    "provider": "none",
                    "error": str(e),
                    "original_text": text,
                })

        return results

    def __del__(self):
        """Clean up HTTP client on shutdown."""
        if self.client is not None:
            try:
                self.client.close()
            except Exception:
                pass


# Singleton instance for easy import
_service: Optional[TranslationService] = None


def get_service() -> TranslationService:
    """Get or create singleton TranslationService instance."""
    global _service
    if _service is None:
        _service = TranslationService()
    return _service


def translate(text: str, source: str = "uk", target: str = "en") -> dict:
    """
    Convenience function for quick translation.

    Uses singleton service instance with caching.
    """
    return get_service().translate(text, source, target)


def translate_batch(texts: list[str], source: str = "uk", target: str = "en") -> list[dict]:
    """Convenience function for batch translation."""
    return get_service().translate_batch(texts, source, target)
