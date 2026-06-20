"""Generate and open private local email drafts for review."""

from __future__ import annotations

import os
import subprocess
import sys
import webbrowser
from collections.abc import Callable, Sequence
from email.message import EmailMessage
from html import escape
from pathlib import Path
from urllib.parse import urlencode


def _plain_body(message: EmailMessage) -> str:
    """Extract the plain-text body from a draft message."""
    body = message.get_body(preferencelist=("plain",))
    return body.get_content().strip() if body is not None else ""


def save_review_page(
    messages: Sequence[EmailMessage],
    draft_paths: Sequence[Path],
    path: Path,
    cv_path: Path,
    *,
    browser_compose: bool = False,
) -> Path:
    """Save an escaped local HTML index listing complete ``.eml`` drafts."""
    if len(messages) != len(draft_paths):
        raise ValueError("Each review message must have a matching draft path.")

    cards: list[str] = []
    for index, (message, draft_path) in enumerate(zip(messages, draft_paths, strict=True), start=1):
        recipient = escape(str(message.get("To", "")))
        subject = escape(str(message.get("Subject", "")))
        body = escape(_plain_body(message))
        draft_name = escape(draft_path.name)
        compose_url = "https://mail.google.com/mail/?" + urlencode({
            "view": "cm",
            "fs": "1",
            "to": str(message.get("To", "")),
            "su": str(message.get("Subject", "")),
            "body": _plain_body(message),
        })
        compose_button = (
            f'<p><a class="button" href="{escape(compose_url, quote=True)}" target="_blank" '
            'rel="noopener">Open in Gmail</a> <strong>Then attach your CV manually.</strong></p>'
            if browser_compose
            else ""
        )
        cards.append(
            f"""<article>
<h2>{index}. {recipient}</h2>
<p><strong>Subject:</strong> {subject}</p>
<pre>{body}</pre>
<p><strong>Draft file:</strong> {draft_name}</p>
{compose_button}
</article>"""
        )

    if browser_compose:
        notice = (
            "Click <strong>Open in Gmail</strong>, attach "
            f"<strong>{escape(cv_path.name)}</strong> manually, review, and send."
        )
    else:
        notice = (
            f"Every `.eml` draft contains <strong>{escape(cv_path.name)}</strong>. "
            "Open a draft in your desktop email application, review it, and send it yourself."
        )

    document = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Email draft review</title>
<style>
body {{
  font-family: system-ui, sans-serif; max-width: 920px; margin: 2rem auto;
  padding: 0 1rem; line-height: 1.5;
}}
.notice {{ padding: 1rem; border: 2px solid #287a3e; background: #effaf2; border-radius: .5rem; }}
article {{ margin: 1.5rem 0; padding: 1.25rem; border: 1px solid #ccc; border-radius: .5rem; }}
pre {{ white-space: pre-wrap; font: inherit; background: #f6f8fa; padding: 1rem; border-radius: .4rem; }}
.button {{ display: inline-block; padding: .65rem 1rem; color: white; background: #1769aa;
  text-decoration: none; border-radius: .4rem; }}
</style>
</head>
<body>
<h1>Review your complete email drafts</h1>
<div class="notice"><strong>Nothing has been sent.</strong> {notice}</div>
{''.join(cards)}
</body>
</html>
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(document, encoding="utf-8")
    return path


def open_email_draft(
    path: Path,
    opener: Callable[[Path], None] | None = None,
) -> bool:
    """Open an ``.eml`` file with the operating system's default application."""
    try:
        if opener is not None:
            opener(path.resolve())
        elif os.name == "nt":
            os.startfile(str(path.resolve()))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path.resolve())])
        else:
            subprocess.Popen(["xdg-open", str(path.resolve())])
    except (OSError, TypeError):
        return False
    return True


def open_drafts_folder(
    path: Path,
    opener: Callable[[Path], None] | None = None,
) -> bool:
    """Open the generated drafts directory in the operating system's file manager."""
    return open_email_draft(path, opener)


def open_review_page(path: Path, opener: Callable[[str], bool] = webbrowser.open) -> bool:
    """Open a local review index in the user's default browser."""
    return opener(path.resolve().as_uri())
