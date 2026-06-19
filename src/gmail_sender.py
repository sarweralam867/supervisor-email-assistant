from __future__ import annotations

import smtplib
from email.message import EmailMessage


class GmailSender:
    def __init__(self, email_address: str, app_password: str) -> None:
        if not email_address or not app_password:
            raise ValueError("EMAIL_ADDRESS and EMAIL_APP_PASSWORD are required for send mode.")
        self.email_address = email_address
        self.app_password = app_password
        self._smtp: smtplib.SMTP_SSL | None = None

    def __enter__(self) -> "GmailSender":
        self._smtp = smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30)
        self._smtp.login(self.email_address, self.app_password)
        return self

    def send(self, message: EmailMessage) -> None:
        if self._smtp is None:
            raise RuntimeError("Gmail connection is not open.")
        self._smtp.send_message(message)

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self._smtp is not None:
            try:
                self._smtp.quit()
            except smtplib.SMTPException:
                self._smtp.close()

