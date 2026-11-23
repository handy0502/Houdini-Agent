"""Real coordinator worker callbacks and localhost disconnect detection."""
import json
import socketserver
import threading
import time
from unittest.mock import MagicMock

import pytest

QtCore = pytest.importorskip("PySide6.QtCore")
from houdini_agent.ui_qml import external_app as external
from houdini_agent.bridge import doctor


class ControllerStub(QtCore.QObject):
    toast = QtCore.Signal(str)

    def __init__(self):
        super().__init__()
        self._session = object()
        self.running = False
        self.houdiniConnection = {"state": "disconnected", "port": 0, "sessions": []}
        self.callback_threads = []
        self.refreshContext = MagicMock()

    def update_houdini_connection(self, **values):
        self.callback_threads.append(QtCore.QThread.currentThread())
        self.houdiniConnection.update(values)


@pytest.fixture
def coordinator(monkeypatch, tmp_path):
    app = QtCore.QCoreApplication.instance() or QtCore.QCoreApplication([])
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    win = QtCore.QObject()
    ctrl = ControllerStub()
    coord = external.ExternalCoordinator(win, ctrl, str(tmp_path))
    yield app, coord, ctrl
    coord.poll.stop()
    coord._launch_watch.stop()


@pytest.fixture
def bridge_factory():
    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            line = self.rfile.readline(65536)
            if not line:
                return
            request = json.loads(line)
            result = {"id": request["id"], "success": True,
                      "result": {"status": "ok", "houdini": "22.0.test"}}
            self.wfile.write((json.dumps(result) + "\n").encode())

    class Server(socketserver.ThreadingMixIn, socketserver.TCPServer):
        allow_reuse_address = True
        daemon_threads = True

    servers = []

    def create():
        server = Server(("127.0.0.1", 0), Handler)
        threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True).start()
        servers.append(server)
        return server

    yield create
    for server in servers:
        server.shutdown()
        server.server_close()


def probe(app, coord):
    coord._poll_tick()
    deadline = time.monotonic() + 2
    while coord._probing and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    assert not coord._probing, "The worker must always deliver a completion signal"


def test_active_session_disconnects_before_full_scan_and_reconnects(coordinator, bridge_factory, monkeypatch):
    app, coord, ctrl = coordinator
    first = bridge_factory()
    first_port = first.server_address[1]
    monkeypatch.setenv("HAGENT_BRIDGE_PORT", str(first_port))
    probe(app, coord)
    assert coord.connected and ctrl.houdiniConnection["port"] == first_port
    assert coord.poll.interval() == 1500
    ctrl.houdiniConnection["sessions"] = [{"port": first_port, "version": "22.0.test"}]
    first.shutdown()
    first.server_close()
    original = coord._probe
    full_scan = MagicMock(side_effect=AssertionError("Connected heartbeats must not scan ports"))
    monkeypatch.setattr(coord, "_probe", full_scan)
    probe(app, coord)
    assert coord.connected  # one transient miss is tolerated
    probe(app, coord)
    assert not coord.connected
    assert ctrl.houdiniConnection["state"] == "disconnected"
    assert ctrl.houdiniConnection["version"] == ""
    assert ctrl.houdiniConnection["port"] == 0
    assert ctrl.houdiniConnection["sessions"] == []
    full_scan.assert_not_called()
    assert all(thread == app.thread() for thread in ctrl.callback_threads)
    second = bridge_factory()
    second_port = second.server_address[1]
    monkeypatch.setattr(coord, "_probe", original)
    monkeypatch.setattr(doctor, "_candidate_ports", lambda: [second_port])
    probe(app, coord)
    assert coord.connected
    assert ctrl.houdiniConnection["state"] == "connected"
    assert ctrl.houdiniConnection["port"] == second_port


def test_probe_exception_releases_the_inflight_flag(coordinator, monkeypatch):
    app, coord, ctrl = coordinator
    monkeypatch.setenv("HAGENT_BRIDGE_PORT", "45172")
    coord._attach({"status": "ok", "houdini": "22.0.test"})
    client = MagicMock()
    client.ping.side_effect = OSError("Offline fixture")
    monkeypatch.setattr(external, "BridgeClient", MagicMock(return_value=client))
    probe(app, coord)
    probe(app, coord)
    assert ctrl.houdiniConnection["state"] == "disconnected"


def test_manual_disconnect_blocks_requests_until_another_session_is_chosen(coordinator, bridge_factory, monkeypatch):
    app, coord, ctrl = coordinator
    first, second = bridge_factory(), bridge_factory()
    first_port, second_port = first.server_address[1], second.server_address[1]
    monkeypatch.setenv("HAGENT_BRIDGE_PORT", str(first_port))
    probe(app, coord)
    assert coord.connected
    ctrl.houdiniConnection["sessions"] = [
        {"port": first_port, "version": "22.0.test"}, {"port": second_port, "version": "22.0.test"}]
    generation = coord._connection_generation
    coord.connection_action("disconnect")
    assert ctrl.houdiniConnection["paused"]
    assert ctrl.houdiniConnection["state"] == "disconnected"
    coord._poll_tick()
    assert not coord._probing
    coord._on_poll_result({"status": "ok", "houdini": "stale"}, generation)
    assert not coord.connected
    assert coord.bridge.ping() is None
    with pytest.raises(RuntimeError, match="手动断开"):
        coord.bridge.execute_tool("read_selection")
    # Only this Agent connection is paused; the Houdini sessions stay alive.
    assert external.BridgeClient(port=first_port).ping()["status"] == "ok"
    coord.connection_action("connect:" + str(second_port))
    assert ctrl.houdiniConnection["paused"]  # no scene request before verification
    probe(app, coord)
    assert coord.connected and not ctrl.houdiniConnection["paused"]
    assert ctrl.houdiniConnection["port"] == second_port
    assert coord.bridge.ping()["status"] == "ok"
