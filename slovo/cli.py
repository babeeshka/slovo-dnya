"""
cli.py — Typer CLI entry point for Слово дня Engine.

Commands:
  slovo ingest <path>                    Ingest lyrics file(s)
  slovo wod                              Get + deliver today's word
  slovo known <lemma>                    Mark a word as known
  slovo translate <lemma> <translation>  Set a custom translation
  slovo note <lemma> <text>              Attach a personal note
  slovo stats                            Corpus statistics
  slovo history                          Recent WoD history
  slovo list                             Browse corpus by frequency
  slovo lookup <lemma>                   Show full detail for a word
"""
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from slovo import ingest as ingest_mod
from slovo import notify, wod as wod_mod

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


# ── translate ─────────────────────────────────────────────────────────────────

@app.command()
def translate(
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


# ── entry ─────────────────────────────────────────────────────────────────────

def main():
    app()


if __name__ == "__main__":
    main()
