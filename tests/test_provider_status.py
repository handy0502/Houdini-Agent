"""Credential presence, provider verification and atomic model switching, offline."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from test_message_queue import ctrl, tick
from houdini_agent.ui_qml import provider_check
from houdini_agent.utils import ai_client_providers as providers


@pytest.fixture
def c(ctrl, monkeypatch):
    monkeypatch.setattr(providers.AIClientProvidersMixin, '_read_api_key', lambda *a: None)
    monkeypatch.setattr(ctrl, '_sub_logged_in', lambda *a: False)
    client = SimpleNamespace(_api_keys={}, set_custom_provider=Mock())
    def save(key, persist=False, provider='openai'):
        client._api_keys[provider] = key
        return True
    client.set_api_key = Mock(side_effect=save)
    ctrl._session = SimpleNamespace(client=client, history=[])
    return ctrl


def custom(c):
    c._custom_providers = [{'id': 'local', 'name': 'Local', 'base_url': 'http://localhost:9999/v1',
                            'api_key': '', 'anthropic': False,
                            'models': [{'name': 'one'}, {'name': 'two'}]}]
    return 'custom:local'


def test_key_save_updates_presence_but_does_not_claim_available(c):
    changes = []
    c.providerStatusChanged.connect(lambda: changes.append(True))
    assert c._provider_status('openai')['state'] == 'missing'
    assert c.submitApiKey('openai', 'offline-test-key')
    status = c._provider_status('openai')
    assert status['configured'] and status['state'] == 'unverified' and changes
    assert 'offline-test-key' not in str(c.builtinProviderItems())
    c._session.client.set_api_key.assert_called_once_with('offline-test-key', persist=True, provider='openai')


def test_custom_no_key_and_verified_status_are_shared_across_models(c):
    key = custom(c)
    assert c._provider_status(key)['configured']
    assert c._provider_status(key)['stateLabel'] == c.tr('未填写 Key · 未验证')
    assert c.selectProviderModel(key, 'one')
    config = c._provider_snapshot(key)
    c._on_provider_check(dict(provider=key, model='one', fingerprint=provider_check.provider_fingerprint(config), state='ok'))
    assert c._provider_status(key)['state'] == 'ok'
    assert c.selectProviderModel(key, 'two')
    assert c._provider_status(key)['state'] == 'ok'
    assert c.selectProviderModel(key, 'one')
    assert c._provider_status(key)['state'] == 'ok'


def test_failed_key_save_does_not_report_configured(c, monkeypatch):
    c._session.client.set_api_key.side_effect = None
    c._session.client.set_api_key.return_value = False
    info = Mock()
    monkeypatch.setattr(c, '_info', info)
    assert not c.submitApiKey('openai', 'offline-key')
    assert c._provider_status('openai')['state'] == 'missing'
    info.assert_called_once()


def test_stale_key_check_cannot_mark_new_credentials_available(c):
    c.submitApiKey('openai', 'first')
    config = c._provider_snapshot('openai')
    c.submitApiKey('openai', 'second')
    c._on_provider_check(dict(provider='openai', model=config['model'],
                             fingerprint=provider_check.provider_fingerprint(config), state='ok'))
    assert c._provider_status('openai')['state'] == 'unverified'


def test_switch_is_atomic_and_missing_credentials_open_configuration(c):
    original = (c.provider, c.model)
    opened = []
    c.openApiKeyDialog.connect(opened.append)
    target_model = c._provider_model_names('deepseek')[0]
    assert not c.selectProviderModel('deepseek', target_model)
    assert (c.provider, c.model) == original and opened == ['deepseek']
    c._running = True
    assert not c.selectProviderModel('deepseek', 'different-model')
    assert (c.provider, c.model) == original
    c._running = False


def test_verification_is_explicit_and_only_one_check_runs_for_provider(c, monkeypatch):
    c.submitApiKey('openai', 'offline')
    pending = []
    monkeypatch.setattr('houdini_agent.ui_qml.controller.threading.Thread',
                        lambda target, **kw: SimpleNamespace(start=lambda: pending.append(target)))
    checked = []
    monkeypatch.setattr(provider_check, 'check_model', lambda config: checked.append(config['model']) or 'ok')
    c.setModel(c._provider_model_names('openai')[-1])
    c.verifyProvider('openai')
    c.verifyProvider('openai')
    assert len(pending) == 1 and c._provider_status('openai')['state'] == 'checking'
    pending[0]()
    tick()
    assert checked == [c._provider_model_names('openai')[0]]
    assert c._provider_status('openai')['state'] == 'ok'
    c.setModel(c._provider_model_names('openai')[1])
    c.verifyProvider('openai')
    assert len(pending) == 1


def test_subscription_change_rejects_old_account_result(c, monkeypatch):
    monkeypatch.setattr(c, '_sub_logged_in', lambda *a: True)
    monkeypatch.setattr(c, '_provider_account_signature', lambda *a: 'first-account')
    config = c._provider_snapshot('codex')
    monkeypatch.setattr(c, '_provider_account_signature', lambda *a: 'second-account')
    c._reset_subscription_checks()
    c._on_provider_check(dict(provider='codex', model=config['model'],
                             fingerprint=provider_check.provider_fingerprint(config), state='ok'))
    assert c._provider_status('codex')['state'] == 'unverified'


def test_verified_result_survives_reload_and_skips_duplicate_request(c, monkeypatch):
    from houdini_agent.ui_qml.controller import QSettings
    c.submitApiKey('openai', 'offline-secret')
    notices = []
    c.toast.connect(notices.append)
    config = c._provider_snapshot('openai')
    c._on_provider_check(dict(provider='openai', model=config['model'],
                             fingerprint=provider_check.provider_fingerprint(config), state='ok'))
    stored = QSettings('HoudiniAI', 'Assistant').value('provider_model_checks')
    assert 'offline-secret' not in stored
    assert '保存验证状态失败' not in notices
    c._provider_checks.clear()
    c._load_provider_checks()
    assert c._provider_status('openai')['state'] == 'ok'
    worker = Mock()
    monkeypatch.setattr('houdini_agent.ui_qml.controller.threading.Thread', worker)
    c.verifyProvider('openai')
    worker.assert_not_called()
    c.submitApiKey('openai', 'changed-secret')
    assert c._provider_status('openai')['state'] == 'unverified'


def test_inactive_provider_keeps_available_dot_for_verified_nondefault_model(c):
    key = custom(c)
    config = c._provider_snapshot(key, 'two')
    c._on_provider_check(dict(provider=key, model='two',
                             fingerprint=provider_check.provider_fingerprint(config), state='ok'))
    assert c.customProviderItems()[0]['state'] == 'ok'


def test_legacy_per_model_verification_is_reused_for_provider(c, monkeypatch):
    key = custom(c)
    config = c._provider_snapshot(key, 'two')
    c._provider_checks[(key, 'two')] = dict(state='ok', fingerprint=provider_check.fingerprint(config))
    assert c._provider_status(key)['state'] == 'ok'
    worker = Mock()
    monkeypatch.setattr('houdini_agent.ui_qml.controller.threading.Thread', worker)
    c.verifyProvider(key)
    worker.assert_not_called()
    c._custom_providers[0]['base_url'] = 'https://changed.invalid/v1'
    assert c._provider_status(key)['state'] == 'unverified'


def test_provider_verification_survives_model_list_changes(c):
    key = custom(c)
    config = c._provider_snapshot(key)
    c._on_provider_check(dict(provider=key, model=config['model'],
                             fingerprint=provider_check.provider_fingerprint(config), state='ok'))
    c._custom_providers[0]['models'] = [dict(name='new-version')]
    assert c._provider_status(key)['state'] == 'ok'


def test_unchanged_subscription_account_keeps_saved_verification(c, monkeypatch):
    monkeypatch.setattr(c, '_sub_logged_in', lambda *a: True)
    monkeypatch.setattr(c, '_provider_account_signature', lambda *a: 'same-account')
    config = c._provider_snapshot('codex')
    c._on_provider_check(dict(provider='codex', model=config['model'],
                             fingerprint=provider_check.provider_fingerprint(config), state='ok'))
    c._reset_subscription_checks()
    assert c._provider_status('codex')['state'] == 'ok'


def test_masked_custom_key_is_preserved_when_form_does_not_edit_it(c):
    import json
    key = custom(c)
    c._custom_providers[0]['api_key'] = 'saved-offline-key'
    item = c.customProviderItems()[0]
    assert item['api_key'] == '••••••••'
    assert c.providerConfiguration(key)['key_preview'] == '••••••••'
    del item['api_key']
    item['name'] = 'Renamed'
    assert c.saveCustomProvider(json.dumps(item))['ok']
    assert c._provider_snapshot(key)['key'] == 'saved-offline-key'
    item['api_key'] = ''
    assert c.saveCustomProvider(json.dumps(item))['ok']
    assert c._provider_snapshot(key)['key'] == ''


@pytest.mark.parametrize('field,value', [('base_url', 'https://changed.invalid/v1'), ('anthropic', True)])
def test_custom_endpoint_or_protocol_change_invalidates_verification(c, field, value):
    key = custom(c)
    config = c._provider_snapshot(key)
    c._on_provider_check(dict(provider=key, model=config['model'],
                             fingerprint=provider_check.provider_fingerprint(config), state='ok'))
    c._custom_providers[0][field] = value
    assert c._provider_status(key)['state'] == 'unverified'


def test_api_key_persistence_failure_preserves_runtime_key(monkeypatch):
    client = providers.AIClientProvidersMixin()
    client._api_keys = {'openai': 'old-offline-key'}
    monkeypatch.setattr(providers, 'load_config', lambda *a, **kw: ({}, 'offline.ini'))
    monkeypatch.setattr(providers, 'save_config', lambda *a, **kw: (False, ''))
    assert not client.set_api_key('new-offline-key', persist=True)
    assert client._api_keys['openai'] == 'old-offline-key'


def test_switching_to_keyless_profile_cannot_reuse_previous_profile_key():
    client = providers.AIClientProvidersMixin()
    client._api_keys = {'custom': 'previous-profile-key'}
    client.set_custom_provider('http://localhost:9999/v1', '')
    assert client._api_keys['custom'] == ''
    client.set_custom_provider('https://offline.invalid/v1', 'new-profile-key')
    assert client._api_keys['custom'] == 'new-profile-key'


@pytest.mark.parametrize('result,expected', [
    ({'ok': True, 'content': 'OK'}, 'ok'),
    ({'ok': True, 'content': None, 'finish_reason': 'length'}, 'ok'),
    ({'ok': True, 'content': None}, 'error'),
    ({'ok': True, 'finish_reason': 'stop', 'raw': {'error': {'message': 'echoed-secret'}}}, 'error'),
    ({'ok': True, 'finish_reason': 'stop', 'raw': {}}, 'error'),
    ({'ok': False, 'error': 'HTTP 401: echoed-secret'}, 'error'),
    ({'ok': False, 'error': 'HTTP 429: too many requests'}, 'busy'),
    ({'ok': False, 'error': 'HTTP 503'}, 'error'),
])
def test_isolated_check_uses_correct_model_no_tools_or_history(result, expected):
    client = SimpleNamespace(_http_session=SimpleNamespace(close=Mock()),
                             set_custom_provider=Mock(), chat=Mock(return_value=result))
    config = {'provider': 'custom:local', 'custom': True, 'url': 'http://localhost:9999/v1',
              'key': 'offline', 'model': 'target-model', 'anthropic': True}
    assert provider_check.check_model(config, lambda: client) == expected
    client.set_custom_provider.assert_called_once_with(config['url'], 'offline', True, True)
    args, kwargs = client.chat.call_args
    assert len(args[0]) == 1 and kwargs['model'] == 'target-model' and kwargs['provider'] == 'custom'
    assert 'tools' not in kwargs and 'max_tokens' not in kwargs and client._max_retries == 1
    client._http_session.close.assert_called_once()
