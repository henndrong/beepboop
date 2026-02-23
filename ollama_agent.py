import json
import os
import re
import sys
from typing import Any, Dict, Optional

import anyio
import requests
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

# ---- Config ----
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")
API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")
MCP_SERVER_SCRIPT = os.getenv("MCP_SERVER_SCRIPT", "mcp_server.py")


def _parse_json_value_loose(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # try to extract first JSON object/array block
        m = re.search(r"(\{.*\}|\[.*\])", text, flags=re.DOTALL)
        if not m:
            return None
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            return None


def _decode_mcp_tool_result(result: Any) -> Any:
    if getattr(result, "isError", False):
        raise RuntimeError(f"MCP tool returned error: {result}")

    structured = getattr(result, "structuredContent", None)
    if structured is not None:
        # FastMCP may wrap non-dict outputs if structured output is enabled.
        if isinstance(structured, dict) and set(structured.keys()) == {"result"}:
            return structured["result"]
        return structured

    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if not text:
            continue
        parsed = _parse_json_value_loose(text)
        if parsed is not None:
            return parsed
        return text

    raise RuntimeError("MCP tool returned no content")


async def _best_second_items_mcp(unit_id: str, required_item: str, min_games: int = 1):
    env = dict(os.environ)
    env["API_BASE"] = API_BASE

    server_params = StdioServerParameters(
        command=sys.executable,
        args=[MCP_SERVER_SCRIPT],
        env=env,
        cwd=os.path.dirname(os.path.abspath(__file__)),
    )

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(
                "best_second_items",
                {
                    "unit_id": unit_id,
                    "required_item": required_item,
                    "min_games": min_games,
                },
            )
            return _decode_mcp_tool_result(result)


# Strict MCP path: call tools only through the MCP server.
def best_second_items(unit_id: str, required_item: str, min_games: int = 1):
    return anyio.run(_best_second_items_mcp, unit_id, required_item, min_games)

SYSTEM = """You are a TFT stats assistant.
You MUST respond in one of two ways:

1) TOOL_CALL JSON exactly like:
{"tool":"best_second_items","args":{"unit_id":"TFT16_Yunara","required_item":"TFT_Item_GuinsoosRageblade","min_games":1}}

2) FINAL JSON exactly like:
{"final":"...your answer to the user..."}

Mapping rules:
- "Guinsoo" or "Rageblade" => TFT_Item_GuinsoosRageblade
- If user gives a unit name without prefix, guess the unit_id as TFT16_<Name> (e.g. Yunara -> TFT16_Yunara).
If unsure, ask a short clarification in FINAL.

Always include sample size (games) in your final answer.
If tool returns empty list, say we have insufficient sample in our dataset.
Do not set min_games above 3 unless the user explicitly asks for a higher threshold.
Do not claim statistical significance or reliability thresholds unless the user explicitly asks for that analysis.
"""

def ollama_chat(messages):
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "format": "json",  # encourages valid JSON
        "options": {"temperature": 0.2},
    }
    r = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=60)
    r.raise_for_status()
    return r.json()["message"]["content"]

def parse_json_loose(text: str) -> Optional[Dict[str, Any]]:
    parsed = _parse_json_value_loose(text)
    return parsed if isinstance(parsed, dict) else None

def main():
    DEFAULT_MIN_GAMES = 3
    messages = [{"role": "system", "content": SYSTEM}]
    print("Local TFT Agent ready. Type 'exit' to quit.\n")

    while True:
        user = input("> ").strip()
        if user.lower() in {"exit", "quit"}:
            break

        messages.append({"role": "user", "content": user})

        raw = ollama_chat(messages)
        obj = parse_json_loose(raw)

        if not obj:
            print("Model returned non-JSON. Try again or use a bigger model.\n")
            continue

        # Tool call path
        if obj.get("tool") == "best_second_items":
            args = obj.get("args", {})
            unit_id = args.get("unit_id")
            required_item = args.get("required_item")
            if not unit_id or not required_item:
                print("Tool call missing required args (unit_id, required_item).\n")
                continue
            # Keep tool behavior deterministic; do not let the model silently raise thresholds.
            requested_min_games = args.get("min_games")
            if requested_min_games is None:
                min_games = DEFAULT_MIN_GAMES
            else:
                try:
                    min_games = int(requested_min_games)
                except (TypeError, ValueError):
                    min_games = DEFAULT_MIN_GAMES
                min_games = max(DEFAULT_MIN_GAMES, min_games)

            try:
                data = best_second_items(unit_id, required_item, min_games=min_games)
            except Exception as e:
                print(f"MCP tool call failed: {e}\n")
                continue

            # Feed tool results back to model to write a human answer
            messages.append({"role": "assistant", "content": raw})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"TOOL_RESULT (min_games={min_games}): {json.dumps(data)}. "
                        "Use this exact threshold in your answer. Do not mention any other threshold."
                    ),
                }
            )

            raw2 = ollama_chat(messages)
            obj2 = parse_json_loose(raw2)

            if obj2 and "final" in obj2:
                print(obj2["final"], "\n")
                messages.append({"role": "assistant", "content": raw2})
            else:
                print("Tool worked, but model did not produce FINAL JSON. Raw:\n", raw2, "\n")

        # Final answer path
        elif "final" in obj:
            print(obj["final"], "\n")
            messages.append({"role": "assistant", "content": raw})

        else:
            print("Unexpected JSON from model:\n", raw, "\n")

if __name__ == "__main__":
    main()
