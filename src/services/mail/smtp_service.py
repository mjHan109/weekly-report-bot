"""
GmailSmtpService — sends weekly report emails via Gmail SMTP.

Replaces Microsoft Graph mail integration for environments without
an Azure subscription.

Uses aiosmtplib for async SMTP over TLS (port 465).

Environment variables
---------------------
    GMAIL_USER         — Gmail address used as SMTP login
    GMAIL_APP_PASSWORD — 16-character Google App Password
    MAIL_FROM          — Sender address shown in From header
    MAIL_TO            — Default recipient address
"""

from __future__ import annotations

import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib

from src.infra.config import get_settings

logger = logging.getLogger(__name__)

_SMTP_HOST = "smtp.gmail.com"
_SMTP_PORT = 465


class GmailSmtpService:
    """Sends HTML/plain-text emails via Gmail SMTP."""

    async def send_weekly_report(
        self,
        subject: str,
        body_text: str,
        to: str | None = None,
    ) -> None:
        """
        Send the aggregated weekly report email.

        Args:
            subject:   Email subject line.
            body_text: Plain-text body (Korean weekly report content).
            to:        Override recipient. Falls back to MAIL_TO setting.

        Raises:
            RuntimeError: If Gmail credentials are not configured.
            aiosmtplib.SMTPException: On SMTP-level errors.
        """
        settings = get_settings()

        if not settings.gmail_user or not settings.gmail_app_password:
            raise RuntimeError(
                "Gmail credentials not configured. "
                "Set GMAIL_USER and GMAIL_APP_PASSWORD in .env"
            )

        recipient = to or settings.mail_to
        if not recipient:
            raise RuntimeError("No recipient configured. Set MAIL_TO in .env")

        sender = settings.mail_from or settings.gmail_user

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = recipient

        # Plain text part
        msg.attach(MIMEText(body_text, "plain", "utf-8"))

        # Simple HTML version with line breaks preserved
        html_body = body_text.replace("\n", "<br>\n")
        html = f"""<html><body>
<pre style="font-family: sans-serif; white-space: pre-wrap;">{html_body}</pre>
</body></html>"""
        msg.attach(MIMEText(html, "html", "utf-8"))

        logger.info(
            "Sending weekly report email | from=%s | to=%s | subject=%r",
            sender, recipient, subject,
        )

        # Strip spaces from App Password (Google shows it with spaces)
        password = settings.gmail_app_password.replace(" ", "")

        await aiosmtplib.send(
            msg,
            hostname=_SMTP_HOST,
            port=_SMTP_PORT,
            username=settings.gmail_user,
            password=password,
            use_tls=True,
        )

        logger.info("Weekly report email sent successfully to %s", recipient)
