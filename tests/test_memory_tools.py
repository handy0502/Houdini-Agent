"""Offline persistence, runtime gating and app-side routing of user memories."""
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
import threading
from unittest.mock import Mock

import pytest

from test_message_queue import ctrl, tick
from houdini_agent.utils import memory_store, memory_tools
from houdini_agent.utils.embedding import LocalEmbedder
from houdini_agent.ui_qml.agent_session import AgentSession
from houdini_agent.ui_qml.bridge_session import BridgeAgentSession


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(LocalEmbedder, '_try_load_model', lambda self: setattr(self, '_backend', 'fallback'))
    embedder = LocalEmbedder(cache_dir=tmp_path / 'embeddings')
    db = memory_store.MemoryStore(tmp_path / 'memories.db', embedder=embedder)
    monkeypatch.setattr(memory_store, 'get_memory_store', lambda: db)
    yield db
    db._conn.close()


def test_save_deduplicates_and_persists_across_reopen(store):
    first = memory_tools.save_memory({'content': 'Prefer Houdini native nodes.'}, enabled=True)
    second = memory_tools.save_memory({'content': '  Prefer Houdini native nodes.  '}, enabled=True)
    assert first['success'] and first['created']
    assert second['id'] == first['id'] and not second['created']
    assert store.count_semantic() == 1
    reopened = memory_store.MemoryStore(store.db_path, embedder=store.embedder)
    try:
        record = reopened.get_semantic(first['id'])
        assert record.rule == 'Prefer Houdini native nodes.'
        assert record.abstraction_level == 0 and record.confidence == 1.0
    finally:
        reopened._conn.close()


@pytest.mark.parametrize('args', [dict(content=''), dict(content='  '), dict(content=42),
    dict(content='x' * 4001), dict(content='OK', category='invalid')])
def test_invalid_saves_leave_store_untouched(store, args):
    assert not memory_tools.save_memory(args, enabled=True)['success']
    assert store.count_semantic() == 0


def test_disabled_tools_fail_closed_without_opening_store(monkeypatch):
    factory = Mock(side_effect=AssertionError('Disabled memory must not access its database'))
    monkeypatch.setattr(memory_store, 'get_memory_store', factory)
    monkeypatch.setattr(memory_tools, 'memory_enabled', lambda: False)
    assert not memory_tools.save_memory(dict(content='secret'))['success']
    assert not memory_tools.search_memory(dict(query='secret'))['success']
    factory.assert_not_called()


def test_search_context_and_delete_read_actual_fields(store, ctrl):
    result = memory_tools.save_memory(dict(content='Always answer in Chinese.', category='preference'), enabled=True)
    found = memory_tools.search_memory(dict(query='Chinese'), enabled=True)
    assert found['success'] and found['memories'][0]['id'] == result['id']
    for cls in (AgentSession, BridgeAgentSession):
        context = cls._context_messages('unrelated new conversation', rag=False, memory=True)
        assert len(context) == 1 and 'Always answer in Chinese.' in context[0]['content']
        assert 'embedding=' not in context[0]['content'] and 'SemanticRecord(' not in context[0]['content']
        assert cls._context_messages('Chinese', rag=False, memory=False) == []
    ctrl._delete_memory_now('semantic', result['id'])
    assert AgentSession._context_messages('Chinese', rag=False, memory=True) == []


def test_episodic_context_reads_task_and_summary_without_record_dump(store):
    store.add_episodic(memory_store.EpisodicRecord(task_description='Build traffic', result_summary='Preserve node names'))
    context = memory_tools.memory_context('traffic')
    assert 'Build traffic: Preserve node names' in context
    assert 'EpisodicRecord(' not in context and 'embedding=' not in context


def test_manual_save_while_off_and_local_tool_routing_without_houdini(store, ctrl):
    assert not ctrl.memoryEnabled
    assert ctrl.addMemory('Native Houdini tools first.', 'preference')
    ctrl._session = SimpleNamespace(client=SimpleNamespace(is_stop_requested=lambda: False),
        bridge=SimpleNamespace(ping=Mock(side_effect=AssertionError('Must stay local'))))
    assert not ctrl._tool_executor('save_memory', content='Disabled save')['success']
    ctrl._memory_enabled = True
    refreshed = []
    ctrl.managementChanged.connect(lambda: refreshed.append(True))
    saved = ctrl._tool_executor('save_memory', content='Keep existing node names.')
    found = ctrl._tool_executor('search_memory', query='node names')
    assert saved['success'] and found['success'] and refreshed
    assert any(row['id'] == saved['id'] for row in ctrl.memoryItems('semantic'))
    ctrl._session.bridge.ping.assert_not_called()


def test_memory_save_respects_confirmation_mode(store, ctrl, monkeypatch):
    ctrl._memory_enabled = True
    ctrl._confirm_mode = True
    confirm = Mock(return_value=False)
    monkeypatch.setattr(ctrl, '_await_confirm', confirm)
    assert not ctrl._tool_executor('save_memory', content='Do not persist this.')['success']
    confirm.assert_called_once()
    assert store.count_semantic() == 0
    ctrl._memory_enabled = False
    confirm.reset_mock()
    assert not ctrl._tool_executor('save_memory', content='Still disabled.')['success']
    confirm.assert_not_called()


@pytest.mark.parametrize('session_type', [AgentSession, BridgeAgentSession])
@pytest.mark.parametrize('enabled', [False, True])
def test_sessions_only_advertise_memory_tools_when_enabled(store, monkeypatch, session_type, enabled):
    memory_tools.save_memory(dict(content='Use native Houdini nodes.'), enabled=True)
    schemas = [memory_tools.SAVE_MEMORY_TOOL,
        {'type': 'function', 'function': {'name': 'search_memory'}},
        {'type': 'function', 'function': {'name': 'read_selection'}}]
    monkeypatch.setattr('houdini_agent.utils.mcp.fx_compat.tools_for_request', lambda tools, *a, **kw: tools)
    session = session_type.__new__(session_type)
    session.tools, session.history = schemas, []
    session._sys_think = session._sys_no_think = 'System'
    session.client = SimpleNamespace(reset_stop=Mock(), _tool_executor=Mock(), set_tool_executor=Mock(), agent_loop_auto=Mock(return_value={
        'ok': True, 'final_content': 'OK', 'new_messages': []}))
    session.run('New conversation', 'offline', 'openai', 'Agent', {}, rag=False, memory=enabled)
    request = session.client.agent_loop_auto.call_args.kwargs
    names = {tool['function']['name'] for tool in request['tools_override']}
    assert ('save_memory' in names) == enabled and ('search_memory' in names) == enabled
    assert any('Use native Houdini nodes.' in msg.get('content', '') for msg in request['messages']) == enabled


def test_embedded_dispatch_and_registry_modes(store, monkeypatch):
    from houdini_agent.utils.mcp import HoudiniMCP
    from houdini_agent.utils.tool_registry import ToolRegistry
    from houdini_agent.utils.ai_client import HOUDINI_TOOLS
    assert memory_tools.SAVE_MEMORY_TOOL in HOUDINI_TOOLS
    monkeypatch.setattr(memory_tools, 'memory_enabled', lambda: True)
    mcp = HoudiniMCP.__new__(HoudiniMCP)
    assert mcp._TOOL_DISPATCH['save_memory'] == '_tool_save_memory'
    assert mcp._tool_save_memory(dict(content='Embedded memory'))['success']
    assert mcp._tool_search_memory(dict(query='Embedded'))['count'] == 1
    registry = ToolRegistry()
    registry.register_core_tools([memory_tools.SAVE_MEMORY_TOOL])
    for mode in ['agent', 'ask', 'plan_planning', 'plan_executing']:
        assert registry.is_tool_allowed_in_mode('save_memory', mode)


@pytest.mark.parametrize('mode', ['agent', 'ask', 'plan_planning', 'plan_executing'])
@pytest.mark.parametrize('confirm_mode,approved', [(True, True), (True, False), (False, True)])
def test_legacy_dispatch_confirms_before_saving_and_uses_background(store, monkeypatch, mode, confirm_mode, approved):
    from houdini_agent.core.agent_runner import AgentRunnerMixin
    from houdini_agent.ui.run_mixin import RunMixin
    from houdini_agent.ui.ai_tab import AITab
    from houdini_agent.utils.mcp import HoudiniMCP

    class LegacyHarness(AgentRunnerMixin, RunMixin):
        _execute_tool_in_bg = AITab._execute_tool_in_bg

    monkeypatch.setattr(memory_tools, 'memory_enabled', lambda: True)
    harness = LegacyHarness()
    harness.client = SimpleNamespace(is_stop_requested=lambda: False)
    harness._agent_mode = mode == 'agent'
    harness._plan_mode = mode.startswith('plan_')
    harness._plan_phase = 'planning' if mode == 'plan_planning' else 'executing'
    harness._confirm_mode = confirm_mode
    harness._main_thread_busy = True  # A cook must not prevent local memory writes.
    harness._showToolStatus = SimpleNamespace(emit=Mock())
    harness._hideToolStatus = SimpleNamespace(emit=Mock())
    harness._execute_tool_in_main_thread = Mock(side_effect=AssertionError('Memory must not enter Houdini'))
    events, execution_threads = [], []
    mcp = HoudiniMCP.__new__(HoudiniMCP)

    def confirm(name, args):
        assert name == 'save_memory' and args['content'] == 'Keep existing node names.'
        assert store.count_semantic() == 0
        events.append('confirm')
        return approved

    def execute(name, args):
        events.append('execute')
        execution_threads.append(threading.get_ident())
        return getattr(mcp, mcp._TOOL_DISPATCH[name])(args)

    harness._request_tool_confirmation = Mock(side_effect=confirm)
    harness.mcp = SimpleNamespace(execute_tool=execute)
    main_thread = threading.get_ident()
    with ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(harness._execute_tool_with_todo, 'save_memory',
                             content='Keep existing node names.').result(timeout=5)
    if confirm_mode and not approved:
        assert not result['success'] and events == ['confirm']
        assert store.count_semantic() == 0
        assert execution_threads == []
    else:
        assert result['success'] and store.get_semantic(result['id']).rule == 'Keep existing node names.'
        assert events == (['confirm', 'execute'] if confirm_mode else ['execute'])
        assert execution_threads and execution_threads[0] != main_thread
    assert harness._request_tool_confirmation.call_count == int(confirm_mode)
    harness._execute_tool_in_main_thread.assert_not_called()


def test_legacy_ask_and_plan_tool_lists_keep_memory_save_available():
    from houdini_agent.core.agent_runner import AgentRunnerMixin
    from houdini_agent.utils.ai_client import HOUDINI_TOOLS
    from houdini_agent.utils.ultra_optimizer import UltraOptimizer
    for allowed in [AgentRunnerMixin._ASK_MODE_TOOLS, AgentRunnerMixin._PLAN_PLANNING_TOOLS]:
        schemas = UltraOptimizer.optimize_tool_definitions([
            schema for schema in HOUDINI_TOOLS if schema['function']['name'] in allowed])
        assert 'save_memory' in {schema['function']['name'] for schema in schemas}
