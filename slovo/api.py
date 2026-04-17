"""
api.py -- FastAPI REST endpoints for slovo-dnya.

Run with: uvicorn slovo.api:app --reload

Endpoints:
    GET  /                  Health check
    GET  /words             List words (with filters)
    GET  /words/{lemma}     Get single word detail
    POST /words/{lemma}/known       Mark word as known
    POST /words/{lemma}/translation Set custom translation
    POST /words/{lemma}/note        Add note to word
    GET  /wod               Get word of the day
    POST /wod               Pick and record word of the day
    GET  /stats             Corpus statistics
    GET  /history           WoD history
    GET  /songs             List ingested songs
    POST /translate         Translate Ukrainian text
    GET  /genius/search     Search Genius for songs
    GET  /genius/song/{id}  Get song with lyrics from Genius
    GET  /export            Export vocabulary as JSON
"""
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from slovo.db import songs_col, words_col
from slovo.wod import (
    get_history,
    get_or_translate,
    get_stats,
    mark_known,
    pick_example_line,
    pick_word,
    record_shown,
    set_note,
    set_translation,
)

app = FastAPI(
    title="Slovo Dnya API",
    description="Ukrainian word-of-the-day engine powered by music lyrics",
    version="0.2.0",
)


# --- Pydantic models for request/response ---

class ExampleLine(BaseModel):
    cyrillic: str
    translit: str
    translation: str
    song: str


class WordResponse(BaseModel):
    lemma: str
    pos: Optional[str] = None
    frequency: int = 0
    songs: list[str] = Field(default_factory=list)
    known: bool = False
    translation: Optional[str] = None
    shown_at: Optional[datetime] = None
    notes: str = ""
    example_lines: list[ExampleLine] = Field(default_factory=list)


class WordListItem(BaseModel):
    lemma: str
    pos: Optional[str] = None
    frequency: int = 0
    known: bool = False
    translation: Optional[str] = None


class WodResponse(BaseModel):
    lemma: str
    translation: str
    pos: Optional[str] = None
    frequency: int = 0
    songs: list[str] = Field(default_factory=list)
    example_line: Optional[ExampleLine] = None


class StatsResponse(BaseModel):
    total: int
    known: int
    seen_not_known: int
    untouched: int
    pos_breakdown: list[dict]
    top_unknown: list[dict]


class HistoryEntry(BaseModel):
    lemma: str
    pos: Optional[str] = None
    translation: Optional[str] = None
    example_line: Optional[ExampleLine] = None
    shown_at: Optional[datetime] = None


class SongResponse(BaseModel):
    artist: str
    title: str
    filepath: str
    word_count: int = 0
    line_count: int = 0
    ingested_at: Optional[datetime] = None


class TranslationRequest(BaseModel):
    translation: str


class NoteRequest(BaseModel):
    note: str


class MessageResponse(BaseModel):
    message: str
    lemma: str


class TranslateRequest(BaseModel):
    text: str
    source: str = "uk"
    target: str = "en"


class TranslateResponse(BaseModel):
    translation: str
    provider: str
    detected_language: Optional[str] = None
    part_of_speech: Optional[str] = None
    formality: Optional[str] = None
    fallback_reason: Optional[str] = None


class GeniusSongResult(BaseModel):
    id: int
    title: str
    artist: str
    url: str


class GeniusSongDetail(BaseModel):
    id: int
    title: str
    artist: str
    url: str
    lyrics: str
    release_date: str


class ExportResponse(BaseModel):
    words: list[dict]
    count: int


# --- Endpoints ---

@app.get("/")
def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "slovo-dnya"}


@app.get("/words", response_model=list[WordListItem])
def list_words(
    pos: Optional[str] = Query(None, description="Filter by part of speech: NOUN, VERB, ADJ, ADV"),
    unknown_only: bool = Query(False, description="Only return words not marked as known"),
    artist: Optional[str] = Query(None, description="Filter to words from songs by this artist"),
    min_freq: int = Query(1, description="Minimum frequency threshold"),
    limit: int = Query(50, ge=1, le=500, description="Max results to return"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
):
    """List words from the corpus with optional filters."""
    query: dict = {"frequency": {"$gte": min_freq}}
    if pos:
        query["pos"] = pos.upper()
    if unknown_only:
        query["known"] = False
    if artist:
        query["songs"] = {"$regex": artist, "$options": "i"}

    cursor = (
        words_col()
        .find(query, {"lemma": 1, "pos": 1, "frequency": 1, "known": 1, "translation": 1})
        .sort("frequency", -1)
        .skip(offset)
        .limit(limit)
    )
    return [WordListItem(**doc) for doc in cursor]


@app.get("/words/{lemma}", response_model=WordResponse)
def get_word(lemma: str):
    """Get full details for a specific word."""
    doc = words_col().find_one({"lemma": lemma.lower()})
    if not doc:
        raise HTTPException(status_code=404, detail=f"Word not found: {lemma}")
    return WordResponse(**doc)


@app.post("/words/{lemma}/known", response_model=MessageResponse)
def api_mark_known(lemma: str):
    """Mark a word as known so it won't appear as word of the day."""
    if mark_known(lemma):
        return MessageResponse(message="Word marked as known", lemma=lemma)
    raise HTTPException(status_code=404, detail=f"Word not found: {lemma}")


@app.post("/words/{lemma}/translation", response_model=MessageResponse)
def api_set_translation(lemma: str, body: TranslationRequest):
    """Set a custom translation for a word."""
    if set_translation(lemma, body.translation):
        return MessageResponse(message="Translation updated", lemma=lemma)
    raise HTTPException(status_code=404, detail=f"Word not found: {lemma}")


@app.post("/words/{lemma}/note", response_model=MessageResponse)
def api_set_note(lemma: str, body: NoteRequest):
    """Add a note to a word (grammar tips, memory hooks, etc.)."""
    if set_note(lemma, body.note):
        return MessageResponse(message="Note saved", lemma=lemma)
    raise HTTPException(status_code=404, detail=f"Word not found: {lemma}")


@app.get("/wod", response_model=Optional[WodResponse])
def get_wod_preview(
    pos: Optional[str] = Query(None, description="Filter by POS"),
    min_freq: int = Query(1, description="Minimum frequency"),
    artist: Optional[str] = Query(None, description="Filter by artist"),
):
    """
    Preview the next word of the day without marking it as seen.

    This is a read-only endpoint. Use POST /wod to actually pick and record.
    """
    word = pick_word(min_frequency=min_freq, pos_filter=pos, artist_filter=artist)
    if not word:
        return None

    translation = get_or_translate(word)
    example_line = pick_example_line(word)

    return WodResponse(
        lemma=word["lemma"],
        translation=translation,
        pos=word.get("pos"),
        frequency=word.get("frequency", 0),
        songs=word.get("songs", []),
        example_line=ExampleLine(**example_line) if example_line else None,
    )


@app.post("/wod", response_model=Optional[WodResponse])
def pick_and_record_wod(
    pos: Optional[str] = Query(None, description="Filter by POS"),
    min_freq: int = Query(1, description="Minimum frequency"),
    artist: Optional[str] = Query(None, description="Filter by artist"),
):
    """
    Pick the word of the day, record it in history, and return it.

    This marks the word as seen and adds it to history.
    """
    word = pick_word(min_frequency=min_freq, pos_filter=pos, artist_filter=artist)
    if not word:
        return None

    translation = get_or_translate(word)
    example_line = pick_example_line(word)

    record_shown(word, translation, example_line)

    return WodResponse(
        lemma=word["lemma"],
        translation=translation,
        pos=word.get("pos"),
        frequency=word.get("frequency", 0),
        songs=word.get("songs", []),
        example_line=ExampleLine(**example_line) if example_line else None,
    )


@app.get("/stats", response_model=StatsResponse)
def api_stats():
    """Get corpus statistics."""
    return StatsResponse(**get_stats())


@app.get("/history", response_model=list[HistoryEntry])
def api_history(limit: int = Query(10, ge=1, le=100)):
    """Get recent word-of-the-day history."""
    entries = get_history(limit=limit)
    return [HistoryEntry(**e) for e in entries]


@app.get("/songs", response_model=list[SongResponse])
def list_songs(
    artist: Optional[str] = Query(None, description="Filter by artist name"),
    limit: int = Query(50, ge=1, le=200),
):
    """List ingested songs."""
    query: dict = {}
    if artist:
        query["artist"] = {"$regex": artist, "$options": "i"}

    cursor = songs_col().find(query).sort("ingested_at", -1).limit(limit)
    return [SongResponse(**doc) for doc in cursor]


# --- Translation endpoints ---

@app.post("/translate", response_model=TranslateResponse)
def api_translate(body: TranslateRequest):
    """Translate text using Google Translate API with fallback to deep-translator."""
    from slovo.translation import translate

    try:
        result = translate(body.text, source=body.source, target=body.target)
        return TranslateResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


# --- Genius endpoints ---

@app.get("/genius/search", response_model=list[GeniusSongResult])
def genius_search(
    q: str = Query(..., description="Search query"),
    limit: int = Query(10, ge=1, le=50, description="Max results"),
):
    """Search Genius for songs."""
    from slovo.genius import GeniusService

    try:
        service = GeniusService()
        songs = service.search_songs(q, max_results=limit)
        return [GeniusSongResult(**song) for song in songs]
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Genius API error: {e}")


@app.get("/genius/song/{song_id}", response_model=GeniusSongDetail)
def genius_song(song_id: int):
    """Get song details and lyrics from Genius."""
    from slovo.genius import GeniusService

    try:
        service = GeniusService()
        song = service.get_song(song_id)
        return GeniusSongDetail(**song)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Genius API error: {e}")


# --- Export endpoint ---

@app.get("/export", response_model=ExportResponse)
def api_export(
    pos: Optional[str] = Query(None, description="Filter by POS"),
    unknown_only: bool = Query(False, description="Only unknown words"),
):
    """Export vocabulary as JSON."""
    query: dict = {}
    if pos:
        query["pos"] = pos.upper()
    if unknown_only:
        query["known"] = False

    cursor = (
        words_col()
        .find(query, {"_id": 0, "lemma": 1, "pos": 1, "frequency": 1, "translation": 1, "known": 1, "notes": 1})
        .sort("frequency", -1)
    )
    words = list(cursor)
    return ExportResponse(words=words, count=len(words))
