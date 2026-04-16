"""
wod.py — Word-of-the-day selection, translation, example line picking, history.
"""
import random
from datetime import datetime, timezone, timedelta
from typing import Optional

from deep_translator import GoogleTranslator
from rich.console import Console

from slovo.db import words_col, history_col

console = Console()

COOLDOWN_DAYS = 30
_translator = GoogleTranslator(source="uk", target="en")


# ── Translation helpers ───────────────────────────────────────────────────────

def _fetch_translation(lemma: str) -> str:
    try:
        result = _translator.translate(lemma)
        return result.strip() if result else ""
    except Exception as e:
        console.print(f"[dim]Translation lookup failed ({e})[/dim]")
        return ""


def get_or_translate(word_doc: dict) -> str:
    """Return stored translation or auto-fetch + persist."""
    if word_doc.get("translation"):
        return word_doc["translation"]
    translation = _fetch_translation(word_doc["lemma"])
    if translation:
        words_col().update_one(
            {"_id": word_doc["_id"]},
            {"$set": {"translation": translation}},
        )
    return translation or "(translation unavailable)"


def _ensure_line_translation(line: dict) -> dict:
    """
    If an example line is missing its translation, fetch it now and persist it.
    Returns the (possibly updated) line dict.
    """
    if line.get("translation"):
        return line
    try:
        result = _translator.translate(line["cyrillic"])
        translation = result.strip() if result else ""
    except Exception:
        translation = ""

    if translation:
        # Patch the specific line inside the array in MongoDB
        words_col().update_one(
            {"example_lines.cyrillic": line["cyrillic"]},
            {"$set": {"example_lines.$.translation": translation}},
        )
        line = {**line, "translation": translation}
    return line


# ── Word selection ────────────────────────────────────────────────────────────

def pick_word(
    min_frequency: int = 1,
    pos_filter: Optional[str] = None,
    artist_filter: Optional[str] = None,
) -> Optional[dict]:
    """
    Select the best WoD candidate.

    Priority:
      1. Not marked known.
      2. Not shown within COOLDOWN_DAYS.
      3. Optionally restricted to words from a specific artist substring.
      4. Highest frequency first (most useful vocabulary surfaces first).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=COOLDOWN_DAYS)
    query: dict = {
        "known": False,
        "frequency": {"$gte": min_frequency},
        "$or": [
            {"shown_at": None},
            {"shown_at": {"$lt": cutoff}},
        ],
    }
    if pos_filter:
        query["pos"] = pos_filter.upper()
    if artist_filter:
        # Filter to words that appear in at least one song by this artist
        query["songs"] = {"$regex": artist_filter, "$options": "i"}

    return words_col().find_one(query, sort=[("frequency", -1)])


def pick_example_line(word_doc: dict) -> Optional[dict]:
    """
    Pick an example lyric line for the WoD. Prefers lines with a translation;
    falls back to the first available line. Returns None if no lines stored.
    """
    lines: list[dict] = word_doc.get("example_lines", [])
    if not lines:
        return None

    # Prefer lines that already have a translation
    translated = [l for l in lines if l.get("translation")]
    chosen = random.choice(translated) if translated else lines[0]

    # Make sure the chosen line has a translation (lazy-fetch if needed)
    return _ensure_line_translation(chosen)


# ── State mutations ───────────────────────────────────────────────────────────

def record_shown(word_doc: dict, translation: str, example_line: Optional[dict]) -> None:
    now = datetime.now(timezone.utc)
    words_col().update_one({"_id": word_doc["_id"]}, {"$set": {"shown_at": now}})
    history_col().insert_one({
        "lemma": word_doc["lemma"],
        "pos": word_doc.get("pos", ""),
        "translation": translation,
        "example_line": example_line,
        "shown_at": now,
    })


def mark_known(lemma: str) -> bool:
    result = words_col().update_one(
        {"lemma": lemma.lower()},
        {"$set": {"known": True}},
    )
    return result.matched_count > 0


def set_translation(lemma: str, translation: str) -> bool:
    result = words_col().update_one(
        {"lemma": lemma.lower()},
        {"$set": {"translation": translation}},
    )
    return result.matched_count > 0


def set_note(lemma: str, note: str) -> bool:
    result = words_col().update_one(
        {"lemma": lemma.lower()},
        {"$set": {"notes": note}},
    )
    return result.matched_count > 0


# ── Stats / history ───────────────────────────────────────────────────────────

def get_stats() -> dict:
    wcol = words_col()
    total = wcol.count_documents({})
    known = wcol.count_documents({"known": True})
    seen = wcol.count_documents({"shown_at": {"$ne": None}, "known": False})
    untouched = wcol.count_documents({"shown_at": None, "known": False})
    pos_breakdown = list(wcol.aggregate([
        {"$group": {"_id": "$pos", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]))
    top_words = list(
        wcol.find(
            {"known": False},
            {"_id": 0, "lemma": 1, "pos": 1, "frequency": 1, "translation": 1},
        )
        .sort("frequency", -1)
        .limit(10)
    )
    return {
        "total": total,
        "known": known,
        "seen_not_known": seen,
        "untouched": untouched,
        "pos_breakdown": pos_breakdown,
        "top_unknown": top_words,
    }


def get_history(limit: int = 10) -> list[dict]:
    return list(history_col().find({}, {"_id": 0}).sort("shown_at", -1).limit(limit))
