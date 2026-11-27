"""Exercise the spec without PyInstaller/Qt collection or writing a real build."""
from pathlib import Path
from types import ModuleType, SimpleNamespace
import runpy
import sys

import pytest


@pytest.fixture
def evaluated_spec(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    spec = root / 'installer/HoudiniAgent.spec'
    hooks = ModuleType('PyInstaller.utils.hooks')
    collected = []
    def collect(package):
        collected.append(package)
        return [package]
    hooks.collect_submodules = collect
    monkeypatch.setitem(sys.modules, 'PyInstaller', ModuleType('PyInstaller'))
    monkeypatch.setitem(sys.modules, 'PyInstaller.utils', ModuleType('PyInstaller.utils'))
    monkeypatch.setitem(sys.modules, 'PyInstaller.utils.hooks', hooks)
    calls = {}
    def analysis(scripts, **kwargs):
        # Match real Analysis: relative script paths resolve beside the spec,
        # independently of pathex and the shell's current working directory.
        resolved = [(spec.parent / script).resolve() for script in scripts]
        assert all(script.is_file() for script in resolved), resolved
        calls.update(scripts=resolved, **kwargs)
        return SimpleNamespace(binaries=[], datas=[], pure=[], zipped_data=[], scripts=[], zipfiles=[])
    namespace = runpy.run_path(str(spec), init_globals={
        'SPECPATH': str(spec.parent), 'Analysis': analysis,
        'PYZ': lambda *a, **kw: None, 'EXE': lambda *a, **kw: None,
        'COLLECT': lambda *a, **kw: None})
    return root, calls, collected, namespace


def test_entrypoint_and_bridge_resources_survive_spec_relocation(evaluated_spec):
    root, calls, _, _ = evaluated_spec
    assert calls['scripts'] == [root / 'launcher.py']
    resources = {(Path(src).relative_to(root).as_posix(), Path(dest).as_posix())
                 for src, dest in calls['datas']}
    for source, destination in (
        ('VERSION', '.'), ('VERSION', 'bridge_payload'),
        ('houdini_agent/bridge/server.py', 'bridge_payload/houdini_agent/bridge'),
        ('shared/common_utils.py', 'bridge_payload/shared'),
        ('houdini_agent/ui_qml/qml/Main.qml', 'houdini_agent/ui_qml/qml'),
        ('houdini_agent/houdini_package/python_panels/HoudiniAgent.pypanel',
         'houdini_agent/houdini_package/python_panels'),
    ):
        assert (source, destination) in resources


def test_qt_is_targeted_and_personal_outputs_are_not_bundled(evaluated_spec):
    root, calls, collected, _ = evaluated_spec
    assert 'PySide6' not in collected
    assert {'PySide6.QtQml', 'PySide6.QtQuickWidgets', 'PySide6.QtSvg'} <= set(calls['hiddenimports'])
    for source, _ in calls['datas']:
        path = Path(source).relative_to(root)
        assert 'trainData' not in path.parts and '__pycache__' not in path.parts
        assert path.suffix.lower() not in ('.pyc', '.pyo')
        assert path.as_posix() not in ('config/houdini_ai.ini', 'config/templates.json')


def test_directory_collection_omits_caches_but_keeps_resources(evaluated_spec, tmp_path):
    _, _, _, namespace = evaluated_spec
    source = tmp_path / 'payload'
    (source / '__pycache__').mkdir(parents=True)
    (source / '__pycache__/main.cpython-313.pyc').write_bytes(b'cache')
    (source / 'main.py').write_text('print("ready")')
    (source / 'data.json').write_text('{}')
    (source / 'legacy.pyc').write_bytes(b'cache')
    namespace['datas_for'].__globals__['ROOT'] = tmp_path
    files = namespace['datas_for']('payload', 'bridge_payload')
    assert {Path(src).name for src, _ in files} == {'main.py', 'data.json'}
