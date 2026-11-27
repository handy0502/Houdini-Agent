"""Small, bounded effect controls and variants. All hou calls run on the main thread."""
import json
import math
import re


def _network(hou, path):
    node = hou.node(path)
    if node is None or not node.isNetwork() or not path.startswith('/obj/'):
        raise ValueError('Choose an editable object/SOP network below /obj')
    if node.isInsideLockedHDA():
        raise ValueError('Cannot edit a locked asset')
    return node


def _target(root, relative):
    if not isinstance(relative, str) or not re.fullmatch(r'[A-Za-z0-9_/]+', relative):
        raise ValueError('Use a relative parameter path inside the effect network')
    parm = root.parm(relative)
    if parm is None or parm.keyframes() or parm.isLocked():
        raise ValueError('Target must be an existing, unlocked numeric parameter without animation/references: ' + relative)
    value = parm.eval()
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('Target must be a finite numeric scalar: ' + relative)
    return parm


def create_controls(args, hou):
    root = _network(hou, args.get('network_path', ''))
    specs = args.get('controls') or []
    if not isinstance(specs, list) or not 1 <= len(specs) <= 12:
        raise ValueError('Supply 1–12 controls')
    group = root.parmTemplateGroup()
    original_group = root.parmTemplateGroup()
    prepared, targets, names = [], set(), set()
    for spec in specs:
        name = spec.get('name', '')
        if not re.fullmatch(r'[a-z][a-z0-9_]{0,39}', name) or name in names or root.parmTuple(name) is not None or group.find(name):
            raise ValueError('Control needs a new, unique lower-case parameter name')
        names.add(name)
        minimum, maximum, value = (float(spec[k]) for k in ('min', 'max', 'value'))
        if not all(math.isfinite(v) for v in (minimum, maximum, value)) or not minimum <= value <= maximum or minimum == maximum:
            raise ValueError('Control requires finite min < max and min <= value <= max')
        bindings = spec.get('targets') or []
        if not isinstance(bindings, list) or not 1 <= len(bindings) <= 12:
            raise ValueError('Supply 1–12 parameter targets per control')
        bound = []
        for relative in bindings:
            parm = _target(root, relative)
            if relative in targets:
                raise ValueError('A target can only be driven by one control')
            targets.add(relative)
            if parm.parmTemplate().type() != hou.parmTemplateType.Float:
                raise ValueError('Continuous controls require float targets; use variants for integer/menu choices')
            bound.append((parm, parm.eval()))
        template = hou.FloatParmTemplate(name, spec.get('label') or name, 1, default_value=(value,),
                    min=minimum, max=maximum, min_is_strict=True, max_is_strict=True,
                    help=spec.get('description', ''))
        group.append(template)
        prepared.append((name, value, bound))
    previous_metadata = root.userData('hagent_controls')
    touched = []
    try:
        with hou.undos.group('Agent effect controls'):
            root.setParmTemplateGroup(group)
            for name, value, bound in prepared:
                root.parm(name).set(value)
                for parm, previous in bound:
                    touched.append((parm, previous))
                    reference = parm.node().relativePathTo(root) + '/' + name
                    parm.setExpression('ch("%s")' % reference, language=hou.exprLanguage.Hscript)
            root.setUserData('hagent_controls', json.dumps(specs, ensure_ascii=False))
    except Exception:
        for parm, previous in reversed(touched):
            parm.deleteAllKeyframes()
            parm.set(previous)
        root.setParmTemplateGroup(original_group)
        if previous_metadata is None:
            root.destroyUserData('hagent_controls')
        else:
            root.setUserData('hagent_controls', previous_metadata)
        raise
    return {'success': True, 'controls': specs, 'node_path': root.path(),
            'result': 'Effect controls created on ' + root.path() + '; verify output before accepting.'}


def create_variants(mcp, args, hou):
    from .verification import verify
    source = _network(hou, args.get('network_path', ''))
    specs = args.get('variants') or []
    criteria = args.get('criteria') or []
    if not isinstance(specs, list) or not 1 <= len(specs) <= 4 or not criteria:
        raise ValueError('Supply 1–4 variants and measurable criteria')
    # Validate every requested edit before copying anything. Reject absolute references
    # and animated parameters so experiments cannot affect the original through ch().
    for spec in specs:
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,39}', spec.get('name', '')):
            raise ValueError('Variant needs an ASCII node name')
        values = spec.get('parameters') or {}
        if not isinstance(values, dict) or not 1 <= len(values) <= 20:
            raise ValueError('Supply 1–20 numeric parameter values per variant')
        for relative, value in values.items():
            _target(source, relative)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError('Variant values must be finite numbers')
    original_selection = hou.selectedNodes()
    display = source.isDisplayFlagSet() if hasattr(source, 'isDisplayFlagSet') else None
    render = source.isRenderFlagSet() if hasattr(source, 'isRenderFlagSet') else None
    created, results = [], []
    try:
        with hou.undos.group('Agent effect variants'):
            for spec in specs:
                if getattr(mcp, '_stop_event', None) is not None and mcp._stop_event.is_set():
                    raise RuntimeError('Variant generation stopped')
                clone = hou.copyNodesTo([source], source.parent())[0]
                created.append(clone)
                clone.setName(spec['name'], unique_name=True)
                for relative, value in spec['parameters'].items():
                    clone.parm(relative).set(value, follow_parm_reference=False)
                if display is not None:
                    clone.setDisplayFlag(False)
                if render is not None:
                    clone.setRenderFlag(False)
                mapped = []
                for rule in criteria:
                    path = rule.get('node_path', '')
                    if not (path == source.path() or path.startswith(source.path() + '/')):
                        raise ValueError('Variant criteria must inspect nodes inside the source network')
                    item = dict(rule, node_path=clone.path() + path[len(source.path()):])
                    if item.get('source_path', '').startswith(source.path() + '/'):
                        item['source_path'] = clone.path() + item['source_path'][len(source.path()):]
                    mapped.append(item)
                checked = verify(mcp, {'network_path': clone.path(), 'criteria': mapped}, hou)
                results.append({'node_path': clone.path(), 'parameters': spec['parameters'],
                                'validation': checked.get('validation'), 'error': checked.get('error')})
                clone.moveToGoodPosition()
    except Exception:
        for node in reversed(created):
            node.destroy()
        raise
    finally:
        if display is not None:
            source.setDisplayFlag(display)
        if render is not None:
            source.setRenderFlag(render)
        for node in hou.selectedNodes():
            node.setSelected(False)
        for node in original_selection:
            node.setSelected(True)
    return {'success': True, 'variants': results, 'original': source.path(),
            'result': json.dumps(results, ensure_ascii=False)}


def package_effect(mcp, args, hou):
    """Export a freshly verified copy, keeping the source network editable."""
    from pathlib import Path
    from .verification import verify
    source = _network(hou, args.get('network_path', ''))
    path = Path(args.get('hda_file', ''))
    type_name, version = args.get('type_name', ''), args.get('version', '1.0')
    if not path.is_absolute() or path.suffix.lower() != '.hda' or path.exists() or not path.parent.is_dir():
        raise ValueError('Choose a new absolute .hda path in an existing directory; files are never overwritten')
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*::[A-Za-z][A-Za-z0-9_]*', type_name) or not re.fullmatch(r'\d+\.\d+(?:\.\d+)?', version):
        raise ValueError('Use namespace::effect_name and a numeric version, e.g. 1.0')
    full_type = type_name + '::' + version
    if full_type in source.type().category().nodeTypes():
        raise ValueError('This asset type/version is already installed; choose a new name or version')
    if not args.get('criteria') or not source.canCreateDigitalAsset():
        raise ValueError('Supply measurable criteria and an asset-compatible network')
    if any(not (rule.get('node_path', '') == source.path()
                or rule.get('node_path', '').startswith(source.path() + '/')) for rule in args['criteria']):
        raise ValueError('Asset criteria must inspect nodes inside the source network')
    checked = verify(mcp, {'network_path': source.path(), 'criteria': args['criteria']}, hou)
    if not checked.get('success') or checked['validation']['status'] != 'passed':
        return {'success': False, 'error': 'Effect failed verification; nothing exported', 'validation': checked.get('validation')}
    selection = hou.selectedNodes()
    displayed = source.isDisplayFlagSet() if hasattr(source, 'isDisplayFlagSet') else None
    rendered = source.isRenderFlagSet() if hasattr(source, 'isRenderFlagSet') else None
    clone = None
    try:
        with hou.undos.group('Agent package effect'):
            clone = hou.copyNodesTo([source], source.parent())[0]
            clone.setName(source.name() + '_asset', unique_name=True)
            if displayed is not None:
                clone.setDisplayFlag(False)
            if rendered is not None:
                clone.setRenderFlag(False)
            clone = clone.createDigitalAsset(name=full_type, hda_file_name=path.as_posix(),
                        description=args.get('label') or source.name(), version=version)
            clone.moveToGoodPosition()
    except Exception:
        if clone is not None:
            clone.destroy()
        raise
    finally:
        if displayed is not None:
            source.setDisplayFlag(displayed)
        if rendered is not None:
            source.setRenderFlag(rendered)
        for node in hou.selectedNodes():
            node.setSelected(False)
        for node in selection:
            node.setSelected(True)
    return {'success': True, 'hda_file': str(path), 'type_name': full_type, 'node_path': clone.path(), 'source_path': source.path(),
            'validation': checked['validation'], 'result': 'Created asset from a copy; source preserved: ' + str(path)}
