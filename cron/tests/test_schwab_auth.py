"""Tests for SchwabTokenManager's cross-process token-rotation handling.

Regression for the 2026-08 incident: the manager cached tokens in memory
forever, so when the api container rotated the refresh token on the shared
file, cron's refreshes 400'd every 15 minutes until a restart.
"""

import json

import pytest

from integrations.schwab_auth import SchwabReauthRequired, SchwabTokenManager

TOKENS_V1 = {
    "access_token": "at-1",
    "refresh_token": "rt-1",
    "expires_at": "2026-01-01T00:00:00+00:00",
}
TOKENS_V2 = {
    "access_token": "at-2",
    "refresh_token": "rt-2",
    "expires_at": "2026-01-01T00:00:00+00:00",
}


def _manager(tmp_path, tokens):
    path = tmp_path / "schwab_tokens.json"
    path.write_text(json.dumps(tokens))
    return SchwabTokenManager(str(path), "client-id", "client-secret"), path


def test_force_refresh_reads_file_fresh_each_time(tmp_path, monkeypatch):
    tm, path = _manager(tmp_path, TOKENS_V1)
    tm.load_tokens()  # populate the in-memory copy with rt-1

    # Another process rotates the file to rt-2
    path.write_text(json.dumps(TOKENS_V2))

    used = []

    def fake_refresh(refresh_token):
        used.append(refresh_token)
        return {
            "access_token": "at-3",
            "refresh_token": "rt-3",
            "expires_at": "2026-01-01T01:00:00+00:00",
        }

    monkeypatch.setattr(tm, "refresh_access_token", fake_refresh)
    tm.force_refresh()

    assert used == ["rt-2"]  # fresh disk read, not the stale in-memory rt-1
    assert json.loads(path.read_text())["refresh_token"] == "rt-3"


def test_refresh_retries_once_with_rotated_on_disk_token(tmp_path, monkeypatch):
    tm, path = _manager(tmp_path, TOKENS_V1)

    used = []

    def fake_refresh(refresh_token):
        used.append(refresh_token)
        if refresh_token == "rt-1":
            # Simulate the other container rotating the file between our read
            # and our refresh call, making our token rejected.
            path.write_text(json.dumps(TOKENS_V2))
            raise RuntimeError("400 rejected")
        return {
            "access_token": "at-3",
            "refresh_token": "rt-3",
            "expires_at": "2026-01-01T01:00:00+00:00",
        }

    monkeypatch.setattr(tm, "refresh_access_token", fake_refresh)
    tm.force_refresh()

    assert used == ["rt-1", "rt-2"]
    assert json.loads(path.read_text())["refresh_token"] == "rt-3"


def test_refresh_failure_without_rotation_propagates(tmp_path, monkeypatch):
    tm, _ = _manager(tmp_path, TOKENS_V1)

    def fake_refresh(refresh_token):
        raise RuntimeError("500 server error")

    monkeypatch.setattr(tm, "refresh_access_token", fake_refresh)
    with pytest.raises(RuntimeError):
        tm.force_refresh()


def test_reauth_required_is_not_retried(tmp_path, monkeypatch):
    tm, _ = _manager(tmp_path, TOKENS_V1)

    calls = []

    def fake_refresh(refresh_token):
        calls.append(refresh_token)
        raise SchwabReauthRequired("dead")

    monkeypatch.setattr(tm, "refresh_access_token", fake_refresh)
    with pytest.raises(SchwabReauthRequired):
        tm.force_refresh()
    assert calls == ["rt-1"]
