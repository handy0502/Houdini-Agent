"""Real HIP fixtures and independent acceptance checks; run with Houdini's hython.

prepare writes unfinished tasks, evaluate checks an Agent-edited HIP, smoke checks
the tool pipeline itself. No LLM is called and smoke is not an Agent success rate.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def prepare(directory, hou):
    directory.mkdir(parents=True, exist_ok=True)
    tasks = []
    for name in ('box_scale', 'detail_points', 'animated_bounds', 'scatter_scale'):
        hip = directory / (name + '.hip')
        if hip.exists() or (directory / (name + '.json')).exists():
            raise ValueError('Refusing to overwrite benchmark: ' + str(hip))
    for name in ('box_scale', 'detail_points', 'animated_bounds', 'scatter_scale'):
        hou.hipFile.clear(suppress_save_prompt=True)
        root = hou.node('/obj').createNode('geo', 'effect')
        base = root.createNode('box', 'base')
        out = root.createNode('null', 'OUT')
        out.setInput(0, base)
        out.setDisplayFlag(True)
        out.setRenderFlag(True)
        path = out.path()
        if name == 'box_scale':
            prompt = '把这个盒子的尺寸调整为 2×3×4，保持 OUT 为输出'
            criteria = [{'kind': 'bounds_size', 'node_path': path, 'axis': a, 'min': v-.001, 'max': v+.001}
                        for a, v in enumerate((2, 3, 4))]
        elif name == 'detail_points':
            prompt = '用 Detail Wrangle 从空输入创建三个点，并添加点属性 pscale=0.2，接到 OUT'
            base.destroy()
            criteria = [{'kind': 'point_count', 'node_path': path, 'min': 3, 'max': 3},
                        {'kind': 'attribute', 'node_path': path, 'owner': 'point', 'name': 'pscale'}]
        elif name == 'animated_bounds':
            prompt = '让盒子 X 尺寸从第 1 帧的 1 线性增至第 25 帧的 3，Y/Z 不变，保留 OUT'
            criteria = [{'kind': 'bounds_size', 'node_path': path, 'axis': 0, 'min': v-.001, 'max': v+.001, 'frames': [f]}
                        for f, v in ((1, 1), (13, 2), (25, 3))]
        else:
            prompt = '在盒子表面散布恰好 32 个点，给点添加 pscale 属性，接到 OUT'
            criteria = [{'kind': 'point_count', 'node_path': path, 'min': 32, 'max': 32},
                        {'kind': 'attribute', 'node_path': path, 'owner': 'point', 'name': 'pscale'},
                        {'kind': 'finite_positions', 'node_path': path}]
        root.layoutChildren()
        hou.hipFile.save((directory / (name + '.hip')).as_posix())
        task = {'name': name, 'prompt': prompt, 'network_path': root.path(), 'criteria': criteria,
                'version': hou.applicationVersionString(), 'scope': 'Declared SOP output and sample frames only'}
        _write(directory / (name + '.json'), task)
        tasks.append(task)
    _write(directory / 'manifest.json', tasks)
    return {'prepared': len(tasks), 'directory': str(directory)}


def evaluate(hip, manifest, hou):
    from houdini_agent.utils.mcp import HoudiniMCP
    from houdini_agent.utils.mcp.verification import verify
    hou.hipFile.load(hip.as_posix(), suppress_save_prompt=True, ignore_load_warnings=True)
    task = json.loads(manifest.read_text(encoding='utf-8'))
    return verify(HoudiniMCP(), task, hou)


def smoke(hou):
    import tempfile
    from houdini_agent.utils.mcp import HoudiniMCP
    from houdini_agent.utils.mcp.effect_controls import create_controls, create_variants, package_effect
    from houdini_agent.utils.mcp.effects import scene_facts
    from houdini_agent.utils.mcp.verification import verify
    hou.hipFile.clear(suppress_save_prompt=True)
    root = hou.node('/obj').createNode('geo', 'effect')
    box = root.createNode('box', 'base')
    out = root.createNode('null', 'OUT')
    out.setInput(0, box)
    out.setDisplayFlag(True)
    out.setRenderFlag(True)
    mcp = HoudiniMCP()
    controls = create_controls({'network_path': root.path(), 'controls': [
        {'name': 'width', 'label': 'Width', 'min': .1, 'max': 10, 'value': 2, 'targets': ['base/sizex']}]}, hou)
    assert abs(out.geometry().boundingBox().sizevec()[0] - 2) < .001
    criteria = [{'kind': 'point_count', 'node_path': out.path(), 'min': 8, 'max': 8},
                {'kind': 'finite_positions', 'node_path': out.path()}]
    variants = create_variants(mcp, {'network_path': root.path(), 'variants': [
        {'name': 'small', 'parameters': {'width': 1}}, {'name': 'large', 'parameters': {'width': 4}}],
        'criteria': criteria}, hou)
    assert all(v['validation']['status'] == 'passed' for v in variants['variants'])
    assert [hou.node(v['node_path'] + '/OUT').geometry().boundingBox().sizevec()[0]
            for v in variants['variants']] == [1, 4]
    assert root.isDisplayFlagSet() and out.isDisplayFlagSet()
    assert box.parm('sizex').eval() == 2
    # Protect existing expressions and all other parameters when one binding is invalid.
    try:
        create_controls({'network_path': root.path(), 'controls': [
            {'name': 'bad', 'min': 0, 'max': 3, 'value': 1, 'targets': ['base/sizex']}]}, hou)
        raise AssertionError('Existing expression should have been rejected')
    except ValueError:
        assert root.parm('bad') is None and box.parm('sizex').eval() == 2
    with tempfile.TemporaryDirectory(prefix='hagent-hda-') as folder:
        asset_path = str(Path(folder) / 'test.hda')
        asset = package_effect(mcp, {'network_path': root.path(), 'hda_file': asset_path,
                               'type_name': 'hagenttest::box', 'criteria': criteria}, hou)
        assert asset['success'] and Path(asset_path).exists() and root.type().name() == 'geo'
        assert asset['type_name'] == 'hagenttest::box::1.0'
        try:
            package_effect(mcp, {'network_path': root.path(), 'hda_file': str(Path(folder) / 'duplicate.hda'),
                            'type_name': 'hagenttest::box', 'criteria': criteria}, hou)
            raise AssertionError('An installed asset type must not be replaced')
        except ValueError:
            assert not (Path(folder) / 'duplicate.hda').exists()
        assert abs(hou.node(asset['node_path'] + '/OUT').geometry().boundingBox().sizevec()[0] - 2) < .001
        hou.node(asset['node_path']).destroy()
        hou.hda.uninstallFile(asset_path)
    assert scene_facts(mcp, {'network_path': root.path()}, hou)['scene_facts']['nodes']
    # Check detection of failures and frame restoration, not just the happy path.
    original_frame = hou.frame()
    bad = verify(mcp, {'network_path': root.path(), 'criteria': [
        {'kind': 'point_count', 'node_path': out.path(), 'min': 100, 'frames': [1, 5]}]}, hou)
    assert bad['validation']['status'] == 'failed' and hou.frame() == original_frame
    return {'success': True, 'version': hou.applicationVersionString(), 'controls': controls['success'], 'hda_export': True,
            'variants': variants['variants'], 'failure_detection': True,
            'scope': 'HOM integration smoke; not an LLM benchmark or simulation-quality proof'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'evaluate', 'smoke'])
    parser.add_argument('--directory', type=Path, default=Path('cache/effect-benchmarks'))
    parser.add_argument('--hip', type=Path)
    parser.add_argument('--task', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    import hou
    if args.action == 'prepare':
        report = prepare(args.directory.resolve(), hou)
    elif args.action == 'evaluate':
        if not args.hip or not args.task:
            parser.error('evaluate requires --hip and --task')
        report = evaluate(args.hip.resolve(), args.task.resolve(), hou)
    else:
        report = smoke(hou)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        _write(args.report, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report.get('validation', {}).get('status') in ('failed', 'unverified') else 0


if __name__ == '__main__':
    raise SystemExit(main())
