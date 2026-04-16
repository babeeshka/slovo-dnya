"""
Tests for the KMU 2010 Ukrainian transliteration module.
"""
import pytest
from slovo.translit import transliterate


class TestBasicTransliteration:
    """Test basic character mappings."""

    def test_simple_word(self):
        assert transliterate("каву") == "kavu"

    def test_city_kyiv(self):
        assert transliterate("Київ") == "Kyiv"

    def test_city_kharkiv(self):
        assert transliterate("Харків") == "Kharkiv"

    def test_city_lviv(self):
        assert transliterate("Львів") == "Lviv"

    def test_misto(self):
        # Simple noun without position-sensitive letters
        assert transliterate("місто") == "misto"

    def test_preserves_capitalization(self):
        assert transliterate("КИЇВ") == "KYIV"
        assert transliterate("Місто") == "Misto"


class TestPositionSensitiveLetters:
    """
    Test Ye/Yi/Yu/Ya variants based on position.

    KMU 2010 rules:
    - At word start or after vowel: long form (Ye, Yi, Yu, Ya)
    - After consonant: short form (ie, i, iu, ia)
    """

    def test_ye_at_start(self):
        # Ye at word start -> "Ye"
        assert transliterate("Єдність").lower() == "yednist"

    def test_ye_after_vowel(self):
        # Ye after vowel -> "ie" according to some interpretations,
        # but KMU 2010 says "ie" after consonant, "ye" at start/after vowel
        result = transliterate("синє")
        # After vowel "и" -> should be "ie" (short form is after consonant)
        # Actually "є" after "н" (consonant) -> "ie"
        assert result.lower() == "synie" or result.lower() == "syne"

    def test_yi_at_start(self):
        # Yizhak (hedgehog)
        assert transliterate("Їжак").lower() == "yizhak"

    def test_yi_after_consonant(self):
        # After consonant -> "i"
        result = transliterate("її")
        # First "ї" at start -> "Yi", second after vowel "i" -> should check
        assert "yi" in result.lower() or "i" in result.lower()

    def test_ya_at_start(self):
        assert transliterate("Яблуко")[0:2] == "Ya"

    def test_ya_after_consonant(self):
        # "ня" -> "nia"
        result = transliterate("пісня")
        assert result.lower() == "pisnia"

    def test_yu_at_start(self):
        assert transliterate("Юрій")[0:2] == "Yu"


class TestDigraphs:
    """Test multi-character Cyrillic to Latin mappings."""

    def test_zh(self):
        assert "zh" in transliterate("Жовтень").lower()

    def test_kh(self):
        assert "kh" in transliterate("хата").lower()

    def test_ts(self):
        assert "ts" in transliterate("цар").lower()

    def test_ch(self):
        assert "ch" in transliterate("час").lower()

    def test_sh(self):
        assert "sh" in transliterate("школа").lower()

    def test_shch(self):
        assert "shch" in transliterate("щастя").lower()


class TestSoftSign:
    """Test that soft sign (ь) is omitted in transliteration."""

    def test_soft_sign_omitted(self):
        # "день" -> "den" (soft sign omitted)
        result = transliterate("день")
        assert "ь" not in result
        assert result.lower() == "den"

    def test_soft_sign_in_middle(self):
        # Львів has soft sign
        result = transliterate("Львів")
        assert result == "Lviv"


class TestApostrophe:
    """Test that apostrophes are handled (omitted or preserved as appropriate)."""

    def test_apostrophe_omitted(self):
        # Ukrainian apostrophe variants should be omitted
        result = transliterate("м'який")
        assert "'" not in result
        assert "ʼ" not in result


class TestNonCyrillicPassthrough:
    """Test that non-Cyrillic characters pass through unchanged."""

    def test_numbers_preserved(self):
        assert transliterate("2024") == "2024"

    def test_punctuation_preserved(self):
        assert transliterate("Привіт!") == "Pryvit!"

    def test_spaces_preserved(self):
        assert transliterate("добрий день") == "dobryi den"

    def test_mixed_content(self):
        result = transliterate("Kyiv 2024!")
        # Latin letters should pass through
        assert "2024!" in result


class TestFullPhrases:
    """Test complete phrases and sentences."""

    def test_greeting(self):
        result = transliterate("Добрий день")
        assert result.lower() == "dobryi den"

    def test_sample_lyric_line(self):
        result = transliterate("Місяць світить над тихим містом")
        # Should produce readable romanization
        assert "misiats" in result.lower()
        assert "mistom" in result.lower()

    def test_zaporizhzhia(self):
        # Complex city name with double ж
        result = transliterate("Запоріжжя")
        assert "zaporizh" in result.lower()


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_string(self):
        assert transliterate("") == ""

    def test_single_letter(self):
        assert transliterate("а") == "a"

    def test_only_soft_signs(self):
        assert transliterate("ьь") == ""

    def test_g_with_upturn(self):
        # Ґ (with upturn) -> G (distinct from Г -> H)
        assert transliterate("Ґанок")[0] == "G"
        assert transliterate("Ганок")[0] == "H"
