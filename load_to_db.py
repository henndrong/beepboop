import json
import os
from pathlib import Path
import psycopg2
from psycopg2.extras import execute_batch

DATA_DIR = Path("data/matches")
DB_URL = "postgresql://tft:tft@localhost:5432/tft"


def get_connection():
    return psycopg2.connect(DB_URL)


def load_all_matches():
    conn = get_connection()
    cur = conn.cursor()

    total_matches = 0

    for file_path in DATA_DIR.glob("*.json"):
        with open(file_path, "r", encoding="utf-8") as f:
            payload = json.load(f)

        metadata = payload.get("metadata", {})
        info = payload.get("info", {})

        match_id = metadata.get("match_id")
        if not match_id:
            continue

        # Insert match
        cur.execute(
            """
            INSERT INTO matches(match_id, game_datetime, game_length, game_version, queue_id, tft_set_core_name)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT (match_id) DO NOTHING
            """,
            (
                match_id,
                info.get("game_datetime"),
                info.get("game_length"),
                info.get("game_version"),
                info.get("queue_id"),
                info.get("tft_set_core_name"),
            ),
        )

        participants = info.get("participants", [])

        for p in participants:
            puuid = p.get("puuid")
            if not puuid:
                continue

            # Insert participant
            cur.execute(
                """
                INSERT INTO participants(
                    match_id, puuid, placement, level,
                    gold_left, last_round, time_eliminated,
                    total_damage_to_players, players_eliminated,
                    riot_id_game_name, riot_id_tagline
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (match_id, puuid) DO NOTHING
                """,
                (
                    match_id,
                    puuid,
                    p.get("placement"),
                    p.get("level"),
                    p.get("gold_left"),
                    p.get("last_round"),
                    p.get("time_eliminated"),
                    p.get("total_damage_to_players"),
                    p.get("players_eliminated"),
                    p.get("riotIdGameName"),
                    p.get("riotIdTagline"),
                ),
            )

            # Insert traits
            for t in p.get("traits", []):
                cur.execute(
                    """
                    INSERT INTO traits(
                        match_id, puuid, trait_name,
                        num_units, style, tier_current, tier_total
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT DO NOTHING
                    """,
                    (
                        match_id,
                        puuid,
                        t.get("name"),
                        t.get("num_units"),
                        t.get("style"),
                        t.get("tier_current"),
                        t.get("tier_total"),
                    ),
                )

            # Insert units + items
            for u in p.get("units", []):
                character_id = u.get("character_id")
                if not character_id:
                    continue

                cur.execute(
                    """
                    INSERT INTO units(
                        match_id, puuid, unit_character_id, rarity, tier
                    )
                    VALUES (%s,%s,%s,%s,%s)
                    ON CONFLICT DO NOTHING
                    """,
                    (
                        match_id,
                        puuid,
                        character_id,
                        u.get("rarity"),
                        u.get("tier"),
                    ),
                )

                items = u.get("itemNames", [])
                for slot, item in enumerate(items[:3]):
                    cur.execute(
                        """
                        INSERT INTO unit_items(
                            match_id, puuid, unit_character_id,
                            item_name, item_slot
                        )
                        VALUES (%s,%s,%s,%s,%s)
                        ON CONFLICT DO NOTHING
                        """,
                        (
                            match_id,
                            puuid,
                            character_id,
                            item,
                            slot,
                        ),
                    )

        total_matches += 1

    conn.commit()
    cur.close()
    conn.close()

    print(f"Loaded {total_matches} matches into Postgres.")


if __name__ == "__main__":
    load_all_matches()