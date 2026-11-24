"""Offline FIFO delivery, cancellation, persistence and draft isolation."""
import os
import copy
import json
import threading
import time
from types import SimpleNamespace

import pytest

QtCore = pytest.importorskip("PySide6.QtCore")
from houdini_agent.ui_qml import controller as C


@pytest.fixture
def ctrl(tmp_path, monkeypatch):
    app = QtCore.QCoreApplication.instance() or QtCore.QCoreApplication([])
    monkeypatch.setattr(C, "QSettings", lambda *a: QtCore.QSettings(str(tmp_path / 'prefs.ini'), QtCore.QSettings.IniFormat))
    monkeypatch.setattr(C.Controller, '_session_cache_dir', lambda *a: tmp_path / 'sessions')
    monkeypatch.setattr(C.Controller, '_migrate_legacy_sessions', lambda *a: None)
    monkeypatch.setattr(C.Controller, '_auto_refresh_models_if_stale', lambda *a: None)
    monkeypatch.setattr('houdini_agent.meshy.telemetry.start', lambda *a: None)
    c = C.Controller(C.ChatModel(), use_backend=False)
    monkeypatch.setattr(c, '_simulate', lambda *a: None)
    c.setProvider('openai')
    yield c
    c._pause_message_queue()
    c._set_running(False)
    app.processEvents()


def tick():
    QtCore.QCoreApplication.processEvents()


def pending_plan(ctrl):
    payload = {'title': 'Plan A', 'status': 'draft',
               'steps': [{'id': 's1', 'title': 'Inspect scene', 'state': 'pending'}]}
    ctrl._plan_phase = 'awaiting'
    ctrl._ui_plan(json.dumps(payload))
    return payload


def test_fifo_waits_for_done_and_preserves_unsent_draft_images(ctrl):
    assert ctrl.send('first')
    ctrl._pending_images = [('eA==', 'image/png')]
    assert ctrl.send('second')
    ctrl._pending_images = [('eQ==', 'image/png')]
    assert ctrl.send('third')
    assert ctrl.running and ctrl.queuedCount == 2
    assert [x['payload']['text'] for x in ctrl._model._items if x['type'] == 'user'] == ['first']
    ctrl._pending_images = [('eg==', 'image/png')]
    ctrl._ui_done('')
    tick()
    assert ctrl.running and ctrl.queuedCount == 1
    users = [x['payload'] for x in ctrl._model._items if x['type'] == 'user']
    assert [x['text'] for x in users] == ['first', 'second']
    assert ctrl._decode_message_images(users[-1]['images'])[0] == [('eA==', 'image/png')]
    assert ctrl._pending_images == [('eg==', 'image/png')]
    ctrl._ui_done('')
    tick()
    assert ctrl.running and ctrl.queuedCount == 0
    assert [x['payload']['text'] for x in ctrl._model._items if x['type'] == 'user'] == ['first', 'second', 'third']
    ctrl._ui_done('')
    tick()
    assert not ctrl.running


@pytest.mark.parametrize('stopped', [False, True])
def test_failure_or_stop_pauses_and_resume_delivers(ctrl, stopped):
    ctrl.send('first')
    ctrl.send('next')
    if stopped:
        ctrl.stop()
    ctrl._ui_done('' if stopped else 'HTTP 429: Too many pending requests')
    tick()
    assert not ctrl.running and ctrl.queuePaused and ctrl.queuedCount == 1
    ctrl.resumeMessageQueue()
    tick()
    assert ctrl.running and ctrl.queuedCount == 0
    assert ctrl._model._items[-2]['payload']['text'] == 'next'


def test_new_foreground_turn_reenables_automatic_queue(ctrl):
    ctrl.send('first')
    ctrl.stop()
    ctrl._ui_done('')
    assert ctrl.queuePaused
    ctrl.send('new')
    ctrl.send('follow up')
    ctrl._ui_done('')
    tick()
    assert ctrl.running and ctrl.queuedCount == 0


def test_edit_cancel_and_restore_persisted_queue(ctrl):
    ctrl.send('first')
    ctrl._pending_images = [('eA==', 'image/png')]
    ctrl.send('edit me')
    ctrl.send('cancel me')
    ctrl.send('keep me')
    drafts = []
    ctrl.restoreFailedDraft.connect(drafts.append)
    ids = [item['id'] for item in ctrl.queuedMessages]
    ctrl.editQueuedMessage(ids[0])
    ctrl.removeQueuedMessage(ids[1])
    assert drafts == ['edit me'] and ctrl._pending_images == [('eA==', 'image/png')]
    assert ctrl.queuedCount == 1
    ctrl._snapshot_active()
    ctrl._save_all()
    ctrl._sessions = []
    ctrl._set_running(False)
    ctrl.restore()
    tick()
    assert not ctrl.running and ctrl.queuePaused
    assert ctrl.queuedMessages[0]['text'] == 'keep me'
    ctrl.resumeMessageQueue()
    tick()
    assert ctrl.running and ctrl.queuedCount == 0


def test_deferred_dispatch_cannot_leak_across_chats(ctrl):
    ctrl.send('first')
    ctrl.send('queued in old chat')
    ctrl._ui_done('')
    ctrl.newSession()
    tick()
    assert not ctrl.running and ctrl.queuedCount == 0 and not ctrl._model._items
    ctrl.switchSession(0)
    tick()
    assert ctrl.queuedCount == 1 and ctrl.queuePaused and not ctrl.running


def test_plan_confirmation_and_model_snapshot(ctrl):
    ctrl.setMode('Ask')
    ctrl.send('first')
    ctrl.send('read only next')
    queued_model = ctrl._model_name
    pending_plan(ctrl)
    ctrl._ui_done('')
    tick()
    assert not ctrl.running and ctrl.queuedCount == 1
    ctrl.setMode('Agent')
    ctrl.setProvider('deepseek')
    ctrl.rejectPlan('plan')
    tick()
    assert ctrl.running and ctrl.queuedCount == 0
    assert ctrl.mode == 'Ask' and ctrl._provider == 'openai' and ctrl._model_name == queued_model


@pytest.mark.parametrize('navigate', ['new', 'existing'])
def test_waiting_plan_does_not_block_another_chat_and_is_restored_on_return(ctrl, navigate):
    ctrl.newSession()  # B already exists for the switch case.
    ctrl.switchSession(0)
    payload = pending_plan(ctrl)
    ctrl._pending_plan_confirm = True
    if navigate == 'new':
        ctrl.newSession()
    else:
        ctrl.switchSession(1)
    assert ctrl._plan_phase == 'idle' and not ctrl._pending_plan_confirm
    assert ctrl._plan_row is None and ctrl._plan_payload is None
    assert ctrl.send('ordinary message in another chat')
    tick()
    assert ctrl.running and ctrl.queuedCount == 0
    ctrl._ui_done('')
    ctrl.switchSession(0)
    assert ctrl._plan_phase == 'awaiting' and ctrl._plan_payload == payload
    assert ctrl._plan_idmap == {'s1': 0}
    assert not ctrl._pending_plan_confirm  # Previous UI confirmation cannot execute on return.
    ctrl.send('follow up after the plan')
    ctrl.resumeMessageQueue()
    tick()
    assert not ctrl.running and ctrl.queuedCount == 1
    ctrl.rejectPlan('')
    tick()
    assert ctrl.running and ctrl.queuedCount == 0


def test_clearing_chat_resets_plan_confirmation_and_allows_sending(ctrl):
    pending_plan(ctrl)
    ctrl._pending_plan_confirm = True
    ctrl._clear_chat_now()
    assert ctrl._plan_phase == 'idle'
    assert ctrl._plan_row is None and ctrl._plan_payload is None and not ctrl._plan_idmap
    assert not ctrl._pending_plan_confirm
    assert ctrl.send('new task after clearing the plan')
    tick()
    assert ctrl.running and ctrl.queuedCount == 0


def test_waiting_plan_is_restored_with_its_own_queue_after_restart(ctrl):
    payload = pending_plan(ctrl)
    ctrl.send('after confirmation')
    ctrl._snapshot_active()
    ctrl._save_all()
    ctrl.newSession()
    ctrl._sessions = []
    ctrl.restore()
    assert ctrl._plan_phase == 'idle'
    ctrl.switchSession(0)
    assert ctrl._plan_phase == 'awaiting' and ctrl._plan_payload == payload
    assert ctrl.queuePaused and ctrl.queuedCount == 1
    ctrl.resumeMessageQueue()
    tick()
    assert not ctrl.running
    ctrl.rejectPlan('')
    tick()
    assert ctrl.running and ctrl.queuedCount == 0


def test_stale_waiting_flag_without_plan_cannot_block_sends_or_dispatch(ctrl):
    ctrl._plan_phase = 'awaiting'
    assert ctrl.send('direct send')
    assert ctrl.running and ctrl.queuedCount == 0
    ctrl.send('queued send')
    ctrl._ui_done('')
    ctrl._plan_phase = 'awaiting'  # Simulate stale phase before the deferred callback.
    tick()
    assert ctrl.running and ctrl.queuedCount == 0


def test_confirm_restored_plan_uses_original_payload(ctrl, monkeypatch):
    payload = pending_plan(ctrl)
    ctrl.newSession()
    ctrl.setMode('Ask')
    ctrl.switchSession(0)
    runs = []
    ctrl._session = SimpleNamespace(tools=[])
    monkeypatch.setattr(ctrl, '_start_run', lambda text, **kw: runs.append(text))
    assert ctrl.confirmPlan('') == 'confirmed'
    assert ctrl._plan_phase == 'executing' and len(runs) == 1
    assert ctrl.mode == 'Plan'
    assert 'Plan A' in runs[0] and 's1' in runs[0]
    assert ctrl._plan_payload == payload


def test_missing_attachment_pauses_instead_of_sending_incomplete_request(ctrl):
    ctrl.send('first')
    ctrl._pending_images = [('eA==', 'image/png')]
    ctrl.send('inspect this')
    item = ctrl._queue_session()['outbox'][0]
    from urllib.request import url2pathname
    from urllib.parse import urlsplit
    from pathlib import Path
    Path(url2pathname(urlsplit(item['images'][0]).path)).unlink()
    ctrl._ui_done('')
    tick()
    assert ctrl.queuePaused and ctrl.queuedCount == 1 and not ctrl.running


def test_queued_image_survives_gc(ctrl):
    ctrl.send('first')
    ctrl._pending_images = [('eA==', 'image/png')]
    ctrl.send('inspect this')
    image = next(ctrl._image_dir().iterdir())
    old = time.time() - 10 * 86400
    os.utime(str(image), (old, old))
    ctrl._gc_images()
    assert image.exists()


def test_new_messages_do_not_bypass_paused_fifo(ctrl):
    ctrl.send('first')
    ctrl.send('second')
    ctrl._ui_done('HTTP 429')
    ctrl.send('third')
    tick()
    assert not ctrl.running and ctrl.queuedCount == 2
    assert [item['text'] for item in ctrl.queuedMessages] == ['second', 'third']
    ctrl.resumeMessageQueue()
    tick()
    assert ctrl._model._items[-2]['payload']['text'] == 'second'


def test_send_does_not_overlap_background_or_plan_continuation(ctrl):
    ctrl.send('first')
    ctrl.send('second')
    ctrl._ui_done('')
    # A previously scheduled continuation wins the idle event-loop gap.
    ctrl._start_run('internal continuation', tools=None, max_iter=None)
    tick()
    assert ctrl.queuedCount == 1 and ctrl.running
    ctrl._ui_done('')
    tick()
    assert ctrl.queuedCount == 0 and ctrl._model._items[-2]['payload']['text'] == 'second'


def test_worker_completion_hands_off_once_with_previous_context(ctrl):
    gates = [threading.Event(), threading.Event()]
    entered = [threading.Event(), threading.Event()]
    calls = []
    active, peak = 0, 0

    class Backend:
        history = []
        tools = []
        client = SimpleNamespace()

        def build_messages(self, *args):
            return copy.deepcopy(self.history)

        def run(self, text, *args, **kwargs):
            nonlocal active, peak
            index = len(calls)
            calls.append((text, copy.deepcopy(self.history)))
            active += 1
            peak = max(active, peak)
            self.history.append({'role': 'user', 'content': text})
            entered[index].set()
            try:
                assert gates[index].wait(3), 'test did not release the offline response'
                self.history.append({'role': 'assistant', 'content': 'answer ' + text})
                return {'ok': True, 'final_content': 'answer ' + text}
            finally:
                active -= 1

    def wait_until(predicate):
        deadline = time.monotonic() + 2
        while not predicate() and time.monotonic() < deadline:
            tick()
            time.sleep(0.005)
        assert predicate()

    ctrl._session = Backend()
    try:
        ctrl.send('first')
        wait_until(entered[0].is_set)
        ctrl.send('second')
        tick()
        assert len(calls) == 1 and ctrl.queuedCount == 1
        gates[0].set()
        wait_until(entered[1].is_set)
        assert calls[1] == ('second', [
            {'role': 'user', 'content': 'first'}, {'role': 'assistant', 'content': 'answer first'}])
        assert peak == 1
        gates[1].set()
        wait_until(lambda: not ctrl.running)
        assert ctrl.queuedCount == 0 and len(calls) == 2
    finally:
        for gate in gates:
            gate.set()
