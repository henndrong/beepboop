import os
import requests
from mcp.server.fastmcp import FastMCP

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")

mcp = FastMCP("tft-stats")

@mcp.tool()
def best_second_items(unit_id: str, required_item: str, min_games: int = 3):
    """
    Returns best 'other' items for a unit, given one required item.
    """
    r = requests.get(
        f"{API_BASE}/unit/{unit_id}/best_second_items_given",
        params={"required_item": required_item, "min_games": min_games},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()

if __name__ == "__main__":
    mcp.run()