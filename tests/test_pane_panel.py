"""Python Panel（pane tab）集成测试。

覆盖三件事，都不需要启动 Houdini：
1. ``HoudiniAgent.pypanel`` 是合法定义（XML + 脚本能编译 + 生命周期钩子齐全）；
2. 面板脚本能自己定位到仓库根（不依赖 hou）；
3. QML 面板能在离屏 Qt 里建起来（真正的 QQuickWidget 路径）。
"""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PYPANEL = REPO / "houdini_agent" / "houdini_package" / "python_panels" / "HoudiniAgent.pypanel"
SHELF = REPO / "houdini_agent" / "houdini_package" / "toolbar" / "HoudiniAgent.shelf"


def _script_of(element):
    node = element.find("script")
    assert node is not None and node.text and node.text.strip()
    return node.text


def test_pypanel_definition_is_valid():
    root = ET.parse(PYPANEL).getroot()
    assert root.tag == "pythonPanelDocument"
    iface = root.find("interface")
    assert iface is not None
    assert iface.get("name") == "hagent_chat"
    assert iface.get("label")
    assert iface.get("icon")

    script = _script_of(iface)
    namespace = {}
    exec(compile(script, str(PYPANEL), "exec"), namespace)
    for hook in ("onCreateInterface", "onDestroyInterface",
                 "onActivateInterface", "onDeactivateInterface"):
        assert callable(namespace[hook]), hook

    # 必须出现在 pane tab 菜单和 Python Panel 的接口下拉里
    assert iface.find("includeInPaneTabMenu") is not None
    assert iface.find("includeInToolbarMenu") is not None


def test_pypanel_script_finds_repo_root(monkeypatch):
    namespace = {"__name__": "hagent_panel_script"}
    exec(compile(_script_of(ET.parse(PYPANEL).getroot().find("interface")),
                 str(PYPANEL), "exec"), namespace)

    monkeypatch.setenv("HAGENT_REPO", str(REPO))
    assert Path(namespace["_repo_root"]()).resolve() == REPO.resolve()

    # HAGENT_REPO 缺失/失效时不该炸，返回空串或推导值
    monkeypatch.setenv("HAGENT_REPO", str(REPO / "does-not-exist"))
    resolved = namespace["_repo_root"]()
    assert resolved == "" or Path(resolved).name or Path(resolved).resolve() == REPO.resolve()


def test_pane_module_resolves_paths():
    from houdini_agent.ui_qml import pane

    assert Path(pane.repo_root()).resolve() == REPO.resolve()
    assert Path(pane.pypanel_path()) == PYPANEL
    assert pane.PANEL_INTERFACE == "hagent_chat"


def test_shelf_definition_is_valid():
    root = ET.parse(SHELF).getroot()
    assert root.tag == "shelfDocument"
    toolshelf = root.find("toolshelf")
    assert toolshelf is not None and toolshelf.get("name")
    members = [m.get("name") for m in toolshelf.findall("memberTool")]
    tools = {t.get("name"): t for t in root.findall("tool")}
    assert members and all(name in tools for name in members)
    for tool in tools.values():
        # shelf 脚本是动作代码，只做语法检查（不能执行：它会真的去开面板）
        compile(_script_of(tool), str(SHELF), "exec")


@pytest.mark.parametrize("renderer", ["native", "widget"])
def test_panel_widget_loads_offscreen(tmp_path, renderer):
    pytest.importorskip("PySide6.QtQuickWidgets")

    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["QT_QUICK_BACKEND"] = "software"
    env["QSG_RHI_BACKEND"] = "software"
    env["QML_DISABLE_DISK_CACHE"] = "1"
    env["HAGENT_PANE_RENDERER"] = renderer
    env["HAGENT_TELEMETRY_OFF"] = "1"
    env["LOCALAPPDATA"] = str(tmp_path / "appdata")
    env["PYTHONPATH"] = str(REPO) + os.pathsep + env.get("PYTHONPATH", "")
    env.pop("HAGENT_REPO", None)

    code = textwrap.dedent(r"""
        import os, sys
        from pathlib import Path
        from unittest.mock import patch
        hfs = Path(os.environ.get('HFS', ''))
        if os.name == 'nt' and (hfs / 'bin').is_dir():
            dll_handle = os.add_dll_directory(str(hfs / 'bin'))
        from PySide6.QtCore import QObject, QSettings, QEvent, Qt, qInstallMessageHandler
        from PySide6.QtWidgets import QApplication
        from PySide6.QtTest import QTest
        from houdini_agent.ui_qml import controller as module, pane
        app = QApplication([])
        state = Path(sys.argv[1])
        settings = QSettings(str(state / 'prefs.ini'), QSettings.IniFormat)
        warnings = []
        def message_handler(kind, context, message):
            if any(word in message for word in ('ReferenceError', 'TypeError',
                       'Cannot assign', 'Unable to assign', 'Binding loop')):
                warnings.append(message)
        qInstallMessageHandler(message_handler)
        with patch.object(module, 'QSettings', return_value=settings), \
             patch.object(module.Controller, '_session_cache_dir', return_value=state / 'sessions'), \
             patch.object(module.Controller, '_migrate_legacy_sessions'), \
             patch.object(module.Controller, '_auto_refresh_models_if_stale'), \
             patch.object(pane, '_install_hooks'):
            widget = pane.create_widget(use_backend=False)
            view = pane.inner_view(widget)
            widget.resize(700, 820)
            widget.show()
            QTest.qWait(900)
            root = view.rootObject()
            assert root is not None, [error.toString() for error in view.errors()]
            assert root.property('embedded')
            field = root.findChild(QObject, 'messageInput')
            assert field is not None and field.property('text') == ''
            pane.activate(widget)
            QTest.qWait(900)
            QTest.keyClick(view, Qt.Key_O)
            QTest.keyClick(view, Qt.Key_K)
            assert field.property('text') == 'ok', field.property('text')
            assert root.property('embeddedFocus'), 'Focused panel must enable Agent shortcuts'
            expanded = root.property('sidebarExpanded')
            QTest.keyClick(view, Qt.Key_B, Qt.ControlModifier)
            app.processEvents()
            assert root.property('sidebarExpanded') != expanded, 'Panel Ctrl+B must work'
            controller = pane.session()[0]
            session_count = len(controller._sessions)
            QTest.keyClick(view, Qt.Key_N, Qt.ControlModifier)
            app.processEvents()
            assert len(controller._sessions) == session_count + 1, 'Panel Ctrl+N must create a chat'
            QTest.keyClick(view, Qt.Key_Comma, Qt.ControlModifier)
            app.processEvents()
            assert root.findChild(QObject, 'settingsWindow').property('opened'), 'Panel Ctrl+, must work'
            widget.hide()
            QTest.qWait(20)
            assert not root.property('embeddedFocus'), 'Hidden panel must release host shortcuts'
            assert not warnings, '\n'.join(warnings)
            pane.deactivate(widget)
            pane.destroy_widget(widget)
            assert not pane._views
            widget.close()
            widget.deleteLater()
            app.sendPostedEvents(None, QEvent.DeferredDelete)
            app.processEvents()
        print('QML loaded OK; typing and panel teardown passed')
    """)
    proc = subprocess.run(
        [sys.executable, "-B", "-c", code, str(tmp_path)],
        cwd=str(REPO), env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=120,
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    assert proc.returncode == 0, output
    assert "QML loaded OK" in output, output


# --------------------------------------------------------------------------- open_pane_tab

class _FakeInterface:
    def __init__(self, name="hagent_chat"):
        self._name = name

    def name(self):
        return self._name


class _FakeTab:
    def __init__(self, interface="hagent_chat", tab_type="pythontab"):
        self._interface = _FakeInterface(interface)
        self._type = tab_type
        self.current = False

    def type(self):
        return self._type

    def activeInterface(self):
        return self._interface

    def setIsCurrentTab(self):
        self.current = True


class _FakePane:
    def __init__(self):
        self.created = []

    def createTab(self, tab_type, interface=None):
        self.created.append((tab_type, interface))
        return "created-tab"


def _fake_hou(tabs=(), pane=None, floating="floating-tab"):
    """最小 hou 替身：只覆盖 open_pane_tab 用到的 API。"""
    import types

    mod = types.ModuleType("hou")
    interfaces = {}
    installs = []
    floating_calls = []
    for tab in tabs:
        try:
            interfaces[tab.activeInterface().name()] = tab.activeInterface()
        except Exception:
            pass

    def install_file(path):
        installs.append(path)
        interfaces["hagent_chat"] = _FakeInterface()

    mod.pypanel = types.SimpleNamespace(
        interfaceByName=lambda name: interfaces.get(name),
        installFile=install_file,
        menuInterfaces=lambda: tuple(interfaces),
    )
    mod.paneTabType = types.SimpleNamespace(PythonPanel="pythontab")
    mod.ui = types.SimpleNamespace(
        paneTabs=lambda: list(tabs),
        paneUnderCursor=lambda: pane,
        paneTabOfType=lambda tab_type, index=0: None,
        curDesktop=lambda: types.SimpleNamespace(
            createFloatingPaneTab=lambda *a, **kw: (
                floating_calls.append((a, kw)) or floating)),
    )
    mod._installs = installs
    mod._floating_calls = floating_calls
    return mod


def test_open_pane_tab_installs_and_creates_tab(monkeypatch):
    from houdini_agent.ui_qml import pane

    fake = _fake_hou(pane=_FakePane())
    monkeypatch.setitem(sys.modules, "hou", fake)

    assert pane.open_pane_tab() == "created-tab"
    assert fake._installs == [pane.pypanel_path()]
    assert fake.ui.paneUnderCursor().created == [("pythontab", "hagent_chat")]
    assert not fake._floating_calls


def test_open_pane_tab_reuses_existing_tab(monkeypatch):
    from houdini_agent.ui_qml import pane

    existing = _FakeTab()
    fake = _fake_hou(tabs=[existing], pane=_FakePane())
    monkeypatch.setitem(sys.modules, "hou", fake)

    assert pane.open_pane_tab() is existing
    assert existing.current
    assert fake._installs == []          # 已加载就不重复 installFile
    assert not fake.ui.paneUnderCursor().created


def test_open_pane_tab_falls_back_to_floating(monkeypatch):
    from houdini_agent.ui_qml import pane

    fake = _fake_hou(pane=None)
    monkeypatch.setitem(sys.modules, "hou", fake)

    assert pane.open_pane_tab() == "floating-tab"
    args, kwargs = fake._floating_calls[-1]
    assert args[0] == "pythontab"
    assert kwargs.get("python_panel_interface") == "hagent_chat"
