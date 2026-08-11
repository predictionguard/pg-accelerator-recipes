"""
Minimal MCP server exposing one example tool. Use as a template — replace
lookup_sku with your pod's real tool(s).

Run: python example_mcp_server.py
Register with Claude Code: claude mcp add inventory-tools -- python example_mcp_server.py
"""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("inventory-tools")

# Stand-in data — replace with a real database/API call.
FAKE_INVENTORY = {
    "4471": {"description": "Steel bracket, 4in", "quantity_on_hand": 812, "warehouse": "IN-03"},
    "5820": {"description": "Grain moisture sensor", "quantity_on_hand": 46, "warehouse": "IN-01"},
}


@mcp.tool()
def lookup_sku(sku: str) -> dict:
    """Look up current inventory for a given SKU."""
    return FAKE_INVENTORY.get(sku, {"error": f"No record found for SKU {sku}"})


if __name__ == "__main__":
    mcp.run()
