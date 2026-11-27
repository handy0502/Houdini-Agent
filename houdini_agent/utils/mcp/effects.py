"""Scene facts and verified workflow archival; called on Houdini's main thread."""
import hashlib
import json


def scene_facts(mcp, args, hou):
    ok, network = mcp.get_network_structure(args.get('network_path'))
    if not ok:
        return {'success': False, 'error': str(network)}
    limit = max(1, min(int(args.get('max_nodes', 50)), 200))
    facts, chars = [], 0
    for metadata in network.get('nodes', [])[:limit]:
        node = hou.node(metadata['path'])
        if node is None:
            continue
        item = {k: metadata.get(k) for k in ('name', 'path', 'type', 'is_displayed', 'has_errors', 'position')}
        item['inputs'] = [n.path() if n else None for n in node.inputs()]
        item['comment'] = node.comment()[:1000]
        item['parameters'] = {}
        for parm in node.parms():
            try:
                if not parm.isAtDefault():
                    value = parm.unexpandedString() if parm.parmTemplate().type() == hou.parmTemplateType.String else parm.eval()
                    if isinstance(value, (str, int, float)):
                        item['parameters'][parm.name()] = value[:1000] if isinstance(value, str) else value
                        if isinstance(value, str) and parm.parmTemplate().stringType() == hou.stringParmType.FileReference:
                            item.setdefault('file_dependencies', []).append({'parameter': parm.name(), 'path': value[:1000]})
                if len(item['parameters']) >= 40:
                    break
            except Exception:
                continue
        if args.get('include_geometry', True) and metadata.get('is_displayed') and hasattr(node, 'geometry'):
            try:
                geo = node.geometry()
                item['geometry'] = {'points': geo.intrinsicValue('pointcount'),
                    'primitives': geo.intrinsicValue('primitivecount'),
                    'bounds_size': list(geo.boundingBox().sizevec()),
                    'attributes': {owner: [{'name': a.name(), 'size': a.size(), 'type': str(a.dataType())}
                                          for a in attrs()[:64]]
                                   for owner, attrs in [('point', geo.pointAttribs), ('primitive', geo.primAttribs),
                                                        ('vertex', geo.vertexAttribs), ('detail', geo.globalAttribs)]}}
            except Exception as exc:
                item['geometry_error'] = str(exc)[:300]
        chars += len(json.dumps(item, ensure_ascii=False, default=str))
        if chars > 60000:
            break
        facts.append(item)
    payload = {'network_path': network.get('network_path'), 'nodes': facts,
               'truncated': len(network.get('nodes', [])) > len(facts),
               'hip_path': hou.hipFile.path(), 'version': hou.applicationVersionString(),
               'frame': hou.frame(), 'fps': hou.fps(), 'frame_range': list(hou.playbar.frameRange()),
               'units': 'not_declared', 'note': 'Facts at this frame only. Refresh after manual edits or switching HIP/session.'}
    payload['revision'] = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()[:20]
    return {'success': True, 'scene_facts': payload, 'result': json.dumps(payload, ensure_ascii=False)}


def save_case(mcp, args, hou):
    from ..effect_library import EffectLibrary
    from .verification import verify
    criteria = args.get('criteria') or []
    if not criteria:
        return {'success': False, 'error': 'Supply measurable criteria; a title or success message is not evidence'}
    checked = verify(mcp, {'network_path': args.get('network_path'), 'check_items': [],
                          'criteria': criteria, 'expected_result': args.get('summary', '')}, hou)
    if not checked.get('success') or checked['validation']['status'] != 'passed':
        return {'success': False, 'error': 'Workflow has not passed fresh verification', 'validation': checked.get('validation')}
    record = {k: args.get(k, '') for k in ('title', 'summary', 'procedure', 'project')}
    record.update(tags=args.get('tags') or [], version=hou.applicationVersionString(),
                  verification=checked['validation'], criteria=criteria,
                  source_hip=hou.hipFile.path(), network_path=args.get('network_path'))
    if args.get('_prepare_only'):
        return {'success': True, 'case_record': record}
    saved = EffectLibrary().save(record)
    return {'success': True, 'result': 'Verified workflow saved: ' + saved['id'], 'case_id': saved['id']}
