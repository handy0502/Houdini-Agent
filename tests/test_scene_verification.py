from types import SimpleNamespace as NS
from houdini_agent.utils.mcp.verification import verify


def fixture():
    state = {'frame': 12}
    geo = NS(intrinsicValue=lambda name: 8 if name == 'pointcount' else 6,
             pointFloatAttribValues=lambda name: [0, 0, 0, float('nan'), 1, 2])
    node = NS(geometry=lambda: geo)
    hou = NS(frame=lambda: state['frame'], setFrame=lambda f: state.update(frame=f), node=lambda p: node if p == '/obj/g/out' else None)
    mcp = NS(get_network_structure=lambda p: (True, {'network_path': '/obj/g', 'nodes': [
        {'path': '/obj/g/out', 'name': 'out', 'type': 'sop/null', 'has_errors': False, 'is_displayed': True}], 'connections': []}))
    return mcp, hou, state


def test_reports_measured_failure_and_restores_frame():
    mcp, hou, state = fixture()
    result = verify(mcp, {'criteria': [{'kind': 'point_count', 'node_path': '/obj/g/out', 'min': 10, 'frames': [1, 2]}]}, hou)
    assert result['success'] and result['validation']['status'] == 'failed'
    assert all(c['actual'] == 8 for c in result['validation']['checks'] if c['kind'] == 'point_count')
    assert state['frame'] == 12


def test_unknown_tests_are_unverified_not_passed():
    mcp, hou, _ = fixture()
    result = verify(mcp, {'criteria': [{'kind': 'looks_beautiful', 'node_path': '/obj/g/out'}]}, hou)
    assert result['validation']['status'] == 'unverified'


def test_nan_positions_and_missing_nodes_fail():
    mcp, hou, _ = fixture()
    for criterion in ({'kind': 'finite_positions', 'node_path': '/obj/g/out'},
                      {'kind': 'node_exists', 'node_path': '/obj/missing'}):
        assert verify(mcp, {'criteria': [criterion]}, hou)['validation']['status'] == 'failed'


def test_declared_counts_can_pass_but_do_not_assert_visual_quality():
    mcp, hou, _ = fixture()
    result = verify(mcp, {'criteria': [{'kind': 'point_count', 'node_path': '/obj/g/out', 'min': 8, 'max': 8}]}, hou)
    assert result['validation']['status'] == 'passed'
    assert 'does not prove' in result['validation']['scope']


def test_numeric_check_without_expected_range_is_not_acceptance():
    mcp, hou, _ = fixture()
    result = verify(mcp, {'criteria': [{'kind': 'point_count', 'node_path': '/obj/g/out'}]}, hou)
    assert result['validation']['status'] == 'unverified'


def test_inspection_failure_and_bad_node_list_are_clean_errors():
    mcp, hou, _ = fixture()
    assert not verify(mcp, {'check_items': [{}]}, hou)['success']
    mcp.get_network_structure = lambda p: (False, 'Disconnected')
    assert verify(mcp, {}, hou) == {'success': False, 'error': 'Disconnected'}
