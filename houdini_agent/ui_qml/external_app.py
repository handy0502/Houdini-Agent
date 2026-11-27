# -*- coding: utf-8 -*-
"""Standalone double-click entry point for Houdini Agent."""

import os
import threading
import time
import traceback
from pathlib import Path

os.environ.setdefault("QML_DISABLE_DISK_CACHE", "1")

try:
    from PySide6.QtCore import QSettings, QTimer, QObject, Signal, Slot
    from PySide6.QtWidgets import QApplication, QMainWindow
except ImportError:
    from PySide2.QtCore import QSettings, QTimer, QObject, Signal, Slot
    from PySide2.QtWidgets import QApplication, QMainWindow

from houdini_agent.bridge.client import BridgeClient
from houdini_agent.launcher.houdini_discovery import (
    find_houdini_installs, install_all_packages, is_houdini_running, launch_houdini
)
from houdini_agent.ui_qml import host
from houdini_agent.ui_qml.bridge_session import BridgeAgentSession
from houdini_agent.ui_qml.controller import ChatModel, Controller


_GEO_ORG = ("HoudiniAI", "External")


class ExternalWindow(QMainWindow):
    def closeEvent(self, event):
        try:
            QSettings(*_GEO_ORG).setValue("geometry", self.saveGeometry())
        except Exception:
            pass
        try:
            ctrl = getattr(self, "_controller", None)
            if ctrl is not None:
                ctrl._snapshot_active()
                ctrl._save_all()
        except Exception:
            pass
        super().closeEvent(event)


class ExternalCoordinator(QObject):
    # 后台探测线程通过此信号把结果回传到 UI 线程（跨线程 emit 默认走队列连接）。
    _probe_done = Signal(object, int)
    # 后台构建好的聊天后端（BridgeAgentSession，失败为 None）回传到 UI 线程挂载。
    _session_ready = Signal(object)
    _sessions_found = Signal(object)

    def __init__(self, win, controller, repo_root):
        super().__init__(win)
        self.win = win
        self.controller = controller
        self.repo_root = str(repo_root)
        self.bridge = BridgeClient()
        self.connected = False
        self.installs = []
        self._connect_requested = False
        self._paused = False
        self._connection_generation = 0
        self._requested_port = None
        self._discovering = False
        self._launch_deadline = 0
        self._launch_started_at = 0
        self._launch_process = None
        self._launch_watch = QTimer(win)
        self._launch_watch.setInterval(500)
        self._launch_watch.timeout.connect(self._check_launch)
        self._probing = False
        self._probe_port = None
        self._building_session = False
        self._session_build_fails = 0
        self._misses = 0            # 已连接状态下心跳连续失败次数
        self._ever_connected = False
        self.poll = QTimer(win)
        self.poll.setInterval(1500)
        # 周期探测改走非阻塞路径：在后台线程 ping，避免冻结 UI 主线程。
        self.poll.timeout.connect(self._poll_tick)
        self._probe_done.connect(self._on_poll_result)
        self._session_ready.connect(self._on_session_ready)
        self._sessions_found.connect(self._on_sessions_found)
        self.controller.update_houdini_connection(external=True, state="connecting")

    def _log(self, msg):
        try:
            import time
            p = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "HoudiniAgent" / "launcher.log"
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("a", encoding="utf-8") as f:
                f.write(time.strftime("[%Y-%m-%d %H:%M:%S] ") + str(msg).rstrip() + "\n")
        except Exception:
            pass

    def start(self):
        self.installs = find_houdini_installs()
        self.controller.update_houdini_connection(installs=[
            {"version": item["version"], "path": item["path"]} for item in self.installs
        ])
        self._ensure_packages()
        # ★ 不等 Bridge：先把聊天后端建好。没有 Houdini 也必须能正常聊天/用 Meshy，
        #   场景工具在 Bridge 连上后自动生效（BridgeClient 每次请求现连、端口动态解析）。
        self._start_session_build()
        self.poll.start()
        self._poll_tick()  # 立即非阻塞探测一次（结果异步回来）

    def _ensure_packages(self):
        """给所有相关 Houdini 版本装集成包：写全部候选用户目录（注册表 Documents /
        USERPROFILE / env），并覆盖安装扫描漏掉但用户目录存在的版本。"""
        try:
            written = install_all_packages(self.repo_root, self.installs)
            self._log("packages installed: %s" % written)
        except Exception as exc:
            print("[external launcher] package install failed:", exc)
            self._log("package install failed: %s" % exc)

    @staticmethod
    def _probe():
        """探一次 Bridge：先 ping 当前解析端口，不通就全端口扫描并自动采纳
        （治愈端口发现文件过期/环境变量指错/服务器顺延换端口）。可能阻塞 ~1 秒，
        只允许在后台线程调用。返回 ping 结果或 None。"""
        try:
            from houdini_agent.bridge import doctor
            port, info = doctor.ensure_connected()
            return dict(info, _bridge_port=port) if info else None
        except Exception:
            return None

    def _attach(self, info):
        """Bridge 已响应：标记连接并广播。聊天后端在启动时就已异步构建（不依赖 Bridge），
        BridgeClient 每次请求现连，场景工具自此自动生效。轮询不停止而是降频为心跳，
        这样 Houdini 关闭/重启能被发现，恢复后自动重连。"""
        if self._paused:
            return False
        self.bridge.set_enabled(True)
        from houdini_agent.bridge.client import resolve_port
        port = info.get("_bridge_port") or resolve_port()
        changed = self.controller.houdiniConnection.get("port") != port
        self.controller.update_houdini_connection(
            state="connected", version=str(info.get("houdini") or ""), port=port, paused=False)
        self._launch_deadline = 0
        self._launch_process = None
        self._launch_watch.stop()
        if self.connected:
            if changed:
                self.controller.toast.emit("已切换 Houdini 会话")
                self.controller.refreshContext()
            return True
        self.connected = True
        self._misses = 0
        self.poll.setInterval(1500)
        if self.controller._session is not None:
            self.controller.toast.emit("已重新连接 Houdini Bridge" if self._ever_connected
                                       else "已连接 Houdini Bridge")
            try:
                self.controller.refreshContext()
            except Exception:
                pass
        else:
            # 后端还没建好/上次构建失败：现在重试，建好后 _on_session_ready 会补报连接
            self._start_session_build()
        self._ever_connected = True
        return True

    def _on_bridge_lost(self):
        """Clear the active connection as soon as its heartbeat is lost."""
        self.connected = False
        current = self.controller.houdiniConnection
        sessions = [item for item in current.get("sessions", []) if item["port"] != current.get("port")]
        self.controller.update_houdini_connection(state="disconnected", version="", port=0, sessions=sessions)
        self._misses = 0
        self.poll.setInterval(1500)     # 恢复快轮询
        self.controller.toast.emit("Houdini 连接已断开——聊天不受影响，重新打开 Houdini 后会自动重连")
        try:
            self.controller.refreshContext()
        except Exception:
            pass

    def _start_session_build(self):
        """后台线程构建聊天后端（LLM 会话）。构建含系统提示词/文档索引，可能耗时数秒，
        放后台线程避免卡 UI；完成后经 _session_ready 信号回 UI 线程挂载。"""
        if (self._building_session or self.controller._session is not None
                or self._session_build_fails >= 3):
            return
        self._building_session = True

        def worker():
            session = None
            try:
                session = BridgeAgentSession(self.bridge)
            except Exception as exc:
                self._log("Chat backend init failed: %s\n%s" % (exc, traceback.format_exc()))
            try:
                self._session_ready.emit(session)   # 跨线程：队列连接，槽在 UI 线程执行
            except Exception:
                pass

        threading.Thread(target=worker, name="HAgentSessionBuild", daemon=True).start()

    @Slot(object)
    def _on_session_ready(self, session):
        """运行在 UI 线程：挂载后台构建好的聊天后端。"""
        self._building_session = False
        if session is None:
            self._session_build_fails += 1
            if self._session_build_fails == 1:
                self.controller.toast.emit("AI 后端初始化失败，正在自动重试…")
            elif self._session_build_fails >= 3:
                log = Path(os.environ.get("LOCALAPPDATA") or str(Path.home())) / "HoudiniAgent" / "launcher.log"
                self.controller.toast.emit("AI 后端多次初始化失败，聊天暂不可用。请反馈日志：%s" % log)
            return
        if self.controller._session is not None:
            return
        self._session_build_fails = 0
        self.controller.attach_backend_session(session, announce=False)
        if self.connected:
            self.controller.toast.emit("已连接 Houdini Bridge")

    def _poll_tick(self):
        """Ping the active session directly; scan ports only while disconnected.

        A failed heartbeat must reach the UI before a potentially slow scan of
        every candidate port. Two short misses normally update within 3 seconds.
        """
        if self.controller._session is None:
            self._start_session_build()   # 构建失败后的自动重试（最多 3 次）
        if self._paused or self._probing:
            return
        self._probing = True
        requested_port = self._requested_port
        self._probe_port = requested_port
        from houdini_agent.bridge.client import resolve_port
        heartbeat_port = resolve_port() if self.connected else None
        generation = self._connection_generation

        def worker():
            info = None
            try:
                if requested_port is not None:
                    info = BridgeClient(port=requested_port, connect_timeout=0.3).ping()
                elif heartbeat_port:
                    info = BridgeClient(port=heartbeat_port, connect_timeout=0.15).ping()
                else:
                    info = self._probe()
                if not isinstance(info, dict) or info.get("status") != "ok":
                    info = None
                elif requested_port is not None or heartbeat_port:
                    info = dict(info, _bridge_port=requested_port if requested_port is not None else heartbeat_port)
            except Exception as exc:
                self._log("Bridge probe failed: %s" % exc)
            try:
                self._probe_done.emit(info, generation)
            except Exception:
                pass

        threading.Thread(target=worker, name="HAgentBridgeProbe", daemon=True).start()

    @Slot(object, int)
    def _on_poll_result(self, info, generation=None):
        """运行在 UI 线程：应用后台探测结果（连接/断开状态机）。"""
        self._probing = False
        if self._paused:
            return
        if generation is not None and generation != self._connection_generation:
            self._poll_tick()
            return
        if not info:
            self._check_launch()
        # A user may select a session while an older background probe is still
        # running. Ignore that result and verify the selected port first.
        if self._probe_port != self._requested_port:
            self._poll_tick()
            return
        if info:
            if self._requested_port is not None:
                if self.controller.running:
                    self._connect_requested = False
                    self._requested_port = None
                    self._paused = not self.connected
                    self.bridge.set_enabled(self.connected)
                    self.controller.update_houdini_connection(state="connected" if self.connected else "disconnected", paused=not self.connected)
                    self.controller.toast.emit("当前任务已开始，暂不切换 Houdini 会话。")
                    return
                from houdini_agent.bridge.doctor import adopt_port
                adopt_port(self._requested_port)
            self._misses = 0
            self._attach(info)
            self._connect_requested = False
            self._requested_port = None
            return
        if self.connected and not self._connect_requested:
            self._misses += 1
            if self._misses >= 2:
                self._on_bridge_lost()
        if self._connect_requested:
            self._connect_requested = False
            self._requested_port = None
            self.controller.toast.emit("未找到可连接的 Houdini Bridge。请先启动 Houdini；若尚未加载 Bridge，请保存场景后重启 Houdini。")
            if self.connected:
                self.bridge.set_enabled(True)
                self.controller.update_houdini_connection(state="connected", paused=False)
            else:
                self._paused = True
                self.controller.update_houdini_connection(paused=True)
        if not self.connected and time.monotonic() >= self._launch_deadline:
            self.controller.update_houdini_connection(state="disconnected", version="", port=0)

    def _refresh_sessions(self):
        if self._discovering:
            return
        self._discovering = True
        self.controller.update_houdini_connection(busy=True)

        def worker():
            try:
                from houdini_agent.bridge.doctor import discover_sessions
                sessions = discover_sessions()
            except Exception:
                sessions = []
            try:
                self._sessions_found.emit(sessions)
            except RuntimeError:
                pass

        threading.Thread(target=worker, name="HAgentSessionDiscovery", daemon=True).start()

    @Slot(object)
    def _on_sessions_found(self, sessions):
        self._discovering = False
        self.controller.update_houdini_connection(busy=False, sessions=sessions)

    def _finish_launch(self, error):
        self._launch_process = None
        self._launch_deadline = 0
        self._launch_watch.stop()
        self._paused = not self.connected
        self.bridge.set_enabled(self.connected)
        self.controller.update_houdini_connection(state="connected" if self.connected else "disconnected", paused=not self.connected)
        self.controller.toast.emit(error)

    def _check_launch(self):
        if not self._launch_deadline:
            return
        now = time.monotonic()
        code = self._launch_process.poll() if self._launch_process is not None else None
        # A successful wrapper may hand over to a running Houdini process.
        exited = code is not None and (code != 0 or (
            now - self._launch_started_at >= 3 and not is_houdini_running()))
        if exited:
            self._finish_launch("Houdini 启动进程已退出（退出码 %s），可以重新启动。" % code)
        elif now >= self._launch_deadline:
            self._finish_launch("等待 Houdini Bridge 连接超时，可以重试启动或连接已打开的会话。")

    def _resume_connection(self):
        self._paused = False
        self._connection_generation += 1
        self.bridge.set_enabled(False)
        self.controller.update_houdini_connection(paused=True)
        self.poll.start()

    def _disconnect(self):
        self._paused = True
        self._connection_generation += 1
        self._connect_requested = False
        self._requested_port = None
        self.connected = False
        self._misses = 0
        self._launch_deadline = 0
        self._launch_process = None
        self._launch_watch.stop()
        self.bridge.set_enabled(False)
        self.controller.update_houdini_connection(state="disconnected", version="", port=0, paused=True)
        self.controller.refreshContext()
        self.controller.toast.emit("已断开 Houdini，可从连接菜单选择其他会话。")

    def connection_action(self, action):
        if action == "refresh":
            self._refresh_sessions()
            return
        if self.controller.running:
            self.controller.toast.emit("请等待当前任务完成后再切换或启动 Houdini。")
            return
        if action == "disconnect":
            self._disconnect()
        elif action == "connect" or action.startswith("connect:"):
            if action != "connect":
                try:
                    port = int(action.split(":", 1)[1])
                except ValueError:
                    return
                sessions = self.controller.houdiniConnection.get("sessions", [])
                if not any(item["port"] == port for item in sessions):
                    return
                self._requested_port = port
            self._resume_connection()
            self._connect_requested = True
            self.controller.update_houdini_connection(state="connecting")
            self._poll_tick()
        elif action.startswith("launch:"):
            self._check_launch()
            if self.controller.houdiniConnection["state"] == "launching":
                return
            try:
                index = int(action.split(":", 1)[1])
                if not 0 <= index < len(self.installs):
                    return
                self._launch_process = launch_houdini(self.repo_root, self.installs[index])
                if not self.connected:
                    self._resume_connection()
                self._launch_started_at = time.monotonic()
                self._launch_deadline = self._launch_started_at + 120
                self._launch_watch.start()
                if not self.connected:
                    self.controller.update_houdini_connection(state="launching")
                self.controller.toast.emit("已启动 Houdini，Bridge 就绪后可连接。")
                self.poll.start()
            except Exception as exc:
                self._finish_launch("启动 Houdini 失败：%s" % exc)

    def prompt_relaunch(self):
        """Scene-dependent actions expose the same compact connection menu."""
        self.controller.openHoudiniMenu.emit()


def _app_icon():
    """品牌应用图标（运行时窗口/任务栏）。打包后取 _MEIPASS/assets，开发时取仓库 assets。"""
    import os, sys
    from PySide6.QtGui import QIcon
    cands = []
    base = getattr(sys, "_MEIPASS", None)
    if base:
        cands.append(os.path.join(base, "assets", "houdini-agent.ico"))
    cands.append(str(Path(__file__).resolve().parents[2] / "assets" / "houdini-agent.ico"))
    for c in cands:
        if os.path.isfile(c):
            return QIcon(c)
    return QIcon()


def show_tool():
    app = QApplication.instance() or QApplication([])
    app.setWindowIcon(_app_icon())
    repo_root = Path(__file__).resolve().parents[2]
    model = ChatModel()
    controller = Controller(model, use_backend=False)
    try:
        controller.restore()
    except Exception:
        pass
    view = host.create_view(controller=controller, model=model)

    prev = getattr(app, "_hagent_external_window", None)
    if prev is not None:
        try:
            prev.close()
            prev.deleteLater()
        except Exception:
            pass

    win = ExternalWindow()
    win.setWindowTitle("Houdini Agent")
    win.setPalette(view.palette())
    win.setAutoFillBackground(True)
    win.setCentralWidget(view)
    win.setMinimumSize(420, 560)
    geo = QSettings(*_GEO_ORG).value("geometry")
    restored = False
    if geo is not None:
        try:
            restored = bool(win.restoreGeometry(geo))
        except Exception:
            restored = False
    if not restored:
        screen = app.primaryScreen()
        available = screen.availableGeometry() if screen else None
        win.resize(min(1100, int(available.width() * 0.9)) if available else 1100,
                   min(820, int(available.height() * 0.9)) if available else 820)

    coord = ExternalCoordinator(win, controller, repo_root)
    try:
        controller.requestOpenHoudini.connect(coord.prompt_relaunch)
        controller.requestHoudiniAction.connect(coord.connection_action)
    except Exception:
        pass
    win._controller = controller
    win._coordinator = coord
    win.show()
    win.raise_()
    win.activateWindow()
    QTimer.singleShot(100, coord.start)
    QTimer.singleShot(4000, controller.silentUpdateCheck)
    app._hagent_external_window = win
    return win


def main():
    app = QApplication.instance() or QApplication([])
    show_tool()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
