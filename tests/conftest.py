"""Offline tests never read operator defaults or contact network services."""

import socket

import pytest


@pytest.fixture(autouse=True)
def isolated_defaults(monkeypatch, tmp_path, request):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    if request.node.get_closest_marker("integration"):
        return

    def denied(*args, **kwargs):
        raise AssertionError("Network access is forbidden in offline tests")

    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
