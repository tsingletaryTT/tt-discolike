# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: © 2026 Tenstorrent AI ULC
import subprocess

import discolike.gozer_status as gozer_status_mod


def completed(stdout="", returncode=0):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


def test_get_status_returns_none_when_gozer_not_resolvable(monkeypatch):
    monkeypatch.setattr(gozer_status_mod, "resolve_binary", lambda name: None)

    assert gozer_status_mod.get_status() is None


def test_get_status_calls_the_resolved_absolute_path_not_a_bare_name(monkeypatch):
    """Regression test: get_status used to call bare "gozer" directly, relying on
    the calling process's own $PATH -- which silently broke once tt-discolike
    itself started running as a systemd --user unit (restricted PATH, same as
    any unit it generates for another app)."""
    monkeypatch.setattr(gozer_status_mod, "resolve_binary", lambda name: "/home/ttuser/.local/bin/gozer")
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return completed(stdout='{"chips": []}')

    monkeypatch.setattr(gozer_status_mod.subprocess, "run", fake_run)

    result = gozer_status_mod.get_status()

    assert calls == [["/home/ttuser/.local/bin/gozer", "status", "--json"]]
    assert result == {"chips": []}


def test_get_status_returns_none_on_nonzero_exit(monkeypatch):
    monkeypatch.setattr(gozer_status_mod, "resolve_binary", lambda name: "/home/ttuser/.local/bin/gozer")
    monkeypatch.setattr(gozer_status_mod.subprocess, "run", lambda cmd, **kwargs: completed(returncode=1))

    assert gozer_status_mod.get_status() is None


def test_get_status_returns_none_on_timeout(monkeypatch):
    monkeypatch.setattr(gozer_status_mod, "resolve_binary", lambda name: "/home/ttuser/.local/bin/gozer")

    def raise_timeout(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=gozer_status_mod.STATUS_TIMEOUT_SECONDS)

    monkeypatch.setattr(gozer_status_mod.subprocess, "run", raise_timeout)

    assert gozer_status_mod.get_status() is None


def test_get_status_returns_none_on_invalid_json(monkeypatch):
    monkeypatch.setattr(gozer_status_mod, "resolve_binary", lambda name: "/home/ttuser/.local/bin/gozer")
    monkeypatch.setattr(gozer_status_mod.subprocess, "run", lambda cmd, **kwargs: completed(stdout="not json"))

    assert gozer_status_mod.get_status() is None
