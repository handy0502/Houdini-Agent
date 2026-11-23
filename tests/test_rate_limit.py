"""Offline rate-limit retries: wait, release responses, preserve the request."""
import copy
from email.utils import formatdate
from types import SimpleNamespace

import pytest

from houdini_agent.utils.ai_client import AIClient
from houdini_agent.utils.ai_client_streaming import AIClientStreamingMixin


class Response:
    def __init__(self, status=429, retry_after=None, anthropic=False):
        self.status_code = status
        self.headers = {} if retry_after is None else {'Retry-After': retry_after}
        self.text = 'Too many pending requests, please retry later'
        self.closed = False
        self.anthropic = anthropic

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        self.closed = True

    def json(self):
        if self.status_code == 200:
            if self.anthropic:
                return {'content': [{'type': 'text', 'text': 'OK'}], 'stop_reason': 'end_turn'}
            return {'choices': [{'message': {'content': 'OK'}, 'finish_reason': 'stop'}]}
        return {'error': {'message': self.text}}

    def raise_for_status(self):
        assert self.status_code == 200

    def iter_content(self, **kwargs):
        yield ('\n\n'.join(self.iter_lines()) + '\n\n').encode('utf-8')

    def iter_lines(self, **kwargs):
        if self.anthropic:
            yield 'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"OK"}}'
            yield 'data: {"type":"message_stop"}'
        else:
            yield 'data: {"choices":[{"delta":{"content":"OK"},"finish_reason":null}]}'
            yield 'data: [DONE]'


def client(monkeypatch, responses):
    c = AIClient()
    monkeypatch.setattr(c, '_get_api_key', lambda *a: 'test')
    monkeypatch.setattr(c, '_get_api_url', lambda *a: 'https://offline.invalid/test')
    monkeypatch.setattr(c, '_is_anthropic_protocol', lambda *a: False)
    payloads = []
    def post(url, json=None, **kw):
        payloads.append(copy.deepcopy(json))
        return responses[len(payloads) - 1]
    c._http_session = SimpleNamespace(post=post)
    c._max_retries = 3
    return c, payloads


@pytest.mark.parametrize('anthropic', [False, True])
@pytest.mark.parametrize('eventual_success', [False, True])
def test_429_retries_are_bounded_and_release_response(monkeypatch, anthropic, eventual_success):
    responses = [Response(retry_after='2'), Response(),
                 Response(200 if eventual_success else 429, anthropic=anthropic)]
    c, payloads = client(monkeypatch, responses)
    waits = []
    def wait(delay):
        assert responses[len(payloads) - 1].closed
        waits.append(delay)
        return True
    monkeypatch.setattr(c, '_wait_for_retry', wait)
    messages = [{'role': 'user', 'content': 'hello'}]
    if anthropic:
        events = list(c._chat_stream_anthropic(messages, 'claude-test', 'custom', enable_thinking=False))
    else:
        events = list(c.chat_stream(messages, 'gpt-test', 'custom'))
    assert waits == [2, 10]
    assert len(payloads) == 3 and payloads[0] == payloads[1] == payloads[2]
    assert all(r.closed for r in responses)
    if eventual_success:
        assert any(e.get('content') == 'OK' for e in events)
        assert not any(e['type'] == 'error' for e in events)
    else:
        assert len(events) == 1 and 'HTTP 429' in events[0]['error']


def test_long_cooldown_does_not_retry_early(monkeypatch):
    c, payloads = client(monkeypatch, [Response(retry_after='120')])
    monkeypatch.setattr(c, '_wait_for_retry', lambda delay: pytest.fail('must not retry early'))
    events = list(c.chat_stream([{'role': 'user', 'content': 'hi'}], 'gpt-test', 'custom'))
    assert len(payloads) == 1 and 'HTTP 429' in events[-1]['error']


@pytest.mark.parametrize('anthropic', [False, True])
@pytest.mark.parametrize('eventual_success', [False, True])
def test_nonstream_rate_limit_waits_without_rapid_retries(monkeypatch, anthropic, eventual_success):
    responses = [Response(retry_after='2'), Response(),
                 Response(200 if eventual_success else 429, anthropic=anthropic)]
    c, payloads = client(monkeypatch, responses)
    waits = []
    def wait(delay):
        assert responses[len(payloads) - 1].closed
        waits.append(delay)
        return True
    monkeypatch.setattr(c, '_wait_for_retry', wait)
    messages = [{'role': 'user', 'content': 'hi'}]
    result = (c._chat_anthropic(messages, 'claude-test', 'custom') if anthropic
              else c.chat(messages, 'gpt-test', 'custom'))
    assert result['ok'] is eventual_success
    assert waits == [2, 10]
    assert len(payloads) == 3 and payloads[0] == payloads[1] == payloads[2]


def test_retry_wait_can_be_cancelled(monkeypatch):
    c, payloads = client(monkeypatch, [Response()])
    c._stop_event.set()
    events = list(c.chat_stream([{'role': 'user', 'content': 'hi'}], 'gpt-test', 'custom'))
    assert len(events) == 1 and events[0]['type'] == 'stopped'
    assert len(payloads) == 1
    assert c._wait_for_retry(60) is False


def test_retry_after_http_date(monkeypatch):
    monkeypatch.setattr('houdini_agent.utils.ai_client_streaming.time.time', lambda: 1000000)
    mixin = AIClientStreamingMixin()
    assert mixin._rate_limit_delay(Response(retry_after=formatdate(1000030, usegmt=True)), 0) == 30


def test_429_after_tool_round_is_not_format_recovery():
    from test_agent_loop_guards import _FakeAgent
    agent = _FakeAgent()
    original = agent.chat_stream
    calls = []
    def stream(**kwargs):
        calls.append(copy.deepcopy(kwargs['messages']))
        if len(calls) == 1:
            yield from original(**kwargs)
        else:
            yield {'type': 'error', 'error': 'HTTP 429: Too many pending requests'}
    agent.chat_stream = stream
    result = agent.agent_loop_stream(
        messages=[{'role': 'user', 'content': 'hello'}], model='gpt-test', provider='custom',
        tools_override=[], max_iterations=10, enable_thinking=False)
    assert len(calls) == 2 and agent.exec_count == 1
    assert not result['ok'] and 'HTTP 429' in result['error']


@pytest.mark.parametrize('session_module,session_name', [
    ('agent_session', 'AgentSession'), ('bridge_session', 'BridgeAgentSession')])
@pytest.mark.parametrize('partial', [False, True])
def test_session_does_not_duplicate_rejected_turn(monkeypatch, session_module, session_name, partial):
    import importlib
    cls = getattr(importlib.import_module('houdini_agent.ui_qml.' + session_module), session_name)
    session = cls.__new__(cls)
    initial = [{'role': 'user', 'content': 'old'}, {'role': 'assistant', 'content': 'answer'}]
    session.history = copy.deepcopy(initial)
    session._sys_think = session._sys_no_think = 'system'
    session.tools = []
    session._context_messages = lambda *a: []
    result = {'ok': False, 'error': 'HTTP 429', 'final_content': '', 'new_messages': []}
    if partial:
        result['new_messages'] = [
            {'role': 'assistant', 'content': '', 'tool_calls': [{'id': 't', 'type': 'function', 'function': {'name': 'inspect', 'arguments': '{}'}}]},
            {'role': 'tool', 'tool_call_id': 't', 'content': 'OK'}]
    session.client = SimpleNamespace(reset_stop=lambda: None, agent_loop_auto=lambda **kw: result)
    session.run('retry me', 'test-model', 'custom', 'Ask', {}, rag=False)
    if partial:
        assert len(session.history) > len(initial) and any(m['role'] == 'tool' for m in session.history)
    else:
        assert session.history == initial
