"""
cli.py — Typer CLI entry point for Слово дня Engine.

Commands:
  slovo ingest <path>                    Ingest lyrics file(s)
  slovo wod                              Get + deliver today's word
  slovo known <lemma>                    Mark a word as known
  slovo set-translation <lemma> <text>   Set a custom translation
  slovo note <lemma> <text>              Attach a personal note
  slovo stats                            Corpus statistics
  slovo history                          Recent WoD history
  slovo list                             Browse corpus by frequency
  slovo lookup <lemma>                   Show full detail for a word
  slovo tr <word>                        Translate Ukrainian word to English
  slovo song search <query>              Search Genius for Ukrainian songs
  slovo song fetch <id>                  Fetch lyrics from Genius and ingest
  slovo export [--format csv|json|anki]  Export vocabulary to file
  slovo study                            Study words with spaced repetition
"""
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from slovo import ingest as ingest_mod
from slovo import notify, wod as wod_mod
from slovo.translit import transliterate

app = typer.Typer(
    name="slovo",
    help="🇺🇦 Слово дня — Ukrainian word-of-the-day engine powered by your music library.",
    no_args_is_help=True,
)
console = Console()

POS_COLORS = {"NOUN": "cyan", "VERB": "green", "ADJ": "magenta", "ADV": "yellow"}


def _pos_color(pos: str) -> str:
    return POS_COLORS.get(pos.upper(), "white")


def _render_lyric_block(line: dict, indent: int = 0) -> Text:
    pad = " " * indent
    t = Text()
    t.append(f"{pad}🎵  {line['cyrillic']}\n", style="bold white")
    t.append(f"{pad}    {line['translit']}\n", style="italic dim")
    t.append(f"{pad}    {line['translation']}\n", style="dim")
    t.append(f"{pad}    — {line['song']}\n", style="dim italic")
    return t


# ── ingest ────────────────────────────────────────────────────────────────────

@app.command()
def ingest(
    path: Path = typer.Argument(..., help="Lyrics .txt file or directory of .txt files"),
    force: bool = typer.Option(False, "--force", "-f", help="Re-ingest files that are already in the corpus"),
):
    """Ingest Ukrainian lyrics into the word corpus."""
    if path.is_dir():
        results = ingest_mod.ingest_directory(path, force=force)
    elif path.is_file():
        results = [ingest_mod.ingest_file(path, force=force)]
    else:
        console.print(f"[red]Path not found:[/red] {path}")
        raise typer.Exit(1)

    total_new = sum(r.get("new_words", 0) for r in results)
    total_updated = sum(r.get("updated_words", 0) for r in results)
    songs_done = sum(1 for r in results if not r.get("skipped"))
    console.print(
        f"\n[bold]Done.[/bold] {songs_done} song(s) processed — "
        f"[green]+{total_new} new[/green] words, [blue]{total_updated} updated[/blue]"
    )


# ── wod ───────────────────────────────────────────────────────────────────────

@app.command()
def wod(
    pos: Optional[str] = typer.Option(None, "--pos", "-p", help="Filter by POS: NOUN VERB ADJ ADV"),
    min_freq: int = typer.Option(1, "--min-freq", "-f", help="Minimum corpus frequency"),
    artist: Optional[str] = typer.Option(None, "--artist", "-a", help="Only words from songs by this artist (substring match)"),
    dry_run: bool = typer.Option(False, "--dry-run", "-d", help="Display word but don't mark as seen or notify"),
    notify_only: bool = typer.Option(False, "--notify-only", "-n", help="Send notification silently, skip rich display"),
):
    """Pick today's word, display it richly, and send a notification."""
    word = wod_mod.pick_word(min_frequency=min_freq, pos_filter=pos, artist_filter=artist)

    if not word:
        console.print(
            "[yellow]No eligible words found.[/yellow] "
            "Try lowering [bold]--min-freq[/bold] or running [bold]slovo ingest[/bold] first."
        )
        raise typer.Exit()

    translation = wod_mod.get_or_translate(word)
    example_line = wod_mod.pick_example_line(word)
    pos_tag = word.get("pos", "")
    color = _pos_color(pos_tag)
    songs = word.get("songs", [])
    frequency = word.get("frequency", 1)

    if not notify_only:
        # ── rich terminal display ──────────────────────────────────────────────
        content = Text()

        # Word + translation
        content.append(f"  {word['lemma']}\n", style="bold white")
        content.append(f"  {translation}\n", style="italic")
        content.append(f"\n  [{pos_tag}]", style=color)
        content.append(f"  ·  freq: {frequency}", style="dim")

        # Example lyric line
        if example_line:
            content.append("\n\n")
            content.append_text(_render_lyric_block(example_line, indent=2))
        else:
            content.append("\n")

        # Songs list
        if songs:
            content.append("\n  Also in: ", style="dim")
            content.append(", ".join(songs[:3]), style="dim italic")
            content.append("\n")

        # Personal note
        if word.get("notes"):
            content.append(f"\n  📝  {word['notes']}\n", style="dim")

        console.print()
        console.print(Panel(
            content,
            title="🇺🇦  Слово дня",
            title_align="left",
            border_style="blue",
            padding=(0, 1),
        ))
        console.print()

    if not dry_run:
        wod_mod.record_shown(word, translation, example_line)
        notify.send(word, translation, example_line)
    else:
        console.print("[dim](dry run — not marked as seen, notification not sent)[/dim]")


# ── known ─────────────────────────────────────────────────────────────────────

@app.command()
def known(
    lemma: str = typer.Argument(..., help="Ukrainian lemma to mark as known"),
):
    """Mark a word as known so it won't appear as WoD."""
    if wod_mod.mark_known(lemma):
        console.print(f"[green]✓[/green] Marked [bold]{lemma}[/bold] as known")
    else:
        console.print(f"[yellow]Not found in corpus:[/yellow] {lemma}")


# ── set-translation ──────────────────────────────────────────────────────────

@app.command(name="set-translation")
def set_translation_cmd(
    lemma: str = typer.Argument(..., help="Ukrainian lemma"),
    translation: str = typer.Argument(..., help="Your preferred English translation"),
):
    """Override the auto-translation for a word with your own."""
    if wod_mod.set_translation(lemma, translation):
        console.print(f"[green]✓[/green] [bold]{lemma}[/bold] → {translation}")
    else:
        console.print(f"[yellow]Not found in corpus:[/yellow] {lemma}")


# ── note ──────────────────────────────────────────────────────────────────────

@app.command()
def note(
    lemma: str = typer.Argument(..., help="Ukrainian lemma to annotate"),
    text: str = typer.Argument(..., help="Your note (grammar tip, memory hook, etc.)"),
):
    """Attach a personal note to a word."""
    if wod_mod.set_note(lemma, text):
        console.print(f"[green]✓[/green] Note saved for [bold]{lemma}[/bold]")
    else:
        console.print(f"[yellow]Not found in corpus:[/yellow] {lemma}")


# ── lookup ────────────────────────────────────────────────────────────────────

@app.command()
def lookup(
    lemma: str = typer.Argument(..., help="Ukrainian lemma to inspect"),
):
    """Show full stored detail for a word including all example lines."""
    from slovo.db import words_col
    word = words_col().find_one({"lemma": lemma.lower()})
    if not word:
        console.print(f"[yellow]Not in corpus:[/yellow] {lemma}")
        raise typer.Exit()

    pos_tag = word.get("pos", "")
    color = _pos_color(pos_tag)
    content = Text()
    content.append(f"  {word['lemma']}\n", style="bold white")
    content.append(f"  {word.get('translation') or '(no translation yet)'}\n", style="italic")
    content.append(f"\n  [{pos_tag}]", style=color)
    content.append(f"  ·  freq: {word.get('frequency', 0)}", style="dim")
    content.append(f"  ·  {'[green]known[/green]' if word.get('known') else '[blue]learning[/blue]'}")

    lines = word.get("example_lines", [])
    if lines:
        content.append(f"\n\n  [dim]Example lines ({len(lines)}):[/dim]\n")
        for line in lines:
            content.append("\n")
            content.append_text(_render_lyric_block(line, indent=2))

    songs = word.get("songs", [])
    if songs:
        content.append(f"\n  Songs: {', '.join(songs)}\n", style="dim")

    if word.get("notes"):
        content.append(f"\n  📝  {word['notes']}\n", style="dim")

    console.print()
    console.print(Panel(content, title=f"🔍  {lemma}", title_align="left", border_style="dim"))
    console.print()


# ── stats ─────────────────────────────────────────────────────────────────────

@app.command()
def stats():
    """Show corpus statistics."""
    s = wod_mod.get_stats()

    summary = Table(show_header=False, box=None, padding=(0, 2))
    summary.add_column(style="dim")
    summary.add_column(style="bold")
    summary.add_row("Total words in corpus", str(s["total"]))
    summary.add_row("Marked known", f"[green]{s['known']}[/green]")
    summary.add_row("Seen, still learning", str(s["seen_not_known"]))
    summary.add_row("Never surfaced yet", str(s["untouched"]))

    console.print()
    console.print(Panel(summary, title="📊  Corpus Stats", title_align="left", border_style="blue"))

    if s["pos_breakdown"]:
        console.print()
        pos_table = Table(title="By Part of Speech", box=None, padding=(0, 2))
        pos_table.add_column("POS")
        pos_table.add_column("Count", justify="right")
        for row in s["pos_breakdown"]:
            c = _pos_color(row["_id"])
            pos_table.add_row(f"[{c}]{row['_id']}[/{c}]", str(row["count"]))
        console.print(pos_table)

    if s["top_unknown"]:
        console.print()
        top = Table(title="Top 10 Unknown Words", box=None, padding=(0, 2))
        top.add_column("Lemma", style="bold")
        top.add_column("POS")
        top.add_column("Freq", justify="right")
        top.add_column("Translation", style="italic")
        for w in s["top_unknown"]:
            c = _pos_color(w.get("pos", ""))
            top.add_row(
                w["lemma"],
                f"[{c}]{w.get('pos', '')}[/{c}]",
                str(w.get("frequency", 0)),
                w.get("translation") or "[dim]—[/dim]",
            )
        console.print(top)


# ── history ───────────────────────────────────────────────────────────────────

@app.command()
def history(
    limit: int = typer.Option(10, "--limit", "-l"),
    with_lines: bool = typer.Option(False, "--lines", help="Show the example lyric line for each entry"),
):
    """Show recent word-of-the-day history."""
    entries = wod_mod.get_history(limit)
    if not entries:
        console.print("[dim]No history yet — run [bold]slovo wod[/bold] first.[/dim]")
        return

    for e in entries:
        shown = e.get("shown_at")
        date_str = shown.strftime("%Y-%m-%d") if shown else "—"
        pos = e.get("pos", "")
        color = _pos_color(pos)
        console.print(
            f"  [dim]{date_str}[/dim]  "
            f"[bold]{e.get('lemma', '')}[/bold]  "
            f"[{color}]{pos}[/{color}]  "
            f"[italic]{e.get('translation', '')}[/italic]"
        )
        if with_lines and e.get("example_line"):
            console.print(_render_lyric_block(e["example_line"], indent=10))


# ── list ──────────────────────────────────────────────────────────────────────

@app.command(name="list")
def list_words(
    pos: Optional[str] = typer.Option(None, "--pos", "-p"),
    unknown_only: bool = typer.Option(False, "--unknown", "-u"),
    artist: Optional[str] = typer.Option(None, "--artist", "-a", help="Filter to words from this artist"),
    limit: int = typer.Option(40, "--limit", "-l"),
):
    """Browse the word corpus sorted by frequency."""
    from slovo.db import words_col
    query: dict = {}
    if pos:
        query["pos"] = pos.upper()
    if unknown_only:
        query["known"] = False
    if artist:
        query["songs"] = {"$regex": artist, "$options": "i"}

    words = list(
        words_col()
        .find(query, {"lemma": 1, "pos": 1, "frequency": 1, "known": 1, "translation": 1, "shown_at": 1})
        .sort("frequency", -1)
        .limit(limit)
    )
    if not words:
        console.print("[yellow]No words match that filter.[/yellow]")
        return

    table = Table(box=None, padding=(0, 2))
    table.add_column("Lemma", style="bold")
    table.add_column("POS")
    table.add_column("Freq", justify="right")
    table.add_column("Translation", style="italic")
    table.add_column("Status", justify="center")

    for w in words:
        c = _pos_color(w.get("pos", ""))
        if w.get("known"):
            status = "[green]known[/green]"
        elif w.get("shown_at"):
            status = "[dim]seen[/dim]"
        else:
            status = "[blue]new[/blue]"
        table.add_row(
            w["lemma"],
            f"[{c}]{w.get('pos', '')}[/{c}]",
            str(w.get("frequency", 0)),
            w.get("translation") or "[dim]—[/dim]",
            status,
        )

    console.print()
    console.print(table)


# ── tr (standalone translate) ────────────────────────────────────────────────

@app.command(name="tr")
def translate_word(
    word: str = typer.Argument(..., help="Ukrainian word or phrase to translate"),
    reverse: bool = typer.Option(False, "--reverse", "-r", help="Translate English to Ukrainian"),
):
    """Translate a Ukrainian word to English (or reverse with -r)."""
    from slovo.translation import translate as api_translate

    source = "en" if reverse else "uk"
    target = "uk" if reverse else "en"

    try:
        result = api_translate(word, source=source, target=target)
    except Exception as e:
        console.print(f"[red]Translation error:[/red] {e}")
        raise typer.Exit(1)

    # Build output
    translit = transliterate(word) if not reverse else transliterate(result["translation"])
    pos = result.get("part_of_speech", "")
    formality = result.get("formality", "")
    provider = result.get("provider", "")

    content = Text()
    content.append(f"  {word}\n", style="bold white")
    if not reverse:
        content.append(f"  {translit}\n", style="dim italic")
    content.append(f"  {result['translation']}\n", style="italic")
    if reverse:
        content.append(f"  {translit}\n", style="dim italic")

    meta_parts = []
    if pos:
        meta_parts.append(f"[{pos}]")
    if formality:
        meta_parts.append(formality)
    if provider:
        meta_parts.append(f"via {provider}")
    if meta_parts:
        content.append(f"\n  {' · '.join(meta_parts)}\n", style="dim")

    console.print()
    console.print(Panel(content, title="Translation", title_align="left", border_style="blue"))
    console.print()


# ── song ─────────────────────────────────────────────────────────────────────

song_app = typer.Typer(help="Search and fetch songs from Genius")
app.add_typer(song_app, name="song")


@song_app.command(name="search")
def song_search(
    query: str = typer.Argument(..., help="Search query (artist, title, or both)"),
    limit: int = typer.Option(10, "--limit", "-l", help="Max results to show"),
):
    """Search Genius for songs matching query."""
    from slovo.genius import GeniusService

    try:
        service = GeniusService()
    except ValueError as e:
        console.print(f"[red]Genius API error:[/red] {e}")
        raise typer.Exit(1)

    try:
        songs = service.search_songs(query, max_results=limit)
    except Exception as e:
        console.print(f"[red]Search failed:[/red] {e}")
        raise typer.Exit(1)

    if not songs:
        console.print("[yellow]No songs found.[/yellow]")
        return

    table = Table(box=None, padding=(0, 2))
    table.add_column("ID", style="dim")
    table.add_column("Title", style="bold")
    table.add_column("Artist")
    table.add_column("URL", style="dim")

    for song in songs:
        table.add_row(
            str(song["id"]),
            song["title"],
            song["artist"],
            song["url"],
        )

    console.print()
    console.print(table)
    console.print()
    console.print("[dim]Use [bold]slovo song fetch <ID>[/bold] to download lyrics[/dim]")


@song_app.command(name="fetch")
def song_fetch(
    song_id: int = typer.Argument(..., help="Genius song ID"),
    save: bool = typer.Option(True, "--save/--no-save", help="Save to lyrics/ directory"),
    ingest_lyrics: bool = typer.Option(True, "--ingest/--no-ingest", help="Ingest into corpus"),
):
    """Fetch lyrics from Genius and optionally ingest into corpus."""
    from slovo.genius import GeniusService

    try:
        service = GeniusService()
    except ValueError as e:
        console.print(f"[red]Genius API error:[/red] {e}")
        raise typer.Exit(1)

    console.print(f"[dim]Fetching song {song_id}...[/dim]")

    try:
        song = service.get_song(song_id)
    except Exception as e:
        console.print(f"[red]Fetch failed:[/red] {e}")
        raise typer.Exit(1)

    console.print(f"[bold]{song['title']}[/bold] by {song['artist']}")

    if not song.get("lyrics"):
        console.print("[yellow]No lyrics found for this song.[/yellow]")
        raise typer.Exit(1)

    # Preview first few lines
    lines = song["lyrics"].split("\n")[:5]
    console.print()
    for line in lines:
        if line.strip():
            console.print(f"  [dim]{line}[/dim]")
    if len(song["lyrics"].split("\n")) > 5:
        console.print("  [dim]...[/dim]")
    console.print()

    if save:
        lyrics_dir = Path("lyrics")
        lyrics_dir.mkdir(exist_ok=True)

        # Sanitize filename
        safe_artist = "".join(c if c.isalnum() or c in " -_" else "_" for c in song["artist"])
        safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in song["title"])
        filename = f"{safe_artist} - {safe_title}.txt"
        filepath = lyrics_dir / filename

        # Write with metadata header
        content = f"# {song['title']}\n# {song['artist']}\n# Genius ID: {song_id}\n\n{song['lyrics']}"
        filepath.write_text(content, encoding="utf-8")
        console.print(f"[green]Saved:[/green] {filepath}")

        if ingest_lyrics:
            result = ingest_mod.ingest_file(filepath, force=True)
            new_words = result.get("new_words", 0)
            updated = result.get("updated_words", 0)
            console.print(f"[green]Ingested:[/green] +{new_words} new, {updated} updated")


@song_app.command(name="show")
def song_show(
    song_id: int = typer.Argument(..., help="Genius song ID"),
):
    """Show full lyrics for a song without saving."""
    from slovo.genius import GeniusService

    try:
        service = GeniusService()
        song = service.get_song(song_id)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    console.print()
    console.print(Panel(
        f"[bold]{song['title']}[/bold]\n{song['artist']}\n{song.get('release_date', '')}",
        border_style="blue",
    ))
    console.print()
    console.print(song.get("lyrics", "(no lyrics)"))
    console.print()


# ── export ───────────────────────────────────────────────────────────────────

@app.command()
def export(
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file path"),
    fmt: str = typer.Option("csv", "--format", "-f", help="Output format: csv, json, or anki"),
    unknown_only: bool = typer.Option(False, "--unknown", "-u", help="Only export unknown words"),
    pos: Optional[str] = typer.Option(None, "--pos", "-p", help="Filter by POS"),
):
    """Export vocabulary to CSV, JSON, or Anki format file."""
    import csv
    import json
    from slovo.db import words_col

    query: dict = {}
    if unknown_only:
        query["known"] = False
    if pos:
        query["pos"] = pos.upper()

    # For Anki, we need example_lines as well
    if fmt.lower() == "anki":
        projection = {"_id": 0, "lemma": 1, "pos": 1, "translation": 1, "example_lines": 1}
    else:
        projection = {"_id": 0, "lemma": 1, "pos": 1, "frequency": 1, "translation": 1, "known": 1, "notes": 1}

    words = list(
        words_col()
        .find(query, projection)
        .sort("frequency", -1)
    )

    if not words:
        console.print("[yellow]No words match that filter.[/yellow]")
        return

    # Generate filename if not provided
    if output is None:
        suffix = "_unknown" if unknown_only else ""
        pos_suffix = f"_{pos.lower()}" if pos else ""
        extension = "txt" if fmt.lower() == "anki" else fmt
        output = Path(f"vocabulary{suffix}{pos_suffix}.{extension}")

    if fmt.lower() == "csv":
        with open(output, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["lemma", "pos", "frequency", "translation", "known", "notes"])
            writer.writeheader()
            for w in words:
                writer.writerow({
                    "lemma": w.get("lemma", ""),
                    "pos": w.get("pos", ""),
                    "frequency": w.get("frequency", 0),
                    "translation": w.get("translation", ""),
                    "known": w.get("known", False),
                    "notes": w.get("notes", ""),
                })
    elif fmt.lower() == "json":
        with open(output, "w", encoding="utf-8") as f:
            json.dump(words, f, ensure_ascii=False, indent=2)
    elif fmt.lower() == "anki":
        with open(output, "w", encoding="utf-8") as f:
            for w in words:
                lemma = w.get("lemma", "")
                pos = w.get("pos", "")
                translation = w.get("translation", "")
                example_lines = w.get("example_lines", [])

                # Front: Ukrainian word + transliteration
                translit = transliterate(lemma)
                front = f"{lemma} ({translit})"

                # Back: translation + POS + example sentence (if available)
                back_parts = []
                if translation:
                    back_parts.append(translation)
                if pos:
                    back_parts.append(f"[{pos}]")

                back = " ".join(back_parts)

                # Add example sentence if available
                if example_lines:
                    example = example_lines[0].get("cyrillic", "")
                    if example:
                        back += f' "{example}"'

                # Write tab-separated line
                f.write(f"{front}\t{back}\n")
    else:
        console.print(f"[red]Unknown format:[/red] {fmt}. Use 'csv', 'json', or 'anki'.")
        raise typer.Exit(1)

    console.print(f"[green]Exported {len(words)} words to:[/green] {output}")


# ── study ─────────────────────────────────────────────────────────────────────

@app.command()
def study(
    limit: int = typer.Option(10, "--limit", "-l", help="Number of words to review"),
    show_stats: bool = typer.Option(True, "--stats/--no-stats", help="Show study statistics before session"),
):
    """Study words using spaced repetition (SM-2 algorithm)."""
    from slovo import study as study_mod
    from slovo.wod import get_or_translate

    if show_stats:
        stats = study_mod.get_study_stats()
        console.print()
        console.print(Panel(
            f"[bold]Words due:[/bold] {stats['words_due']}\n"
            f"[bold]Learning:[/bold] {stats['words_learning']} words\n"
            f"[bold]Mastered:[/bold] {stats['words_mastered']} words\n"
            f"[bold]Average ease:[/bold] {stats['average_ease_factor']}\n"
            f"[bold]Total reviews:[/bold] {stats['total_reviews']}",
            title="Study Progress",
            title_align="left",
            border_style="blue"
        ))
        console.print()

    due_words = study_mod.get_due_words(limit=limit)

    if not due_words:
        console.print("[green]No words due for review![/green]")
        console.print("[dim]Check back later or lower your --limit to review more words.[/dim]")
        return

    console.print(f"[bold]Reviewing {len(due_words)} words[/bold]\n")

    completed = 0
    for word in due_words:
        lemma = word["lemma"]
        pos = word.get("pos", "")
        color = _pos_color(pos)
        review_count = word.get("review_count", 0)

        # Display word
        content = Text()
        content.append(f"  {lemma}\n", style="bold white")

        if review_count == 0:
            content.append(f"  [dim italic](new word)[/dim italic]\n")
        else:
            ease = word.get("ease_factor", 2.5)
            interval = word.get("interval", 0)
            content.append(f"  [dim]Reviews: {review_count}  •  Ease: {ease:.2f}  •  Interval: {interval}d[/dim]\n")

        content.append(f"\n  [{pos}]", style=color)

        console.print()
        console.print(Panel(content, title="Recall this word", title_align="left", border_style="yellow"))
        console.print()

        # Wait for user to recall
        input("Press Enter when ready to see the answer...")

        # Show translation and example
        translation = get_or_translate(word)
        example_lines = word.get("example_lines", [])

        answer_content = Text()
        answer_content.append(f"  {lemma}\n", style="bold white")
        answer_content.append(f"  {translation}\n", style="italic green")
        answer_content.append(f"\n  [{pos}]", style=color)

        if example_lines:
            answer_content.append("\n\n")
            answer_content.append_text(_render_lyric_block(example_lines[0], indent=2))

        console.print(Panel(answer_content, title="Answer", title_align="left", border_style="green"))
        console.print()

        # Get quality rating
        console.print("[dim]Rate your recall:[/dim]")
        console.print("  [red]0[/red] = Complete blackout")
        console.print("  [yellow]1-2[/yellow] = Incorrect, needed help")
        console.print("  [blue]3[/blue] = Correct, with difficulty")
        console.print("  [cyan]4[/cyan] = Correct, with hesitation")
        console.print("  [green]5[/green] = Perfect, immediate recall")

        while True:
            try:
                rating_input = input("\nYour rating (0-5): ").strip()
                if not rating_input:
                    console.print("[yellow]Skipping this word...[/yellow]")
                    break

                quality = int(rating_input)
                if not 0 <= quality <= 5:
                    console.print("[red]Please enter a number between 0 and 5[/red]")
                    continue

                result = study_mod.record_review(lemma, quality)
                completed += 1

                if quality < 3:
                    console.print(f"[yellow]Don't worry! You'll see this again soon.[/yellow]")
                elif quality == 3:
                    console.print(f"[blue]Next review in {result['interval']} day(s)[/blue]")
                elif quality == 4:
                    console.print(f"[cyan]Good! Next review in {result['interval']} day(s)[/cyan]")
                else:
                    console.print(f"[green]Excellent! Next review in {result['interval']} day(s)[/green]")

                break
            except ValueError:
                console.print("[red]Please enter a valid number[/red]")
            except Exception as e:
                console.print(f"[red]Error recording review:[/red] {e}")
                break

        console.print()

    # Summary
    console.print()
    console.print(Panel(
        f"[bold]Session complete![/bold]\n\n"
        f"Reviewed: {completed} / {len(due_words)} words",
        title="Study Summary",
        title_align="left",
        border_style="blue"
    ))
    console.print()


# ── entry ─────────────────────────────────────────────────────────────────────

def main():
    app()


if __name__ == "__main__":
    main()
