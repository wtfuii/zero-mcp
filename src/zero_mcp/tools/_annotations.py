"""MCP tool annotations shared by the vertical slices.

Hints describe the tool to an MCP host so it can warn before changing broker
state. Read tools are marked idempotent because repeating a GET is harmless;
order tools are destructive because they move real money.
"""

from mcp.types import ToolAnnotations

READ_ONLY = ToolAnnotations(
    read_only_hint=True,
    idempotent_hint=True,
    open_world_hint=True,
)

ADDITIVE = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=False,
    open_world_hint=True,
)

DESTRUCTIVE = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=True,
    idempotent_hint=False,
    open_world_hint=True,
)
