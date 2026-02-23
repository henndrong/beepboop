from fastapi import FastAPI, Query
import psycopg2
import os

DB_URL = os.getenv("DB_URL", "postgresql://tft:tft@localhost:5432/tft")

app = FastAPI(title="TFT Stats API")

def get_conn():
    return psycopg2.connect(DB_URL)

@app.get("/unit/{unit_id}/best_second_items_given")
def best_second_items_given(
    unit_id: str,
    required_item: str = Query(..., description="Must-have item, e.g. TFT_Item_GuinsoosRageblade"),
    min_games: int = 3
):
    sql = """
    WITH unit_has_required AS (
      SELECT DISTINCT u.match_id, u.puuid
      FROM units u
      JOIN unit_items ui
        ON ui.match_id = u.match_id
       AND ui.puuid = u.puuid
       AND ui.unit_character_id = u.unit_character_id
      WHERE u.unit_character_id = %s
        AND ui.item_name = %s
    )
    SELECT
      ui2.item_name AS second_item,
      COUNT(*) AS games,
      AVG(CASE WHEN p.placement <= 4 THEN 1.0 ELSE 0.0 END) AS top4_rate,
      AVG(p.placement) AS avg_place
    FROM unit_has_required r
    JOIN unit_items ui2
      ON ui2.match_id = r.match_id AND ui2.puuid = r.puuid
    JOIN participants p
      ON p.match_id = r.match_id AND p.puuid = r.puuid
    WHERE ui2.item_name <> %s
      -- only count items actually on THIS unit (not other units)
      AND ui2.unit_character_id = %s
    GROUP BY ui2.item_name
    HAVING COUNT(*) >= %s
    ORDER BY top4_rate DESC, avg_place ASC, games DESC
    LIMIT 30;
    """

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (unit_id, required_item, required_item, unit_id, min_games))
            rows = cur.fetchall()
        return [
            {
                "second_item": r[0],
                "games": r[1],
                "top4_rate": float(r[2]),
                "avg_place": float(r[3]),
            }
            for r in rows
        ]
    finally:
        conn.close()

@app.get("/unit/{unit_id}/best_item_pairs_given")
def best_item_pairs_given(
    unit_id: str,
    required_item: str = Query(..., description="Item that must be present, e.g. TFT_Item_GuinsoosRageblade"),
    min_games: int = 3
):
    sql = """
    WITH unit_items_agg AS (
      SELECT
        u.match_id,
        u.puuid,
        ARRAY_AGG(ui.item_name ORDER BY ui.item_name) AS items
      FROM units u
      JOIN unit_items ui
        ON ui.match_id = u.match_id
       AND ui.puuid = u.puuid
       AND ui.unit_character_id = u.unit_character_id
      WHERE u.unit_character_id = %s
      GROUP BY u.match_id, u.puuid
    ),
    with_required AS (
      SELECT
        match_id,
        puuid,
        ARRAY_REMOVE(items, %s) AS other_items
      FROM unit_items_agg
      WHERE %s = ANY(items)
    ),
    pairs AS (
      SELECT
        match_id,
        puuid,
        CASE
          WHEN COALESCE(other_items[1], '') <= COALESCE(other_items[2], '')
          THEN ARRAY[other_items[1], other_items[2]]
          ELSE ARRAY[other_items[2], other_items[1]]
        END AS item_pair
      FROM with_required
      WHERE array_length(other_items, 1) = 2
    )
    SELECT
      item_pair[1] AS item2,
      item_pair[2] AS item3,
      COUNT(*) AS games,
      AVG(CASE WHEN p.placement <= 4 THEN 1.0 ELSE 0.0 END) AS top4_rate,
      AVG(p.placement) AS avg_place
    FROM pairs
    JOIN participants p
      ON p.match_id = pairs.match_id AND p.puuid = pairs.puuid
    GROUP BY item_pair
    HAVING COUNT(*) >= %s
    ORDER BY top4_rate DESC, avg_place ASC, games DESC
    LIMIT 20;
    """

    
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (unit_id, required_item, required_item, min_games))
            rows = cur.fetchall()
        return [
            {"item2": r[0], "item3": r[1], "games": r[2], "top4_rate": float(r[3]), "avg_place": float(r[4])}
            for r in rows
        ]
    finally:
        conn.close()


@app.get("/unit/{unit_id}/best_three_item_combos")
def best_three_item_combos(
    unit_id: str,
    min_games: int = 3
):
    sql = """
    WITH unit_items_agg AS (
      SELECT
        u.match_id,
        u.puuid,
        ARRAY_AGG(ui.item_name ORDER BY ui.item_name) AS items
      FROM units u
      JOIN unit_items ui
        ON ui.match_id = u.match_id
       AND ui.puuid = u.puuid
       AND ui.unit_character_id = u.unit_character_id
      WHERE u.unit_character_id = %s
      GROUP BY u.match_id, u.puuid
    ),
    full_builds AS (
      SELECT match_id, puuid, items
      FROM unit_items_agg
      WHERE array_length(items, 1) = 3
    )
    SELECT
      items[1] AS item1,
      items[2] AS item2,
      items[3] AS item3,
      COUNT(*) AS games,
      AVG(CASE WHEN p.placement <= 4 THEN 1.0 ELSE 0.0 END) AS top4_rate,
      AVG(p.placement) AS avg_place
    FROM full_builds
    JOIN participants p
      ON p.match_id = full_builds.match_id AND p.puuid = full_builds.puuid
    GROUP BY items
    HAVING COUNT(*) >= %s
    ORDER BY top4_rate DESC, avg_place ASC, games DESC
    LIMIT 20;
    """

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (unit_id, min_games))
            rows = cur.fetchall()
        return [
            {
                "item1": r[0],
                "item2": r[1],
                "item3": r[2],
                "games": r[3],
                "top4_rate": float(r[4]),
                "avg_place": float(r[5]),
            }
            for r in rows
        ]
    finally:
        conn.close()
