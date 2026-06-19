from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

EXPECTED_COLUMNS = {
    "Professor / Researcher",
    "Email",
    "University",
    "Best-fit Domain",
}
EMAIL_RE = re.compile(r"^[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9.-]+\.[A-Z]{2,}$", re.IGNORECASE)
GENERIC_LOCAL_PARTS = {
    "admin", "admission", "admissions", "contact", "enquiries", "enquiry",
    "info", "office", "research", "support",
}


@dataclass(frozen=True)
class Professor:
    name: str
    email: str
    university: str
    domain: str


def normalize_email(value: object) -> str:
    return str(value).strip().lower() if value is not None and not pd.isna(value) else ""


def email_skip_reason(value: object) -> str | None:
    email = normalize_email(value)
    if not email:
        return "missing email"
    if "use official profile contact" in email:
        return "official profile contact required"
    if not EMAIL_RE.fullmatch(email):
        return "invalid email address"
    if email.split("@", 1)[0] in GENERIC_LOCAL_PARTS:
        return "non-personal email address"
    return None


def load_professors(csv_path: Path) -> list[tuple[Professor | None, str | None, dict[str, str]]]:
    if not csv_path.is_file():
        raise FileNotFoundError(f"Professor CSV not found: {csv_path}")

    frame = pd.read_csv(csv_path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    missing = EXPECTED_COLUMNS.difference(frame.columns)
    if missing:
        raise ValueError(f"CSV is missing required columns: {', '.join(sorted(missing))}")

    results = []
    for _, row in frame.iterrows():
        raw = {str(key): str(value).strip() for key, value in row.items()}
        reason = email_skip_reason(raw.get("Email"))
        professor = None
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

