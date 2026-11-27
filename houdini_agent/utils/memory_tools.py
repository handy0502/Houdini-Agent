"""Local memory operations shared by desktop, Bridge and embedded tools."""
import threading


CATEGORIES = ['preference', 'command', 'debug', 'pitfall', 'workflow', 'knowledge', 'user_profile', 'general']
MEMORY_TOOLS = frozenset({'save_memory', 'search_memory'})
_lock = threading.RLock()

SAVE_MEMORY_TOOL = {
    'type': 'function',
    'function': {
        'name': 'save_memory',
        'description': (
            '将用户明确要求记住的偏好、个人信息或可复用经验保存到本机长期记忆，供后续会话读取。'
            '仅在用户明确要求保存或记住时调用，不要自动保存推测、临时任务状态、密码或 API Key。'
            '成功返回记忆 ID；只有 success=true 才能告诉用户已保存。重复内容不会重复创建。'
        ),
        'parameters': {
            'type': 'object',
            'properties': {
                'content': {'type': 'string', 'description': '精炼、完整的记忆内容，1–4000 字符'},
                'category': {'type': 'string', 'enum': CATEGORIES, 'description': '用途分类，默认 preference'},
            },
            'required': ['content'],
        },
    },
}


def memory_enabled():
    try:
        from houdini_agent.qt_compat import QSettings
        value = QSettings('HoudiniAI', 'Assistant').value('memory_enabled', False)
        return value.lower() == 'true' if isinstance(value, str) else bool(value)
    except Exception:
        return False


def save_memory(args, enabled=None, store=None):
    if not (memory_enabled() if enabled is None else enabled):
        return {'success': False, 'error': '长期记忆已关闭，请在设置 › 常规中开启'}
    content, category = args.get('content', ''), args.get('category', 'preference')
    if not isinstance(content, str) or not 1 <= len(content.strip()) <= 4000:
        return {'success': False, 'error': '记忆内容须为 1–4000 个字符'}
    if category not in CATEGORIES:
        return {'success': False, 'error': '无效的记忆分类'}
    content = content.strip()
    try:
        from .memory_store import get_memory_store, SemanticRecord
        store = store if store is not None else get_memory_store()
        with _lock:
            for record in store.get_all_semantic():
                if record.rule.strip() == content:
                    if record.abstraction_level != 0 or record.confidence < 1.0:
                        record.abstraction_level = 0
                        record.confidence = 1.0
                        store.add_semantic(record)
                    return {'success': True, 'id': record.id, 'created': False, 'result': '该记忆已保存'}
            record = SemanticRecord(rule=content, category=category, confidence=1.0, abstraction_level=0)
            record_id = store.add_semantic(record)
        return {'success': True, 'id': record_id, 'created': True, 'result': '已保存到本机长期记忆'}
    except Exception as exc:
        return {'success': False, 'error': '记忆保存失败：%s' % exc}


def search_memory(args, enabled=None, store=None):
    if not (memory_enabled() if enabled is None else enabled):
        return {'success': False, 'error': '长期记忆已关闭，请在设置 › 常规中开启'}
    query = args.get('query', '')
    if not isinstance(query, str) or not query.strip():
        return {'success': False, 'error': 'query 参数不能为空'}
    category = args.get('category')
    if category is not None and category not in CATEGORIES:
        return {'success': False, 'error': '无效的记忆分类'}
    try:
        top_k = min(max(int(args.get('top_k', 5)), 1), 10)
        from .memory_store import get_memory_store, ABSTRACTION_LEVELS
        store = store if store is not None else get_memory_store()
        with _lock:
            results = store.search_all_levels(query, category=category, top_k=top_k, min_confidence=0.1)
            memories = []
            for record, score in results:
                memories.append(dict(id=record.id, rule=record.rule, category=record.category,
                    abstraction_level=record.abstraction_level,
                    level_name=ABSTRACTION_LEVELS.get(record.abstraction_level, 'unknown'),
                    confidence=round(record.confidence, 2), relevance=round(score, 3),
                    activation_count=record.activation_count))
                store.increment_semantic_activation(record.id)
        return {'success': True, 'count': len(memories), 'memories': memories, 'query': query}
    except Exception as exc:
        return {'success': False, 'error': '记忆搜索失败：%s' % exc}


def memory_context(query):
    from .memory_store import get_memory_store
    store = get_memory_store()
    with _lock:
        records = store.get_core_memories(5)
        records += [record for record, _score in store.search_all_levels(query, top_k=3)]
        seen, parts = set(), []
        for record in records:
            if record.id not in seen:
                seen.add(record.id)
                parts.append('- ' + record.rule[:600])
        for record, _score in store.search_episodic(query, top_k=2):
            parts.append('- ' + record.task_description[:300] + ': ' + record.result_summary[:300])
    return ('长期记忆参考（用户保存的偏好及历史经验，结合当前任务使用）:\n' + '\n'.join(parts))[:4000] if parts else ''
