WITH yunara_items AS (
  SELECT
    u.match_id,
    u.puuid,
    -- collect the 3 item names for Yunara into an array
    ARRAY_AGG(ui.item_name ORDER BY ui.item_name) AS items
  FROM units u
  JOIN unit_items ui
    ON ui.match_id = u.match_id
   AND ui.puuid = u.puuid
   AND ui.unit_character_id = u.unit_character_id
  WHERE u.unit_character_id = 'TFT16_Yunara'
  GROUP BY u.match_id, u.puuid
),
yunara_with_guinsoo AS (
  SELECT
    yi.match_id,
    yi.puuid,
    -- remove Guinsoo from the array; remaining are candidates for (2nd, 3rd)
    ARRAY_REMOVE(yi.items, 'TFT_Item_GuinsoosRageblade') AS other_items
  FROM yunara_items yi
  WHERE 'TFT_Item_GuinsoosRageblade' = ANY(yi.items)
),
pairs AS (
  SELECT
    match_id,
    puuid,
    -- normalize pair ordering so (IE, QSS) = (QSS, IE)
    CASE
      WHEN COALESCE(other_items[1], '') <= COALESCE(other_items[2], '')
      THEN ARRAY[other_items[1], other_items[2]]
      ELSE ARRAY[other_items[2], other_items[1]]
    END AS item_pair
  FROM yunara_with_guinsoo
  -- only keep games where Yunara has exactly 3 items total (Guinsoo + 2 others)
  WHERE array_length(other_items, 1) = 2
)
SELECT
  item_pair[1] AS second_item,
  item_pair[2] AS third_item,
  COUNT(*) AS games,
  AVG(CASE WHEN p.placement <= 4 THEN 1.0 ELSE 0.0 END) AS top4_rate,
  AVG(p.placement) AS avg_place
FROM pairs
JOIN participants p
  ON p.match_id = pairs.match_id
 AND p.puuid = pairs.puuid
GROUP BY item_pair
HAVING COUNT(*) >= 3
ORDER BY top4_rate DESC, avg_place ASC, games DESC
LIMIT 20;