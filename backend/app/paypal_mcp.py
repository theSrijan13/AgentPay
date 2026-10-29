"""Optional read-only bridge to PayPal's official local MCP server.

The MCP subprocess receives a short-lived OAuth access token through its environment.
The API allows only read-style tools; order creation, payment, capture, and refund remain
on AgentPay's explicitly approved server-side REST endpoints.
"""
from __future__ import annotations

import os
import shutil
from typing import Any

import httpx

from .config import settings
from .paypal import _access_token

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
except ImportError:  # Optional so the rest of AgentPay runs without MCP installed.
    ClientSession = None  # type: ignore[assignment,misc]
    StdioServerParameters = None  # type: ignore[assignment,misc]
    stdio_client = None  # type: ignore[assignment]


BLOCKED_NAME_PARTS = ("create", "pay_", "capture", "refund", "cancel", "delete", "update", "send", "approve", "void")


def configured() -> bool:
    return bool(
        settings.paypal_mcp_enabled
        and settings.paypal_client_id.strip()
        and settings.paypal_client_secret.strip()
        and shutil.which("npx")
        and ClientSession is not None
        and stdio_client is not None
    )


def status() -> dict[str, Any]:
    if not settings.paypal_mcp_enabled:
        reason = "PayPal MCP is disabled. Set PAYPAL_MCP_ENABLED=true to enable the read-only MCP tool explorer."
    elif not (settings.paypal_client_id.strip() and settings.paypal_client_secret.strip()):
        reason = "PayPal Sandbox REST credentials are missing."
    elif not shutil.which("npx"):
        reason = "Node.js/npm npx was not found. Install Node.js 18+ to run the official local PayPal MCP server."
    elif ClientSession is None or stdio_client is None:
        reason = "The Python MCP client is not installed. Install backend requirements and restart FastAPI."
    else:
        reason = "PayPal MCP bridge is ready. Tool discovery starts when requested."
    return {"configured": configured(), "enabled": settings.paypal_mcp_enabled, "mode": "sandbox", "message": reason}


def _is_read_only(name: str) -> bool:
    low = name.lower()
    return (low.startswith("get_") or low.startswith("list_") or low.startswith("search_") or low.startswith("find_")) and not any(part in low for part in BLOCKED_NAME_PARTS)


async def _open_mcp_session():
    """Context manager setup kept internal; each request receives a fresh access token."""
    if not configured():
        raise RuntimeError(status()["message"])
    async with httpx.AsyncClient(timeout=15) as http_client:
        token = await _access_token(http_client)
    # Pass only the minimum required environment. Do not forward Channel3, Elastic,
    # or unrelated process secrets into the MCP subprocess.
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
        "PAYPAL_ACCESS_TOKEN": token,
        "PAYPAL_ENVIRONMENT": "SANDBOX",
    }
    params = StdioServerParameters(
        command=shutil.which("npx") or "npx",
        args=["-y", "@paypal/mcp", "--tools=all"],
        env=env,
    )
    return params


async def list_read_only_tools() -> list[dict[str, Any]]:
    params = await _open_mcp_session()
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.list_tools()
            tools: list[dict[str, Any]] = []
            for tool in result.tools:
                if _is_read_only(tool.name):
                    tools.append({
                        "name": tool.name,
                        "description": (tool.description or "")[:500],
                        "inputSchema": getattr(tool, "inputSchema", None) or getattr(tool, "input_schema", None) or {"type": "object", "properties": {}},
                    })
            return tools[:60]


async def call_read_only_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if not _is_read_only(name):
        raise ValueError("Only read-only PayPal MCP tools are allowed from AgentPay. Mutating actions require their dedicated approval flow.")
    params = await _open_mcp_session()
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.list_tools()
            available = {tool.name for tool in result.tools if _is_read_only(tool.name)}
            if name not in available:
                raise ValueError("That read-only tool is not available from the connected PayPal MCP server. Refresh the tool list.")
            response = await session.call_tool(name, arguments=arguments)
            content = []
            for item in getattr(response, "content", []) or []:
                if getattr(item, "type", "") == "text":
                    content.append(str(getattr(item, "text", ""))[:4000])
                else:
                    content.append({"type": getattr(item, "type", "unknown")})
            return {"tool_name": name, "isError": bool(getattr(response, "isError", False)), "content": content[:20]}
