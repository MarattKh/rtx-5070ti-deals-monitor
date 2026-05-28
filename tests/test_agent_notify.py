from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import agent_notify
import tools.agent_cycle as agent_cycle


def test_load_config_reads_env_file_and_process_env_overrides(tmp_path):
    env_path = tmp_path / "agent-notify.env"
    env_path.write_text(
        "\n".join(
            [
                "AGENT_NOTIFY_TELEGRAM_TOKEN=file-token",
                "AGENT_NOTIFY_TELEGRAM_CHAT_ID=file-chat",
                "AGENT_NOTIFY_EMAIL_HOST=smtp.local",
                "AGENT_NOTIFY_EMAIL_FROM=agent@example.test",
                "AGENT_NOTIFY_EMAIL_TO='ops@example.test;dev@example.test'",
                "AGENT_NOTIFY_EMAIL_TLS=false",
            ]
        ),
        encoding="utf-8",
    )

    config = agent_notify.load_config(
        {"AGENT_NOTIFY_TELEGRAM_TOKEN": "env-token", "AGENT_NOTIFY_EMAIL_PORT": "2525"},
        env_path,
    )

    assert config.telegram_token == "env-token"
    assert config.telegram_chat_id == "file-chat"
    assert config.telegram_enabled is True
    assert config.email_host == "smtp.local"
    assert config.email_port == 2525
    assert config.email_to == ("ops@example.test", "dev@example.test")
    assert config.email_tls is False
    assert config.email_enabled is True


def test_parse_notify_events_accepts_all_and_rejects_unknown():
    assert agent_notify.parse_notify_events("all") == agent_notify.EVENTS
    assert agent_notify.parse_notify_events("failed,needs_review") == {"failed", "needs_review"}

    with pytest.raises(agent_notify.NotifyError, match="Unknown notification"):
        agent_notify.parse_notify_events("failed,unknown")


def test_notifier_disabled_or_unconfigured_does_not_send(monkeypatch):
    called = False

    def fake_urlopen(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(agent_notify.urllib.request, "urlopen", fake_urlopen)
    config = agent_notify.NotifyConfig(telegram_token="token", telegram_chat_id="chat")

    assert agent_notify.Notifier(config, enabled=False).send("failed", "title") is False
    assert agent_notify.Notifier(agent_notify.NotifyConfig(), enabled=True).send("failed", "title") is False
    assert called is False


def test_notifier_sends_telegram_with_urllib(monkeypatch):
    requests = []

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return Response()

    monkeypatch.setattr(agent_notify.urllib.request, "urlopen", fake_urlopen)
    config = agent_notify.NotifyConfig(telegram_token="token", telegram_chat_id="chat")

    sent = agent_notify.Notifier(config, enabled=True, timeout=3).send(
        "failed",
        "Task failed",
        {"branch": "agent/a"},
    )

    assert sent is True
    request, timeout = requests[0]
    assert request.full_url == "https://api.telegram.org/bottoken/sendMessage"
    assert request.get_method() == "POST"
    assert timeout == 3
    body = request.data.decode("utf-8")
    assert "chat_id=chat" in body
    assert "Task+failed" in body


def test_notifier_sends_email_with_smtplib(monkeypatch):
    sent_messages = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            self.host = host
            self.port = port
            self.timeout = timeout
            self.started_tls = False

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def starttls(self, context):
            self.started_tls = True

        def login(self, username, password):
            self.username = username
            self.password = password

        def send_message(self, message):
            sent_messages.append((self, message))

    monkeypatch.setattr(agent_notify.smtplib, "SMTP", FakeSMTP)
    config = agent_notify.NotifyConfig(
        email_host="smtp.example.test",
        email_port=2525,
        email_username="agent",
        email_password="secret",
        email_from="agent@example.test",
        email_to=("ops@example.test",),
    )

    sent = agent_notify.Notifier(config, enabled=True, timeout=4).send("needs_review", "Review needed")

    assert sent is True
    smtp, message = sent_messages[0]
    assert smtp.host == "smtp.example.test"
    assert smtp.port == 2525
    assert smtp.timeout == 4
    assert smtp.started_tls is True
    assert smtp.username == "agent"
    assert message["To"] == "ops@example.test"
    assert message["Subject"] == "[monitor-agent] needs_review: Review needed"


def test_cycle_sends_pr_created_without_merge_notification(tmp_path, monkeypatch):
    task_file = tmp_path / "task.md"
    task_file.write_text("do work", encoding="utf-8")
    queue_path = tmp_path / "queue.json"
    queue_path.write_text(
        agent_cycle.json.dumps(
            {
                "tasks": [
                    {
                        "id": "task_a",
                        "status": "pending",
                        "task": str(task_file),
                        "branch": "agent/a",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    state_path = tmp_path / "state.json"
    pr_view = agent_cycle.json.dumps(
        {"number": 4, "url": "https://github.test/pull/4", "state": "OPEN", "mergeable": "MERGEABLE"}
    )
    runner = agent_cycle_test_runner(
        {("gh", "pr", "view", "agent/a", "--json", "number,url,state,mergeable"): pr_view}
    )
    sent_events = []

    class FakeNotifier:
        enabled = True

        def send(self, event, title, details=None):
            sent_events.append((event, title, details))
            return True

    monkeypatch.setattr(agent_cycle, "build_notifier", lambda args: FakeNotifier())
    monkeypatch.setattr(agent_cycle, "check_dirty_worktree", lambda runner: "")
    args = SimpleNamespace(
        queue=str(queue_path),
        state=str(state_path),
        max_tasks=1,
        create_pr=True,
        auto_merge_safe=False,
        dry_run=False,
        once=True,
        notify=True,
        notify_test=False,
        notify_on="all",
    )

    assert agent_cycle.run_cycle(args, runner) == 0

    assert [event for event, _, _ in sent_events] == ["pr_created_without_merge", "needs_review"]


class agent_cycle_test_runner:
    def __init__(self, outputs=None):
        self.outputs = outputs or {}
        self.commands = []
        self.logger = SimpleNamespace(lines=[], write=lambda message="": self.logger.lines.append(message))

    def run(self, args, **kwargs):
        command = list(args)
        self.commands.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout=self.outputs.get(tuple(command), ""), stderr="")
