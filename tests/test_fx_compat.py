from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


class FXCompatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fake_hou = MagicMock(name="hou")
        cls.fake_hou.frame.return_value = 24.0
        cls.fake_hou.fps.return_value = 24.0
        cls.hou_patch = patch.dict(sys.modules, {"hou": cls.fake_hou})
        cls.hou_patch.start()

        import houdini_agent.utils.mcp.fx_compat as compat

        cls.previous_hou = compat.hou
        cls.previous_loaded = compat._loaded
        compat.hou = cls.fake_hou
        compat._loaded = False
        cls.compat = compat

    @classmethod
    def tearDownClass(cls):
        cls.compat.hou = cls.previous_hou
        cls.compat._loaded = cls.previous_loaded
        cls.hou_patch.stop()

    def test_catalog_is_available_outside_houdini(self):
        previous = self.compat.hou
        try:
            self.compat.hou = None
            self.assertGreaterEqual(len(self.compat.list_commands()), 170)
            self.assertEqual(
                self.compat.command_name("fx_lops_get_stage_info"),
                "lops.get_stage_info",
            )
        finally:
            self.compat.hou = previous

    def test_embedded_command_catalog_and_schema(self):
        commands = self.compat.list_commands()

        self.assertGreaterEqual(len(commands), 170)
        self.assertIn("animation.get_frame", commands)
        self.assertIn("lops.get_stage_info", commands)
        self.assertIn("workflow.setup_pyro_sim", commands)
        self.assertNotIn("code.execute_python", commands)
        self.assertNotIn("nodes.create_node", commands)
        self.assertNotIn("viewport.capture_screenshot", commands)
        schema = self.compat.schema_for("animation.set_keyframe")
        self.assertEqual(schema["function"]["name"], "fx_animation_set_keyframe")
        self.assertGreaterEqual(
            set(schema["function"]["parameters"]["required"]),
            {"node_path", "parm_name", "frame", "value"},
        )

    def test_agent_registration_and_intent_routing(self):
        from houdini_agent.utils.tool_registry import ToolRegistry

        registry = ToolRegistry()
        count = self.compat.register_agent_tools(registry)

        self.assertGreaterEqual(count, 170)
        self.assertTrue(registry.has_tool("fx_animation_set_keyframe"))
        self.assertIn("animation", registry.classify_intent("给 tx 添加一个关键帧动画"))
        names = {
            item["function"]["name"]
            for item in registry.get_tools_for_intent({"animation"})
        }
        self.assertIn("fx_animation_set_keyframe", names)
        self.assertNotIn("fx_lops_get_stage_info", names)

    def test_frozen_app_packages_static_catalog(self):
        spec = (
            Path(__file__).resolve().parents[1] / "HoudiniAgent.spec"
        ).read_text(encoding="utf-8")
        self.assertIn(
            'datas_for("houdini_agent/utils/mcp/fx_commands.json", '
            '"houdini_agent/utils/mcp")',
            spec,
        )

    def test_execute_normalizes_dispatch_result(self):
        result = self.compat.execute("animation.get_frame")

        self.assertTrue(result["success"])
        payload = json.loads(result["result"])
        self.assertEqual(payload["frame"], 24.0)
        self.assertEqual(payload["fps"], 24.0)

    def test_bridge_executes_on_main_thread_without_redispatch(self):
        from houdini_agent.bridge import server as bridge

        self.compat._load_commands()
        from houdini_agent.utils.mcp.fxhoudinimcp_server import dispatcher

        main_dispatch = MagicMock()
        main_dispatch.executeInMainThreadWithResult.side_effect = AssertionError(
            "already on the main thread"
        )
        mcp = MagicMock()
        mcp.execute_tool.side_effect = lambda name, args: self.compat.execute(
            self.compat.command_name(name), args
        )
        with patch.object(dispatcher, "HAS_HDEFEREVAL", True), \
                patch.object(dispatcher, "hdefereval", main_dispatch, create=True), \
                patch.object(bridge, "_main_thread", lambda fn: fn()), \
                patch.object(bridge, "_mcp", return_value=mcp):
            result = bridge._execute_tool({"name": "fx_animation_get_frame"})

        self.assertTrue(result["success"], result)
        main_dispatch.executeInMainThreadWithResult.assert_not_called()

    def test_background_dispatch_still_marshals_to_houdini(self):
        self.compat._load_commands()
        from houdini_agent.utils.mcp.fxhoudinimcp_server import dispatcher

        main_dispatch = MagicMock()
        main_dispatch.executeInMainThreadWithResult.side_effect = lambda fn: fn()
        results = []
        with patch.object(dispatcher, "HAS_HDEFEREVAL", True), \
                patch.object(dispatcher, "hdefereval", main_dispatch, create=True):
            worker = threading.Thread(
                target=lambda: results.append(self.compat.execute("animation.get_frame"))
            )
            worker.start()
            worker.join(timeout=2)
            self.assertFalse(worker.is_alive())

        self.assertTrue(results[0]["success"], results)
        main_dispatch.executeInMainThreadWithResult.assert_called_once()

    def test_domain_failure_is_propagated_through_adapter_and_fastmcp(self):
        self.compat._load_commands()
        from houdini_agent.utils.mcp.fxhoudinimcp_server import dispatcher
        from houdini_agent.utils.mcp import server

        failure = {
            "success": False, "errors": ["Render failed: no license"],
            "message": "No output written", "wrote_files": False,
        }
        registered = {}

        class FakeMCP:
            def tool(self, *, name, description):
                def register(fn):
                    registered[name] = fn
                    return fn
                return register

        with patch.dict(dispatcher._handler_registry, {
                "rendering.start_render": lambda **kwargs: failure}), \
                patch.object(server, "mcp", FakeMCP()):
            result = self.compat.execute("rendering.start_render", {"node_path": "/out/test"})
            server._register_fx_compat_tools()
            mcp_result = registered["fx_execute"]("rendering.start_render", {"node_path": "/out/test"})

        self.assertFalse(result["success"])
        self.assertIn("no license", result["error"])
        self.assertEqual(result["details"], failure)
        self.assertEqual(mcp_result["status"], "error")
        self.assertIn("no license", mcp_result["message"])

    def test_session_requests_receive_relevant_fx_tools_in_every_mode(self):
        from houdini_agent.ui_qml.agent_session import AgentSession
        from houdini_agent.ui_qml.bridge_session import BridgeAgentSession
        from houdini_agent.utils.tool_registry import ToolRegistry

        registry = ToolRegistry()
        self.compat.register_agent_tools(registry)
        native = {"type": "function", "function": {"name": "read_selection"}}
        modes = [
            ("Agent", None, True), ("Ask", None, False),
            ("Plan", None, False), ("Plan", "plan_executing", True),
        ]
        cases = [(mode, tool_mode, allows_writes, think_tags)
                 for mode, tool_mode, allows_writes in modes
                 for think_tags in (True, False)]
        for session_type in (AgentSession, BridgeAgentSession):
            for mode, tool_mode, allows_writes, think_tags in cases:
                with self.subTest(session=session_type.__name__, mode=mode,
                                  phase=tool_mode, think_tags=think_tags):
                    session = session_type.__new__(session_type)
                    session.client = MagicMock()
                    session.client.agent_loop_auto.return_value = {"final_content": "OK"}
                    session.tools = [native]
                    session.history = []
                    session._sys_think = "thinking system"
                    session._sys_no_think = "plain system"
                    session._context_messages = MagicMock(return_value=[])
                    with patch("houdini_agent.utils.tool_registry.get_tool_registry", return_value=registry):
                        session.run(
                            "查看动画并设置关键帧", "offline", "offline", mode, {},
                            tools=[native], tool_mode=tool_mode, rag=False, memory=False,
                            think_tags=think_tags,
                        )
                    request = session.client.agent_loop_auto.call_args.kwargs
                    self.assertEqual(request["messages"][0]["content"],
                                     "thinking system" if think_tags else "plain system")
                    sent = request["tools_override"]
                    names = {tool["function"]["name"] for tool in sent}
                    self.assertIn("read_selection", names)
                    self.assertIn("fx_animation_get_frame", names)
                    self.assertEqual("fx_animation_set_keyframe" in names, allows_writes)
                    self.assertNotIn("fx_lops_get_stage_info", names)

    def test_request_filter_respects_disabled_tools_and_removes_stale_fx_schemas(self):
        from houdini_agent.utils.tool_registry import ToolRegistry

        registry = ToolRegistry()
        self.compat.register_agent_tools(registry)
        registry.set_enabled("fx_animation_get_frame", False)
        base = list(self.compat.available_tool_definitions())
        with patch("houdini_agent.utils.tool_registry.get_tool_registry", return_value=registry):
            selected = self.compat.tools_for_request(base, "动画关键帧", "ask")
        names = {item["function"]["name"] for item in selected}
        self.assertNotIn("fx_animation_get_frame", names)
        self.assertNotIn("fx_animation_set_keyframe", names)
        self.assertNotIn("fx_lops_get_stage_info", names)
        self.assertIn("fx_animation_get_keyframes", names)

    def test_embedded_handlers_coexist_with_preloaded_upstream_server(self):
        code = textwrap.dedent("""
            import sys, types
            from unittest.mock import MagicMock
            upstream = types.ModuleType('fxhoudinimcp_server')
            upstream.__path__ = []
            dispatcher = types.ModuleType('fxhoudinimcp_server.dispatcher')
            registry = {}
            dispatcher.register_handler = lambda name, fn: registry.update({name: fn})
            dispatcher.list_commands = lambda: sorted(registry)
            sys.modules['fxhoudinimcp_server'] = upstream
            sys.modules['fxhoudinimcp_server.dispatcher'] = dispatcher
            hou = MagicMock()
            hou.frame.return_value = 24.0
            hou.fps.return_value = 24.0
            sys.modules['hou'] = hou
            from houdini_agent.utils.mcp.fx_compat import execute
            result = execute('animation.get_frame')
            assert result['success'], result
            assert registry == {}, registry
            assert sys.modules['fxhoudinimcp_server'] is upstream
            assert sys.modules['fxhoudinimcp_server.dispatcher'] is dispatcher
            from houdini_agent.utils.mcp.fxhoudinimcp_server.dispatcher import list_commands
            assert len(list_commands()) >= 188
        """)
        result = subprocess.run(
            [sys.executable, "-B", "-c", code],
            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


@unittest.skipUnless(os.name == "nt", "PowerShell launcher is Windows-only")
class LauncherPythonSelectionTests(unittest.TestCase):
    def test_launcher_starts_only_agent_before_version_confirmation(self):
        script = Path(__file__).resolve().parents[1] / "start_houdini_agent.ps1"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / "Side Effects Software" / "Houdini 22.0.429" / "python313"
            runtime.mkdir(parents=True)
            (runtime / "python.exe").touch()
            (runtime / "pythonw.exe").touch()
            ps = """
                $ErrorActionPreference = 'Stop'
                $env:ProgramFiles = '%s'
                $global:agentLauncherCalls = @()
                function Start-Process {
                    param($FilePath, $ArgumentList, $WorkingDirectory, $WindowStyle)
                    $global:agentLauncherCalls += [pscustomobject]@{
                        path = $FilePath; args = @($ArgumentList); style = $WindowStyle
                    }
                }
                & '%s'
                ConvertTo-Json -Compress -InputObject @($global:agentLauncherCalls)
            """ % (str(root).replace("'", "''"), str(script).replace("'", "''"))
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                capture_output=True, text=True, timeout=15,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            launched = json.loads(result.stdout.strip().splitlines()[-1])
            self.assertEqual(len(launched), 1)
            self.assertEqual(Path(launched[0]["path"]), runtime / "pythonw.exe")
            self.assertEqual(launched[0]["args"], [str(script.parent / "launcher.py")])
            self.assertNotEqual(launched[0]["style"], "Hidden")

    def test_launcher_selects_newest_complete_interpreter(self):
        script = Path(__file__).resolve().parents[1] / "start_houdini_agent.ps1"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("python39", "python310", "python311", "python313"):
                install = root / name
                install.mkdir()
                if name != "python39":
                    (install / "python.exe").touch()
                if name in ("python310", "python311"):
                    (install / "pythonw.exe").touch()
            # Execute only the real selection expression, never the launcher.
            ps = """
                $ErrorActionPreference = 'Stop'
                $tokens = $null; $errors = $null
                $ast = [System.Management.Automation.Language.Parser]::ParseFile(
                    '%s', [ref]$tokens, [ref]$errors)
                if ($errors.Count) { throw $errors[0] }
                $assignment = $ast.Find({ param($node)
                    $node -is [System.Management.Automation.Language.AssignmentStatementAst] -and
                    $node.Left.Extent.Text -eq '$PythonHome'
                }, $true)
                $Hfs = '%s'
                Invoke-Expression $assignment.Extent.Text
                Write-Output $PythonHome.Name
            """ % (str(script).replace("'", "''"), str(root).replace("'", "''"))
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                capture_output=True, text=True, timeout=15,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(result.stdout.strip(), "python311")


if __name__ == "__main__":
    unittest.main()
