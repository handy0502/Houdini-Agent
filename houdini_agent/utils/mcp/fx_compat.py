# -*- coding: utf-8 -*-
"""Adapter for the embedded FXHoudini-MCP command set.

Houdini Agent owns tool selection, execution and result formatting. The
embedded project contributes commands without replacing Agent-native tools.
"""
from __future__ import annotations

import copy
import json
import re
import threading
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

try:
    import hou  # type: ignore
except Exception:
    hou = None  # type: ignore


_load_lock = threading.RLock()
_loaded = False
_catalog_cache: Optional[Dict[str, dict]] = None

# Existing Agent tools retain control of security checks, undo snapshots,
# pagination and UI-specific result handling. These upstream equivalents are
# deliberately not exposed under a second name.
_AGENT_OWNED_COMMANDS = frozenset({
    "code.execute_python",
    "context.get_node_errors_detailed",
    "context.get_selection",
    "geometry.get_geometry_info",
    "graph.build_network",
    "nodes.connect_nodes",
    "nodes.copy_node",
    "nodes.create_node",
    "nodes.delete_node",
    "nodes.get_node_info",
    "nodes.layout_children",
    "nodes.list_children",
    "parameters.get_parameter",
    "parameters.get_parameters",
    "parameters.set_parameter",
    "scene.save_scene",
    "vex.create_wrangle",
    "viewport.capture_screenshot",
})


def _catalog() -> Dict[str, dict]:
    """Load the generated schema catalog; this works outside Houdini."""
    global _catalog_cache
    if _catalog_cache is None:
        path = Path(__file__).with_name("fx_commands.json")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            _catalog_cache = (
                {
                    command: metadata
                    for command, metadata in payload.items()
                    if command not in _AGENT_OWNED_COMMANDS
                }
                if isinstance(payload, dict)
                else {}
            )
        except Exception:
            _catalog_cache = {}
    return _catalog_cache


def _load_commands() -> bool:
    """Load the embedded handlers once, and only inside Houdini."""
    global _loaded
    if _loaded:
        return True
    if hou is None:
        return False
    with _load_lock:
        if _loaded:
            return True
        from .fxhoudinimcp_server import handlers as _handlers  # noqa: F401
        _loaded = True
    return True


def list_commands() -> list[str]:
    """Return the packaged command catalog in every Agent process."""
    return sorted(_catalog())


def tool_name(command: str) -> str:
    return "fx_" + re.sub(r"[^a-zA-Z0-9_]+", "_", command).strip("_")


def command_name(name: str) -> Optional[str]:
    if not name.startswith("fx_"):
        return None
    candidate = name[3:].replace("_", ".", 1)
    return candidate if candidate in _catalog() else None


def schema_for(command: str) -> Optional[dict]:
    entry = _catalog().get(command)
    schema = entry.get("schema") if isinstance(entry, dict) else None
    return copy.deepcopy(schema) if isinstance(schema, dict) else None


def _is_readonly(command: str) -> bool:
    entry = _catalog().get(command, {})
    return bool(entry.get("readonly"))


def _intent_for(command: str) -> str:
    entry = _catalog().get(command, {})
    return str(entry.get("intent") or command.split(".", 1)[0])


def execute(command: str, params: Optional[dict] = None) -> dict:
    """Execute an embedded command and normalize it to Agent's result shape."""
    if command not in _catalog():
        return {
            "success": False,
            "error": f"Unknown FX MCP command: {command}",
            "error_code": "UNKNOWN_COMMAND",
            "details": {"available_commands": list_commands()},
        }
    if not _load_commands():
        return {"success": False, "error": "FX MCP tools require a Houdini Python session."}
    from .fxhoudinimcp_server.dispatcher import dispatch
    from .fxhoudinimcp_server.serialize import to_jsonable

    response = dispatch(command, params or {})
    if response.get("status") != "success":
        error = response.get("error", {})
        return {
            "success": False,
            "error": error.get("message", str(error)),
            "error_code": error.get("code", "FX_MCP_ERROR"),
            "details": to_jsonable(error),
        }

    data = to_jsonable(response.get("data"))
    if isinstance(data, dict) and data.get("success") is False:
        errors = data.get("errors") or []
        error = data.get("error") or (
            "; ".join(str(item) for item in errors)
            if isinstance(errors, list) else str(errors)
        ) or data.get("message") or f"FX MCP command failed: {command}"
        return {
            "success": False,
            "error": str(error),
            "error_code": data.get("error_code") or "FX_COMMAND_FAILED",
            "details": data,
        }
    result = {"success": True, "result": json.dumps(data, ensure_ascii=False)}
    if isinstance(data, dict) and data.get("image_base64"):
        result["_viewport_image"] = data["image_base64"]
        result["_image_media_type"] = data.get("mime_type", "image/png")
    return result


def register_agent_tools(registry: Any) -> int:
    """Register all packaged upstream commands in Agent's ToolRegistry."""
    count = 0
    for command in list_commands():
        schema = schema_for(command)
        if not schema:
            continue
        name = tool_name(command)
        readonly = _is_readonly(command)
        modes = {"agent", "plan_executing"}
        if readonly:
            modes.update({"ask", "plan_planning"})
        registry.register(
            name=name,
            schema=schema,
            handler=lambda args, _command=command: execute(_command, args),
            source="core",
            plugin_name="fxhoudinimcp",
            tags={"fx_mcp", f"intent:{_intent_for(command)}"}
                 | ({"readonly"} if readonly else set()),
            modes=modes,
        )
        count += 1
    return count


def available_tool_definitions() -> Iterable[dict]:
    for command in list_commands():
        schema = schema_for(command)
        if schema:
            yield schema


def tools_for_request(base_tools: Iterable[dict], user_message: str,
                      mode: str = "agent") -> list[dict]:
    """Merge relevant, enabled FX schemas into the list actually sent to the model.

    Keep native/plugin tools selected by the caller; FX tools use the registry's
    intent and mode filters in both the embedded and standalone frontends.
    """
    from ..tool_registry import get_tool_registry

    registry = get_tool_registry()
    intents = registry.classify_intent(user_message)
    tools = [tool for tool in base_tools
             if command_name(tool.get("function", {}).get("name", "")) is None]
    names = {tool.get("function", {}).get("name", "") for tool in tools}
    for schema in registry.get_tools_for_intent(intents, mode=mode):
        name = schema.get("function", {}).get("name", "")
        if command_name(name) is not None and name not in names:
            tools.append(schema)
            names.add(name)
    return tools
