"""Provider-neutral SMTP delivery with bounded exponential retries."""

from __future__ import annotations

import logging
import smtplib
import ssl
import time
from collections.abc import Callable
from email.message import EmailMessage
from types import TracebackType

from config import Settings

LOGGER = logging.getLogger(__name__)
RetryableSMTPError = (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError, TimeoutError, OSError)


class SMTPSender:
    """Open and reuse a generic authenticated SMTP connection."""

    def __init__(self, settings: Settings, *, sleep: Callable[[float], None] = time.sleep) -> None:
        if not settings.smtp_host:
            raise ValueError("SMTP_HOST is required for send mode.")
        if not settings.sender_address or not settings.auth_username or not settings.auth_password:
            raise ValueError("EMAIL_ADDRESS, SMTP_USERNAME, and SMTP_PASSWORD are required for send mode.")
        self.settings = settings
        self._sleep = sleep
        self._smtp: smtplib.SMTP | smtplib.SMTP_SSL | None = None

    def _connect(self) -> None:
        """Connect, secure, and authenticate using configured provider settings."""
        context = ssl.create_default_context()
        if self.settings.smtp_use_ssl:
            smtp: smtplib.SMTP | smtplib.SMTP_SSL = smtplib.SMTP_SSL(
                self.settings.smtp_host, self.settings.smtp_port,
                timeout=self.settings.smtp_timeout, context=context,
            )
        else:
            smtp = smtplib.SMTP(
                self.settings.smtp_host, self.settings.smtp_port,
                timeout=self.settings.smtp_timeout,
            )
            if self.settings.smtp_use_starttls:
                smtp.starttls(context=context)
        smtp.login(self.settings.auth_username, self.settings.auth_password)
        self._smtp = smtp

    def _with_retry(self, operation: Callable[[], None], description: str) -> None:
        """Run a transient SMTP operation with exponential backoff."""
        attempts = self.settings.smtp_retries + 1
        for attempt in range(1, attempts + 1):
            try:
                operation()
                return
            except RetryableSMTPError as exc:
                if attempt == attempts:
                    raise RuntimeError(f"{description} failed after {attempts} attempt(s): {exc}") from exc
                delay = self.settings.retry_backoff_seconds * (2 ** (attempt - 1))
                LOGGER.warning(
                    "%s failed (attempt %d/%d); retrying in %.1fs: %s",
                    description,
                    attempt,
                    attempts,
                    delay,
                    exc,
                )
                self._sleep(delay)

    def __enter__(self) -> SMTPSender:
        """Connect to SMTP and return this sender."""
        self._with_retry(self._connect, "SMTP connection")
        return self

    def send(self, message: EmailMessage) -> None:
        """Send one message, reconnecting before retrying a dropped connection."""
        def deliver() -> None:
            if self._smtp is None:
                self._connect()
            assert self._smtp is not None
            try:
                self._smtp.send_message(message)
            except RetryableSMTPError:
                self.close()
                raise

        self._with_retry(deliver, f"SMTP delivery to {message.get('To', '<unknown>')}")

    def close(self) -> None:
        """Close the active SMTP connection without masking an earlier error."""
        if self._smtp is None:
            return
        try:
            self._smtp.quit()
        except (smtplib.SMTPException, OSError):
            self._smtp.close()
        finally:
            self._smtp = None

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the SMTP connection when leaving a context manager."""
        self.close()


GmailSender = SMTPSender
"""Backward-compatible name retained for existing imports."""
