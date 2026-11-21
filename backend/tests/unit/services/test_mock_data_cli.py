"""Clock failures are actionable and never expose transport details."""

import io
import urllib.error

import pytest

from app import mock_data


@pytest.mark.parametrize("payload", [b"{}", b"bad json", b'{"now":"2026-10-23T00:00:00"}'])
def test_invalid_clock_refused(monkeypatch, payload):
    monkeypatch.setattr(mock_data.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(payload))
    with pytest.raises(ValueError, match="Start the backend"):
        mock_data.backend_reference()


def test_unreachable_clock_refused_without_transport_details(monkeypatch):
    def unavailable(*args, **kwargs):
        raise urllib.error.URLError("private transport detail")

    monkeypatch.setattr(mock_data.urllib.request, "urlopen", unavailable)
    with pytest.raises(ValueError) as stopped:
        mock_data.backend_reference()
    assert "Start the backend" in str(stopped.value)
    assert "private transport detail" not in str(stopped.value)


def test_clock_reference_has_timezone(monkeypatch):
    monkeypatch.setattr(
        mock_data.urllib.request,
        "urlopen",
        lambda *a, **k: io.BytesIO(b'{"now":"2026-10-23T21:00:00+07:00"}'),
    )
    assert mock_data.backend_reference().isoformat() == "2026-10-23T21:00:00+07:00"
