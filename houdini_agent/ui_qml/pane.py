# -*- coding: utf-8 -*-
"""Houdini Python Panel（面板 Tab）入口。

Houdini 内嵌界面只有一条路：Python Panel。它的 ``onCreateInterface()`` 必须返回
一个 QtWidget，Houdini 会把该 widget 放进 pane tab。我们的 QML 界面由
``host.create_view()``（QQuickWidget）或 ``host.create_native_view()``（QQuickView）
承载，这里补的是：

1. 准备/复用一份 Agent 会话（Controller + ChatModel）；
2. 把 view 挂到这份会话上（多个面板共享同一条会话）；
3. 面板默认用 QQuickView 原生窗口（QWidget.createWindowContainer 嵌入）—— pane 里的
   QQuickWidget 没有独立原生窗口，键盘事件走不到它；原生窗口被点击即激活，键盘由
   OS 直接送达；
4. 兜底接管焦点/快捷键（见 ``_build_focus_guard`` / ``_build_shortcut_filter``），
   并保留 ``HAGENT_PANE_RENDERER=widget`` 回退到 QQuickWidget 路径；
5. 面板销毁 / 切 hip / Houdini 退出时落盘会话，但不打断正在跑的回合。

加载链路::

    houdini_agent/houdini_package/python_panels/HoudiniAgent.pypanel   (自动加载)
        -> onCreateInterface()
        -> houdini_agent.ui_qml.pane.create_widget(kwargs["paneTab"])
        -> host.create_native_view(controller, model)                  (QQuickView)
        -> QWidget.createWindowContainer(view)                         (返回给 Houdini)

也可以在 shelf / 脚本里直接 :func:`open_pane_tab` 打开（自动 installFile +
切到当前 pane 的新 tab）。旧的浮动窗口入口（``ui_qml.app.show_tool``）保持不变。
"""

from __future__ import annotations

import os
import sys

# 面板重开时重新读盘上的 QML（开发热更新）；和 app.py 的做法一致。
os.environ.setdefault("QML_DISABLE_DISK_CACHE", "1")

PANEL_INTERFACE = "hagent_chat"
PANEL_LABEL = "Houdini Agent"

_state = None        # {"controller": ..., "model": ...} 进程级单例
_views = []          # 还活着的 QQuickWidget（一个面板一个）
_save_hook = None    # hipFile 事件回调，必须持有引用
_hip_hooked = False
_about_hooked = False


# --------------------------------------------------------------------------- paths

def repo_root():
    """返回 Houdini 侧代码根目录（含 houdini_agent/ 的那一层）。"""
    env = os.environ.get("HAGENT_REPO", "").strip()
    if env and os.path.isdir(os.path.join(env, "houdini_agent")):
        return os.path.abspath(env)
    # <root>/houdini_agent/ui_qml/pane.py -> <root>
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(here, "..", ".."))


def pypanel_path():
    """``.pypanel`` 定义文件的位置（源码树与 PyInstaller 的 bridge_payload 同构）。"""
    return os.path.join(repo_root(), "houdini_agent", "houdini_package",
                        "python_panels", "HoudiniAgent.pypanel")


def _houdini_available():
    try:
        import hou  # noqa: F401
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------- session

def session(use_backend=None):
    """返回 (controller, model)，首次调用时创建并恢复历史会话。"""
    global _state
    if _state is not None:
        return _state["controller"], _state["model"]

    from .controller import ChatModel, Controller

    if use_backend is None:
        use_backend = _houdini_available()

    model = ChatModel()
    controller = Controller(model, use_backend=use_backend)
    try:
        controller.restore()
    except Exception as exc:  # 坏会话文件不该让面板打不开
        print("[pane] restore failed:", exc)

    _state = {"controller": controller, "model": model}
    _install_hooks(controller)
    return controller, model


def has_session():
    return _state is not None


def _save():
    if _state is None:
        return
    try:
        _state["controller"]._save_all()
    except Exception as exc:
        print("[pane] save sessions failed:", exc)


def _install_hooks(controller):
    """会话保存钩子：切 hip 前、Houdini 退出时落盘；顺手排一次更新检查。"""
    global _hip_hooked, _about_hooked, _save_hook

    if not _hip_hooked:
        try:
            import hou
        except Exception:
            hou = None
        if hou is not None:
            def _on_hip(event_type):
                try:
                    if event_type in (hou.hipFileEventType.BeforeClear,
                                      hou.hipFileEventType.BeforeLoad):
                        _save()
                except Exception:
                    pass
            _save_hook = _on_hip
            try:
                hou.hipFile.addEventCallback(_on_hip)
                _hip_hooked = True
            except Exception as exc:
                print("[pane] hipFile callback failed:", exc)

    if not _about_hooked:
        try:
            from houdini_agent.qt_compat import QtWidgets
            app = QtWidgets.QApplication.instance()
            if app is not None:
                app.aboutToQuit.connect(_save)
                _about_hooked = True
        except Exception:
            pass

    try:
        from houdini_agent.qt_compat import QtCore
        QtCore.QTimer.singleShot(4000, controller.silentUpdateCheck)
    except Exception:
        pass


# --------------------------------------------------------------------------- widget

def _qt():
    from houdini_agent.qt_compat import QtWidgets, QtCore, QtGui
    return QtWidgets, QtCore, QtGui


def _diag(message):
    """面板焦点问题诊断：stdout（Houdini Python Shell）+ pane.log。"""
    try:
        print("[Houdini Agent][pane] " + str(message))
    except Exception:
        pass
    try:
        import time
        from pathlib import Path
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "HoudiniAgent"
        base.mkdir(parents=True, exist_ok=True)
        with (base / "pane.log").open("a", encoding="utf-8") as handle:
            handle.write(time.strftime("[%Y-%m-%d %H:%M:%S] ") + str(message).rstrip() + "\n")
    except Exception:
        pass


def _qml_root(view):
    try:
        return view.rootObject()
    except Exception:
        return None


def _active_focus_item(view):
    """QQuickWidget 与 QQuickView 取 QML 焦点项的方式不同，这里统一。"""
    try:
        if hasattr(view, "quickWindow"):
            return view.quickWindow().activeFocusItem()
        return view.activeFocusItem()
    except Exception:
        return None


def _view_visible(view):
    try:
        return bool(view.isVisible())
    except Exception:
        return False


def _focus_widget(entry):
    """面板里真正应该拿键盘焦点的 QWidget（一律是 container）。"""
    return entry["container"]


def _build_focus_guard():
    """应用级事件过滤器：兜住 Houdini 不把键盘交给面板的情况（主要是旧 QQuickWidget 路径）。

    - 鼠标在面板里按下 → 把焦点给容器（原生窗口顺便 activate）；
    - ShortcutOverride 纯字母键在面板里直接接受，压掉 Houdini 单键热键；
    - 焦点不在面板上时，按键 / 输入法事件复制一份转发给面板并吞掉原事件。
    只在“最近一次点击发生在面板里”时生效，点到 Houdini 别的控件自动放开。
    """
    QtWidgets, QtCore, QtGui = _qt()

    class FocusGuard(QtCore.QObject):
        def __init__(self):
            super().__init__()
            self.armed = None          # 最近点击过的 entry
            self.forwarded = 0
            self._sending = False

        def _entry_for(self, obj):
            for entry in list(_views):
                if obj is entry["view"] or obj is entry["container"]:
                    return entry
                if isinstance(obj, QtWidgets.QWidget):
                    try:
                        if entry["container"].isAncestorOf(obj):
                            return entry
                    except Exception:
                        pass
            return None

        def _clone(self, event):
            kind = event.type()
            if kind in (QtCore.QEvent.KeyPress, QtCore.QEvent.KeyRelease,
                        QtCore.QEvent.ShortcutOverride):
                return QtGui.QKeyEvent(kind, event.key(), event.modifiers(),
                                       event.text(), event.isAutoRepeat(), event.count())
            if kind == QtCore.QEvent.InputMethod:
                try:
                    return QtGui.QInputMethodEvent(event)
                except Exception:
                    return None
            return None

        def _plain_key(self, event):
            mods = event.modifiers()
            blocked = (QtCore.Qt.ControlModifier | QtCore.Qt.AltModifier
                       | QtCore.Qt.MetaModifier)
            return not (mods & blocked)

        def _take_focus(self, entry):
            try:
                _focus_entry(entry)
            except Exception:
                pass

        def eventFilter(self, obj, event):
            kind = event.type()
            if kind == QtCore.QEvent.MouseButtonPress:
                entry = self._entry_for(obj)
                # 原生窗口（QQuickView）自己处理鼠标/键盘，这里不能再抢焦点：
                # 否则每点一次按钮/菜单都把 QML 焦点抢到输入框，点击就被打断了。
                if entry is not None and not entry.get("native"):
                    self.armed = entry
                    self._take_focus(entry)
                else:
                    self.armed = None
                return False

            if kind == QtCore.QEvent.ShortcutOverride and self._plain_key(event):
                entry = self.armed
                if (entry is not None and not entry.get("native")
                        and _view_visible(entry["view"])
                        and _active_focus_item(entry["view"]) is not None):
                    event.accept()
                    return True

            if kind in (QtCore.QEvent.KeyPress, QtCore.QEvent.KeyRelease,
                        QtCore.QEvent.ShortcutOverride, QtCore.QEvent.InputMethod):
                if self._sending:
                    return False
                entry = self.armed
                if entry is None or entry.get("native") or not _view_visible(entry["view"]):
                    return False
                container = entry["container"]
                try:
                    focused = QtWidgets.QApplication.focusWidget()
                except Exception:
                    focused = None
                if focused is container or (focused is not None
                                            and container.isAncestorOf(focused)):
                    return False
                _focus_entry(entry)
                clone = self._clone(event)
                if clone is None:
                    return False
                self._sending = True
                try:
                    QtWidgets.QApplication.sendEvent(entry["view"], clone)
                finally:
                    self._sending = False
                self.forwarded += 1
                if self.forwarded in (1, 50):
                    _diag("key/IME forwarded to panel (%d)" % self.forwarded)
                return True
            return False

    return FocusGuard()


def _sync_shortcut_focus(entry):
    """Only enable Agent shortcuts while this view owns the keyboard."""
    try:
        view = entry["view"]
        root = _qml_root(view)
        if root is not None:
            focused = view.isActive() if entry.get("native") else view.hasFocus()
            root.setProperty("embeddedFocus", bool(focused) and _view_visible(view))
    except Exception:
        pass  # A deferred focus event may outlive its panel.


def _build_shortcut_filter(entry):
    """面板里打字时，别让 Houdini 的单键热键把字母键吃掉。"""
    QtWidgets, QtCore, QtGui = _qt()

    class ShortcutFilter(QtCore.QObject):
        def eventFilter(self, obj, event):
            if event.type() in (QtCore.QEvent.FocusIn, QtCore.QEvent.FocusOut,
                                QtCore.QEvent.Show, QtCore.QEvent.Hide):
                QtCore.QTimer.singleShot(0, lambda: _sync_shortcut_focus(entry))
            if event.type() != QtCore.QEvent.ShortcutOverride:
                return False
            if entry.get("native"):
                return False
            try:
                mods = event.modifiers()
                if mods & (QtCore.Qt.ControlModifier | QtCore.Qt.AltModifier
                           | QtCore.Qt.MetaModifier):
                    return False
                item = _active_focus_item(entry["view"])
                if item is None:
                    return False
                if item.property("text") is not None:
                    event.accept()
                    return True
            except Exception:
                pass
            return False

    return ShortcutFilter()


def _start_focus_watch(entry):
    """诊断：QML 焦点变化与容器焦点状态打到 pane.log（仅在变化时记）。"""
    QtWidgets, QtCore, QtGui = _qt()
    timer = QtCore.QTimer()
    timer.setInterval(400)

    def tick():
        item = _active_focus_item(entry["view"])
        try:
            name = item.objectName() if item is not None else ""
            if not name:
                name = item.metaObject().className() if item is not None else "<none>"
        except Exception:
            name = "<dead>"
        if name != entry.get("_focus"):
            entry["_focus"] = name
            container = entry["container"]
            try:
                widget_focused = bool(container.hasFocus())
            except Exception:
                widget_focused = False
            try:
                active = bool(entry["view"].isActive()) if hasattr(entry["view"], "isActive") else widget_focused
            except Exception:
                active = widget_focused
            _diag("focus -> %s (container focused=%s active=%s)" % (name, widget_focused, active))

    timer.timeout.connect(tick)
    timer.start()
    return timer


def _build_key_log(entry):
    QtWidgets, QtCore, QtGui = _qt()

    class KeyLog(QtCore.QObject):
        def eventFilter(self, obj, event):
            if event.type() == QtCore.QEvent.KeyPress:
                entry["_keys"] = entry.get("_keys", 0) + 1
                if entry["_keys"] <= 8:
                    item = _active_focus_item(entry["view"])
                    name = item.objectName() if item is not None else "<none>"
                    _diag("key code=%s -> qml focus %s" % (event.key(), name))
            return False

    return KeyLog()


def _build_mouse_log(entry):
    """诊断：前几次鼠标事件打到 pane.log，确认原生窗口有没有收到点击。"""
    QtWidgets, QtCore, QtGui = _qt()

    class MouseLog(QtCore.QObject):
        def eventFilter(self, obj, event):
            kind = event.type()
            if kind in (QtCore.QEvent.MouseButtonPress, QtCore.QEvent.MouseButtonRelease):
                entry["_mouse"] = entry.get("_mouse", 0) + 1
                if entry["_mouse"] <= 8:
                    _diag("mouse %s on %s" % (
                        "press" if kind == QtCore.QEvent.MouseButtonPress else "release",
                        type(obj).__name__))
            return False

    return MouseLog()


_guard = None


def _focus_guard():
    global _guard
    if _guard is not None:
        return _guard
    try:
        QtWidgets, QtCore, QtGui = _qt()
        app = QtWidgets.QApplication.instance()
        if app is None:
            return None
        _guard = _build_focus_guard()
        app.installEventFilter(_guard)
        _diag("focus guard installed")
        return _guard
    except Exception as exc:
        _diag("focus guard failed: %s" % exc)
        return None


def create_widget(pane_tab=None, use_backend=None):
    """Python Panel 的 ``onCreateInterface()`` 直接返回本函数的返回值。

    默认用 QQuickView（原生 QWindow）+ ``QWidget.createWindowContainer`` 嵌进 pane：
    pane 里的 QQuickWidget 没有独立原生窗口，键盘事件走不到它（pane.log 里看不到任何
    key code）；原生窗口被点击时会直接激活，键盘由操作系统送达。设
    ``HAGENT_PANE_RENDERER=widget`` 可回退到旧的 QQuickWidget 路径。
    """
    controller, model = session(use_backend=use_backend)

    from . import host
    native = os.environ.get("HAGENT_PANE_RENDERER", "native").strip().lower() != "widget"
    view = None
    if native:
        try:
            view = host.create_native_view(controller=controller, model=model)
        except Exception as exc:
            _diag("native view failed (%s), fallback to QQuickWidget" % exc)
            view = None
    if view is None:
        view = host.create_view(controller=controller, model=model)
        native = False

    try:
        root = _qml_root(view)
        if root is not None:
            root.setProperty("embedded", True)
    except Exception:
        pass

    QtWidgets, QtCore, QtGui = _qt()
    if native:
        container = QtWidgets.QWidget.createWindowContainer(view)
        container.setObjectName("hagentPaneRoot")
        container.setFocusPolicy(QtCore.Qt.StrongFocus)
        container.setAttribute(QtCore.Qt.WA_InputMethodEnabled, True)
    else:
        view.setFocusPolicy(QtCore.Qt.StrongFocus)
        view.setAttribute(QtCore.Qt.WA_InputMethodEnabled, True)
        container = QtWidgets.QWidget()
        container.setObjectName("hagentPaneRoot")
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(view)
        container.setFocusPolicy(QtCore.Qt.StrongFocus)
        try:
            container.setFocusProxy(view)
        except Exception:
            pass

    entry = {"view": view, "container": container, "native": native, "filters": []}
    _views.append(entry)
    try:
        container.destroyed.connect(lambda *_: _forget(container))
    except Exception:
        pass

    shortcut_filter = _build_shortcut_filter(entry)
    key_log = _build_key_log(entry)
    mouse_log = _build_mouse_log(entry)
    filters = [key_log, mouse_log, shortcut_filter]
    if native:
        view.activeChanged.connect(lambda: _sync_shortcut_focus(entry))
    for filt in filters:
        try:
            view.installEventFilter(filt)
        except Exception:
            pass
        try:
            container.installEventFilter(filt)
        except Exception:
            pass
    entry["filters"] = filters
    try:
        entry["watch"] = _start_focus_watch(entry)
    except Exception as exc:
        _diag("focus watch failed: %s" % exc)

    _focus_guard()
    _apply_label(pane_tab)
    _schedule_focus(entry)
    _diag("panel created: view=%s native=%s" % (type(view).__name__, native))
    return container


def _apply_label(pane_tab):
    if pane_tab is None:
        return
    try:
        pane_tab.setLabel(PANEL_LABEL)
    except Exception:
        pass


def inner_view(widget):
    """从 create_widget 返回的容器（或 view 本身）取回 QML view（QWindow / QWidget）。"""
    if widget is None:
        return None
    for entry in list(_views):
        if entry["container"] is widget or entry["view"] is widget:
            return entry["view"]
    return widget


def _schedule_focus(entry):
    """Houdini 会在 onCreateInterface 之后才把 widget 塞进 pane，所以焦点要重试几次。"""
    QtWidgets, QtCore, QtGui = _qt()
    view = entry["view"]
    container = entry["container"]

    def grab():
        try:
            if not _view_visible(view):
                return
        except Exception:
            pass
        _focus_entry(entry)

    for delay in (0, 60, 250, 800):
        try:
            QtCore.QTimer.singleShot(delay, grab)
        except Exception:
            break


def _focus_entry(entry):
    """把键盘焦点交给容器 + QML 输入框；原生窗口顺带 requestActivate。"""
    view = entry["view"]
    container = entry["container"]
    root = _qml_root(view)
    try:
        if root is not None:
            from houdini_agent.qt_compat import QtCore
            QtCore.QMetaObject.invokeMethod(root, "focusComposer")
    except Exception:
        pass
    try:
        container.setFocus()
    except Exception:
        pass
    if entry.get("native"):
        try:
            view.requestActivate()
        except Exception:
            pass


def _forget(widget):
    global _views
    keep = []
    try:
        for entry in _views:
            if entry["container"] is widget or entry["view"] is widget:
                try:
                    if entry.get("watch") is not None:
                        entry["watch"].stop()
                except Exception:
                    pass
                continue
            keep.append(entry)
        _views = keep
    except Exception:
        _views = []


def destroy_widget(widget=None):
    """面板销毁（关闭 / 换 pane tab 类型 / reload interface）时调用。"""
    if _guard is not None:
        try:
            entry = next((e for e in _views
                          if e["container"] is widget or e["view"] is widget), None)
            if entry is not None and _guard.armed is entry:
                _guard.armed = None
        except Exception:
            pass
    _forget(widget)
    _save()


def activate(widget=None):
    """``onActivateInterface``：切到这个 tab 时把焦点给输入框。"""
    entry = None
    if widget is None:
        entry = _views[-1] if _views else None
    else:
        entry = next((e for e in _views
                      if e["container"] is widget or e["view"] is widget), None)
    if entry is not None:
        _schedule_focus(entry)


def deactivate(widget=None):
    """``onDeactivateInterface``：切走时落一次盘，避免异常退出丢历史。"""
    _save()


# --------------------------------------------------------------------------- pane tab

def _ensure_installed(hou, interface):
    if hou.pypanel.interfaceByName(interface) is not None:
        return
    path = pypanel_path()
    if not os.path.isfile(path):
        raise RuntimeError("找不到面板定义文件: %s" % path)
    hou.pypanel.installFile(path)
    if hou.pypanel.interfaceByName(interface) is None:
        raise RuntimeError("面板接口 %r 安装失败（检查 %s 的 XML / script）" % (interface, path))


def _existing_tab(hou, interface):
    try:
        tabs = hou.ui.paneTabs()
    except Exception:
        return None
    for tab in tabs:
        try:
            if tab.type() != hou.paneTabType.PythonPanel:
                continue
            iface = tab.activeInterface()
            if iface is not None and iface.name() == interface:
                return tab
        except Exception:
            continue
    return None


def _target_pane(hou):
    """优先用鼠标下方的 pane，其次用第一个网络编辑器的 pane（shelf 工具调用时）。"""
    try:
        pane = hou.ui.paneUnderCursor()
        if pane is not None:
            return pane
    except Exception:
        pass
    try:
        tab = hou.ui.paneTabOfType(hou.paneTabType.NetworkEditor)
        if tab is not None:
            return tab.pane()
    except Exception:
        pass
    return None


def open_pane_tab(interface=PANEL_INTERFACE, pane=None):
    """把 Agent 面板作为新 tab 打开在当前 pane（没有 pane 就开浮动面板）。"""
    import hou

    _ensure_installed(hou, interface)

    existing = _existing_tab(hou, interface)
    if existing is not None:
        try:
            existing.setIsCurrentTab()
        except Exception:
            pass
        return existing

    target = pane if pane is not None else _target_pane(hou)
    if target is not None:
        try:
            tab = target.createTab(hou.paneTabType.PythonPanel, interface)
            if tab is not None:
                return tab
        except Exception as exc:
            print("[pane] createTab failed, falling back to floating panel:", exc)

    desktop = hou.ui.curDesktop()
    try:
        return desktop.createFloatingPaneTab(
            hou.paneTabType.PythonPanel, python_panel_interface=interface)
    except TypeError:
        # 老版本没有 python_panel_interface 参数
        tab = desktop.createFloatingPaneTab(hou.paneTabType.PythonPanel)
        tab.setActiveInterface(hou.pypanel.interfaceByName(interface))
        return tab


def reload_active_panel():
    """重载当前 Agent 面板的 interface（改 .pypanel 脚本后免重启 Houdini）。"""
    import hou
    tab = _existing_tab(hou, PANEL_INTERFACE)
    if tab is None:
        return None
    tab.reloadActiveInterface()
    return tab


# --------------------------------------------------------------------------- selftest

def _selftest():
    """离屏自检：不启动 Houdini，只验证 QML 面板能建起来、无 QML 错误、能收到键盘。"""
    from houdini_agent.qt_compat import QtWidgets, QtCore, QtGui

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    container = create_widget(use_backend=False)
    view = inner_view(container)
    container.resize(460, 820)
    container.show()
    for _ in range(10):
        app.processEvents()

    root = view.rootObject()
    if root is None:
        print("[pane selftest] FAILED: no QML root")
        return 1

    print("[pane selftest] QML loaded OK — view:", type(view).__name__,
          "root:", root is not None)

    # 键盘通路自检。
    # QQuickWidget 路径能走真实 Qt 键盘分发（离屏可验证）；QQuickView 的原生窗口键盘
    # 只能靠 OS 在 Houdini 里验证，这里只测 QML 侧的 focusInput/activeFocus 接线。
    try:
        from houdini_agent.qt_compat import QtCore
        input_area = root.findChild(QtCore.QObject, "messageInput")
        if hasattr(view, "quickWindow"):
            from PySide6.QtTest import QTest
            container.setFocus()
            app.processEvents()
            QTest.keyClicks(view, "ok")
            for _ in range(10):
                app.processEvents()
            print("[pane selftest] keyboard -> messageInput:",
                  repr(input_area.property("text") or ""))
        else:
            composer = root.findChild(QtCore.QObject, "composer")
            invoked = composer is not None and QtCore.QMetaObject.invokeMethod(
                composer, "focusInput")
            for _ in range(10):
                app.processEvents()
            print("[pane selftest] keyboard (native) -> focusInput=%s activeFocus=%s" % (
                invoked, input_area.property("activeFocus") if input_area is not None else False))
    except Exception as exc:
        print("[pane selftest] keyboard probe failed:", exc)

    shot = os.environ.get("HAGENT_PANE_SNAPSHOT")
    if shot:
        app.processEvents()
        ok = root.grabToImage().save(shot)
        print("[pane selftest] snapshot", "saved" if ok else "FAILED", shot)
    return 0


if __name__ == "__main__":
    sys.exit(_selftest())
