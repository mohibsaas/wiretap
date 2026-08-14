"""MCP server — expose wiretap tools to coding agents.

Registration only; the tool bodies live in ``wiretap.mcp.tools`` so they can be
tested without the optional ``mcp`` dependency installed.
"""

from __future__ import annotations

import inspect
from typing import Any

_INSTALL_HINT = "MCP extra not installed. Install with: uv sync --extra mcp"


def _package_version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("wiretap")
    except PackageNotFoundError:
        return "0.0.0"


def _server_class() -> Any:
    """Return the server class for whichever MCP major version is installed.

    2.x renamed ``mcp.server.fastmcp.FastMCP`` to ``mcp.server.mcpserver.MCPServer``;
    both expose the ``add_tool`` / ``run`` surface used here.
    """
    try:
        from mcp.server.mcpserver import MCPServer

        return MCPServer
    except ImportError:
        pass
    try:
        from mcp.server.fastmcp import FastMCP

        return FastMCP
    except ImportError as exc:
        raise SystemExit(_INSTALL_HINT) from exc


def build_server() -> Any:
    """Create the MCP server with every wiretap tool registered."""
    from wiretap.mcp.tools import TOOLS

    cls = _server_class()
    kwargs: dict[str, Any] = {}
    # 2.x MCPServer reports a version in the initialize handshake; 1.x
    # FastMCP has no such parameter.
    if "version" in inspect.signature(cls.__init__).parameters:
        kwargs["version"] = _package_version()
    server = cls("wiretap", **kwargs)
    for fn in TOOLS:
        server.add_tool(fn)
    return server


def main() -> None:
    from wiretap.services.secrets import load_dotenv

    load_dotenv()
    build_server().run()


if __name__ == "__main__":
    main()
