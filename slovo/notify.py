"""
notify.py — Deliver word-of-the-day via multiple backends.

Supported methods (set NOTIFY_METHOD in .env):

  ntfy       — HTTP push via ntfy.sh. Free, no account needed.
               iOS app: search "ntfy" in the App Store.
               macOS: subscribe via https://ntfy.sh/<NTFY_TOPIC> in browser,
               or use the ntfy CLI / any HTTP client.

  email      — HTML email. Works with any SMTP server; easiest via Gmail
               app password (no 2FA risk). Renders nicely on iPhone Mail.

  osascript  — macOS native notification popup (no extra deps or accounts).

  discord    — Discord webhook embed (rich formatting).

  print      — Plain stdout fallback. Good for cron logs / testing.
"""
import os
import smtplib
import textwrap
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import requests
from dotenv import load_dotenv
from rich.console import Console

load_dotenv()
console = Console()


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _pos_label(pos: str) -> str:
    return {"NOUN": "noun", "VERB": "verb", "ADJ": "adjective", "ADV": "adverb"}.get(pos, pos.lower())


# ── ntfy ───────────────────────────────────────────────────────────────────────

def _notify_ntfy(
    lemma: str, translation: str, pos: str,
    songs: list[str], example_line: Optional[dict],
) -> None:
    """
    Sends to ntfy.sh. The iOS ntfy app shows title + body as a push notification.

    To subscribe on iPhone:
      1. Install "ntfy" from the App Store (free).
      2. Tap "+" → enter your NTFY_TOPIC.
      Done — notifications arrive even with the app closed.
    """
    topic = os.environ.get("NTFY_TOPIC", "slovo-dnya")

    lines_parts: list[str] = [
        f"{translation}  [{_pos_label(pos)}]",
    ]

    if example_line:
        lines_parts += [
            "",
            f"🎵  {example_line['cyrillic']}",
            f"    {example_line['translit']}",
            f"    {example_line['translation']}",
            f"    — {example_line['song']}",
        ]

    songs_preview = ", ".join(songs[:2])
    if songs_preview:
        lines_parts += ["", f"Found in: {songs_preview}"]

    body = "\n".join(lines_parts)

    try:
        resp = requests.post(
            f"https://ntfy.sh/{topic}",
            data=body.encode("utf-8"),
            headers={
                "Title": f"🇺🇦  {lemma}",
                "Priority": "default",
                "Tags": "ukraine,language,music",
            },
            timeout=8,
        )
        resp.raise_for_status()
        console.print(f"[green]✓[/green] ntfy → https://ntfy.sh/{topic}")
    except Exception as e:
        console.print(f"[red]ntfy failed:[/red] {e}")


# ── Email (HTML) ───────────────────────────────────────────────────────────────

def _notify_email(
    lemma: str, translation: str, pos: str,
    songs: list[str], example_line: Optional[dict],
) -> None:
    """
    Sends an HTML email. Renders nicely in Apple Mail on iPhone and macOS.

    Required .env keys:
      EMAIL_FROM       sender address (e.g. yourname@gmail.com)
      EMAIL_TO         recipient (can be same address)
      EMAIL_PASSWORD   app password (Gmail: myaccount.google.com → Security → App passwords)
      EMAIL_SMTP_HOST  default: smtp.gmail.com
      EMAIL_SMTP_PORT  default: 587
    """
    smtp_host = os.environ.get("EMAIL_SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("EMAIL_SMTP_PORT", "587"))
    email_from = os.environ.get("EMAIL_FROM", "")
    email_to = os.environ.get("EMAIL_TO", email_from)
    password = os.environ.get("EMAIL_PASSWORD", "")

    if not email_from or not password:
        console.print("[red]EMAIL_FROM and EMAIL_PASSWORD must be set for email delivery[/red]")
        return

    pos_label = _pos_label(pos)
    songs_html = "".join(f"<li>{s}</li>" for s in songs[:4])

    lyric_block = ""
    if example_line:
        lyric_block = textwrap.dedent(f"""
        <div style="margin:24px 0;padding:16px 20px;background:#f0f4ff;border-left:4px solid #005BBB;border-radius:4px;">
          <div style="font-size:18px;font-weight:600;color:#1a1a2e;margin-bottom:6px;">
            {example_line['cyrillic']}
          </div>
          <div style="font-size:14px;color:#555;font-style:italic;margin-bottom:4px;">
            {example_line['translit']}
          </div>
          <div style="font-size:14px;color:#333;">
            {example_line['translation']}
          </div>
          <div style="font-size:12px;color:#888;margin-top:8px;">— {example_line['song']}</div>
        </div>
        """).strip()

    html = textwrap.dedent(f"""
    <!DOCTYPE html>
    <html lang="en">
    <head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
    <body style="margin:0;padding:0;background:#f9f9fb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
      <div style="max-width:520px;margin:32px auto;background:#fff;border-radius:12px;
                  box-shadow:0 2px 12px rgba(0,0,0,.08);overflow:hidden;">

        <!-- Header -->
        <div style="background:linear-gradient(135deg,#005BBB 0%,#003f8a 100%);
                    padding:28px 32px;text-align:center;">
          <div style="font-size:11px;letter-spacing:2px;color:rgba(255,255,255,.7);
                      text-transform:uppercase;margin-bottom:8px;">🇺🇦 Слово дня</div>
          <div style="font-size:42px;font-weight:700;color:#fff;letter-spacing:-1px;">
            {lemma}
          </div>
          <div style="font-size:14px;color:rgba(255,255,255,.8);margin-top:6px;">
            {translation} &nbsp;·&nbsp; <em>{pos_label}</em>
          </div>
        </div>

        <!-- Body -->
        <div style="padding:28px 32px;">

          {lyric_block}

          <div style="margin-top:20px;">
            <div style="font-size:11px;letter-spacing:1px;text-transform:uppercase;
                        color:#999;margin-bottom:8px;">Found in</div>
            <ul style="margin:0;padding:0 0 0 18px;color:#444;font-size:14px;line-height:1.7;">
              {songs_html}
            </ul>
          </div>

        </div>

        <!-- Footer -->
        <div style="padding:16px 32px;background:#f5f5f7;border-top:1px solid #eee;
                    font-size:11px;color:#aaa;text-align:center;">
          Слово дня Engine &nbsp;·&nbsp; Reply to manage your word list
        </div>
      </div>
    </body>
    </html>
    """).strip()

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🇺🇦 Слово дня: {lemma} — {translation}"
    msg["From"] = email_from
    msg["To"] = email_to
    msg.attach(MIMEText(f"{lemma}\n{translation} ({pos_label})\n\n{example_line['cyrillic'] if example_line else ''}", "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(email_from, password)
            server.sendmail(email_from, email_to, msg.as_string())
        console.print(f"[green]✓[/green] Email sent → {email_to}")
    except Exception as e:
        console.print(f"[red]Email failed:[/red] {e}")


# ── osascript (macOS) ──────────────────────────────────────────────────────────

def _notify_osascript(lemma: str, translation: str, pos: str, example_line: Optional[dict], **_) -> None:
    import subprocess
    subtitle = example_line["cyrillic"] if example_line else _pos_label(pos)
    msg = f"{translation}  [{_pos_label(pos)}]"
    script = (
        f'display notification "{msg}" '
        f'with title "🇺🇦 Слово дня: {lemma}" '
        f'subtitle "{subtitle}"'
    )
    try:
        subprocess.run(["osascript", "-e", script], check=True, capture_output=True)
        console.print("[green]✓[/green] macOS notification sent")
    except Exception as e:
        console.print(f"[red]osascript failed:[/red] {e}")


# ── Discord ────────────────────────────────────────────────────────────────────

def _notify_discord(
    lemma: str, translation: str, pos: str,
    songs: list[str], frequency: int, example_line: Optional[dict],
) -> None:
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        console.print("[red]DISCORD_WEBHOOK_URL not set[/red]")
        return

    fields = [
        {"name": "Translation", "value": translation, "inline": True},
        {"name": "Part of Speech", "value": _pos_label(pos).capitalize(), "inline": True},
        {"name": "Frequency", "value": str(frequency), "inline": True},
    ]

    if example_line:
        lyric_value = (
            f"**{example_line['cyrillic']}**\n"
            f"*{example_line['translit']}*\n"
            f"{example_line['translation']}\n"
            f"— {example_line['song']}"
        )
        fields.append({"name": "🎵 Example lyric", "value": lyric_value, "inline": False})

    songs_val = "\n".join(f"• {s}" for s in songs[:5]) or "—"
    fields.append({"name": "Found in", "value": songs_val, "inline": False})

    payload = {
        "embeds": [{
            "title": f"🇺🇦  Слово дня: **{lemma}**",
            "color": 0x005BBB,
            "fields": fields,
            "footer": {"text": "Слово дня Engine"},
        }]
    }
    try:
        resp = requests.post(webhook_url, json=payload, timeout=5)
        resp.raise_for_status()
        console.print("[green]✓[/green] Discord notification sent")
    except Exception as e:
        console.print(f"[red]Discord failed:[/red] {e}")


# ── Print fallback ─────────────────────────────────────────────────────────────

def _notify_print(lemma: str, translation: str, pos: str, example_line: Optional[dict], **_) -> None:
    print(f"\nСЛОВО ДНЯ: {lemma}  |  {translation}  |  {_pos_label(pos)}")
    if example_line:
        print(f"\n  {example_line['cyrillic']}")
        print(f"  {example_line['translit']}")
        print(f"  {example_line['translation']}")
        print(f"  — {example_line['song']}\n")


# ── Dispatcher ────────────────────────────────────────────────────────────────

def send(word_doc: dict, translation: str, example_line: Optional[dict]) -> None:
    method = os.environ.get("NOTIFY_METHOD", "print").lower()
    lemma = word_doc.get("lemma", "")
    pos = word_doc.get("pos", "NOUN")
    songs = word_doc.get("songs", [])
    frequency = word_doc.get("frequency", 1)

    kwargs = dict(
        lemma=lemma,
        translation=translation,
        pos=pos,
        songs=songs,
        frequency=frequency,
        example_line=example_line,
    )

    if method == "ntfy":
        _notify_ntfy(**kwargs)
    elif method == "email":
        _notify_email(**kwargs)
    elif method == "osascript":
        _notify_osascript(**kwargs)
    elif method == "discord":
        _notify_discord(**kwargs)
    else:
        _notify_print(**kwargs)
