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

import draft_launcher
import main as main_module
from config import Settings, load_subject
from email_builder import build_message, extract_last_name, render_body, save_draft
from gmail_sender import SMTPSender
from load_professors import Professor, email_skip_reason, load_professors
from main import (
    append_log,
    blocked_addresses,
    clear_generated_drafts,
    completed_addresses,
    effective_limit,
    load_opt_outs,
    record_opt_out,
    run,
    sent_addresses,
    sent_today,
)
from review_page import open_drafts_folder, open_email_draft, open_review_page, save_review_page


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


def test_sent_addresses_excludes_draft_only_state() -> None:
    rows = [
        {"email": "draft@example.edu", "status": "drafted"},
        {"email": "sent@example.edu", "status": "sent"},
    ]
    assert sent_addresses(rows) == {"sent@example.edu"}


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


def test_all_is_allowed_for_drafts_but_never_sending(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    assert effective_limit(Namespace(limit=None, mode="draft_only", all=True), settings, []) > 1_000_000
    with pytest.raises(ValueError, match="cannot be used for real sending"):
        effective_limit(Namespace(limit=None, mode="send", all=True), settings, [])


def test_subject_file_is_private_single_line_configuration(tmp_path: Path) -> None:
    subject_path = tmp_path / "subject.txt"
    subject_path.write_text("A focused research enquiry\n", encoding="utf-8")
    assert load_subject(subject_path) == "A focused research enquiry"

    subject_path.write_text("First line\nSecond line", encoding="utf-8")
    with pytest.raises(ValueError, match="single line"):
        load_subject(subject_path)


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
    assert message["X-Unsent"] == "1"
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


def test_smtp_sender_does_not_retry_authentication_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = make_settings(tmp_path, smtp_retries=3, retry_backoff_seconds=0)
    sleeps: list[float] = []
    sender = SMTPSender(settings, sleep=sleeps.append)
    attempts = 0

    def reject_login() -> None:
        nonlocal attempts
        attempts += 1
        raise smtplib.SMTPAuthenticationError(535, b"bad credentials")

    monkeypatch.setattr(sender, "_connect", reject_login)
    with pytest.raises(RuntimeError, match=r"rejected \(535\)"):
        sender.__enter__()
    assert attempts == 1
    assert sleeps == []


def test_review_page_escapes_content_and_opens_local_file(tmp_path: Path) -> None:
    message = EmailMessage()
    message["To"] = "person@example.edu"
    message["Subject"] = "Research <discussion>"
    message.set_content("Hello <script>alert('no')</script>")
    draft_path = tmp_path / "person.eml"
    draft_path.write_bytes(message.as_bytes())
    review_path = save_review_page(
        [message],
        [draft_path],
        tmp_path / "review.html",
        tmp_path / "cv.pdf",
    )
    page = review_path.read_text(encoding="utf-8")

    assert "Hello &lt;script&gt;" in page
    assert "<script>alert" not in page
    assert "Draft file:" in page
    assert draft_path.name in page
    assert "Open in Gmail" not in page

    opened: list[str] = []
    assert open_review_page(review_path, lambda url: opened.append(url) or True)
    assert opened == [review_path.resolve().as_uri()]

    opened_drafts: list[Path] = []
    assert open_email_draft(draft_path, opened_drafts.append)
    assert opened_drafts == [draft_path.resolve()]

    opened_folders: list[Path] = []
    assert open_drafts_folder(tmp_path, opened_folders.append)
    assert opened_folders == [tmp_path.resolve()]


def test_all_draft_mode_creates_every_draft_and_opens_first(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = make_settings(tmp_path, email_subject="Research enquiry")
    settings.csv_path.write_text(
        "Professor / Researcher,Email,University,Best-fit Domain\n"
        "Dr First Person,first@example.edu,Example University,Medical AI\n"
        "Dr Second Person,second@example.edu,Example University,Computer Vision\n",
        encoding="utf-8",
    )
    settings.template_path.write_text("Dear Professor {{ last_name }}, {{ domain }}", encoding="utf-8")
    settings.cv_path.write_bytes(b"%PDF-1.4\n%%EOF")
    opened_drafts: list[Path] = []
    opened_folders: list[Path] = []
    monkeypatch.setattr(
        main_module,
        "open_email_draft",
        lambda path: opened_drafts.append(path) or True,
    )
    monkeypatch.setattr(
        main_module,
        "open_drafts_folder",
        lambda path: opened_folders.append(path) or True,
    )

    result = run(
        settings,
        Namespace(
            mode="draft_only",
            preview=False,
            limit=None,
            opt_out=None,
            all=True,
            open_drafts=True,
        ),
    )

    assert result == 0
    assert len(list(settings.drafts_dir.glob("*.eml"))) == 2
    assert (settings.drafts_dir / "review.html").is_file()
    assert len(opened_drafts) == 1
    assert opened_drafts[0].suffix == ".eml"
    assert opened_folders == [settings.drafts_dir]


@pytest.mark.parametrize(
    ("choice", "expected"),
    [
        ("1", ["--mode", "draft_only", "--all", "--refresh-drafts", "--open-drafts"]),
        ("2", ["--mode", "draft_only", "--all", "--refresh-drafts", "--browser-review"]),
        ("3", ["--mode", "send"]),
    ],
)
def test_beginner_launcher_menu(
    monkeypatch: pytest.MonkeyPatch,
    choice: str,
    expected: list[str],
) -> None:
    received: list[list[str]] = []
    monkeypatch.setattr(draft_launcher, "main", lambda args: received.append(args) or 0)

    assert draft_launcher.run(input_fn=lambda _: choice, output=io.StringIO()) == 0
    assert received == [expected]


def test_browser_review_has_gmail_compose_link_and_manual_cv_warning(tmp_path: Path) -> None:
    message = EmailMessage()
    message["To"] = "person@example.edu"
    message["Subject"] = "Research discussion"
    message.set_content("Hello Professor")
    draft_path = tmp_path / "person.eml"
    draft_path.write_bytes(message.as_bytes())

    page_path = save_review_page(
        [message],
        [draft_path],
        tmp_path / "review.html",
        tmp_path / "cv.pdf",
        browser_compose=True,
    )
    page = page_path.read_text(encoding="utf-8")

    assert "Open in Gmail" in page
    assert "attach <strong>cv.pdf</strong> manually" in page
    assert "mail.google.com/mail/?" in page


def test_refresh_removes_generated_drafts_but_preserves_other_files(tmp_path: Path) -> None:
    drafts_dir = tmp_path / "drafts"
    drafts_dir.mkdir()
    (drafts_dir / "old.eml").write_text("old", encoding="utf-8")
    (drafts_dir / "review.html").write_text("old", encoding="utf-8")
    keep = drafts_dir / ".gitkeep"
    keep.write_text("", encoding="utf-8")

    assert clear_generated_drafts(drafts_dir) == 2
    assert keep.is_file()
    assert not (drafts_dir / "old.eml").exists()
    assert not (drafts_dir / "review.html").exists()


def test_refresh_rebuilds_drafted_but_never_sent_addresses(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, email_subject="Research enquiry")
    settings.csv_path.write_text(
        "Professor / Researcher,Email,University,Best-fit Domain\n"
        "Dr Draft Person,draft@example.edu,Example University,Medical AI\n"
        "Dr Sent Person,sent@example.edu,Example University,Computer Vision\n",
        encoding="utf-8",
    )
    settings.template_path.write_text("Dear Professor {{ last_name }}, {{ domain }}", encoding="utf-8")
    settings.cv_path.write_bytes(b"%PDF-1.4\n%%EOF")
    append_log(
        settings.log_path,
        "Dr Draft Person",
        "draft@example.edu",
        "Example University",
        "draft_only",
        "drafted",
    )
    append_log(
        settings.log_path,
        "Dr Sent Person",
        "sent@example.edu",
        "Example University",
        "send",
        "sent",
    )
    settings.drafts_dir.mkdir(parents=True)
    (settings.drafts_dir / "stale.eml").write_text("old", encoding="utf-8")

    result = run(
        settings,
        Namespace(
            mode="draft_only",
            preview=False,
            limit=None,
            opt_out=None,
            all=True,
            open_drafts=False,
            refresh_drafts=True,
        ),
    )

    assert result == 0
    drafts = list(settings.drafts_dir.glob("*.eml"))
    assert len(drafts) == 1
    assert "draft_example.edu" in drafts[0].name


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
