"""Typed application configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _int_setting(name: str, default: int, *, minimum: int = 0) -> int:
    """Read an integer environment setting and enforce its lower bound."""
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a whole number, not {raw!r}.") from exc
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}.")
    return value


def _float_setting(name: str, default: float, *, minimum: float = 0) -> float:
    """Read a floating-point environment setting and enforce its lower bound."""
    raw = os.getenv(name, str(default)).strip()
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number, not {raw!r}.") from exc
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}.")
    return value


def _bool_setting(name: str, default: bool) -> bool:
    """Read a conventional boolean environment setting."""
    raw = os.getenv(name, str(default)).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false, not {raw!r}.")


def _project_path(raw_path: str) -> Path:
    """Resolve a path relative to the repository root."""
    path = Path(raw_path).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


@dataclass(frozen=True)
class Settings:
    """Validated, immutable configuration for one application run."""

    email_address: str
    email_app_password: str
    default_mode: str
    daily_limit: int
    cv_path: Path
    csv_path: Path
    template_path: Path
    log_path: Path
    drafts_dir: Path
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 465
    smtp_use_ssl: bool = True
    smtp_use_starttls: bool = False
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_timeout: float = 30.0
    smtp_retries: int = 2
    retry_backoff_seconds: float = 2.0
    send_delay_min: int = 120
    send_delay_max: int = 300
    opt_out_path: Path = PROJECT_ROOT / "private_data" / "opt_out.csv"
    log_level: str = "INFO"
    email_subject: str = "Prospective Master by Research/MPhil Student - Medical AI"

    @property
    def sender_address(self) -> str:
        """Return the configured From address."""
        return self.email_address

    @property
    def auth_username(self) -> str:
        """Return the SMTP username, falling back to the sender address."""
        return self.smtp_username or self.email_address

    @property
    def auth_password(self) -> str:
        """Return the SMTP password, supporting the legacy Gmail variable."""
        return self.smtp_password or self.email_app_password


def load_settings() -> Settings:
    """Load and validate settings from ``.env`` and the process environment."""
    load_dotenv(PROJECT_ROOT / ".env")
    mode = os.getenv("DEFAULT_MODE", "draft_only").strip().lower()
    if mode not in {"draft_only", "send"}:
        raise ValueError("DEFAULT_MODE must be 'draft_only' or 'send'.")

    delay_min = _int_setting("SEND_DELAY_MIN_SECONDS", 120, minimum=120)
    delay_max = _int_setting("SEND_DELAY_MAX_SECONDS", 300, minimum=delay_min)
    use_ssl = _bool_setting("SMTP_USE_SSL", True)
    use_starttls = _bool_setting("SMTP_USE_STARTTLS", False)
    if use_ssl and use_starttls:
        raise ValueError("SMTP_USE_SSL and SMTP_USE_STARTTLS cannot both be true.")

    log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper()
    if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ValueError("LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR, or CRITICAL.")

    email_address = os.getenv("EMAIL_ADDRESS", "").strip()
    app_password = os.getenv("EMAIL_APP_PASSWORD", "").replace(" ", "").strip()
    return Settings(
        email_address=email_address,
        email_app_password=app_password,
        default_mode=mode,
        daily_limit=min(_int_setting("DAILY_LIMIT", 10, minimum=1), 10),
        cv_path=_project_path(os.getenv("CV_PATH", "private_data/cv.pdf")),
        csv_path=_project_path(os.getenv("PROFESSOR_CSV_PATH", "private_data/professors.csv")),
        template_path=_project_path(os.getenv("EMAIL_TEMPLATE_PATH", "private_data/email_template.txt")),
        log_path=_project_path(os.getenv("AUDIT_LOG_PATH", "logs/email_log.csv")),
        drafts_dir=_project_path(os.getenv("DRAFTS_DIR", "logs/drafts")),
        smtp_host=os.getenv("SMTP_HOST", "smtp.gmail.com").strip(),
        smtp_port=_int_setting("SMTP_PORT", 465, minimum=1),
        smtp_use_ssl=use_ssl,
        smtp_use_starttls=use_starttls,
        smtp_username=os.getenv("SMTP_USERNAME", email_address).strip(),
        smtp_password=os.getenv("SMTP_PASSWORD", app_password).replace(" ", "").strip(),
        smtp_timeout=_float_setting("SMTP_TIMEOUT_SECONDS", 30, minimum=1),
        smtp_retries=_int_setting("SMTP_RETRIES", 2, minimum=0),
        retry_backoff_seconds=_float_setting("SMTP_RETRY_BACKOFF_SECONDS", 2, minimum=0),
        send_delay_min=delay_min,
        send_delay_max=delay_max,
        opt_out_path=_project_path(os.getenv("OPT_OUT_PATH", "private_data/opt_out.csv")),
        log_level=log_level,
        email_subject=os.getenv(
            "EMAIL_SUBJECT",
            "Prospective Master by Research/MPhil Student - Medical AI",
        ).strip(),
    )
