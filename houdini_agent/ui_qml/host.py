# -*- coding: utf-8 -*-
"""
QQuickWidget host — embeds the QML UI inside a QWidget so it can live in
Houdini's PySide widget tree (drop-in replacement for the old AITab widget).
"""

import os
import sys
from pathlib import Path

try:
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QFont, QPalette
    from PySide6.QtQuickWidgets import QQuickWidget
except ImportError:  # Houdini <= 20.5 (Qt5)
    from PySide2.QtCore import QUrl
    from PySide2.QtGui import QFont, QPalette
    from PySide2.QtQuickWidgets import QQuickWidget

from .controller import ChatModel, Controller

QML_DIR = Path(__file__).parent / "qml"
MAIN_QML = QML_DIR / "Main.qml"

_FONTS_REGISTERED = False


def register_fonts():
    """Load UI font faces and register CJK / monospace fallbacks."""
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return
    try:
        from PySide6.QtGui import QFontDatabase
    except ImportError:
        from PySide2.QtGui import QFontDatabase
    fonts_dir = Path(__file__).parent / "fonts"
    for ttf in ("Fraunces.ttf", "Newsreader.ttf", "SpaceMono-Regular.ttf"):
        p = fonts_dir / ttf
        if p.exists():
            try:
                QFontDatabase.addApplicationFont(str(p))
            except Exception as e:
                print("[host] font load failed:", ttf, e)
    # Offscreen Qt on Windows may not enumerate system fonts. Register the
    # system faces explicitly in that case so previews retain CJK and UI text.
    if sys.platform == "win32":
        families = set(QFontDatabase.families())
        system_fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        for family, files in (
            ("Segoe UI", ("segoeui.ttf", "seguisb.ttf")),
            ("Microsoft YaHei UI", ("msyh.ttc", "msyhbd.ttc")),
            ("Consolas", ("consola.ttf",)),
        ):
            if family not in families:
                for name in files:
                    path = system_fonts / name
                    if path.exists():
                        QFontDatabase.addApplicationFont(str(path))
    # CJK + generic fallbacks (the bundled fonts are Latin-only)
    QFont.insertSubstitutions("Fraunces",   ["Georgia", "Microsoft YaHei", "Songti SC", "serif"])
    QFont.insertSubstitutions("Newsreader", ["Georgia", "Microsoft YaHei", "Songti SC", "serif"])
    QFont.insertSubstitutions("Space Mono", ["Consolas", "Courier New", "monospace"])
    QFont.insertSubstitutions("Segoe UI", ["Microsoft YaHei UI", "Microsoft YaHei", "Noto Sans CJK SC", "sans-serif"])
    QFont.insertSubstitutions("Cascadia Code", ["Consolas", "Microsoft YaHei UI", "monospace"])
    _FONTS_REGISTERED = True


try:
    from PySide6.QtCore import QTimer as _QTimer
    from PySide6.QtQml import QQmlIncubationController as _QQmlIncubationController
except ImportError:
    from PySide2.QtCore import QTimer as _QTimer
    from PySide2.QtQml import QQmlIncubationController as _QQmlIncubationController


class _FrameIncubator(_QQmlIncubationController):
    """有待创建的异步 QML 对象时，每 16ms 拿出 8ms 做增量创建，其余时间留给界面。"""

    def __init__(self):
        super().__init__()
        self._timer = _QTimer()
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)

    def incubatingObjectCountChanged(self, count):
        if count > 0:
            if not self._timer.isActive():
                self._timer.start()
        else:
            self._timer.stop()

    def _tick(self):
        if self.incubatingObjectCount() > 0:
            self.incubateFor(8)
        else:
            self._timer.stop()


def create_native_view(controller=None, model=None):
    """Build a top-level QQuickView (native QWindow) hosting the same QML.

    Houdini 的 pane tab 里，QQuickWidget 没有自己的原生窗口，键盘事件常常走不到它
    （见 pane.log 里“无 key code、qquickwidget focused 一直在闪”）。QQuickView 有独立
    原生窗口，配合 QWidget.createWindowContainer 嵌进 pane 后，点击就会激活该窗口，
    键盘由操作系统直接送达 —— 这正是社区在 Houdini Python Panel 里跑 QML 的推荐姿势。
    """
    register_fonts()
    if model is None:
        model = ChatModel()
    if controller is None:
        controller = Controller(model)

    try:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QColor
        from PySide6.QtQuick import QQuickView
    except ImportError:
        from PySide2.QtCore import QUrl
        from PySide2.QtGui import QColor
        from PySide2.QtQuick import QQuickView

    view = QQuickView()
    view.setResizeMode(QQuickView.SizeRootObjectToView)
    view.setColor(QColor("#0d0d0d"))
    view.engine().addImportPath(str(QML_DIR))
    ctx = view.rootContext()
    ctx.setContextProperty("chatModel", model)
    ctx.setContextProperty("controller", controller)
    view.setSource(QUrl.fromLocalFile(str(MAIN_QML)))

    root = view.rootObject()
    if root is not None:
        try:
            view.setColor(root.property("color"))

            def sync_color():
                try:
                    view.setColor(root.property("color"))
                except Exception:
                    pass
            root.colorChanged.connect(sync_color)
        except Exception as exc:
            print("[host] native color sync failed:", exc)

    view._controller = controller
    view._model = model
    return view


def create_view(parent=None, controller=None, model=None):
    """Build the QQuickWidget. Returns the widget (with ._controller/._model)."""
    register_fonts()
    if model is None:
        model = ChatModel()
    if controller is None:
        controller = Controller(model)

    view = QQuickWidget(parent)
    # QQuickWidget 的离屏窗口没有渲染循环，引擎上也就没有孵化控制器；没有它
    # Loader.asynchronous 会退化成同步创建。装一个分帧孵化器后，打开长会话时
    # 较早的消息才能在后续帧里分批创建，界面不被冻住。
    try:
        if view.engine().incubationController() is None:
            inc = _FrameIncubator()
            view.engine().setIncubationController(inc)
            view._incubator = inc   # 引擎不持有所有权，必须保活
    except Exception as e:
        print("[host] incubation controller setup failed:", e)
    view.engine().addImportPath(str(QML_DIR))
    ctx = view.rootContext()
    ctx.setContextProperty("chatModel", model)
    ctx.setContextProperty("controller", controller)
    view.setResizeMode(QQuickWidget.SizeRootObjectToView)
    view.setSource(QUrl.fromLocalFile(str(MAIN_QML)))
    root = view.rootObject()
    if root is not None:
        # The native widget and render target must match QML before the first
        # frame (and when its framebuffer is recreated after a resize).
        def sync_background():
            background = root.property("color")
            view.setClearColor(background)
            palette = view.palette()
            palette.setColor(QPalette.Window, background)
            palette.setColor(QPalette.Base, background)
            view.setPalette(palette)

        sync_background()
        root.colorChanged.connect(sync_background)
        view.setAutoFillBackground(True)

    # keep python refs alive
    view._controller = controller
    view._model = model
    return view
