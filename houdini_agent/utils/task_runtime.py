"""Per-turn execution evidence, bounded continuation, and plan progress.

No Qt objects are read here: all state is owned by the worker running the turn.
"""
import copy
import time
import threading


def changes_scene(name):
    from .tool_registry import _READONLY_TOOLS
    if name in _READONLY_TOOLS or name in {'create_plan', 'update_plan_step', 'add_todo', 'update_todo',
            'ask_question', 'save_memory', 'execute_shell', 'list_skills', 'verify_and_summarize',
            'check_houdini_connection', 'repair_houdini_connection', 'save_effect_case'}:
        return False
    if name.startswith('meshy_'):
        return False
    if name.startswith('fx_'):
        from .mcp.fx_compat import command_name, _is_readonly
        command = command_name(name)
        return command is not None and not _is_readonly(command)
    return True


class TaskRuntime:
    def __init__(self, mode='Agent', tool_mode=None, plan=None, max_followups=3, max_calls=200, max_seconds=900):
        self.enabled = mode != 'Ask' and tool_mode != 'plan_planning' and (mode != 'Plan' or tool_mode == 'plan_executing')
        self.steps = {str(s['id']): s.get('status', s.get('state', 'pending'))
                      for s in (plan or {}).get('steps', []) if isinstance(s, dict) and s.get('id')}
        self.revision = 0
        self.verified_revision = -1
        self.validation = None
        self.followups = 0
        self.max_followups = max_followups
        self.last_signature = None
        self.same_progress = 0
        self.calls = 0
        self.last_error = ''
        self.max_calls = max_calls
        self.deadline = time.monotonic() + max_seconds
        self.exhausted = False
        self.scene_facts = None
        self._budget_lock = threading.Lock()

    def execute(self, executor, name, args):
        with self._budget_lock:
            if self.calls >= self.max_calls or time.monotonic() >= self.deadline:
                self.exhausted = True
                return {'success': False, 'error': 'Task execution budget exhausted; stop and report unverified work.'}
            self.calls += 1
        try:
            result = executor(name, **args)
        except Exception:
            self.observe(name, args, {'success': False}, count=False)
            raise
        self.observe(name, args, result, count=False)
        return result

    def observe(self, name, args, result, count=True):
        if count:
            self.calls += 1
        if not isinstance(result, dict):
            return
        if name == 'get_scene_facts' and result.get('success'):
            self.scene_facts = copy.deepcopy(result.get('scene_facts'))
        if name == 'update_plan_step' and result.get('success'):
            sid = str(args.get('step_id', ''))
            if sid in self.steps:
                self.steps[sid] = args.get('status', 'pending')
        if name == 'verify_and_summarize':
            self.validation = copy.deepcopy(result.get('validation'))
            self.verified_revision = self.revision
        elif changes_scene(name):
            # Even a failed mutating command can leave a partial network behind.
            self.revision += 1
            if not result.get('success'):
                self.last_error = str(result.get('error', 'Tool failed'))[:300]

    def pending(self):
        return [sid for sid, status in self.steps.items() if status not in ('done', 'completed')]

    def _needs_verification(self):
        return self.revision > 0 and (self.verified_revision != self.revision
                or not self.validation or self.validation.get('status') != 'passed'
                or not self.validation.get('measured'))

    def continuation(self):
        if self.exhausted:
            return None
        if not self.enabled or (not self.pending() and not self._needs_verification()):
            return None
        signature = (self.revision, tuple(sorted(self.steps.items())),
                     self.verified_revision, str(self.validation))
        self.same_progress = self.same_progress + 1 if signature == self.last_signature else 0
        self.last_signature = signature
        if self.followups >= self.max_followups or self.same_progress >= 1:
            return None
        self.followups += 1
        message = '任务尚未验收，请继续处理，不要仅输出完成总结。'
        if self.pending():
            message += ' 尚未完成的计划步骤：%s。逐步执行并通过 update_plan_step 更新状态。' % ', '.join(self.pending())
        if self._needs_verification():
            message += (' 修改后必须调用 verify_and_summarize，提供 network_path、目标节点与可测量 criteria；'
                        '修复失败项后重新检查。验证只覆盖声明的检查及采样帧，不能把结构通过说成视觉或全时段通过。')
            if self.validation:
                failed = [c for c in self.validation.get('checks', []) if c.get('status') != 'passed']
                message += ' 未通过项：%s。' % str(failed)[:1200]
        return message

    def finish(self, result):
        self.exhausted = self.exhausted or bool(result.get('budget_exhausted'))
        incomplete = self.exhausted or (self.enabled and (bool(self.pending()) or self._needs_verification()
                      or (self.revision > 0 and not result.get('ok', True))))
        report = {'status': 'incomplete' if incomplete else ('verified' if self.enabled and self.revision else 'not_required'),
                  'pending_steps': self.pending(), 'scene_revision': self.revision,
                  'verification': self.validation, 'continuations': self.followups, 'tool_calls': self.calls,
                  'budget_exhausted': self.exhausted}
        if self.scene_facts:
            report['scene_facts'] = self.scene_facts
        result['task_report'] = report
        if incomplete and (self.calls or result.get('ok', True)):
            note = '\n\n本轮任务尚未通过验收：仍有未完成步骤或未通过的场景检查。已停止自动重试，当前结果保留，可继续修改。'
            result['final_content'] = (result.get('final_content') or result.get('content') or '') + note
            result['content'] = (result.get('content') or '') + note
            return note
        return ''
