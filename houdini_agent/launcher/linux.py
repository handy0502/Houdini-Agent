"""Standalone Linux entry point; importing hou is deliberately avoided."""
import argparse
import importlib.util
import json
import os
import sys

from .houdini_discovery import find_houdini_installs, install_all_packages, _bridge_python_root
from pathlib import Path


def clean_environment(env):
    """A Houdini shell must not load Houdini's Python/Qt into the external UI."""
    result = dict(env)
    for key in ('PYTHONHOME', 'PYTHONPATH', 'QT_PLUGIN_PATH', 'QT_QPA_PLATFORM_PLUGIN_PATH',
                'QML_IMPORT_PATH', 'QML2_IMPORT_PATH', 'QT_QUICK_CONTROLS_STYLE'):
        result.pop(key, None)
    hfs = env.get('HFS', '').rstrip('/')
    if hfs and result.get('LD_LIBRARY_PATH'):
        entries = [path for path in result['LD_LIBRARY_PATH'].split(':')
                   if path and not (path == hfs or path.startswith(hfs + '/'))]
        if entries:
            result['LD_LIBRARY_PATH'] = ':'.join(entries)
        else:
            result.pop('LD_LIBRARY_PATH', None)
    result.setdefault('QT_QPA_PLATFORM', 'xcb')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description='Houdini Agent standalone Linux launcher')
    parser.add_argument('--houdini-root', action='append', default=[], help='Houdini install or parent directory (repeatable)')
    parser.add_argument('--check', action='store_true', help='Print runtime/install diagnostics without opening a window')
    parser.add_argument('--install-bridge', action='store_true', help='Install Bridge packages without opening a window')
    args = parser.parse_args(argv)
    if not sys.platform.startswith('linux'):
        parser.error('This entry point is for Linux. Use launcher.py on Windows.')
    if sys.version_info < (3, 11):
        parser.error('Python 3.11 or newer is required for the standalone Linux UI.')
    if args.houdini_root:
        roots = args.houdini_root + [os.environ.get('HAGENT_HOUDINI_ROOTS', '')]
        os.environ['HAGENT_HOUDINI_ROOTS'] = ':'.join(root for root in roots if root)
    if args.check:
        print(json.dumps({
            'python': sys.version.split()[0],
            'dependencies': {name: importlib.util.find_spec(name) is not None for name in ('PySide6', 'numpy', 'requests')},
            'houdini_installs': find_houdini_installs(),
            'display': bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')),
        }, ensure_ascii=False, indent=2))
        return 0
    if args.install_bridge:
        written = install_all_packages(str(_bridge_python_root(Path(__file__).resolve().parents[2])))
        print(json.dumps(written, ensure_ascii=False, indent=2))
        return 0 if any(written.values()) else 1
    env = clean_environment(os.environ)
    if env != dict(os.environ):
        # Qt's dynamic linker environment must be clean at process startup.
        os.chdir(Path(__file__).resolve().parents[2])
        os.execve(sys.executable, [sys.executable, '-m', 'houdini_agent.launcher.linux'] +
                  (sys.argv[1:] if argv is None else list(argv)), env)
    missing = [name for name in ('PySide6', 'numpy', 'requests') if importlib.util.find_spec(name) is None]
    if missing:
        parser.error('Missing dependencies: %s. Run: bash start_houdini_agent.sh --setup' % ', '.join(missing))
    if not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
        parser.error('No graphical desktop detected. Start from an X11 desktop terminal or use --check.')
    from houdini_agent.ui_qml.external_app import main as start
    return start()


if __name__ == '__main__':
    raise SystemExit(main())
