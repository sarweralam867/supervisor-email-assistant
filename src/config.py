from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a whole number, not {raw!r}.") from exc
    if value < 1:
        raise ValueError(f"{name} must be at least 1.")
    return value


def _project_path(raw_path: str) -> Path:
    path = Path(raw_path).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


@dataclass(frozen=True)
class Settings:
    email_address: str
    email_app_password: str
    default_mode: str
    daily_limit: int
    cv_path: Path
    csv_path: Path
    template_path: Path
    log_path: Path
    drafts_dir: Path


def load_settings() -> Settings:
    load_dotenv(PROJECT_ROOT / ".env")
    mode = os.getenv("DEFAULT_MODE", "draft_only").strip().lower()
    if mode not in {"draft_only", "send"}:
        raise ValueError("DEFAULT_MODE must be 'draft_only' or 'send'.")

    # Ten is an absolute safety cap even if the environment requests more.
    daily_limit = min(_positive_int("DAILY_LIMIT", 10), 10)
    return Settings(
        email_address=os.getenv("EMAIL_ADDRESS", "").strip(),
        email_app_password=os.getenv("EMAIL_APP_PASSWORD", "").replace(" ", "").strip(),
        default_mode=mode,
        daily_limit=daily_limit,
        cv_path=_project_path(os.getenv("CV_PATH", "private_data/cv.pdf")),
        csv_path=_project_path(os.getenv("PROFESSOR_CSV_PATH", "private_data/professors.csv")),
        template_path=_project_path(os.getenv("EMAIL_TEMPLATE_PATH", "private_data/email_template.txt")),
        log_path=PROJECT_ROOT / "logs" / "email_log.csv",
        drafts_dir=PROJECT_ROOT / "logs" / "drafts",
    )
