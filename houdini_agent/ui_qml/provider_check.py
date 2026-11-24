"""Isolated, opt-in checks of a single provider/model, without chat history."""
import hashlib
import json
import re


def fingerprint(config):
    return hashlib.sha256(json.dumps(config, sort_keys=True).encode('utf-8')).hexdigest()


def provider_fingerprint(config):
    """Account/endpoint identity, shared by all models of one provider."""
    return fingerprint({key: value for key, value in config.items() if key != 'model'})


def check_model(config, client_factory=None):
    if client_factory is None:
        from houdini_agent.utils.ai_client import AIClient
        client_factory = AIClient
    client = None
    try:
        client = client_factory()
        client._max_retries = 1
        route = config['provider']
        if config.get('custom'):
            route = 'custom'
            client.set_custom_provider(config['url'], config.get('key', ''), True, config.get('anthropic', False))
        elif config.get('key'):
            client.set_api_key(config['key'], provider=route)
        result = client.chat([{'role': 'user', 'content': 'Reply OK.'}],
                             model=config['model'], provider=route, timeout=20)
        raw = result.get('raw')
        if isinstance(raw, dict) and raw.get('error'):
            return error_state(raw['error'])
        valid = (result.get('content') is not None or bool(result.get('tool_calls'))
                 or result.get('finish_reason') in ('stop', 'length', 'tool_calls', 'end_turn', 'max_tokens'))
        if isinstance(raw, dict) and not (raw.get('choices') or isinstance(raw.get('content'), list)):
            valid = False
        if result.get('ok') and valid:
            return 'ok'
        return error_state(result.get('error', ''))
    except Exception:
        return 'error'
    finally:
        session = getattr(client, '_http_session', None)
        if session is not None:
            try:
                session.close()
            except Exception:
                pass


def error_state(error):
    # Never display arbitrary response bodies: gateways can echo credentials.
    return 'busy' if re.search(r'\b429\b', str(error)) else 'error'
