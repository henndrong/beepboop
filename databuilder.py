#!/usr/bin/env python3
"""
TFT Small Sample Collector (Masters/GM/Challenger NA)
- Seeds from tft-league-v1 (na1)
- Uses puuid directly from league entry payloads
- Pulls match IDs and match details via tft-match-v1 (americas)
- Saves raw match JSON to ./data/matches/<match_id>.json
- Optional: SQLite dedupe (recommended) to avoid re-downloading matches

Requirements:
  pip install requests

Env:
  export RIOT_API_KEY="YOUR_KEY"
"""

import os
import time
import json
import random
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

from dotenv import load_dotenv
import os

load_dotenv()

RIOT_API_KEY = os.getenv("RIOT_API_KEY")
if not RIOT_API_KEY:
    raise SystemExit("Missing RIOT_API_KEY in environment.")
# Routing: platform (na1) for league/summoner, regional (americas) for match history
PLATFORM = "na1"
REGIONAL = "americas"

BASE_PLATFORM = f"https://{PLATFORM}.api.riotgames.com"
BASE_REGIONAL = f"https://{REGIONAL}.api.riotgames.com"

HEADERS = {"X-Riot-Token": RIOT_API_KEY}

DATA_DIR = Path("data")
MATCH_DIR = DATA_DIR / "matches"
DATA_DIR.mkdir(exist_ok=True)
MATCH_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "tft_sample.sqlite3"


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def request_json(session: requests.Session, url: str, params: Optional[dict] = None, max_retries: int = 6) -> Any:
    """
    Riot APIs will rate limit (429). This handles backoff using Retry-After when present.
    """
    for attempt in range(max_retries):
        resp = session.get(url, params=params, timeout=30)

        if resp.status_code == 200:
            return resp.json()

        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            sleep_s = int(retry_after) if retry_after and retry_after.isdigit() else (2 ** attempt)
            # add jitter so we don't hammer at the same interval
            sleep_s = sleep_s + random.uniform(0, 0.5)
            print(f"[429] Rate limited. Sleeping {sleep_s:.2f}s then retrying... ({attempt+1}/{max_retries})")
            time.sleep(sleep_s)
            continue

        if resp.status_code in (500, 502, 503, 504):
            sleep_s = (2 ** attempt) + random.uniform(0, 0.5)
            print(f"[{resp.status_code}] Server error. Sleeping {sleep_s:.2f}s... ({attempt+1}/{max_retries})")
            time.sleep(sleep_s)
            continue

        # Other errors: show the response body for debugging
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        raise RuntimeError(f"Request failed {resp.status_code} for {url} params={params} body={body}")

    raise RuntimeError(f"Request failed after {max_retries} retries: {url}")


def init_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS downloaded_matches (
            match_id TEXT PRIMARY KEY,
            downloaded_at INTEGER NOT NULL
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS seen_puuids (
            puuid TEXT PRIMARY KEY,
            seen_at INTEGER NOT NULL
        );
        """
    )
    conn.commit()
    return conn


def already_downloaded(conn: sqlite3.Connection, match_id: str) -> bool:
    cur = conn.execute("SELECT 1 FROM downloaded_matches WHERE match_id = ?", (match_id,))
    return cur.fetchone() is not None


def mark_downloaded(conn: sqlite3.Connection, match_id: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO downloaded_matches(match_id, downloaded_at) VALUES (?, ?)",
        (match_id, int(time.time())),
    )
    conn.commit()


def mark_seen_puuid(conn: sqlite3.Connection, puuid: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO seen_puuids(puuid, seen_at) VALUES (?, ?)",
        (puuid, int(time.time())),
    )
    conn.commit()


# ---- Riot API calls ----

def fetch_league(session: requests.Session, tier: str) -> Dict[str, Any]:
    """
    tier in {"challenger", "grandmaster", "master"}
    """
    url = f"{BASE_PLATFORM}/tft/league/v1/{tier}"
    return request_json(session, url)


def fetch_summoner_by_id(session: requests.Session, summoner_id: str) -> Dict[str, Any]:
    url = f"{BASE_PLATFORM}/tft/summoner/v1/summoners/{summoner_id}"
    return request_json(session, url)


def fetch_match_ids_by_puuid(session: requests.Session, puuid: str, count: int = 20) -> List[str]:
    url = f"{BASE_REGIONAL}/tft/match/v1/matches/by-puuid/{puuid}/ids"
    return request_json(session, url, params={"count": count})


def fetch_match_by_id(session: requests.Session, match_id: str) -> Dict[str, Any]:
    url = f"{BASE_REGIONAL}/tft/match/v1/matches/{match_id}"
    return request_json(session, url)


def save_match_json(match_id: str, payload: Dict[str, Any]) -> None:
    out_path = MATCH_DIR / f"{match_id}.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def extract_participant_puuids(match_payload: Dict[str, Any]) -> List[str]:
    """
    The match DTO has participants under payload["info"]["participants"] in typical responses.
    Each participant includes "puuid".
    """
    info = match_payload.get("info", {})
    participants = info.get("participants", []) or []
    puuids = []
    for p in participants:
        puuid = p.get("puuid")
        if puuid:
            puuids.append(puuid)
    return puuids


def main(
    tiers: Tuple[str, ...] = ("challenger", "grandmaster", "master"),
    seed_players_per_tier: int = 20,
    matches_per_player: int = 10,
    max_total_matches: int = 200,
) -> None:
    session = make_session()
    conn = init_db()

    print("CONFIG:", seed_players_per_tier, matches_per_player, max_total_matches)


    # 1) Pull ladder lists and pick a subset of players
    seed_puuids: List[str] = []
    for tier in tiers:
        league = fetch_league(session, tier)
        entries = league.get("entries", []) or []
        print("First entry keys:", list(entries[0].keys()) if entries else "NO ENTRIES")


        # entries contains puuid + summonerId + leaguePoints + etc.
        # We'll randomly sample to avoid hammering the same top few
        random.shuffle(entries)
        picked = entries[:seed_players_per_tier]
        tier_puuids = [e["puuid"] for e in picked if "puuid" in e]
        seed_puuids.extend(tier_puuids)

        for puuid in tier_puuids:
            mark_seen_puuid(conn, puuid)

        print(f"Seeded {len(tier_puuids)} puuids from {tier} ({len(entries)} total entries).")

    print(f"Total seed puuids: {len(seed_puuids)}")

    # 3) For each seed player, fetch some match IDs, then match details
    downloaded = 0
    for idx, puuid in enumerate(seed_puuids, start=1):
        if downloaded >= max_total_matches:
            break

        match_ids = fetch_match_ids_by_puuid(session, puuid, count=matches_per_player)
        print(f"[{idx}/{len(seed_puuids)}] Got {len(match_ids)} match IDs for seed puuid.")

        for match_id in match_ids:
            if downloaded >= max_total_matches:
                break

            if already_downloaded(conn, match_id):
                continue

            match_payload = fetch_match_by_id(session, match_id)
            save_match_json(match_id, match_payload)
            mark_downloaded(conn, match_id)
            downloaded += 1

            # Optional propagation: mark all participant puuids as "seen"
            for p in extract_participant_puuids(match_payload):
                mark_seen_puuid(conn, p)

            if downloaded % 10 == 0:
                print(f"Downloaded {downloaded} matches so far...")

            # be a polite crawler; add a tiny delay
            time.sleep(0.15)

    print(f"Done. Downloaded {downloaded} matches into {MATCH_DIR.resolve()}")
    print(f"SQLite dedupe DB at {DB_PATH.resolve()}")


if __name__ == "__main__":
    # You can tweak these numbers to keep it "small sample"
    main(
        seed_players_per_tier=15,   # e.g., 15 from Challenger + 15 GM + 15 Master
        matches_per_player=8,       # e.g., last 8 matches per player
        max_total_matches=150       # hard cap so you don't over-collect
    )
