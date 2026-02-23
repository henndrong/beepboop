import json
import os
import re
import requests
from typing import Any, Dict, Optional

# ---- Config ----
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")
API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")  # we'll call the same endpoint directly for speed

# If you want *strictly* MCP here, we can do that next.
# Fastest path: call your tool endpoint directly (same logic as MCP tool).
def best_second_items(unit_id: str, required_item: str, min_games: int = 1):
    r = requests.get(
        f"{API_BASE}/unit/{unit_id}/best_second_items_given",
        params={"required_item": required_item, "min_games": min_games},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()

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
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # try to extract first {...} block
        m = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None

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

            data = best_second_items(unit_id, required_item, min_games=min_games)

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
