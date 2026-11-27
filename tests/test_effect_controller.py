"""Cases stay local; Houdini verification retains the existing dispatch boundary."""
from types import SimpleNamespace
from unittest.mock import Mock

from test_message_queue import ctrl, tick
from houdini_agent.utils.effect_library import EffectLibrary


def test_case_save_uses_scene_dispatch_and_can_be_found_without_bridge(ctrl, monkeypatch):
    ctrl._session = SimpleNamespace(client=SimpleNamespace(is_stop_requested=lambda: False))
    result = {'success': True, 'case_record': {'title': 'Scatter', 'summary': 'Scatter points',
              'procedure': 'Use native nodes', 'verification': {'status': 'passed'}, 'version': '22.0'}}
    dispatch = Mock(return_value=result)
    monkeypatch.setattr(ctrl, '_dispatch_scene_tool', dispatch)
    saved = ctrl._tool_executor('save_effect_case', title='Scatter')
    assert saved['success']
    dispatch.assert_called_once_with('save_effect_case', {'title': 'Scatter', '_prepare_only': True})
    found = ctrl._tool_executor('search_effect_cases', query='Scatter')
    assert found['cases'][0]['id'] == saved['case_id']
    assert dispatch.call_count == 1


def test_case_failed_verification_is_not_archived(ctrl, monkeypatch):
    ctrl._session = SimpleNamespace(client=SimpleNamespace(is_stop_requested=lambda: False))
    monkeypatch.setattr(ctrl, '_dispatch_scene_tool', Mock(return_value={'success': False, 'error': 'Check failed'}))
    assert not ctrl._tool_executor('save_effect_case', title='Broken')['success']
    assert EffectLibrary().search('Broken') == []


def test_unverified_completion_pauses_outbox_and_persists_report(ctrl):
    ctrl.send('Build effect')
    ctrl.send('Next edit')
    ctrl._ui_task_report({'status': 'incomplete', 'pending_steps': ['a']})
    ctrl._ui_done('')
    tick()
    assert ctrl.queuePaused and not ctrl.running and ctrl.queuedCount == 1
    assert ctrl._sessions[ctrl._active]['task_report']['pending_steps'] == ['a']
