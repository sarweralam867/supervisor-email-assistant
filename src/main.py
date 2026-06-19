from __future__ import annotations

import argparse
import csv
import random
import smtplib
import sys
import time
from contextlib import nullcontext
from datetime import datetime
from pathlib import Path

from config import Settings, load_settings
from email_builder import build_message, save_draft
from gmail_sender import GmailSender
from load_professors import Professor, load_professors, normalize_email

LOG_FIELDS = [
    "timestamp", "professor_name", "email", "university", "mode", "status", "error_message"
]


def parse_args(settings: Settings) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create or send personalized professor outreach emails.")
    parser.add_argument("--mode", choices=("draft_only", "send"), default=settings.default_mode)
    parser.add_argument("--limit", type=int, help="Maximum emails for this run (hard-capped at 10).")
    return parser.parse_args()


def ensure_log(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if not log_path.exists() or log_path.stat().st_size == 0:
        with log_path.open("w", newline="", encoding="utf-8") as handle:
            csv.DictWriter(handle, fieldnames=LOG_FIELDS).writeheader()


def read_log(log_path: Path) -> list[dict[str, str]]:
    ensure_log(log_path)
    with log_path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def append_log(
    log_path: Path,
    professor_name: str,
    email: str,
    university: str,
    mode: str,
    status: str,
    error_message: str = "",
) -> None:
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
    return {
        normalize_email(row.get("email", ""))
        for row in rows
        if row.get("status", "").lower() in {"drafted", "sent"}
    }


def sent_today(rows: list[dict[str, str]]) -> int:
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
    requested = settings.daily_limit if args.limit is None else args.limit
    if requested < 1:
        raise ValueError("--limit must be at least 1.")
    limit = min(requested, settings.daily_limit, 10)
    if args.mode == "send":
        limit = min(limit, max(0, settings.daily_limit - sent_today(log_rows)), max(0, 10 - sent_today(log_rows)))
    return limit


def raw_identity(raw: dict[str, str]) -> tuple[str, str, str]:
    return (
        raw.get("Professor / Researcher", ""),
        raw.get("Email", ""),
        raw.get("University", ""),
    )


def run(settings: Settings, args: argparse.Namespace) -> int:
    rows = read_log(settings.log_path)
    limit = effective_limit(args, settings, rows)
    if args.mode == "send":
        if limit == 0:
            print("Daily sending limit has already been reached. No emails sent.")
            return 0
        confirmation = input("Type SEND to confirm real email sending: ")
        if confirmation != "SEND":
            print("Confirmation not received. No emails sent.")
            return 0
        if not settings.email_address or not settings.email_app_password:
            raise ValueError("EMAIL_ADDRESS and EMAIL_APP_PASSWORD are required for send mode.")

    processed = completed_addresses(rows)
    candidates: list[Professor] = []
    for professor, reason, raw in load_professors(settings.csv_path):
        name, email, university = raw_identity(raw)
        normalized = normalize_email(email)
        if reason:
            append_log(settings.log_path, name, email, university, args.mode, "skipped", reason)
            print(f"SKIP {name or '<unknown>'}: {reason}")
        elif normalized in processed:
            append_log(settings.log_path, name, email, university, args.mode, "skipped", "duplicate: already drafted or sent")
            print(f"SKIP {name}: already drafted or sent")
        elif professor is not None:
            candidates.append(professor)
            processed.add(normalized)

    candidates = candidates[:limit]
    if not candidates:
        print("No eligible emails to process.")
        return 0

    sender_address = settings.email_address or "draft-review@example.invalid"
    context = GmailSender(settings.email_address, settings.email_app_password) if args.mode == "send" else nullcontext()
    completed = 0
    try:
        with context as gmail:
            for index, professor in enumerate(candidates):
                try:
                    message = build_message(professor, sender_address, settings.template_path, settings.cv_path)
                    if args.mode == "draft_only":
                        path = save_draft(message, professor, settings.drafts_dir)
                        status = "drafted"
                        print(f"DRAFT {professor.email}: {path}")
                    else:
                        gmail.send(message)
                        status = "sent"
                        print(f"SENT {professor.email}")
                    append_log(settings.log_path, professor.name, professor.email, professor.university, args.mode, status)
                    completed += 1
                    if args.mode == "send" and index < len(candidates) - 1:
                        delay = random.randint(120, 300)
                        print(f"Waiting {delay} seconds before the next email...")
                        time.sleep(delay)
                except (OSError, ValueError, smtplib.SMTPException) as exc:
                    append_log(
                        settings.log_path, professor.name, professor.email, professor.university,
                        args.mode, "error", str(exc),
                    )
                    print(f"ERROR {professor.email}: {exc}", file=sys.stderr)
    except (OSError, smtplib.SMTPException) as exc:
        print(f"Gmail connection failed: {exc}", file=sys.stderr)
        return 1

    print(f"Completed {completed} of {len(candidates)} eligible email(s) in {args.mode} mode.")
    return 0 if completed == len(candidates) else 1


def main() -> int:
    try:
        settings = load_settings()
        args = parse_args(settings)
        return run(settings, args)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
