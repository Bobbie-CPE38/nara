"""CLI authenticates to the local Backend and does not expose codes on failure."""

import io
import json
import urllib.error
from unittest.mock import Mock

import pytest

from app import line_accounts
from app.core.config import settings


def test_cli_issue_displays_only_committed_response(monkeypatch, capsys):
    monkeypatch.setattr(settings, "internal_job_secret", "test-admin-secret")
    response = io.BytesIO(
        json.dumps({"code": "test-code", "expires_at": "2026-10-14T10:00:00+07:00"}).encode()
    )
    opener = Mock(return_value=response)
    monkeypatch.setattr(line_accounts.urllib.request, "urlopen", opener)
    line_accounts.main(["issue-code", "--staff-id", "201"])
    request = opener.call_args.args[0]
    assert request.full_url == "http://localhost:8000/internal/line-accounts/201/issue-code"
    assert request.get_header("X-internal-secret") == "test-admin-secret"
    assert "LINK test-code" in capsys.readouterr().out


def test_cli_failure_does_not_print_response_or_secret(monkeypatch, capsys):
    monkeypatch.setattr(settings, "internal_job_secret", "test-admin-secret")
    error = urllib.error.HTTPError("local", 500, "error", {}, io.BytesIO(b"sensitive-code"))
    monkeypatch.setattr(line_accounts.urllib.request, "urlopen", Mock(side_effect=error))
    with pytest.raises(SystemExit, match="refused"):
        line_accounts.main(["issue-code", "--staff-id", "201"])
    output = capsys.readouterr()
    assert "sensitive-code" not in output.out + output.err
    assert "test-admin-secret" not in output.out + output.err


def test_cli_without_admin_secret_does_not_call_backend(monkeypatch):
    monkeypatch.setattr(settings, "internal_job_secret", None)
    opener = Mock()
    monkeypatch.setattr(line_accounts.urllib.request, "urlopen", opener)
    with pytest.raises(SystemExit, match="INTERNAL_JOB_SECRET"):
        line_accounts.main(["issue-code", "--staff-id", "201"])
    opener.assert_not_called()
