CREATE TABLE IF NOT EXISTS matches (
  match_id TEXT PRIMARY KEY,
  game_datetime BIGINT,
  game_length DOUBLE PRECISION,
  game_version TEXT,
  queue_id INTEGER,
  tft_set_core_name TEXT
);

CREATE TABLE IF NOT EXISTS participants (
  match_id TEXT REFERENCES matches(match_id),
  puuid TEXT,
  placement INTEGER,
  level INTEGER,
  gold_left INTEGER,
  last_round INTEGER,
  time_eliminated DOUBLE PRECISION,
  total_damage_to_players INTEGER,
  players_eliminated INTEGER,
  riot_id_game_name TEXT,
  riot_id_tagline TEXT,
  PRIMARY KEY (match_id, puuid)
);

CREATE TABLE IF NOT EXISTS traits (
  match_id TEXT,
  puuid TEXT,
  trait_name TEXT,
  num_units INTEGER,
  style INTEGER,
  tier_current INTEGER,
  tier_total INTEGER,
  PRIMARY KEY (match_id, puuid, trait_name),
  FOREIGN KEY (match_id, puuid) REFERENCES participants(match_id, puuid)
);

CREATE TABLE IF NOT EXISTS units (
  match_id TEXT,
  puuid TEXT,
  unit_character_id TEXT,
  rarity INTEGER,
  tier INTEGER,
  PRIMARY KEY (match_id, puuid, unit_character_id),
  FOREIGN KEY (match_id, puuid) REFERENCES participants(match_id, puuid)
);

CREATE TABLE IF NOT EXISTS unit_items (
  match_id TEXT,
  puuid TEXT,
  unit_character_id TEXT,
  item_name TEXT,
  item_slot INTEGER,
  PRIMARY KEY (match_id, puuid, unit_character_id, item_slot),
  FOREIGN KEY (match_id, puuid, unit_character_id) REFERENCES units(match_id, puuid, unit_character_id)
);

CREATE INDEX IF NOT EXISTS idx_units_character_id ON units(unit_character_id);
CREATE INDEX IF NOT EXISTS idx_items_item_name ON unit_items(item_name);
CREATE INDEX IF NOT EXISTS idx_traits_trait_name ON traits(trait_name);
CREATE INDEX IF NOT EXISTS idx_participants_placement ON participants(placement);