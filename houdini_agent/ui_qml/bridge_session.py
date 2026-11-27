# -*- coding: utf-8 -*-
"""AgentSession-compatible backend that executes Houdini tools through BridgeClient."""

import copy
import re

from houdini_agent.bridge.client import BridgeClient
from houdini_agent.ui_qml.agent_session import _make_system_prompt


class _BridgeMCP:
    def __init__(self, bridge):
        self._bridge = bridge

    def execute_tool(self, name, args):
        return self._bridge.execute_tool(name, args)


class BridgeAgentSession:
    def __init__(self, bridge=None):
        from houdini_agent.utils.ai_client import AIClient, HOUDINI_TOOLS

        self.client = AIClient()
        self.bridge = bridge or BridgeClient()
        self.mcp = _BridgeMCP(self.bridge)
        self.tools = list(HOUDINI_TOOLS)
        # Meshy 集成（网络工具在 app 侧执行，import/export 经 bridge 在 Houdini 侧执行）
        try:
            from houdini_agent import meshy
            self.tools = self.tools + list(meshy.MESHY_TOOLS)
        except Exception as e:
            print("[bridge_session] meshy tools unavailable:", e)
        # 连接诊断/修复工具（仅独立 app 有意义：让 agent 能排查甚至重连 Houdini）
        try:
            from houdini_agent.bridge.doctor import CONNECTION_TOOLS
            self.tools = self.tools + list(CONNECTION_TOOLS)
        except Exception as e:
            print("[bridge_session] connection tools unavailable:", e)
        self.history = []
        note = (
            "\n\n[Standalone Bridge Mode]\n"
            "You run inside a standalone desktop app connected to Houdini through a local bridge. "
            "Chat, planning, web/doc search and Meshy generation always work, even without Houdini. "
            "Only scene tools need the bridge. If a scene tool reports the Houdini connection is lost, "
            "do NOT give up: call check_houdini_connection to diagnose, then follow its advice with "
            "repair_houdini_connection (action='reconnect' for port changes, 'reinstall_package' when the "
            "integration package is missing/stale, 'launch_houdini' to start Houdini and wait for it). "
            "The integration package can also provide the Houdini Agent Python Panel and shelf entry. "
            "After the user restarts Houdini, verify the connection by calling "
            "repair_houdini_connection(action='reconnect', wait_seconds=30) yourself. "
            "If Houdini must be restarted manually, tell the user exactly what to do and continue helping.")
        self._sys_think = _make_system_prompt(True) + note
        self._sys_no_think = _make_system_prompt(False) + note

    def set_tool_executor(self, fn):
        self._tool_executor = fn
        self.client.set_tool_executor(fn)

    def stop(self):
        self.client.request_stop()

    def build_messages(self, with_thinking):
        sys = self._sys_think if with_thinking else self._sys_no_think
        messages = [{"role": "system", "content": sys}] + copy.deepcopy(self.history)
        facts = getattr(self, '_scene_facts', None)
        if facts:
            import json
            brief = {k: facts.get(k) for k in ('network_path', 'hip_path', 'version', 'frame', 'revision')}
            brief['nodes'] = [{k: n.get(k) for k in ('path', 'type', 'comment', 'geometry')} for n in facts.get('nodes', [])[:12]]
            messages.insert(1, {'role': 'system', 'content': '上次场景观察（可能过期，不是当前事实；换 HIP/会话、手动修改或写操作前重新 get_scene_facts）：'
                             + json.dumps(brief, ensure_ascii=False)[:2500]})
        return messages

    def run(self, user_text, model, provider, mode, callbacks, context_limit=128000,
            enable_thinking=True, supports_vision=False, tools=None, max_iter=None,
            think_tags=True,
            images=None, rag=True, memory=False, tool_mode=None, plan=None):
        self.client.reset_stop()
        incoming_images = images or []
        usable_images = incoming_images if supports_vision else []
        if usable_images:
            content = self._build_content(user_text, usable_images)
        elif incoming_images and not supports_vision:
            content = (user_text or "") + "\n\n[系统提示：当前模型不支持图片输入，用户附加的图片已忽略。]"
        else:
            content = user_text
        self.history.append({"role": "user", "content": content})
        # think_tags=False：模型有原生推理摘要（如 ChatGPT 订阅），不再要求正文里写 <think>
        messages = self.build_messages(enable_thinking and think_tags)
        extra = self._context_messages(user_text, rag, memory)
        if extra:
            messages[1:1] = extra
        if max_iter is None:
            max_iter = 15 if mode == "Ask" else 999
        tools_override = tools if tools is not None else self.tools
        from houdini_agent.utils.mcp.fx_compat import tools_for_request
        tools_override = tools_for_request(
            tools_override, user_text,
            mode=tool_mode or {"Ask": "ask", "Plan": "plan_planning"}.get(mode, "agent"),
        )
        # 非视觉模型默认禁用视口截图检查工具（依赖把图片回注给模型分析）
        if not memory:
            from houdini_agent.utils.memory_tools import MEMORY_TOOLS
            tools_override = [t for t in tools_override if t.get("function", {}).get("name") not in MEMORY_TOOLS]
        if not supports_vision and tools_override:
            tools_override = [
                t for t in tools_override
                if (t.get("function") or {}).get("name") != "capture_viewport"
            ]
        from houdini_agent.utils.task_runtime import TaskRuntime
        runtime = TaskRuntime(mode, tool_mode, plan)
        executor = getattr(self, '_tool_executor', self.client._tool_executor)
        def tracked(name, **kwargs):
            return runtime.execute(executor, name, kwargs)
        self.client.set_tool_executor(tracked)
        try:
            result = self.client.agent_loop_auto(
                messages=messages,
                model=model,
                provider=provider,
                max_iterations=min(max_iter, 80),
                max_tool_calls=200,
                max_tokens=None,
                enable_thinking=enable_thinking,
                supports_vision=bool(supports_vision),
                tools_override=tools_override,
                context_limit=context_limit,
                on_content=callbacks.get("on_content"),
                on_thinking=callbacks.get("on_thinking"),
                on_tool_call=callbacks.get("on_tool_call"),
                on_tool_result=callbacks.get("on_tool_result"),
                on_tool_args_delta=callbacks.get("on_tool_args_delta"),
                on_iteration_start=callbacks.get("on_iteration_start"),
                on_plan_incomplete=runtime.continuation,
            )
        finally:
            self.client.set_tool_executor(executor)
        note = runtime.finish(result)
        if runtime.scene_facts:
            self._scene_facts = runtime.scene_facts
        if note and callbacks.get('on_content'):
            callbacks['on_content'](note)

        if (not result.get("ok") and not result.get("new_messages")
                and not result.get("final_content") and not result.get("content")):
            self.history.pop()
        else:
            self._absorb(result)
        return result

    def _absorb(self, result):
        if not isinstance(result, dict):
            return
        for i, nm in enumerate(result.get("new_messages", []) or []):
            if i == len(result.get("new_messages", []) or []) - 1 and nm.get("role") == "assistant" and not nm.get("tool_calls"):
                continue
            clean = dict(nm)
            clean.pop("reasoning_content", None)
            self.history.append(clean)
        final = result.get("final_content") or result.get("content") or ""
        clean = re.sub(r"<think>[\s\S]*?</think>", "", final).strip()
        if clean or not self.history or self.history[-1].get("role") != "assistant":
            self.history.append({"role": "assistant", "content": clean or "(no content)"})

    def reset(self):
        self.history = []
        self._scene_facts = None

    @staticmethod
    def _build_content(text, images):
        if not images:
            return text
        parts = [{"type": "text", "text": text}]
        for b64, mt in images:
            parts.append({"type": "image_url", "image_url": {"url": "data:%s;base64,%s" % (mt, b64)}})
        return parts

    @staticmethod
    def _context_messages(query, rag, memory):
        from houdini_agent.ui_qml.agent_session import AgentSession
        return AgentSession._context_messages(query, rag, memory)
