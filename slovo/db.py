"""
db.py — MongoDB connection and collection accessors.
"""
import os
from functools import lru_cache

from dotenv import load_dotenv
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.collection import Collection
from pymongo.database import Database

load_dotenv()


@lru_cache(maxsize=1)
def get_client() -> MongoClient:
    uri = os.environ.get("MONGODB_URI")
    if not uri:
        raise RuntimeError("MONGODB_URI not set in environment / .env")
    return MongoClient(uri)


def get_db() -> Database:
    db_name = os.environ.get("MONGODB_DB", "slovo_dnya")
    return get_client()[db_name]


def words_col() -> Collection:
    """
    Schema:
    {
        lemma:          str   — canonical dictionary form (lowercase Cyrillic)
        pos:            str   — NOUN | VERB | ADJ | ADV
        frequency:      int   — total occurrences across corpus
        songs:          [str] — "Artist - Title" labels where word appears
        known:          bool  — user has marked this as known; skipped in WoD
        translation:    str   — auto-fetched or manually set English gloss
        shown_at:       date  — last surfaced as WoD (null = never)
        notes:          str   — personal grammar tips, memory hooks, etc.
        example_lines:  [     — up to MAX_EXAMPLE_LINES lines containing this word
            {
                cyrillic:    str  — original line as it appears in lyrics
                translit:    str  — KMU 2010 romanisation
                translation: str  — English translation of the whole line
                song:        str  — "Artist - Title"
            }
        ]
    }
    """
    col = get_db()["words"]
    col.create_index([("lemma", ASCENDING)], unique=True)
    col.create_index([("known", ASCENDING), ("frequency", DESCENDING)])
    col.create_index([("shown_at", ASCENDING)])
    return col


def songs_col() -> Collection:
    """
    Schema:
    {
        artist:      str
        title:       str
        filepath:    str
        word_count:  int  — unique content words ingested
        line_count:  int  — non-empty lines processed
        ingested_at: date
    }
    """
    col = get_db()["songs"]
    col.create_index([("filepath", ASCENDING)], unique=True)
    return col


def history_col() -> Collection:
    """
    Schema:
    {
        lemma:        str
        translation:  str
        pos:          str
        example_line: {cyrillic, translit, translation, song}
        shown_at:     date
    }
    """
    col = get_db()["history"]
    col.create_index([("shown_at", DESCENDING)])
    return col
