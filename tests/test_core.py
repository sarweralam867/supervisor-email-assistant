from __future__ import annotations

import sys
import tempfile
import unittest
from argparse import Namespace
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from config import Settings
from email_builder import build_message, extract_last_name, save_draft
from load_professors import Professor, email_skip_reason, load_professors
from main import completed_addresses, effective_limit, sent_today


class CoreTests(unittest.TestCase):
    def test_extract_last_names(self) -> None:
        self.assertEqual(extract_last_name("Assoc. Prof. Example Researcher"), "Researcher")
        self.assertEqual(extract_last_name("Prof. Erik Meijering"), "Meijering")
        self.assertEqual(extract_last_name("Dr Imran Razzak"), "Razzak")

    def test_email_validation(self) -> None:
        self.assertIsNone(email_skip_reason("Professor.Name@university.edu.au"))
        self.assertEqual(email_skip_reason("Use official profile contact"), "official profile contact required")
        self.assertEqual(email_skip_reason("contact@university.edu.au"), "non-personal email address")
        self.assertEqual(email_skip_reason("not-an-email"), "invalid email address")

    def test_completed_addresses_are_normalized(self) -> None:
        rows = [{"email": "Name@Example.edu", "status": "drafted"}]
        self.assertEqual(completed_addresses(rows), {"name@example.edu"})

    def test_sent_today(self) -> None:
        rows = [{"timestamp": datetime.now().astimezone().isoformat(), "status": "sent"}]
        self.assertEqual(sent_today(rows), 1)

    def test_daily_limit_is_hard_capped_and_counts_prior_sends(self) -> None:
        settings = Settings("", "", "draft_only", 10, Path(), Path(), Path(), Path(), Path())
        rows = [
            {"timestamp": datetime.now().astimezone().isoformat(), "status": "sent"}
            for _ in range(3)
        ]
        self.assertEqual(effective_limit(Namespace(limit=99, mode="send"), settings, rows), 7)

    def test_build_and_save_eml_with_pdf_attachment(self) -> None:
        professor = Professor("Assoc. Prof. Example Researcher", "researcher@example.edu", "Example", "Medical AI")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            template = root / "template.txt"
            cv = root / "cv.pdf"
            template.write_text("Dear Professor {{ last_name }},\nResearch: {{ domain }}", encoding="utf-8")
            cv.write_bytes(b"%PDF-1.4\n%%EOF")
            message = build_message(professor, "sender@example.com", template, cv)
            draft = save_draft(message, professor, root / "drafts")

            self.assertTrue(draft.is_file())
            self.assertEqual(message["To"], professor.email)
            self.assertIn("Dear Professor Researcher", message.get_body(preferencelist=("plain",)).get_content())
            attachments = list(message.iter_attachments())
            self.assertEqual(len(attachments), 1)
            self.assertEqual(attachments[0].get_filename(), "cv.pdf")

    def test_public_sample_csv_schema_loads(self) -> None:
        loaded = load_professors(ROOT / "examples" / "professors.sample.csv")
        self.assertEqual(loaded, [])

    def test_missing_domain_uses_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "professors.csv"
            csv_path.write_text(
                "Professor / Researcher,Email,University,Best-fit Domain\n"
                "Dr Example Person,person@example.edu,Example University,\n",
                encoding="utf-8",
            )
            professor, reason, _ = load_professors(csv_path)[0]
            self.assertIsNone(reason)
            self.assertEqual(professor.domain, "artificial intelligence and machine learning")


if __name__ == "__main__":
    unittest.main()
