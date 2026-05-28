from __future__ import annotations

import os
import smtplib
import ssl
import urllib.parse
import urllib.error
import urllib.request
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Mapping


DEFAULT_ENV_PATH = Path(r"C:\ProgramData\MonitorAgent\agent-notify.env")

EVENTS = {
    "needs_review",
    "failed",
    "auto_merge_denied",
    "dirty_worktree",
    "pr_created_without_merge",
    "cycle_completed_with_errors",
}


class NotifyError(RuntimeError):
    pass


@dataclass(frozen=True)
class NotifyConfig:
    telegram_token: str | None = None
    telegram_chat_id: str | None = None
    email_host: str | None = None
    email_port: int = 587
    email_username: str | None = None
    email_password: str | None = None
    email_from: str | None = None
    email_to: tuple[str, ...] = ()
    email_tls: bool = True
    email_ssl: bool = False

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_token and self.telegram_chat_id)

    @property
    def email_enabled(self) -> bool:
        return bool(self.email_host and self.email_from and self.email_to)

    @property
    def any_enabled(self) -> bool:
        return self.telegram_enabled or self.email_enabled


def read_env_file(path: Path = DEFAULT_ENV_PATH) -> dict[str, str]:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return {}

    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key] = value
    return values


def load_config(env: Mapping[str, str] | None = None, env_path: Path = DEFAULT_ENV_PATH) -> NotifyConfig:
    merged = read_env_file(env_path)
    merged.update(dict(os.environ if env is None else env))

    return NotifyConfig(
        telegram_token=_get(merged, "AGENT_NOTIFY_TELEGRAM_BOT_TOKEN"),
        telegram_chat_id=_get(merged, "AGENT_NOTIFY_TELEGRAM_CHAT_ID"),
        email_host=_get(merged, "AGENT_NOTIFY_EMAIL_SMTP_HOST"),
        email_port=_parse_int(_get(merged, "AGENT_NOTIFY_EMAIL_SMTP_PORT"), default=587),
        email_username=_get(merged, "AGENT_NOTIFY_EMAIL_USERNAME"),
        email_password=_get(merged, "AGENT_NOTIFY_EMAIL_PASSWORD"),
        email_from=_get(merged, "AGENT_NOTIFY_EMAIL_FROM"),
        email_to=_split_recipients(_get(merged, "AGENT_NOTIFY_EMAIL_TO")),
        email_tls=_parse_bool(_get(merged, "AGENT_NOTIFY_EMAIL_USE_TLS"), default=True),
    )


def _get(values: Mapping[str, str], *keys: str) -> str | None:
    for key in keys:
        value = values.get(key)
        if value:
            return value
    return None


def _parse_int(value: str | None, *, default: int) -> int:
    if not value:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise NotifyError(f"Invalid integer notification setting: {value}") from exc


def _parse_bool(value: str | None, *, default: bool) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _split_recipients(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(item.strip() for item in value.replace(";", ",").split(",") if item.strip())


def parse_notify_events(raw: str | None) -> set[str]:
    if not raw or raw.strip().lower() == "all":
        return set(EVENTS)
    events = {item.strip() for item in raw.split(",") if item.strip()}
    unknown = events - EVENTS
    if unknown:
        raise NotifyError("Unknown notification event(s): " + ", ".join(sorted(unknown)))
    return events


def format_message(event: str, title: str, details: Mapping[str, object] | None = None) -> tuple[str, str]:
    subject = f"[monitor-agent] {event}: {title}"
    lines = [subject]
    if details:
        for key in sorted(details):
            value = details[key]
            if value is None or value == "":
                continue
            lines.append(f"{key}: {value}")
    return subject, "\n".join(lines)


class Notifier:
    def __init__(
        self,
        config: NotifyConfig,
        *,
        enabled: bool,
        events: set[str] | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.config = config
        self.enabled = enabled
        self.events = set(EVENTS if events is None else events)
        self.timeout = timeout

    def should_send(self, event: str) -> bool:
        return self.enabled and event in self.events and self.config.any_enabled

    def send(self, event: str, title: str, details: Mapping[str, object] | None = None) -> bool:
        if event not in EVENTS:
            raise NotifyError(f"Unknown notification event: {event}")
        if not self.should_send(event):
            return False

        subject, body = format_message(event, title, details)
        errors: list[str] = []
        if self.config.telegram_enabled:
            try:
                self._send_telegram(body)
            except Exception as exc:  # noqa: BLE001 - preserve email attempt and report both channels.
                errors.append(f"telegram: {exc}")
        if self.config.email_enabled:
            try:
                self._send_email(subject, body)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"email: {exc}")
        if errors:
            raise NotifyError("; ".join(errors))
        return True

    def _send_telegram(self, text: str) -> None:
        assert self.config.telegram_token
        assert self.config.telegram_chat_id
        url = f"https://api.telegram.org/bot{self.config.telegram_token}/sendMessage"
        payload = urllib.parse.urlencode(
            {
                "chat_id": self.config.telegram_chat_id,
                "text": text,
                "disable_web_page_preview": "true",
            }
        ).encode("utf-8")
        request = urllib.request.Request(url, data=payload, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                status = getattr(response, "status", 200)
                if status >= 400:
                    raise NotifyError(f"Telegram returned HTTP {status}")
        except urllib.error.URLError as exc:
            raise NotifyError(str(exc)) from exc

    def _send_email(self, subject: str, body: str) -> None:
        assert self.config.email_host
        assert self.config.email_from
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self.config.email_from
        message["To"] = ", ".join(self.config.email_to)
        message.set_content(body)

        if self.config.email_ssl:
            smtp_factory = smtplib.SMTP_SSL
            smtp_kwargs = {"context": ssl.create_default_context()}
        else:
            smtp_factory = smtplib.SMTP
            smtp_kwargs = {}

        with smtp_factory(self.config.email_host, self.config.email_port, timeout=self.timeout, **smtp_kwargs) as smtp:
            if self.config.email_tls and not self.config.email_ssl:
                smtp.starttls(context=ssl.create_default_context())
            if self.config.email_username:
                smtp.login(self.config.email_username, self.config.email_password or "")
            smtp.send_message(message)
