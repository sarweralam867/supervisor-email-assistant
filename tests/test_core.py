"""Behavioral tests for parsing, rendering, safety state, and delivery retries."""

from __future__ import annotations

import csv
import io
import smtplib
from argparse import Namespace
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

import pytest

from config import Settings
from email_builder import build_message, extract_last_name, render_body, save_draft
from gmail_sender import SMTPSender
from load_professors import Professor, email_skip_reason, load_professors
from main import (
    blocked_addresses,
    completed_addresses,
    effective_limit,
    load_opt_outs,
    record_opt_out,
    run,
    sent_today,
)


def make_settings(tmp_path: Path, **overrides: object) -> Settings:
    """Create isolated settings suitable for unit tests."""
    values: dict[str, object] = {
        "email_address": "sender@example.com",
        "email_app_password": "secret",
        "default_mode": "draft_only",
        "daily_limit": 10,
        "cv_path": tmp_path / "cv.pdf",
        "csv_path": tmp_path / "professors.csv",
        "template_path": tmp_path / "template.txt",
        "log_path": tmp_path / "email_log.csv",
        "drafts_dir": tmp_path / "drafts",
        "opt_out_path": tmp_path / "opt_out.csv",
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("name", "surname"),
    [
        ("Assoc. Prof. Example Researcher", "Researcher"),
        ("Prof. Erik Meijering", "Meijering"),
        ("Dr Imran Razzak", "Razzak"),
    ],
)
def test_extract_last_name(name: str, surname: str) -> None:
    assert extract_last_name(name) == surname


@pytest.mark.parametrize(
    ("address", "reason"),
    [
        ("Professor.Name@university.edu.au", None),
        ("Use official profile contact", "official profile contact required"),
        ("contact@university.edu.au", "non-personal email address"),
        ("name..dot@example.edu", "invalid email address"),
        ("name@-example.edu", "invalid email address"),
        ("not-an-email", "invalid email address"),
    ],
)
def test_email_validation(address: str, reason: str | None) -> None:
    assert email_skip_reason(address) == reason


def test_csv_parsing_normalizes_and_supplies_domain_fallback(tmp_path: Path) -> None:
    csv_path = tmp_path / "professors.csv"
    csv_path.write_text(
        "Professor / Researcher,Email,University,Best-fit Domain\n"
        "Dr Example Person, PERSON@Example.edu ,Example University,\n",
        encoding="utf-8",
    )

    professor, reason, raw = load_professors(csv_path)[0]

    assert reason is None
    assert professor == Professor(
        "Dr Example Person",
        "person@example.edu",
        "Example University",
        "artificial intelligence and machine learning",
    )
    assert raw["Email"] == "PERSON@Example.edu"


def test_csv_row_errors_are_returned_without_losing_valid_rows(tmp_path: Path) -> None:
    csv_path = tmp_path / "professors.csv"
    csv_path.write_text(
        "Professor / Researcher,Email,University,Best-fit Domain\n"
        ",bad-address,Example University,AI\n"
        "Dr Valid Person,valid@example.edu,Example University,AI\n",
        encoding="utf-8",
    )

    loaded = load_professors(csv_path)

    assert loaded[0][0] is None
    assert loaded[0][1] == "invalid email address"
    assert loaded[1][0] is not None


@pytest.mark.parametrize(
    ("contents", "message"),
    [
        ("", "empty"),
        ("Email,University\na@example.edu,Example\n", "missing required columns"),
        (
            "Professor / Researcher,Email,University,Best-fit Domain\n"
            'Dr Person,"broken,Example,AI\n',
            "malformed",
        ),
    ],
)
def test_malformed_csv_has_clear_error(tmp_path: Path, contents: str, message: str) -> None:
    csv_path = tmp_path / "professors.csv"
    csv_path.write_text(contents, encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        load_professors(csv_path)


def test_template_rendering_uses_strict_fields(tmp_path: Path) -> None:
    template = tmp_path / "template.txt"
    template.write_text("Dear Professor {{ last_name }},\nResearch: {{ domain }}", encoding="utf-8")
    professor = Professor("Assoc. Prof. Example Researcher", "person@example.edu", "Example", "Medical AI")

    body = render_body(template, professor)

    assert body == "Dear Professor Researcher,\nResearch: Medical AI\n"


def test_template_rendering_rejects_unknown_variables(tmp_path: Path) -> None:
    template = tmp_path / "template.txt"
    template.write_text("Hello {{ unknown_value }}", encoding="utf-8")
    professor = Professor("Dr Example Person", "person@example.edu", "Example", "AI")
    with pytest.raises(Exception, match="unknown_value"):
        render_body(template, professor)


def test_duplicate_detection_is_case_insensitive() -> None:
    rows = [
        {"email": "Name@Example.edu", "status": "drafted"},
        {"email": "other@example.edu", "status": "error"},
    ]
    assert completed_addresses(rows) == {"name@example.edu"}


def test_opt_out_state_and_registry_are_case_insensitive(tmp_path: Path) -> None:
    path = tmp_path / "opt_out.csv"
    assert record_opt_out(path, "Person@Example.edu") is True
    assert record_opt_out(path, "person@example.edu") is False
    assert load_opt_outs(path) == {"person@example.edu"}
    assert blocked_addresses([{"email": "PERSON@example.edu", "status": "opted_out"}]) == {
        "person@example.edu"
    }
    with path.open(newline="", encoding="utf-8") as handle:
        assert len(list(csv.DictReader(handle))) == 1


def test_daily_limit_is_hard_capped_and_counts_prior_sends(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    rows = [
        {"timestamp": datetime.now().astimezone().isoformat(), "status": "sent"}
        for _ in range(3)
    ]
    assert sent_today(rows) == 3
    assert effective_limit(Namespace(limit=99, mode="send"), settings, rows) == 7


def test_build_and_save_eml_with_pdf_attachment(tmp_path: Path) -> None:
    professor = Professor(
        "Assoc. Prof. Example Researcher",
        "researcher@example.edu",
        "Example",
        "Medical AI",
    )
    template = tmp_path / "template.txt"
    cv = tmp_path / "cv.pdf"
    template.write_text("Dear Professor {{ last_name }},\nResearch: {{ domain }}", encoding="utf-8")
    cv.write_bytes(b"%PDF-1.4\n%%EOF")

    message = build_message(professor, "sender@example.com", template, cv)
    draft = save_draft(message, professor, tmp_path / "drafts")

    assert draft.is_file()
    assert message["To"] == professor.email
    assert "Dear Professor Researcher" in message.get_body(preferencelist=("plain",)).get_content()
    attachments = list(message.iter_attachments())
    assert len(attachments) == 1
    assert attachments[0].get_filename() == "cv.pdf"


def test_smtp_sender_retries_transient_delivery(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    settings = make_settings(tmp_path, smtp_retries=1, retry_backoff_seconds=0)
    sender = SMTPSender(settings, sleep=lambda _: None)
    attempts = 0

    class FakeSMTP:
        def send_message(self, message: EmailMessage) -> None:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise smtplib.SMTPServerDisconnected("temporary disconnect")

        def quit(self) -> None:
            return None

        def close(self) -> None:
            return None

    monkeypatch.setattr(sender, "_connect", lambda: setattr(sender, "_smtp", FakeSMTP()))
    message = EmailMessage()
    message["To"] = "person@example.edu"

    sender.send(message)

    assert attempts == 2


def test_preview_renders_without_cv_or_generated_files(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    settings.csv_path.write_text(
        "Professor / Researcher,Email,University,Best-fit Domain\n"
        "Dr Example Person,person@example.edu,Example University,Medical AI\n",
        encoding="utf-8",
    )
    settings.template_path.write_text(
        "Dear Professor {{ last_name }}, {{ domain }}",
        encoding="utf-8",
    )
    output = io.StringIO()

    result = run(
        settings,
        Namespace(mode="preview", preview=False, limit=1, opt_out=None),
        output=output,
    )

    assert result == 0
    assert "Dear Professor Person, Medical AI" in output.getvalue()
    assert not settings.cv_path.exists()
    assert not settings.log_path.exists()
    assert not settings.drafts_dir.exists()


def test_public_sample_csv_schema_loads() -> None:
    root = Path(__file__).resolve().parents[1]
    assert load_professors(root / "examples" / "professors.sample.csv") == []
