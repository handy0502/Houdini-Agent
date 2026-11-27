"""Source runs must not advertise or install upstream release binaries."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

pytest.importorskip('PySide6.QtCore')
from test_message_queue import ctrl
from houdini_agent.utils import updater


@pytest.fixture
def source_runtime(monkeypatch):
    monkeypatch.setattr(updater.sys, 'frozen', False, raising=False)
    network = Mock(side_effect=AssertionError('A source run must not fetch release metadata'))
    monkeypatch.setattr(updater, 'check_update', network)
    return network


def test_source_silent_check_clears_stale_indicator_without_network(ctrl, source_runtime):
    ctrl._update_info, ctrl._update_state = 'Cached release', 'available'
    ctrl.silentUpdateCheck()
    assert ctrl.updateText == '' and ctrl.updateState == ''
    ctrl._set_update('Late release result')
    assert ctrl.updateText == '' and ctrl.updateState == ''
    source_runtime.assert_not_called()


def test_source_manual_check_and_update_explain_repository_flow(ctrl, source_runtime, monkeypatch):
    info, browser = Mock(), Mock()
    monkeypatch.setattr(ctrl, '_info', info)
    monkeypatch.setattr('webbrowser.open', browser)
    for action in (ctrl._check_update, ctrl.startUpdate):
        action()
        assert '源码' in info.call_args.args[1] and '当前分支' in info.call_args.args[1]
        assert ctrl.updateState == ''
    browser.assert_not_called()
    source_runtime.assert_not_called()


def test_packaged_check_still_advertises_updates(ctrl, monkeypatch):
    import threading
    finished = threading.Event()
    monkeypatch.setattr(updater, 'supports_installer_updates', lambda: True)
    def check():
        finished.set()
        return {'has_update': True, 'remote_version': '9.0'}
    monkeypatch.setattr(updater, 'check_update', check)
    ctrl.silentUpdateCheck()
    assert finished.wait(2)
    # Process the queued worker signal before inspecting controller state.
    from PySide6.QtTest import QTest
    QTest.qWait(50)
    assert ctrl.updateState == 'available' and '9.0' in ctrl.updateText


def test_legacy_source_cannot_start_zip_overwrite(source_runtime, monkeypatch):
    from houdini_agent.core import update_mixin
    info, manual = Mock(), Mock()
    monkeypatch.setattr(update_mixin.QtWidgets.QMessageBox, 'information', info)
    obj = SimpleNamespace(_on_check_update=manual)
    update_mixin.UpdateMixin._silent_update_check(obj)
    update_mixin.UpdateMixin._on_check_update(obj)
    update_mixin.UpdateMixin._start_update(obj)
    assert '源码' in info.call_args.args[2]
    manual.assert_called_once()
    source_runtime.assert_not_called()


def test_installer_support_depends_on_actual_packaging(monkeypatch):
    for frozen in (False, True):
        monkeypatch.setattr(updater.sys, 'frozen', frozen, raising=False)
        assert updater.supports_installer_updates() is frozen
