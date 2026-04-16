"""
ingest.py — Parse lyrics .txt files, run stanza NLP, upsert word corpus.

Lyrics file format:
    # Artist: BoomBox
    # Title: Врятуй

    Рядок першого куплету...
    ...

Lines beginning with # are metadata/section markers and are skipped.
Everything else is treated as lyric text and processed line by line.
"""
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import stanza
from deep_translator import GoogleTranslator
from rich.console import Console
from rich.progress import track

from slovo.db import words_col, songs_col
from slovo.translit import transliterate

console = Console()

CONTENT_POS = {"NOUN", "VERB", "ADJ", "ADV"}

STOP_LEMMAS = {
    "і", "й", "та", "або", "але", "як", "що", "це", "він", "вона",
    "воно", "вони", "ми", "ви", "я", "ти", "не", "ні", "так", "вже",
    "ще", "від", "до", "на", "в", "у", "з", "за", "по", "про",
    "при", "для", "через", "над", "під", "між", "без", "де", "там",
    "тут", "коли", "чому", "хто", "що", "цей", "той", "свій", "мій",
    "твій", "весь", "бути", "мати", "його", "її", "їх", "нас", "вас",
}

# Max example lyric lines stored per word across the whole corpus
MAX_EXAMPLE_LINES = 3

_pipeline: Optional[stanza.Pipeline] = None
_translator = GoogleTranslator(source="uk", target="en")


def get_pipeline() -> stanza.Pipeline:
    global _pipeline
    if _pipeline is None:
        console.print("[dim]Loading Ukrainian NLP model (downloads ~100 MB on first run)…[/dim]")
        stanza.download("uk", verbose=False)
        _pipeline = stanza.Pipeline(
            lang="uk",
            processors="tokenize,pos,lemma",
            verbose=False,
        )
        console.print("[green]✓[/green] NLP model ready")
    return _pipeline


def _translate_line(line: str) -> str:
    try:
        result = _translator.translate(line.strip())
        return result.strip() if result else ""
    except Exception:
        return ""


def _parse_metadata(lines: list[str]) -> tuple[str, str, list[str]]:
    artist, title = "Unknown", "Unknown"
    content: list[str] = []
    for line in lines:
        s = line.strip()
        if s.startswith("# Artist:"):
            artist = s.removeprefix("# Artist:").strip()
        elif s.startswith("# Title:"):
            title = s.removeprefix("# Title:").strip()
        elif not s.startswith("#") and s:
            content.append(s)
    return artist, title, content


def _is_cyrillic(text: str) -> bool:
    return bool(re.search(r"[а-яіїєґА-ЯІЇЄҐʼ]", text))


def _tokenize_line(line: str, nlp: stanza.Pipeline) -> list[dict]:
    doc = nlp(line)
    results = []
    for sentence in doc.sentences:
        for word in sentence.words:
            pos = word.upos
            lemma = (word.lemma or word.text).lower()
            if (
                pos not in CONTENT_POS
                or len(lemma) < 2
                or lemma in STOP_LEMMAS
                or not _is_cyrillic(lemma)
            ):
                continue
            results.append({"lemma": lemma, "pos": pos})
    return results


def ingest_file(filepath: str | Path, force: bool = False) -> dict:
    """
    Ingest a single lyrics .txt file.

    Each word is stored with up to MAX_EXAMPLE_LINES example lines, where each
    line record contains:  {cyrillic, translit, translation, song}.

    Returns: {song, new_words, updated_words, skipped}
    """
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    raw_lines = path.read_text(encoding="utf-8").splitlines()
    artist, title, content_lines = _parse_metadata(raw_lines)
    song_label = f"{artist} - {title}"

    existing = songs_col().find_one({"filepath": str(path)})
    if existing and not force:
        console.print(
            f"[yellow]⚠[/yellow]  Already ingested: [bold]{song_label}[/bold] "
            "— pass --force to re-ingest"
        )
        return {"skipped": True, "song": song_label}

    nlp = get_pipeline()
    console.print(
        f"\n[cyan]→[/cyan]  Processing [bold]{song_label}[/bold] ({len(content_lines)} lines)…"
    )

    # ── Phase 1: analyse each line ────────────────────────────────────────────
    # Build a list of processed line records + their token lists
    line_data: list[dict] = []

    for line in track(content_lines, description="  NLP + translating lines…", console=console):
        if not _is_cyrillic(line):
            continue
        tokens = _tokenize_line(line, nlp)
        if not tokens:
            continue
        line_data.append({
            "cyrillic": line,
            "translit": transliterate(line),
            "translation": _translate_line(line),
            "song": song_label,
            "tokens": tokens,
        })

    if not line_data:
        console.print("[yellow]⚠[/yellow]  No processable lines found — check encoding")
        return {"skipped": True, "song": song_label}

    # ── Phase 2: build lemma → {pos, count, example_lines} index ─────────────
    lemma_index: dict[str, dict] = {}

    for ld in line_data:
        seen_in_line: set[str] = set()
        for tok in ld["tokens"]:
            key = tok["lemma"]
            if key not in lemma_index:
                lemma_index[key] = {"pos": tok["pos"], "count": 0, "lines": []}
            lemma_index[key]["count"] += 1
            if key not in seen_in_line and len(lemma_index[key]["lines"]) < MAX_EXAMPLE_LINES:
                lemma_index[key]["lines"].append({
                    "cyrillic": ld["cyrillic"],
                    "translit": ld["translit"],
                    "translation": ld["translation"],
                    "song": ld["song"],
                })
                seen_in_line.add(key)

    # ── Phase 3: upsert into MongoDB ──────────────────────────────────────────
    new_words = updated_words = 0
    wcol = words_col()

    for lemma, data in track(lemma_index.items(), description="  Upserting corpus…", console=console):
        # Upsert core fields — $setOnInsert ensures known/notes are never clobbered
        existing_doc = wcol.find_one_and_update(
            {"lemma": lemma},
            {
                "$inc": {"frequency": data["count"]},
                "$addToSet": {"songs": song_label},
                "$setOnInsert": {
                    "pos": data["pos"],
                    "known": False,
                    "translation": None,
                    "shown_at": None,
                    "notes": "",
                    "example_lines": [],
                },
            },
            upsert=True,
            return_document=True,
        )

        # Merge example lines, deduplicating by cyrillic text, capped at MAX
        if existing_doc is not None:
            existing_lines: list[dict] = existing_doc.get("example_lines", [])
            seen_cyrillics = {l["cyrillic"] for l in existing_lines}
            merged = existing_lines[:]
            for nl in data["lines"]:
                if nl["cyrillic"] not in seen_cyrillics and len(merged) < MAX_EXAMPLE_LINES:
                    merged.append(nl)
                    seen_cyrillics.add(nl["cyrillic"])
            if len(merged) != len(existing_lines):
                wcol.update_one({"lemma": lemma}, {"$set": {"example_lines": merged}})
            updated_words += 1
        else:
            wcol.update_one({"lemma": lemma}, {"$set": {"example_lines": data["lines"]}})
            new_words += 1

    # ── Phase 4: record song ──────────────────────────────────────────────────
    songs_col().replace_one(
        {"filepath": str(path)},
        {
            "artist": artist,
            "title": title,
            "filepath": str(path),
            "word_count": len(lemma_index),
            "line_count": len(line_data),
            "ingested_at": datetime.now(timezone.utc),
        },
        upsert=True,
    )

    console.print(
        f"[green]✓[/green]  [bold]{song_label}[/bold] — "
        f"[green]+{new_words} new[/green], [blue]{updated_words} updated[/blue]"
    )
    return {
        "song": song_label,
        "new_words": new_words,
        "updated_words": updated_words,
        "skipped": False,
    }


def ingest_directory(dirpath: str | Path, force: bool = False) -> list[dict]:
    dirpath = Path(dirpath)
    files = sorted(dirpath.glob("*.txt"))
    if not files:
        console.print(f"[yellow]No .txt files found in {dirpath}[/yellow]")
        return []
    return [ingest_file(f, force=force) for f in files]
