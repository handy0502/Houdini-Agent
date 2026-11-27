from houdini_agent.utils.task_runtime import TaskRuntime


def test_mutation_requires_fresh_validation_and_later_edits_invalidate_it():
    runtime = TaskRuntime()
    runtime.observe('create_node', {}, {'success': True})
    assert runtime.continuation()
    runtime.observe('verify_and_summarize', {}, {'success': True, 'validation': {'status': 'passed', 'measured': True}})
    assert runtime.continuation() is None
    result = {}
    assert runtime.finish(result) == '' and result['task_report']['status'] == 'verified'
    runtime.observe('set_node_parameter', {}, {'success': True})
    assert runtime.continuation()


def test_plan_continues_even_when_model_finishes_without_tool_work():
    runtime = TaskRuntime('Plan', 'plan_executing', {'steps': [{'id': 'a'}, {'id': 'b'}]})
    assert 'a, b' in runtime.continuation()
    runtime.observe('update_plan_step', {'step_id': 'a', 'status': 'done'}, {'success': True})
    assert 'b' in runtime.continuation()
    runtime.observe('update_plan_step', {'step_id': 'b', 'status': 'done'}, {'success': True})
    assert runtime.continuation() is None


def test_no_progress_stops_instead_of_repeating_forever():
    runtime = TaskRuntime()
    runtime.observe('execute_python', {}, {'success': False, 'error': 'partial mutation'})
    assert runtime.continuation()
    assert runtime.continuation() is None
    result = {'ok': True}
    assert '尚未通过' in runtime.finish(result)
    assert result['task_report']['status'] == 'incomplete'


def test_budget_blocks_execution_and_cannot_be_reported_verified():
    runtime = TaskRuntime(max_calls=1)
    calls = []
    execute = lambda name, **kw: calls.append(name) or {'success': True}
    runtime.execute(execute, 'read_selection', {})
    assert not runtime.execute(execute, 'create_node', {})['success']
    assert calls == ['read_selection']
    result = {}
    runtime.finish(result)
    assert result['task_report']['budget_exhausted']


def test_ask_and_plan_planning_do_not_auto_execute_a_plan():
    for mode, tool_mode in [('Ask', 'ask'), ('Plan', 'plan_planning')]:
        runtime = TaskRuntime(mode, tool_mode, {'steps': [{'id': 'a'}]})
        assert runtime.continuation() is None


def test_failed_or_unverified_checks_do_not_count_as_acceptance():
    for status in ('failed', 'unverified'):
        runtime = TaskRuntime()
        runtime.observe('create_node', {}, {'success': True})
        runtime.observe('verify_and_summarize', {}, {'success': True, 'validation': {'status': status}})
        assert runtime.continuation()


def test_structure_only_pass_does_not_establish_effect_acceptance():
    runtime = TaskRuntime()
    runtime.observe('create_node', {}, {'success': True})
    runtime.observe('verify_and_summarize', {}, {'success': True, 'validation': {'status': 'passed', 'measured': False}})
    assert runtime.continuation()
