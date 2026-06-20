"""Command-line orchestration for safe professor outreach."""

from __future__ import annotations

import argparse
import csv
import logging
import random
import smtplib
import sys
import time
from collections.abc import Sequence
from contextlib import AbstractContextManager, nullcontext
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import TextIO, cast

from config import Settings, load_settings
from email_builder import build_message, render_body, save_draft
from gmail_sender import SMTPSender
from load_professors import Professor, email_skip_reason, load_professors, normalize_email
from review_page import open_review_page, save_review_page

LOGGER = logging.getLogger("supervisor_email_assistant")
LOG_FIELDS = [
    "timestamp", "professor_name", "email", "university", "mode", "status", "error_message"
]
OPT_OUT_FIELDS = ["email", "timestamp", "reason"]
COMPLETED_STATUSES = {"drafted", "sent"}
BLOCKED_STATUSES = {"opted_out", "unsubscribed"}


def configure_logging(level: str) -> None:
    """Configure concise level-aware console logging."""
    logging.basicConfig(level=getattr(logging, level), format="%(levelname)s: %(message)s")


def parse_args(settings: Settings, argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI options while preserving the original mode-based interface."""
    parser = argparse.ArgumentParser(
        description="Preview, draft, or send personalized professor outreach emails."
    )
    parser.add_argument("--mode", choices=("preview", "draft_only", "send"), default=settings.default_mode)
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Preview rendered messages without creating files.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Maximum emails for this run; real sending is always capped at 10 per day.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process every eligible record in preview or draft mode; never allowed for sending.",
    )
    parser.add_argument(
        "--open-drafts",
        action="store_true",
        help="Open the private local review page after creating drafts.",
    )
    parser.add_argument("--opt-out", metavar="EMAIL", help="Record an address that must never be contacted.")
    return parser.parse_args(argv)


def ensure_log(log_path: Path) -> None:
    """Create the private CSV audit log with its schema when needed."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if not log_path.exists() or log_path.stat().st_size == 0:
        with log_path.open("w", newline="", encoding="utf-8") as handle:
            csv.DictWriter(handle, fieldnames=LOG_FIELDS).writeheader()


def read_log(log_path: Path) -> list[dict[str, str]]:
    """Read audit rows, rejecting a malformed log header clearly."""
    if not log_path.exists():
        return []
    with log_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not set(LOG_FIELDS).issubset(reader.fieldnames):
            raise ValueError(f"Audit log has an invalid header: {log_path}")
        return list(reader)


def append_log(
    log_path: Path,
    professor_name: str,
    email: str,
    university: str,
    mode: str,
    status: str,
    error_message: str = "",
) -> None:
    """Append one processing result to the private CSV audit trail."""
    ensure_log(log_path)
    row = {
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "professor_name": professor_name,
        "email": normalize_email(email),
        "university": university,
        "mode": mode,
        "status": status,
        "error_message": error_message,
    }
    with log_path.open("a", newline="", encoding="utf-8") as handle:
        csv.DictWriter(handle, fieldnames=LOG_FIELDS).writerow(row)


def completed_addresses(rows: list[dict[str, str]]) -> set[str]:
    """Return normalized addresses already drafted or sent."""
    return {
        normalize_email(row.get("email", ""))
        for row in rows
        if row.get("status", "").lower() in COMPLETED_STATUSES
    }


def blocked_addresses(rows: list[dict[str, str]]) -> set[str]:
    """Return normalized addresses with opt-out states in the audit log."""
    return {
        normalize_email(row.get("email", ""))
        for row in rows
        if row.get("status", "").lower() in BLOCKED_STATUSES
    }


def load_opt_outs(path: Path) -> set[str]:
    """Load the private opt-out registry, tolerating a missing file."""
    if not path.exists():
        return set()
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or "email" not in reader.fieldnames:
                raise ValueError(f"Opt-out file has an invalid header: {path}")
            return {normalize_email(row.get("email", "")) for row in reader if row.get("email")}
    except csv.Error as exc:
        raise ValueError(f"Opt-out file is malformed: {path}: {exc}") from exc


def record_opt_out(path: Path, email: str, reason: str = "manual opt-out") -> bool:
    """Persist an opt-out address; return false when it was already present."""
    normalized = normalize_email(email)
    validation_error = email_skip_reason(normalized)
    if validation_error:
        raise ValueError(f"Cannot record opt-out: {validation_error}.")
    if normalized in load_opt_outs(path):
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OPT_OUT_FIELDS)
        if write_header:
            writer.writeheader()
        writer.writerow({
            "email": normalized,
            "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
            "reason": reason,
        })
    return True


def sent_today(rows: list[dict[str, str]]) -> int:
    """Count successful sends on the current local calendar day."""
    today = datetime.now().astimezone().date()
    count = 0
    for row in rows:
        if row.get("status", "").lower() != "sent":
            continue
        try:
            timestamp = datetime.fromisoformat(row["timestamp"])
        except (KeyError, TypeError, ValueError):
            continue
        if timestamp.astimezone().date() == today:
            count += 1
    return count


def effective_limit(args: argparse.Namespace, settings: Settings, log_rows: list[dict[str, str]]) -> int:
    """Apply the requested limit, configured limit, and absolute daily cap."""
    process_all = getattr(args, "all", False)
    if process_all:
        if args.mode == "send":
            raise ValueError("--all cannot be used for real sending; the daily cap is 10.")
        return sys.maxsize
    requested = settings.daily_limit if args.limit is None else args.limit
    if requested < 1:
        raise ValueError("--limit must be at least 1.")
    if args.mode == "send":
        prior_sends = sent_today(log_rows)
        return min(
            requested,
            settings.daily_limit,
            10,
            max(0, settings.daily_limit - prior_sends),
            max(0, 10 - prior_sends),
        )
    return requested


def raw_identity(raw: dict[str, str]) -> tuple[str, str, str]:
    """Extract identity fields from a raw professor row."""
    return (
        raw.get("Professor / Researcher", ""),
        raw.get("Email", ""),
        raw.get("University", ""),
    )


def preview_professors(professors: Sequence[Professor], template_path: Path, output: TextIO) -> None:
    """Write rendered messages to stdout without creating drafts or attachments."""
    for index, professor in enumerate(professors, start=1):
        body = render_body(template_path, professor)
        output.write(f"\n--- Preview {index}: {professor.name} <{professor.email}> ---\n{body}")


def run(settings: Settings, args: argparse.Namespace, *, output: TextIO = sys.stdout) -> int:
    """Execute opt-out recording, previewing, drafting, or confirmed sending."""
    if args.opt_out:
        added = record_opt_out(settings.opt_out_path, args.opt_out)
        append_log(settings.log_path, "", args.opt_out, "", "opt_out", "opted_out", "manual opt-out")
        LOGGER.info(
            "%s is %s the opt-out registry.",
            normalize_email(args.opt_out),
            "now in" if added else "already in",
        )
        return 0

    if args.preview:
        args.mode = "preview"
    rows = read_log(settings.log_path)
    limit = effective_limit(args, settings, rows)
    if args.mode == "send":
        if limit == 0:
            LOGGER.warning("Daily sending limit has already been reached. No emails sent.")
            return 0
        confirmation = input("Type SEND to confirm real email sending: ")
        if confirmation != "SEND":
            LOGGER.warning("Confirmation not received. No emails sent.")
            return 0
        if not settings.sender_address or not settings.auth_password:
            raise ValueError("EMAIL_ADDRESS and SMTP_PASSWORD are required for send mode.")

    processed = completed_addresses(rows)
    opted_out = blocked_addresses(rows) | load_opt_outs(settings.opt_out_path)
    candidates: list[Professor] = []
    for professor, reason, raw in load_professors(settings.csv_path):
        name, email, university = raw_identity(raw)
        normalized = normalize_email(email)
        if normalized in opted_out:
            reason = "recipient opted out"
            if args.mode != "preview":
                append_log(settings.log_path, name, email, university, args.mode, "opted_out", reason)
            LOGGER.warning("SKIP %s: %s", name or "<unknown>", reason)
        elif reason:
            if args.mode != "preview":
                append_log(settings.log_path, name, email, university, args.mode, "skipped", reason)
            LOGGER.warning("SKIP %s: %s", name or "<unknown>", reason)
        elif normalized in processed:
            if args.mode != "preview":
                append_log(
                    settings.log_path,
                    name,
                    email,
                    university,
                    args.mode,
                    "skipped",
                    "duplicate: already drafted or sent",
                )
            LOGGER.warning("SKIP %s: already drafted or sent", name)
        elif professor is not None:
            candidates.append(professor)
            processed.add(normalized)

    candidates = candidates[:limit]
    if not candidates:
        LOGGER.info("No eligible emails to process.")
        existing_review = settings.drafts_dir / "review.html"
        if args.mode == "draft_only" and getattr(args, "open_drafts", False) and existing_review.is_file():
            open_review_page(existing_review)
        return 0
    if args.mode == "preview":
        preview_professors(candidates, settings.template_path, output)
        LOGGER.info("Previewed %d eligible email(s); no files created and nothing sent.", len(candidates))
        return 0

    sender_address = settings.sender_address or "draft-review@example.invalid"
    context: AbstractContextManager[SMTPSender | None]
    context = SMTPSender(settings) if args.mode == "send" else nullcontext()
    completed = 0
    draft_messages: list[EmailMessage] = []
    try:
        with context as smtp:
            for index, professor in enumerate(candidates):
                try:
                    message = build_message(
                        professor,
                        sender_address,
                        settings.template_path,
                        settings.cv_path,
                        settings.email_subject,
                    )
                    if args.mode == "draft_only":
                        path = save_draft(message, professor, settings.drafts_dir)
                        draft_messages.append(message)
                        status = "drafted"
                        LOGGER.info("DRAFT %s: %s", professor.email, path)
                    else:
                        cast(SMTPSender, smtp).send(cast(EmailMessage, message))
                        status = "sent"
                        LOGGER.info("SENT %s", professor.email)
                    append_log(
                        settings.log_path,
                        professor.name,
                        professor.email,
                        professor.university,
                        args.mode,
                        status,
                    )
                    completed += 1
                    if args.mode == "send" and index < len(candidates) - 1:
                        delay = random.randint(settings.send_delay_min, settings.send_delay_max)
                        LOGGER.info("Waiting %d seconds before the next email.", delay)
                        time.sleep(delay)
                except (OSError, ValueError, RuntimeError, smtplib.SMTPException) as exc:
                    append_log(
                        settings.log_path, professor.name, professor.email, professor.university,
                        args.mode, "error", str(exc),
                    )
                    LOGGER.error("Could not process %s: %s", professor.email, exc)
    except (OSError, RuntimeError, smtplib.SMTPException) as exc:
        LOGGER.error("SMTP connection failed: %s", exc)
        return 1

    if draft_messages:
        review_path = save_review_page(
            draft_messages,
            settings.drafts_dir / "review.html",
            settings.cv_path,
        )
        LOGGER.info("REVIEW PAGE: %s", review_path)
        if getattr(args, "open_drafts", False) and not open_review_page(review_path):
            LOGGER.warning("Could not open the browser automatically. Open this file: %s", review_path)

    LOGGER.info("Completed %d of %d eligible email(s) in %s mode.", completed, len(candidates), args.mode)
    return 0 if completed == len(candidates) else 1


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point with concise configuration and input errors."""
    try:
        settings = load_settings()
        configure_logging(settings.log_level)
        args = parse_args(settings, argv)
        return run(settings, args)
    except (FileNotFoundError, ValueError, PermissionError) as exc:
        LOGGER.error("Configuration or input error: %s", exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
