"""Shared, measurable scene checks for embedded and Bridge execution."""
import math


def _within(value, rule):
    if not math.isfinite(float(value)):
        return False
    return (('min' not in rule or value >= rule['min'])
            and ('max' not in rule or value <= rule['max']))


def verify(mcp, args, hou_module=None):
    ok, network = mcp.get_network_structure(args.get('network_path'))
    if not ok:
        return {'success': False, 'error': str(network)}
    checks, warnings = [], []
    nodes = network.get('nodes', [])
    paths = {n['path']: n for n in nodes}
    names = {n.get('name'): n for n in nodes}
    for node in nodes:
        checks.append({'kind': 'node_health', 'node_path': node['path'],
                       'status': 'failed' if node.get('has_errors') else 'passed'})
    sop_nodes = [n for n in nodes if n.get('type', '').startswith('sop/')]
    if sop_nodes:
        checks.append({'kind': 'display_output', 'status':
                       'passed' if any(n.get('is_displayed') for n in sop_nodes) else 'failed'})
    connected = {c[k] for c in network.get('connections', []) for k in ('from', 'to') if k in c}
    if len(nodes) > 1:
        warnings = ['Unconnected branch: ' + n['path'] for n in nodes if n['path'] not in connected]
    items = args.get('check_items') or []
    if not isinstance(items, list) or any(not isinstance(item, str) for item in items):
        return {'success': False, 'error': 'check_items must be an array of node paths or names'}
    for item in items:
        found = paths.get(item) or names.get(item)
        checks.append({'kind': 'node_exists', 'node_path': item,
                       'status': 'passed' if found else ('failed' if item.startswith('/') else 'unverified')})
    criteria = args.get('criteria') or []
    if not isinstance(criteria, list) or len(criteria) > 50:
        return {'success': False, 'error': 'criteria must contain at most 50 checks'}
    if criteria and hou_module is None:
        import hou as hou_module
    original_frame = hou_module.frame() if criteria else None
    try:
        for rule in criteria:
            if not isinstance(rule, dict):
                return {'success': False, 'error': 'Each criterion must be an object'}
            frames = rule.get('frames') or [original_frame]
            if not isinstance(frames, list) or len(frames) > 120:
                return {'success': False, 'error': 'Each criterion supports at most 120 sample frames'}
            for frame in frames:
                if getattr(mcp, '_stop_event', None) is not None and mcp._stop_event.is_set():
                    return {'success': False, 'error': 'Verification stopped'}
                result = {'kind': rule.get('kind'), 'node_path': rule.get('node_path'), 'frame': frame}
                try:
                    if not isinstance(frame, (int, float)) or not math.isfinite(frame):
                        raise ValueError('Invalid frame')
                    hou_module.setFrame(frame)
                    result.update(_check(hou_module, rule))
                except Exception as exc:
                    result.update(status='failed', error=str(exc)[:400])
                checks.append(result)
    finally:
        if criteria:
            hou_module.setFrame(original_frame)
    if not checks:
        status = 'unverified'
    elif any(c['status'] == 'failed' for c in checks):
        status = 'failed'
    elif any(c['status'] == 'unverified' for c in checks):
        status = 'unverified'
    else:
        status = 'passed'
    validation = {'status': status, 'measured': bool(criteria), 'network_path': network.get('network_path'), 'checks': checks,
                  'warnings': warnings, 'expected_result': args.get('expected_result', ''),
                  'scope': 'Only the reported structural/declared checks and sampled frames were tested. '
                           'A description or screenshot alone does not prove simulation or visual quality.'}
    return {'success': True, 'validation': validation,
            'result': 'Verification %s: %d checks, %d failed, %d unverified. %s' %
                      (status, len(checks), sum(c['status'] == 'failed' for c in checks),
                       sum(c['status'] == 'unverified' for c in checks), validation['scope'])}


def _check(hou, rule):
    kind = rule.get('kind')
    node = hou.node(rule.get('node_path', ''))
    if node is None:
        return {'status': 'failed', 'error': 'Node does not exist'}
    if kind == 'node_exists':
        return {'status': 'passed'}
    if kind == 'connection':
        source = node.input(int(rule.get('input_index', 0)))
        return {'status': 'passed' if source and source.path() == rule.get('source_path') else 'failed'}
    if kind in ('parameter', 'point_count', 'primitive_count', 'bounds_size') and not any(k in rule for k in ('min', 'max', 'value')):
        return {'status': 'unverified', 'error': 'Supply numeric min/max, or value for a parameter check'}
    if kind == 'parameter':
        parm = node.parm(rule.get('name', ''))
        if parm is None:
            return {'status': 'failed', 'error': 'Parameter does not exist'}
        value = parm.eval()
        passed = value == rule['value'] if 'value' in rule else _within(value, rule)
        return {'status': 'passed' if passed else 'failed', 'actual': value}
    if kind not in ('point_count', 'primitive_count', 'attribute', 'bounds_size', 'finite_positions'):
        return {'status': 'unverified', 'error': 'Unsupported criterion; no check was performed'}
    geo = node.geometry()
    if geo is None:
        return {'status': 'failed', 'error': 'No geometry'}
    if kind in ('point_count', 'primitive_count'):
        value = geo.intrinsicValue('pointcount' if kind == 'point_count' else 'primitivecount')
        return {'status': 'passed' if _within(value, rule) else 'failed', 'actual': value}
    if kind == 'bounds_size':
        axis = int(rule.get('axis', 0))
        if axis not in (0, 1, 2):
            raise ValueError('axis must be 0, 1 or 2')
        value = geo.boundingBox().sizevec()[axis]
        return {'status': 'passed' if _within(value, rule) else 'failed', 'actual': value}
    if kind == 'attribute':
        owner = rule.get('owner', 'point')
        lookup = {'point': geo.findPointAttrib, 'primitive': geo.findPrimAttrib,
                  'vertex': geo.findVertexAttrib, 'detail': geo.findGlobalAttrib}
        if owner not in lookup:
            raise ValueError('Unknown attribute owner')
        attrib = lookup[owner](rule.get('name', ''))
        return {'status': 'passed' if attrib is not None else 'failed', 'owner': owner}
    values = geo.pointFloatAttribValues('P')
    return {'status': 'passed' if all(math.isfinite(v) for v in values) else 'failed',
            'components_checked': len(values)}
