# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import os

from PyInstaller.utils.hooks import collect_submodules


block_cipher = None
ROOT = Path(SPECPATH).resolve().parent


def datas_for(path, dest=None):
    src = ROOT / path
    if not src.exists():
        return []
    target = Path(dest or path.replace("\\", "/"))
    if src.is_file():
        return [(str(src), str(target))]
    # Ship source/resources for Houdini's Bridge, without interpreter-specific
    # bytecode or caches created while developing/running this checkout.
    data = []
    for directory, names, files in os.walk(src):
        names[:] = sorted(n for n in names if n not in {"__pycache__", ".git", ".pytest_cache"})
        relative = Path(directory).relative_to(src)
        for name in sorted(files):
            if Path(name).suffix.lower() not in {".pyc", ".pyo"}:
                data.append((str(Path(directory) / name), str(target / relative)))
    return data


datas = []
datas += datas_for("lib", "lib")
# 只打包仓库里跟踪的配置文件。config/houdini_ai.ini（API key、遥测 ID）和 templates.json
# 是开发机本地文件、已被 .gitignore；以前整目录打包，会把开发者的 key 和遥测 ID
# 发给所有用户，并在每次覆盖安装时冲掉用户自己保存的配置。
datas += datas_for("config/plugins.json", "config")
datas += datas_for("config/user_rules.json", "config")
datas += datas_for("rules", "rules")
datas += datas_for("plugins", "plugins")
# Training exports are per-user output and are created on demand at runtime.
datas += datas_for("VERSION", ".")
# Houdini 侧从 bridge_payload 加载代码；没有这份 VERSION，那里的更新检查会读到 0.0.0，
# 永远提示"发现新版本"。
datas += datas_for("VERSION", "bridge_payload")
datas += datas_for("assets/houdini-agent.ico", "assets")
datas += datas_for("houdini_agent", "bridge_payload/houdini_agent")
# bridge_payload 是 Houdini 侧 bridge server 的加载根（HAGENT_REPO 指向它）。
# meshy 依赖顶层 shared 包，必须一并放进去，否则 Houdini 里 import meshy 会 No module named 'shared'。
datas += datas_for("shared", "bridge_payload/shared")
datas += datas_for("houdini_agent/ui_qml/qml", "houdini_agent/ui_qml/qml")
datas += datas_for("houdini_agent/ui_qml/fonts", "houdini_agent/ui_qml/fonts")
datas += datas_for("houdini_agent/houdini_package", "houdini_agent/houdini_package")
datas += datas_for("houdini_agent/utils/mcp/node_inputs.json", "houdini_agent/utils/mcp")
datas += datas_for("houdini_agent/utils/mcp/fx_commands.json", "houdini_agent/utils/mcp")
# meshy 动作库目录：app 侧由冻结模块按 __file__ 相对路径加载，必须放到顶层 meshy 包路径下
# （bridge_payload 那份只供 Houdini 侧；此处与 node_inputs.json 同理）。
datas += datas_for("houdini_agent/meshy/animation_library.json", "houdini_agent/meshy")
# The QtQml/QtQuick hooks collect their runtime QML/plugins and DLL dependencies.
# Do not independently collect the whole Qt tree a second time.

hiddenimports = []
hiddenimports += [
    "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets", "PySide6.QtNetwork",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets",
    "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtSvg",
]
hiddenimports += collect_submodules("houdini_agent")
hiddenimports += [
    "houdini_agent.ui_qml.external_app",
    "houdini_agent.ui_qml.bridge_session",
    "houdini_agent.bridge.client",
    "houdini_agent.bridge.server",
    "houdini_agent.launcher.houdini_discovery",
    "houdini_agent.utils.mcp",
]

# QML 聊天界面只用到 QtQuick / QtQuick.Controls(.Basic) / QtQuick.Layouts / QtQuick.Dialogs，
# 其余 Qt 模块（WebEngine ~200MB、Multimedia/FFmpeg、Pdf、Quick3D、Designer 等）运行时用不到。
# 把它们排除掉给安装包大幅瘦身（保留 opengl32sw 软件渲染兜底与全部 Controls 样式，避免误伤）。
qt_excludes = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel", "PySide6.QtWebView", "PySide6.QtWebSockets",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtSpatialAudio",
    "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    "PySide6.QtQuick3D", "PySide6.Qt3DCore", "PySide6.Qt3DRender",
    "PySide6.Qt3DInput", "PySide6.Qt3DLogic", "PySide6.Qt3DAnimation", "PySide6.Qt3DExtras",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtGraphs",
    "PySide6.QtDesigner", "PySide6.QtUiTools", "PySide6.QtTest", "PySide6.QtQuickTest",
    "PySide6.QtSensors", "PySide6.QtPositioning", "PySide6.QtNfc", "PySide6.QtBluetooth",
    "PySide6.QtSerialPort", "PySide6.QtSerialBus", "PySide6.QtRemoteObjects",
    "PySide6.QtScxml", "PySide6.QtTextToSpeech", "PySide6.QtHelp",
]
hiddenimports = [h for h in hiddenimports if h not in qt_excludes]


a = Analysis(
    [str(ROOT / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PySide2", "hou", "hdefereval"] + qt_excludes,
    noarchive=False,
    optimize=0,
)

# 二次兜底：从最终产物里物理剔除未用 Qt 模块的 DLL / 资源 / qml / 语言包。
# （QtQml hook 也会收集可选 QML 模块，这里按名字过滤掉已有的未使用模块。）
_strip_substr = (
    "webengine", "qtwebengine",
    "qt6multimedia", "multimediawidgets", "spatialaudio",
    "avcodec-", "avformat-", "avutil-", "swscale-", "swresample-",   # FFmpeg
    "qt6pdf", "pdfquick", "pdfwidgets",
    "quick3d", "qt63d", "qt3d",
    "qt6charts", "chartsqml", "datavisualization", "qt6graphs",
    "qt6designer", "qt6quicktest", "qt6test",
    "qt6sensors", "qt6positioning", "qt6nfc", "qt6bluetooth",
    "qt6serialport", "qt6serialbus", "qt6webview", "qt6webchannel",
    "qt6websockets", "qt6remoteobjects", "qt6scxml", "qt6texttospeech",
    "virtualkeyboard", "qt6help",
)


def _keep(dest):
    d = str(dest).lower().replace("\\", "/")
    return not any(s in d for s in _strip_substr)


a.binaries = [b for b in a.binaries if _keep(b[0])]
a.datas = [d for d in a.datas if _keep(d[0])]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Houdini Agent",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "assets" / "houdini-agent.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Houdini Agent",
)
