# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The suite's offline guarantee, asserted rather than asserted-about.

``done_when`` for this worker is *"with no AWS credentials and no network"*.  The autouse
``no_network`` fixture in ``conftest.py`` enforces it by refusing outbound connections.
A guard nobody tests is a guard that becomes a no-op the first time somebody reorders a
fixture, so the guard is tested here — and so is the consequence, that the live providers
report *unreachable* rather than inventing an answer.
"""

from __future__ import annotations

import socket

import pytest
from mainline_recall_agent.providers.errors import ProviderUnavailable
from mainline_recall_agent.providers.registry import current_mode, get_judge_provider

from .conftest import NetworkAccessInTest


def test_the_network_guard_is_actually_installed() -> None:
    with pytest.raises(NetworkAccessInTest):
        socket.create_connection(("bedrock.ap-southeast-2.amazonaws.com", 443), timeout=1)


def test_the_network_guard_blocks_a_raw_socket_connect() -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(NetworkAccessInTest):
            sock.connect(("127.0.0.1", 9))
    finally:
        sock.close()


def test_the_default_mode_is_replay_so_nothing_needs_the_network() -> None:
    assert current_mode() == "cassette"


def test_a_live_judge_reports_unreachable_rather_than_guessing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No credentials must produce a refusal to run, never a fabricated model identity.

    ``bedrock`` mode resolves the inference profile at construction precisely so this
    surfaces at start-up.  Whether the failure arrives as a missing profile or a missing
    session is environment-dependent; that it is ``ProviderUnavailable`` — the exception
    whose ``silence_reason`` is ``unreachable`` — is not.
    """
    monkeypatch.setenv("MAINLINE_RECALL_PROVIDER", "bedrock")
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    monkeypatch.setenv("AWS_CONFIG_FILE", "/nonexistent/mainline/aws/config")
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", "/nonexistent/mainline/aws/creds")
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
    monkeypatch.delenv("AWS_SESSION_TOKEN", raising=False)
    monkeypatch.delenv("AWS_PROFILE", raising=False)

    with pytest.raises(ProviderUnavailable) as excinfo:
        get_judge_provider()
    assert excinfo.value.silence_reason == "unreachable"
