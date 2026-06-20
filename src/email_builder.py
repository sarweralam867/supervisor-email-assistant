from __future__ import annotations

import re
from email.message import EmailMessage
from pathlib import Path

from jinja2 import Environment, StrictUndefined

from load_professors import Professor

SUBJECT = "Prospective Master by Research/MPhil Student - Medical AI"
TITLE_RE = re.compile(
    r"^(?:(?:assoc(?:iate)?\.?|asst\.?|assistant|emeritus)\s+)?"
    r"(?:prof(?:essor)?\.?|dr\.?|mr\.?|mrs\.?|ms\.?)\s+",
    re.IGNORECASE,
)


def extract_last_name(full_name: str) -> str:
    """Extract a surname after removing common academic titles."""
    cleaned = full_name.strip()
    previous = None
    while cleaned and cleaned != previous:
        previous = cleaned
        cleaned = TITLE_RE.sub("", cleaned).strip()
    parts = cleaned.split()
    if not parts:
        raise ValueError("Professor name is empty after removing the title.")
    return parts[-1].strip(",")


def render_body(template_path: Path, professor: Professor) -> str:
    """Render a strict Jinja email template for a professor."""
    if not template_path.is_file():
        raise FileNotFoundError(f"Email template not found: {template_path}")
    template = Environment(undefined=StrictUndefined, autoescape=False).from_string(
        template_path.read_text(encoding="utf-8")
    )
    rendered = template.render(
        last_name=extract_last_name(professor.name),
        domain=professor.domain,
    )
    return rendered.strip() + "\n"


def build_message(
    professor: Professor,
    sender: str,
    template_path: Path,
    cv_path: Path,
    subject: str = SUBJECT,
) -> EmailMessage:
    """Build a plain-text MIME message with a PDF CV attachment."""
    if not cv_path.is_file():
        raise FileNotFoundError(f"CV not found: {cv_path}")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = professor.email
    message.set_content(render_body(template_path, professor))
    message.add_attachment(
        cv_path.read_bytes(),
        maintype="application",
        subtype="pdf",
        filename=cv_path.name,
    )
    return message


def safe_draft_filename(professor: Professor) -> str:
    """Create a portable draft filename from recipient identity."""
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", f"{professor.name}_{professor.email}").strip("_")
    return f"{base}.eml"


def save_draft(message: EmailMessage, professor: Professor, drafts_dir: Path) -> Path:
    """Save a MIME message as an ``.eml`` draft and return its path."""
    drafts_dir.mkdir(parents=True, exist_ok=True)
    path = drafts_dir / safe_draft_filename(professor)
    path.write_bytes(message.as_bytes())
    return path
