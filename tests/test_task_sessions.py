"""Session integration: continuation, history and executor lifetime for both frontends."""
from types import SimpleNamespace
from unittest.mock import Mock
import pytest

from houdini_agent.ui_qml.agent_session import AgentSession
from houdini_agent.ui_qml.bridge_session import BridgeAgentSession


@pytest.fixture(params=[AgentSession, BridgeAgentSession])
def session(request, monkeypatch):
    monkeypatch.setattr('houdini_agent.utils.mcp.fx_compat.tools_for_request', lambda tools, *a, **k: tools)
    obj = request.param.__new__(request.param)
    obj.tools, obj.history = [], []
    obj._sys_think = obj._sys_no_think = 'System'
    obj._tool_executor = Mock(return_value={'success': True})
    client = SimpleNamespace(_tool_executor=obj._tool_executor, reset_stop=Mock())
    client.set_tool_executor = lambda fn: setattr(client, '_tool_executor', fn)
    obj.client = client
    return obj


def test_sessions_track_execution_verify_and_restore_executor(session):
    original = session._tool_executor
    def loop(**kw):
        session.client._tool_executor('create_node', node_type='box')
        assert kw['on_plan_incomplete']()
        original.return_value = {'success': True, 'validation': {'status': 'passed', 'measured': True}}
        session.client._tool_executor('verify_and_summarize', network_path='/obj/effect')
        assert kw['on_plan_incomplete']() is None
        return {'ok': True, 'new_messages': [], 'final_content': 'Done'}
    session.client.agent_loop_auto = loop
    result = session.run('Build', 'test', 'openai', 'Agent', {}, rag=False)
    assert result['task_report']['status'] == 'verified'
    assert session.client._tool_executor is original
    assert session.history[-1] == {'role': 'assistant', 'content': 'Done'}


def test_rejected_plan_request_does_not_leave_unanswered_user_history(session):
    session.client.agent_loop_auto = lambda **kw: {'ok': False, 'error': '429', 'new_messages': []}
    result = session.run('Execute', 'test', 'openai', 'Plan', {}, rag=False,
                         tool_mode='plan_executing', plan={'steps': [{'id': 'a'}]})
    assert result['task_report']['status'] == 'incomplete'
    assert session.history == []


def test_partial_failure_is_reported_and_executor_is_restored(session):
    original = session._tool_executor
    chunks = []
    def loop(**kw):
        session.client._tool_executor('create_node')
        return {'ok': False, 'error': 'Network failed', 'new_messages': [], 'final_content': ''}
    session.client.agent_loop_auto = loop
    result = session.run('Build', 'test', 'openai', 'Agent', {'on_content': chunks.append}, rag=False)
    assert result['task_report']['status'] == 'incomplete' and chunks
    assert '尚未通过验收' in session.history[-1]['content']
    assert session.client._tool_executor is original


def test_executor_is_restored_on_loop_exception(session):
    original = session._tool_executor
    def loop(**kw):
        raise RuntimeError('crashed')
    session.client.agent_loop_auto = loop
    with pytest.raises(RuntimeError):
        session.run('Build', 'test', 'openai', 'Agent', {}, rag=False)
    assert session.client._tool_executor is original


def test_json_mode_content_is_retained_as_assistant_history(session):
    session.client.agent_loop_auto = lambda **kw: {'ok': True, 'content': 'JSON mode answer'}
    session.run('Inspect', 'test', 'openai', 'Ask', {}, rag=False)
    assert session.history[-1] == {'role': 'assistant', 'content': 'JSON mode answer'}
