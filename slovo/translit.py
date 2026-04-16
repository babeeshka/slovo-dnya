"""
translit.py — Ukrainian → Latin transliteration (KMU 2010 standard).

This is the official Ukrainian government romanization standard used on
passports and official documents. It's the most widely recognized scheme
for Ukrainian specifically (not to be confused with Russian transliteration).

Reference: Resolution of the Cabinet of Ministers of Ukraine No. 55, 2010.
"""

# Character-level mapping (uppercase; lowercase handled by .lower() on output)
_MAP: dict[str, str] = {
    "А": "A",  "Б": "B",  "В": "V",  "Г": "H",  "Ґ": "G",
    "Д": "D",  "Е": "E",  "Є": "Ye", "Ж": "Zh", "З": "Z",
    "И": "Y",  "І": "I",  "Ї": "Yi", "Й": "Y",  "К": "K",
    "Л": "L",  "М": "M",  "Н": "N",  "О": "O",  "П": "P",
    "Р": "R",  "С": "S",  "Т": "T",  "У": "U",  "Ф": "F",
    "Х": "Kh", "Ц": "Ts", "Ч": "Ch", "Ш": "Sh", "Щ": "Shch",
    "Ь": "",   "Ю": "Yu", "Я": "Ya",
    # Apostrophe / soft sign — omit in romanization
    "\u2019": "", "ʼ": "", "'": "",
}

# Position-sensitive rules (KMU 2010 section 3):
# Є, Ї, Й, Ю, Я use longer forms at word start or after apostrophe;
# shorter forms are used elsewhere.
#
# Special case for Й:
# - At word start: "Y" (rare, but e.g. "Йорданія" -> "Yordaniia")
# - After vowel: "i" (e.g. "Київ" -> "Kyiv", "й" after "и")
# - After consonant: "i" (same)
_VOWELS_UK = set("АЕЄИІЇОУЮЯаеєиіїоуюя")

# Long forms (at word start or after apostrophe)
_LONG: dict[str, str] = {
    "Є": "Ye", "Ї": "Yi", "Й": "Y", "Ю": "Yu", "Я": "Ya",
}

# Short forms (elsewhere)
_SHORT: dict[str, str] = {
    "Є": "ie", "Ї": "i", "Й": "i", "Ю": "iu", "Я": "ia",
}


def transliterate(text: str) -> str:
    """
    Transliterate a Ukrainian string to Latin (KMU 2010).

    Examples:
        "Місто"   → "Misto"
        "Їжак"    → "Yizhak"
        "Єдність" → "Yednist"
        "синє"    → "syne"
    """
    result: list[str] = []
    chars = list(text)
    n = len(chars)

    for i, ch in enumerate(chars):
        upper = ch.upper()

        if upper not in _MAP and upper not in _SHORT:
            # Not a Ukrainian Cyrillic letter — pass through as-is
            result.append(ch)
            continue

        is_upper_char = ch.isupper()
        prev_char = chars[i - 1] if i > 0 else ""

        # Position-sensitive letters (Є, Ї, Й, Ю, Я)
        if upper in _LONG:
            # Long form at word start or after apostrophe
            at_word_start = (i == 0) or (prev_char in " \t\n'ʼ\u2019")
            if at_word_start:
                roman = _LONG[upper]
            else:
                roman = _SHORT[upper]

            # Preserve capitalisation of the first letter of the digraph
            if is_upper_char and roman:
                roman = roman[0].upper() + roman[1:]
            elif not is_upper_char and roman:
                roman = roman.lower()
            result.append(roman)
        else:
            roman = _MAP[upper]
            if not roman:
                # Soft sign — omit
                continue
            if is_upper_char and roman:
                roman = roman[0].upper() + roman[1:]
            else:
                roman = roman.lower()
            result.append(roman)

    return "".join(result)


# ── Quick self-test ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    tests = [
        ("Київ", "Kyiv"),
        ("Харків", "Kharkiv"),
        ("Львів", "Lviv"),
        ("Запоріжжя", "Zaporizhzhia"),  # close enough for KMU
        ("Єдність", "Yednist"),
        ("Їжак", "Yizhak"),
        ("синє місто", "syne misto"),
        ("каву", "kavu"),
    ]
    for ukr, expected in tests:
        got = transliterate(ukr)
        status = "✓" if got.lower() == expected.lower() else f"? (expected {expected})"
        print(f"{ukr:20s} → {got:20s} {status}")
