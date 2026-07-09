#!/usr/bin/env python3
"""Send one HTML email body."""

from __future__ import annotations

import argparse
import os
import re
import smtplib
import ssl
import sys
from email.message import EmailMessage
from email.utils import parseaddr
from html.parser import HTMLParser
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_DIR / "07-配置" / "email.env"


class PlainTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self.parts.append(text)

    def text(self) -> str:
        return "\n".join(self.parts)


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required email config: {name}")
    return value


def extract_title(html: str, fallback: str) -> str:
    match = re.search(r"<title>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    if match:
        title = re.sub(r"\s+", " ", match.group(1)).strip()
        if title:
            return title
    return fallback


def html_to_text(html: str) -> str:
    parser = PlainTextExtractor()
    parser.feed(html)
    return parser.text()


def sender_domain(mail_from: str) -> str:
    _, address = parseaddr(mail_from)
    if not address or "@" not in address:
        raise RuntimeError(f"MAIL_FROM cannot be parsed: {mail_from}")
    domain = address.rsplit("@", 1)[1].strip().lower()
    if domain.endswith(".com.com"):
        raise RuntimeError(f"MAIL_FROM domain looks mistyped: {domain}")
    return domain


def send_with_resend(mail_from: str, mail_to: str, subject: str, html: str) -> None:
    import resend

    print("Email provider: Resend Python SDK")
    print(f"MAIL_FROM domain: {sender_domain(mail_from)}")
    resend.api_key = required_env("RESEND_API_KEY")
    payload = {
        "from": mail_from,
        "to": [email.strip() for email in mail_to.split(",") if email.strip()],
        "subject": subject,
        "html": html,
        "text": html_to_text(html),
    }
    reply_to = os.environ.get("MAIL_REPLY_TO", "").strip()
    if reply_to:
        payload["reply_to"] = reply_to
    resend.Emails.send(payload)


def send_with_smtp(mail_from: str, mail_to: str, subject: str, html: str) -> None:
    smtp_host = required_env("SMTP_HOST")
    smtp_port = int(required_env("SMTP_PORT"))
    smtp_username = required_env("SMTP_USERNAME")
    smtp_password = required_env("SMTP_PASSWORD")
    mail_reply_to = os.environ.get("MAIL_REPLY_TO", mail_from)

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = mail_from
    msg["To"] = mail_to
    msg["Reply-To"] = mail_reply_to
    msg.set_content(html_to_text(html))
    msg.add_alternative(html, subtype="html")

    context = ssl.create_default_context()
    if smtp_port == 465:
        with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context) as server:
            server.login(smtp_username, smtp_password)
            server.send_message(msg)
    else:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls(context=context)
            server.login(smtp_username, smtp_password)
            server.send_message(msg)


def send(issue_path: Path, subject: str | None = None) -> None:
    load_env(ENV_PATH)
    mail_from = required_env("MAIL_FROM")
    mail_to = required_env("MAIL_TO")
    subject_prefix = os.environ.get("MAIL_SUBJECT_PREFIX", "国际会议与学术机会雷达")
    html = issue_path.read_text(encoding="utf-8")
    final_subject = subject or f"【{subject_prefix}】{extract_title(html, issue_path.stem)}"

    if os.environ.get("RESEND_API_KEY", "").strip():
        send_with_resend(mail_from, mail_to, final_subject, html)
    else:
        send_with_smtp(mail_from, mail_to, final_subject, html)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("issue_html", help="Path to the HTML issue to send")
    parser.add_argument("--subject", help="Optional email subject")
    args = parser.parse_args()

    try:
        send(Path(args.issue_html).resolve(), args.subject)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
