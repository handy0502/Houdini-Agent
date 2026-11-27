"""设置面板的滚动回归：内容比可视区高时，滚动条必须出现且能滚到底。

背景：`ScrollView` 只在内容项挂载那一刻同步一次 `contentHeight`；供应商列表这类
“面板打开后才填进来”的内容变高后不会被重新测量，滚动条（`size` 恒为 1）就不出现，
底部内容被裁掉。`PanelScrollView.contentImplicitHeight` 是这次补的显式同步入口。
"""
from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

pytest.importorskip("PySide6.QtQuickWidgets")


def test_settings_pages_scroll_to_bottom(tmp_path):
    code = textwrap.dedent(r"""
        import os, sys
        from pathlib import Path
        from unittest.mock import patch

        hfs = Path(os.environ.get('HFS', ''))
        if os.name == 'nt' and hfs.is_absolute() and (hfs / 'bin').is_dir():
            os.add_dll_directory(str(hfs / 'bin'))

        from PySide6.QtCore import QObject, QSettings, qInstallMessageHandler
        from PySide6.QtWidgets import QApplication

        app = QApplication([])
        state = Path(sys.argv[1])

        warnings = []
        qInstallMessageHandler(
            lambda kind, context, message: warnings.append(message)
            if 'Binding loop' in message or 'Unable to assign' in message else None)

        from houdini_agent.ui_qml import controller as module
        from houdini_agent.ui_qml.host import create_view

        settings = QSettings(str(state / 'prefs.ini'), QSettings.IniFormat)
        with patch.object(module, 'QSettings', return_value=settings), \
             patch.object(module.Controller, '_session_cache_dir', return_value=state / 'sessions'), \
             patch.object(module.Controller, '_migrate_legacy_sessions'), \
             patch.object(module.Controller, '_auto_refresh_models_if_stale'):
            model = module.ChatModel()
            controller = module.Controller(model, use_backend=False)

        view = create_view(controller=controller, model=model)
        view.resize(717, 564)
        view.show()
        for _ in range(30):
            app.processEvents()

        controller.menuAction('settings')
        for _ in range(30):
            app.processEvents()

        root = view.rootObject()

        def find(name):
            item = root.findChild(QObject, name)
            assert item is not None, name
            return item

        def check(name):
            scroll = find(name)
            content = scroll.property('contentItem')
            height = scroll.property('height')
            content_height = content.property('contentHeight')
            assert content_height > height + 5, (name, content_height, height)
            bars = [c for c in scroll.findChildren(QObject)
                    if 'SmartScrollBar' in c.metaObject().className()
                    and c.property('height') > c.property('width')]
            assert bars and bars[0].property('visible'), name
            content.setProperty('contentY', content_height - height)
            for _ in range(10):
                app.processEvents()
            assert content.property('contentY') > 0, name

        check('settingsPageScroll')

        find('settingsWindow').setProperty('sec', 'model')
        for _ in range(40):
            app.processEvents()
        check('providerListScroll')

        assert not warnings, '\n'.join(warnings)
        print('panel scroll passed')
    """)

    env = os.environ.copy()
    env.update(QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software",
               QT_QUICK_CONTROLS_STYLE="Basic", QML_DISABLE_DISK_CACHE="1",
               HAGENT_TELEMETRY_OFF="1")
    env["PYTHONPATH"] = str(REPO) + os.pathsep + env.get("PYTHONPATH", "")

    script = tmp_path / "panel_scroll_case.py"
    script.write_text(code, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-B", str(script), str(tmp_path)],
        cwd=str(REPO), env=env,
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "panel scroll passed" in result.stdout
