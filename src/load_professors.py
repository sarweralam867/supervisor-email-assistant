"""CSV parsing and validation for professor records."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias

import pandas as pd
from pandas.errors import EmptyDataError, ParserError

EXPECTED_COLUMNS = {
    "Professor / Researcher",
    "Email",
    "University",
    "Best-fit Domain",
}
LOCAL_RE = re.compile(r"^[A-Z0-9!#$%&'*+/=?^_`{|}~.-]{1,64}$", re.IGNORECASE)
DOMAIN_LABEL_RE = re.compile(r"^[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?$", re.IGNORECASE)
GENERIC_LOCAL_PARTS = {
    "admin", "admission", "admissions", "contact", "enquiries", "enquiry",
    "info", "office", "research", "support",
}


@dataclass(frozen=True)
class Professor:
    """One validated outreach recipient."""

    name: str
    email: str
    university: str
    domain: str


ProfessorLoadResult: TypeAlias = tuple[Professor | None, str | None, dict[str, str]]


def normalize_email(value: object) -> str:
    """Normalize a possibly missing CSV value into a lowercase address."""
    return str(value).strip().lower() if value is not None and not pd.isna(value) else ""


def is_valid_email(email: str) -> bool:
    """Validate practical SMTP address syntax without accepting display names."""
    if len(email) > 254 or email.count("@") != 1 or any(char.isspace() for char in email):
        return False
    local, domain = email.rsplit("@", 1)
    if not LOCAL_RE.fullmatch(local) or local.startswith(".") or local.endswith(".") or ".." in local:
        return False
    labels = domain.split(".")
    return (
        len(labels) >= 2
        and len(labels[-1]) >= 2
        and all(DOMAIN_LABEL_RE.fullmatch(label) for label in labels)
    )


def email_skip_reason(value: object) -> str | None:
    """Return a human-readable reason when an address must not be used."""
    email = normalize_email(value)
    if not email:
        return "missing email"
    if "use official profile contact" in email:
        return "official profile contact required"
    if not is_valid_email(email):
        return "invalid email address"
    if email.split("@", 1)[0] in GENERIC_LOCAL_PARTS:
        return "non-personal email address"
    return None


def load_professors(csv_path: Path) -> list[ProfessorLoadResult]:
    """Load professor rows, returning valid records and row-level skip reasons.

    File-level problems are converted into concise ``ValueError`` messages so the
    CLI never exposes a pandas traceback for a malformed input file.
    """
    if not csv_path.is_file():
        raise FileNotFoundError(f"Professor CSV not found: {csv_path}")
    try:
        frame = pd.read_csv(csv_path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    except EmptyDataError as exc:
        raise ValueError("Professor CSV is empty or has no header row.") from exc
    except (ParserError, UnicodeDecodeError) as exc:
        raise ValueError(f"Professor CSV is malformed or is not UTF-8: {exc}") from exc

    frame.columns = [str(column).strip() for column in frame.columns]
    if frame.columns.duplicated().any():
        duplicates = sorted(set(frame.columns[frame.columns.duplicated()]))
        raise ValueError(f"CSV contains duplicate columns: {', '.join(duplicates)}")
    missing = EXPECTED_COLUMNS.difference(frame.columns)
    if missing:
        raise ValueError(f"CSV is missing required columns: {', '.join(sorted(missing))}")

    results: list[ProfessorLoadResult] = []
    for _, row in frame.iterrows():
        raw = {str(key): str(value).strip() for key, value in row.items()}
        reason = email_skip_reason(raw.get("Email"))
        professor: Professor | None = None
        if not reason:
            name = raw.get("Professor / Researcher", "")
            if not name:
                reason = "missing professor name"
            else:
                professor = Professor(
                    name=name,
                    email=normalize_email(raw["Email"]),
                    university=raw.get("University", ""),
                    domain=raw.get("Best-fit Domain", "") or "artificial intelligence and machine learning",
                )
        results.append((professor, reason, raw))
    return results
