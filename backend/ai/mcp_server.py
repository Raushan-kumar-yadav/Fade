"""
Fade MCP Server
===============
Exposes all Fade video-editor tools as an MCP (Model Context Protocol) server.
Any MCP-compatible client — Claude Desktop, Cursor, VS Code Copilot, etc. —
can connect and call these tools with its own LLM.

Requires: mcp>=2.0  (pip install mcp)

Transport modes
---------------
  stdio  (default) — for desktop clients: Claude Desktop, Cursor, VS Code
  sse              — HTTP Server-Sent Events, for web / remote clients

Usage
-----
  # stdio  (Claude Desktop / Cursor)
  python -m backend.ai.mcp_server

  # SSE on a custom port
  python -m backend.ai.mcp_server --transport sse --port 7654

Claude Desktop  (%APPDATA%\\Claude\\claude_desktop_config.json)
  {
    "mcpServers": {
      "fade-editor": {
        "command": "E:\\\\Editor_SIH\\\\Fade\\\\.venv\\\\Scripts\\\\python.exe",
        "args": ["-m", "backend.ai.mcp_server"],
        "cwd": "E:\\\\Editor_SIH\\\\Fade"
      }
    }
  }

Cursor / VS Code (.cursor/mcp.json or .vscode/mcp.json)
  {
    "mcpServers": {
      "fade-editor": {
        "command": "E:\\\\Editor_SIH\\\\Fade\\\\.venv\\\\Scripts\\\\python.exe",
        "args": ["-m", "backend.ai.mcp_server"],
        "cwd": "E:\\\\Editor_SIH\\\\Fade"
      }
    }
  }
"""

from __future__ import annotations

import argparse
import inspect
import os
import sys
from pathlib import Path
from typing import Any

# ── Resolve project root so the module is importable regardless of cwd ─────────
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# ── Load .env ──────────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    _env = _ROOT / ".env"
    if _env.exists():
        load_dotenv(str(_env), override=False)
except ImportError:
    pass

# ── MCP v2 imports ─────────────────────────────────────────────────────────────
try:
    from mcp.server.mcpserver import MCPServer
    from mcp.server.mcpserver.tools import Tool
except ImportError as _e:
    print(
        f"[Fade MCP] Cannot import MCP server: {_e}\n"
        "Install with:  pip install 'mcp>=2.0'\n",
        file=sys.stderr,
    )
    sys.exit(1)

# ── Fade tools ─────────────────────────────────────────────────────────────────
from backend.ai.tools import ALL_TOOLS, set_port

# ── Backend port ───────────────────────────────────────────────────────────────
_BACKEND_PORT: int = int(
    os.environ.get("BACKEND_PORT", os.environ.get("FADE_BACKEND_PORT", 8000))
)
set_port(_BACKEND_PORT)


# ══════════════════════════════════════════════════════════════════════════════
#  Convert LangChain @tool  →  MCP Tool
# ══════════════════════════════════════════════════════════════════════════════

def _lc_to_mcp_tool(lc_tool) -> Tool | None:
    """
    Wrap a LangChain @tool into an MCP v2 Tool via Tool.from_function().

    We build a real Python function with a typed inspect.Signature derived
    from the tool's Pydantic args_schema so the MCP client sees proper
    parameter names and types in the JSON schema.
    """
    name: str = lc_tool.name
    description: str = (lc_tool.description or "").strip()
    schema = getattr(lc_tool, "args_schema", None)

    if schema is None:
        # ── Zero-argument tool ────────────────────────────────────────────────
        def _zero() -> str:
            try:
                return str(lc_tool.invoke({}))
            except Exception as exc:
                return f"[Fade error] {name}: {exc}"

        _zero.__name__ = name
        _zero.__doc__ = description
        _zero.__signature__ = inspect.Signature([], return_annotation=str)
        _zero.__annotations__ = {"return": str}
        return Tool.from_function(_zero, name=name, description=description)

    # ── Inspect Pydantic schema (v1 & v2 compatible) ──────────────────────────
    try:
        fields = schema.model_fields          # Pydantic v2
        def _default_val(fi: Any) -> Any:
            d = fi.default
            s = str(d)
            if s in ("PydanticUndefined", "...", "<class 'pydantic_core.core_schema.missing'>"):
                return inspect.Parameter.empty
            return d
        def _ann(fi: Any) -> Any:
            return fi.annotation
    except AttributeError:
        fields = schema.__fields__            # Pydantic v1
        def _default_val(fi: Any) -> Any:
            d = fi.default
            return inspect.Parameter.empty if d is None else d
        def _ann(fi: Any) -> Any:
            return getattr(fi, "outer_type_", str)

    # Build inspect.Parameter list
    params: list[inspect.Parameter] = []
    annotations: dict[str, Any] = {"return": str}
    field_names: list[str] = list(fields.keys())

    for fn, fi in fields.items():
        raw_ann = _ann(fi)
        clean_ann = raw_ann if raw_ann is not None else str
        annotations[fn] = clean_ann
        dv = _default_val(fi)
        p = inspect.Parameter(
            fn,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            default=dv,
            annotation=clean_ann,
        )
        params.append(p)

    # Capture tool + field names in closure
    def _make_fn(tool_ref, fnames: list[str]):
        def _wrapper(**kwargs) -> str:
            call_args = {k: kwargs.get(k) for k in fnames}
            try:
                return str(tool_ref.invoke(call_args))
            except Exception as exc:
                return f"[Fade error] {tool_ref.name}: {exc}"
        return _wrapper

    fn = _make_fn(lc_tool, field_names)
    fn.__name__ = name
    fn.__doc__ = description
    fn.__annotations__ = annotations

    try:
        fn.__signature__ = inspect.Signature(params, return_annotation=str)
    except Exception:
        pass  # signature injection best-effort

    try:
        return Tool.from_function(fn, name=name, description=description)
    except Exception as exc:
        print(f"[Fade MCP] Tool.from_function failed for '{name}': {exc}", file=sys.stderr)
        return None


# ── Build tool list ────────────────────────────────────────────────────────────
def _ping_fade() -> str:
    """Check that the Fade Backend is reachable. Call this first if unsure the editor is running."""
    import httpx
    try:
        r = httpx.get(f"http://127.0.0.1:{_BACKEND_PORT}/health", timeout=5)
        return f"pong — Fade is running on port {_BACKEND_PORT} (HTTP {r.status_code})"
    except Exception as exc:
        return (
            f"Fade Backend NOT reachable at port {_BACKEND_PORT}. "
            f"Open Fade first, then retry. Detail: {exc}"
        )

_mcp_tools: list[Tool] = []
_registered = 0
for _lc in ALL_TOOLS:
    _t = _lc_to_mcp_tool(_lc)
    if _t is not None:
        _mcp_tools.append(_t)
        _registered += 1
    else:
        print(f"[Fade MCP] Skipped tool: {_lc.name}", file=sys.stderr)

# Add health-check tool
_mcp_tools.append(
    Tool.from_function(
        _ping_fade,
        name="ping_fade",
        description=_ping_fade.__doc__,
    )
)

print(f"[Fade MCP] {_registered}/{len(ALL_TOOLS)} Fade tools + 1 health tool registered", file=sys.stderr)


# ══════════════════════════════════════════════════════════════════════════════
#  Build the MCPServer instance
# ══════════════════════════════════════════════════════════════════════════════

server = MCPServer(
    name="fade-editor",
    title="Fade Video Editor",
    description=(
        "AI-powered video editor. Control the timeline, manage media, add effects, "
        "generate images/audio/video, and export projects."
    ),
    instructions=(
        "Always call get_timeline_state() first when you need clip IDs or frame numbers. "
        "Always call find_free_overlay_track() before placing any text or overlay clip. "
        "Use ping_fade() to verify the editor is running before making edits."
    ),
    tools=_mcp_tools,
)


# ══════════════════════════════════════════════════════════════════════════════
#  CLI entry point
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fade MCP Server — expose all Fade tools to any MCP-compatible LLM client",
    )
    parser.add_argument(
        "--transport", choices=["stdio", "sse"], default="stdio",
        help="stdio: Claude Desktop/Cursor/VS Code  |  sse: web/remote clients  (default: stdio)",
    )
    parser.add_argument(
        "--port", type=int, default=7654,
        help="HTTP port for SSE transport (default: 7654, ignored for stdio)",
    )
    parser.add_argument(
        "--backend-port", type=int, default=_BACKEND_PORT,
        help=f"Fade FastAPI backend port to target (default: {_BACKEND_PORT})",
    )
    args = parser.parse_args()

    if args.backend_port != _BACKEND_PORT:
        set_port(args.backend_port)

    n = len(_mcp_tools)
    print(f"[Fade MCP] transport={args.transport} | {n} tools | backend=http://127.0.0.1:{args.backend_port}", file=sys.stderr)

    if args.transport == "sse":
        print(f"[Fade MCP] SSE listening on http://0.0.0.0:{args.port}/sse", file=sys.stderr)
        server.run(transport="sse", port=args.port)
    else:
        print("[Fade MCP] stdio ready — waiting for MCP client …", file=sys.stderr)
        server.run(transport="stdio")


if __name__ == "__main__":
    main()
