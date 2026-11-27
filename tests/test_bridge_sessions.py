"""Real listeners: separate Houdini instances must never share a Bridge port."""
import os
import socketserver
import sys
from types import SimpleNamespace

import pytest

from houdini_agent.bridge import doctor, server
from houdini_agent.bridge.client import BridgeClient, port_file, resolve_port


@pytest.fixture
def bridges(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("HAGENT_BRIDGE_PORT", raising=False)
    monkeypatch.setitem(sys.modules, "hou", SimpleNamespace(applicationVersionString=lambda: "21.0.test"))
    monkeypatch.setattr(server, "_SERVER", None)
    monkeypatch.setattr(server, "_THREAD", None)
    running = []

    def start(port):
        # Each real Houdini process has its own module-level singleton.
        server._SERVER = None
        bridge = server.start_bridge(port=port)
        assert bridge is not None
        running.append((bridge, server._THREAD))
        return bridge.server_address[1]

    yield start
    for bridge, thread in running:
        bridge.shutdown()
        bridge.server_close()
        thread.join(timeout=2)


def test_multiple_instances_get_distinct_discoverable_ports(bridges, monkeypatch):
    # An ephemeral base avoids assuming the user's default ports are free.
    with server._Server(("127.0.0.1", 0), server._Handler) as reservation:
        base = reservation.server_address[1]
    monkeypatch.setenv("HAGENT_BRIDGE_PORT", str(base))
    first = bridges(base)
    second = bridges(first)
    assert first != second, "A second Houdini must advance to an unoccupied port"
    assert port_file().read_text(encoding="utf-8") == str(second)

    sessions = doctor.discover_sessions()
    assert {item["port"] for item in sessions} >= {first, second}
    assert resolve_port() == base, "Discovery must not change the selected session"
    for port in (second, first):
        doctor.adopt_port(port)
        assert BridgeClient().ping()["houdini"] == "21.0.test"
        assert resolve_port() == port


@pytest.mark.skipif(os.name != "nt", reason="Windows SO_REUSEADDR allows duplicate listeners")
def test_exclusive_listener_rejects_old_reuse_enabled_server():
    class LegacyServer(socketserver.TCPServer):
        allow_reuse_address = True

    with LegacyServer(("127.0.0.1", 0), server._Handler) as legacy:
        with pytest.raises(OSError):
            server._Server(legacy.server_address, server._Handler)
