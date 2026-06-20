"""Generate a private local page for reviewing completed email drafts."""

from __future__ import annotations

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


def gmail_compose_url(message: EmailMessage) -> str:
    """Build a Gmail compose link; browser links cannot include attachments."""
    query = urlencode({
        "view": "cm",
        "fs": "1",
        "to": str(message.get("To", "")),
        "su": str(message.get("Subject", "")),
        "body": _plain_body(message),
    })
    return f"https://mail.google.com/mail/?{query}"


def save_review_page(
    messages: Sequence[EmailMessage],
    path: Path,
    cv_path: Path,
) -> Path:
    """Save an escaped local HTML review page and return its path."""
    cards: list[str] = []
    for index, message in enumerate(messages, start=1):
        recipient = escape(str(message.get("To", "")))
        subject = escape(str(message.get("Subject", "")))
        body = escape(_plain_body(message))
        gmail_url = escape(gmail_compose_url(message), quote=True)
        cards.append(
            f"""<article>
<h2>{index}. {recipient}</h2>
<p><strong>Subject:</strong> {subject}</p>
<pre>{body}</pre>
<a class="button" href="{gmail_url}" target="_blank" rel="noopener noreferrer">Open in Gmail</a>
</article>"""
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
.notice {{ padding: 1rem; border: 2px solid #b66a00; background: #fff7e6; border-radius: .5rem; }}
article {{ margin: 1.5rem 0; padding: 1.25rem; border: 1px solid #ccc; border-radius: .5rem; }}
pre {{ white-space: pre-wrap; font: inherit; background: #f6f8fa; padding: 1rem; border-radius: .4rem; }}
.button {{
  display: inline-block; padding: .65rem 1rem; color: white; background: #1769aa;
  border-radius: .4rem; text-decoration: none;
}}
</style>
</head>
<body>
<h1>Review your email drafts</h1>
<div class="notice"><strong>Nothing has been sent.</strong> Complete `.eml` drafts with the CV attached are
in this folder. Gmail links prefill the recipient, subject, and body, but Gmail cannot attach a local file
through a browser link. Attach <strong>{escape(cv_path.name)}</strong> before sending from Gmail.</div>
{''.join(cards)}
</body>
</html>
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(document, encoding="utf-8")
    return path


def open_review_page(path: Path, opener: Callable[[str], bool] = webbrowser.open) -> bool:
    """Open a local review page in the user's default browser."""
    return opener(path.resolve().as_uri())
