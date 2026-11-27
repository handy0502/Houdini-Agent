"""Linux discovery and launch tests; no real Houdini process or account needed."""
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from houdini_agent.launcher import houdini_discovery as hd
from houdini_agent.launcher import linux


@pytest.fixture
def linux_env(tmp_path, monkeypatch):
    home, installs = tmp_path / 'home', tmp_path / 'opt'
    home.mkdir(); installs.mkdir()
    monkeypatch.setattr(hd, '_IS_WINDOWS', False)
    monkeypatch.setattr(hd, '_IS_LINUX', True)
    monkeypatch.setattr(Path, 'home', lambda: home)
    monkeypatch.setattr(hd, '_linux_install_roots', lambda: [installs])
    monkeypatch.setattr(hd.shutil, 'which', lambda name: None)
    for key in ('HFS', 'HAGENT_HOUDINI_ROOTS', 'HOUDINI_USER_PREF_DIR'):
        monkeypatch.delenv(key, raising=False)
    return home, installs


def fake_install(root, name='hfs21.0.631'):
    directory = root / name
    (directory / 'bin').mkdir(parents=True)
    binary = directory / 'bin/houdini'
    binary.write_text('#!/bin/bash\nexit 0\n')
    binary.chmod(0o755)
    (directory / 'houdini_setup').write_text('export HAGENT_FAKE_SETUP=ready\n')
    return directory


def test_discovers_linux_versions_and_deduplicates_hfs(linux_env, monkeypatch):
    home, root = linux_env
    newest = fake_install(root, 'hfs22.0.429')
    fake_install(root)
    fake_install(root, 'hfs19.0.1')
    monkeypatch.setenv('HFS', str(newest))
    result = hd.find_houdini_installs()
    assert [item['version'] for item in result] == ['22.0.429', '21.0.631']
    assert result[0]['exe'] == str(newest / 'bin/houdini')


def test_custom_root_and_nonversioned_hfs_header(linux_env, monkeypatch, tmp_path):
    custom = tmp_path / 'studio'
    install = fake_install(custom, 'production')
    header = install / 'toolkit/include/SYS/SYS_Version.h'
    header.parent.mkdir(parents=True)
    header.write_text('#define SYS_VERSION_MAJOR_INT 21\n#define SYS_VERSION_MINOR_INT 0\n#define SYS_VERSION_BUILD_INT 631\n')
    monkeypatch.setenv('HAGENT_HOUDINI_ROOTS', os.path.relpath(custom))
    assert hd.find_houdini_installs()[0]['version'] == '21.0.631'


@pytest.mark.skipif(os.name == 'nt', reason='POSIX symlinks and executable bits')
def test_path_symlink_and_nonexecutable_installs(linux_env, monkeypatch):
    home, root = linux_env
    install = fake_install(root)
    link = root / 'current'
    link.symlink_to(install, target_is_directory=True)
    monkeypatch.setenv('HFS', str(link))
    assert len(hd.find_houdini_installs()) == 1
    (install / 'bin/houdini').chmod(0o644)
    assert hd.find_houdini_installs() == []


def test_linux_preferences_and_bridge_package(linux_env):
    home, _ = linux_env
    (home / 'houdini21.0').mkdir()
    (home / 'houdini19.0').mkdir()
    assert hd.known_pref_versions() == {'21.0'}
    assert hd.user_pref_dirs('21.0') == [home / 'houdini21.0']
    written = hd.install_all_packages(str(home / 'agent'), installs=[])
    data = json.loads(Path(written['21.0'][0]).read_text())
    env = {key: value for entry in data['env'] for key, value in entry.items()}
    assert env['HOUDINI_PATH'].endswith('houdini_package:&')
    assert env['PYTHONPATH'].endswith('agent:&')


def test_linux_pref_override_is_first(linux_env, monkeypatch):
    home, _ = linux_env
    monkeypatch.setenv('HOUDINI_USER_PREF_DIR', '$HOME/studio/houdini__HVER__')
    monkeypatch.setenv('HOME', str(home))
    assert hd.user_pref_dirs('22.0') == [home / 'studio/houdini22.0', home / 'houdini22.0']


@pytest.mark.parametrize('name,running', [('houdini-bin', True), ('houdinifx', True), ('hython', False), ('houdini_agent', False)])
def test_linux_process_detection(linux_env, monkeypatch, tmp_path, name, running):
    proc = tmp_path / 'proc'
    (proc / '123').mkdir(parents=True)
    (proc / '123/comm').write_text(name + '\n')
    (proc / '124').mkdir()  # Process disappeared or is not readable.
    monkeypatch.setattr(hd, '_PROC_ROOT', proc)
    assert hd.is_houdini_running() is running


def test_houdini_launch_quotes_paths_and_cleans_qt(linux_env, monkeypatch):
    _, root = linux_env
    install = fake_install(root, 'Houdini 21.0.631 $studio')
    monkeypatch.setenv('PYTHONPATH', '/agent/venv')
    monkeypatch.setenv('QT_PLUGIN_PATH', '/agent/qt/plugins')
    monkeypatch.setenv('LD_LIBRARY_PATH', '/agent/qt/lib')
    monkeypatch.setenv('LD_LIBRARY_PATH_ORIG', '/studio/lib')
    popen = Mock()
    monkeypatch.setattr(hd.subprocess, 'Popen', popen)
    target = {'path': str(install), 'exe': str(install / 'bin/houdini'), 'major_minor': '21.0'}
    hd.launch_houdini(str(root / 'Agent'), target)
    args, kwargs = popen.call_args
    assert args[0][-2:] == [target['path'], target['exe']]
    assert 'set --;' in args[0][2] and 'exec "$hagent_executable"' in args[0][2]
    assert kwargs['env']['LD_LIBRARY_PATH'] == '/studio/lib'
    assert 'PYTHONPATH' not in kwargs['env'] and 'QT_PLUGIN_PATH' not in kwargs['env']
    assert kwargs['start_new_session']


@pytest.mark.skipif(not sys.platform.startswith('linux'), reason='Executes a real POSIX wrapper')
def test_real_linux_houdini_setup_wrapper(linux_env, monkeypatch, tmp_path):
    _, root = linux_env
    install = fake_install(root, 'Houdini 21.0.631 $studio')
    (install / 'houdini_setup').write_text('export HAGENT_FAKE_SETUP=ready\nset -- changed\n')
    binary = install / 'bin/houdini'
    binary.write_text('#!/bin/bash\nprintf "%s|%s|%s" "$HAGENT_FAKE_SETUP" "${PYTHONPATH-unset}" "${QT_PLUGIN_PATH-unset}" > "$HAGENT_TEST_OUTPUT"\n')
    output = tmp_path / 'launch-result'
    monkeypatch.setenv('HAGENT_TEST_OUTPUT', str(output))
    monkeypatch.setenv('PYTHONPATH', '/agent/venv')
    monkeypatch.setenv('QT_PLUGIN_PATH', '/agent/plugins')
    process = hd.launch_houdini(str(tmp_path / 'agent'),
        dict(path=str(install), exe=str(binary), major_minor='21.0'))
    assert process.wait(timeout=5) == 0
    assert output.read_text() == 'ready|unset|unset'


def test_external_environment_cleanup_is_idempotent():
    source = dict(HFS='/opt/hfs21.0', PYTHONPATH='houdini', QT_PLUGIN_PATH='houdini',
        LD_LIBRARY_PATH='/opt/hfs21.0/dsolib:/studio/lib:/opt/hfs21.0-other/lib', DISPLAY=':0')
    cleaned = linux.clean_environment(source)
    assert 'PYTHONPATH' not in cleaned and 'QT_PLUGIN_PATH' not in cleaned
    assert cleaned['LD_LIBRARY_PATH'] == '/studio/lib:/opt/hfs21.0-other/lib'
    assert cleaned['QT_QPA_PLATFORM'] == 'xcb' and cleaned['DISPLAY'] == ':0'
    assert linux.clean_environment(cleaned) == cleaned
    assert 'PYTHONPATH' in source


def test_check_cli_never_imports_hou_or_opens_ui(linux_env, monkeypatch, capsys):
    _, root = linux_env
    fake_install(root)
    monkeypatch.setattr(linux, 'sys', SimpleNamespace(platform='linux', version_info=(3, 11), version='3.11 test'))
    assert linux.main(['--check']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['houdini_installs'][0]['version'] == '21.0.631'
    assert set(result['dependencies']) == {'PySide6', 'numpy', 'requests'}
