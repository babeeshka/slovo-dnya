# Slovo Dnya -- Word of the Day Engine

A CLI tool and REST API that ingests Ukrainian song lyrics, builds a vocabulary corpus in MongoDB,
and surfaces unfamiliar words daily via push notification. Each word is delivered with the lyric
line it came from in Cyrillic, transliteration, and English translation.

Built for learning Ukrainian through music: Re-Read, Mistmorn, BoomBox, Corn Wave, etc.

---

## What a notification looks like

**ntfy / iPhone push:**
```
🇺🇦  місто

town / city  [noun]

🎵  Місяць світить над тихим містом
    Misiats svityt nad tykhym mistom
    The moon shines over the quiet city
    — Sample - Вечірнє місто

Found in: Sample - Вечірнє місто
```

**Email (HTML)** renders the same structure with a styled card — blue header with the word large,
lyric block in a highlighted box, transliteration and translation underneath.

---

## Architecture

```
lyrics/*.txt
    │
    ▼
ingest.py
  ├─ metadata parse  (# Artist / # Title headers)
  ├─ stanza NLP      (tokenize → POS tag → lemmatize)
  ├─ transliterate   (KMU 2010 romanisation, no external dep)
  ├─ line translate  (Google Translate via deep-translator)
  └─ MongoDB upsert  (lemma + frequency + example_lines)
        │
        ▼
   MongoDB Atlas (free cluster)
   ├─ words      {lemma, pos, frequency, songs, known, translation,
   │              shown_at, notes, example_lines[{cyrillic,translit,translation,song}]}
   ├─ songs      {artist, title, filepath, word_count, line_count}
   └─ history    {lemma, translation, pos, example_line, shown_at}
        │
        ▼
    wod.py  →  notify.py
  (frequency-ranked,       ├─ ntfy    (iPhone + macOS push)
   cooldown-aware          ├─ email   (HTML, Apple Mail)
   word selection)         ├─ osascript (macOS popup)
                           ├─ discord
                           └─ print
```

---

## Setup

### 1. Install

```bash
git clone <repo>
cd slovo-dnya
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

### 2. Configure

```bash
cp .env.example .env
# Fill in MONGODB_URI and your preferred NOTIFY_METHOD
```

**MongoDB Atlas:** Create a free M0 cluster at [mongodb.com/atlas](https://mongodb.com/atlas).
Copy the connection string (Driver: Python) into `MONGODB_URI`.

### 3. Pick a notification method

| Method | Best for | Setup |
|--------|----------|-------|
| `ntfy` | iPhone + macOS simultaneously | Install [ntfy app](https://apps.apple.com/app/ntfy/id1625396347) → subscribe to your topic |
| `email` | Apple Mail on iPhone/Mac | Gmail app password → `EMAIL_*` vars in `.env` |
| `osascript` | macOS only | No config needed |
| `discord` | Discord server | Paste webhook URL |
| `print` | Testing / cron logs | No config needed |

**Recommended:** `ntfy` — one subscription covers both iPhone and macOS, free, no account
required, reliable push delivery even when the app is backgrounded.

---

## Lyrics file format

```
# Artist: BoomBox
# Title: Врятуй

Перший рядок тексту пісні...
Другий рядок...

# [Приспів]
Рядок приспіву...
```

- Lines starting with `#` are metadata or section markers — skipped by the NLP
- Everything else is treated as lyrics
- UTF-8 encoding (standard for Ukrainian)
- One file per song, name it `artist_title.txt` for your own organization

---

## Usage

```bash
# Ingest a single song
slovo ingest lyrics/boombox_vryatuy.txt

# Ingest an entire directory
slovo ingest lyrics/

# Re-ingest after editing a file
slovo ingest lyrics/boombox_vryatuy.txt --force

# Get today's word (display + notify)
slovo wod

# Filter to verbs only
slovo wod --pos VERB

# Only words from BoomBox songs
slovo wod --artist BoomBox

# Words that appear 3+ times in corpus (more useful vocabulary first)
slovo wod --min-freq 3

# Preview without marking as seen or sending notification
slovo wod --dry-run

# Show full word detail with all example lines
slovo lookup місто

# Mark a word you already know
slovo known кава

# Override a bad auto-translation
slovo translate іти "to go (on foot)"

# Add a grammar note
slovo note іти "irregular: іти infinitive → іду/ідеш present. Cf. йти (same verb, variant form)"

# Corpus stats + top unknown words
slovo stats

# Browse all words by frequency (unknown nouns from Re-Read only)
slovo list --unknown --pos NOUN --artist "Re-Read"

# Recent WoD history with lyric lines
slovo history --lines --limit 20
```

---

## Automating (cron)

```bash
crontab -e
# 8:30am every day:
30 8 * * * /path/to/.venv/bin/slovo wod >> /tmp/slovo.log 2>&1
```

macOS launchd alternative — create `~/Library/LaunchAgents/com.slovo.wod.plist`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>       <string>com.slovo.wod</string>
    <key>ProgramArguments</key>
    <array>
        <string>/path/to/.venv/bin/slovo</string>
        <string>wod</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict><key>Hour</key><integer>8</integer><key>Minute</key><integer>30</integer></dict>
    <key>StandardOutPath</key> <string>/tmp/slovo.log</string>
    <key>StandardErrorPath</key> <string>/tmp/slovo.log</string>
</dict>
</plist>
```
Then: `launchctl load ~/Library/LaunchAgents/com.slovo.wod.plist`

---

## Transliteration

`translit.py` implements the KMU 2010 standard (Ukrainian government romanization, the same
system used on passports). It handles position-sensitive rules for the letters that have
two forms (long form at word start, short form elsewhere) and has no external dependencies.

---

## MongoDB schema quick reference

```js
// words collection — one doc per unique lemma
{
  lemma: "місто",
  pos: "NOUN",
  frequency: 4,
  songs: ["Sample - Вечірнє місто"],
  known: false,
  translation: "city, town",
  shown_at: ISODate("2026-03-01"),
  notes: "",
  example_lines: [
    {
      cyrillic: "Місяць світить над тихим містом",
      translit: "Misiats svityt nad tykhym mistom",
      translation: "The moon shines over the quiet city",
      song: "Sample - Вечірнє місто"
    }
  ]
}
```

---

## REST API

A FastAPI server exposes the same functionality as the CLI for integration with mobile apps,
Obsidian, or other tools.

### Running the API

```bash
# Development server with auto-reload
uvicorn slovo.api:app --reload

# Production
uvicorn slovo.api:app --host 0.0.0.0 --port 8000
```

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Health check |
| GET | `/words` | List words (supports filters: `pos`, `unknown_only`, `artist`, `min_freq`, `limit`, `offset`) |
| GET | `/words/{lemma}` | Get full detail for a word |
| POST | `/words/{lemma}/known` | Mark word as known |
| POST | `/words/{lemma}/translation` | Set custom translation (body: `{"translation": "..."}`) |
| POST | `/words/{lemma}/note` | Add note to word (body: `{"note": "..."}`) |
| GET | `/wod` | Preview word of the day (does not record) |
| POST | `/wod` | Pick and record word of the day |
| GET | `/stats` | Corpus statistics |
| GET | `/history` | Recent WoD history |
| GET | `/songs` | List ingested songs |

Interactive API docs available at `http://localhost:8000/docs` when the server is running.

---

## Development

### Setup

```bash
# Clone and create virtual environment
git clone https://github.com/babeeshka/slovo-dnya.git
cd slovo-dnya
python -m venv .venv
source .venv/bin/activate

# Install with dev dependencies
pip install -e ".[dev]"

# Copy environment template
cp .env.example .env
# Edit .env with your MongoDB URI
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=slovo --cov-report=term-missing

# Run specific test file
pytest tests/test_translit.py -v
```

Tests use `mongomock` so no MongoDB connection is required.

### Code Quality

```bash
# Lint and format check
ruff check .

# Auto-fix issues
ruff check --fix .
```

### Project Structure

```
slovo-dnya/
    slovo/
        __init__.py
        api.py          # FastAPI REST endpoints
        cli.py          # Typer CLI commands
        db.py           # MongoDB connection and collections
        ingest.py       # Lyrics parsing and NLP processing
        notify.py       # Push notification backends
        translit.py     # KMU 2010 transliteration
        wod.py          # Word-of-the-day selection logic
    tests/
        conftest.py     # Shared test fixtures
        test_api.py     # API endpoint tests
        test_db.py      # Database tests
        test_ingest.py  # Ingestion tests
        test_translit.py # Transliteration tests
        test_wod.py     # Word selection tests
    lyrics/             # Your lyrics files go here
    pyproject.toml      # Project configuration
    .env.example        # Environment template
```

---

## Extending

- **Anki export** -- `genanki` can write `.apkg` files; the schema maps directly to a card front/back
- **Difficulty scoring** -- weight selection toward shorter, simpler words early in learning
- **Phrase-level storage** -- store 2-3 word collocations alongside individual lemmas
- **Audio** -- if you have audio files, timestamp the lyric lines and link deep into the track
