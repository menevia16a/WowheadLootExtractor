"""
Utils package - Contains all supporting modules for Wowhead Loot Extractor.
"""

from .config import (
    MAX_ITEM_ID,
    EXCLUDED_ITEM_IDS,
    PROFESSIONS,
    PROFESSION_SKILL_ID,
    USER_AGENT,
    HTTP_HEADERS,
    MAX_RETRIES,
    RETRY_DELAY,
    REQUEST_TIMEOUT,
    QUALITY_LABELS,
    RECIPE_KEYWORDS,
    QUEST_ITEM_CLASS,
    WOWHEAD_BASE_URL,
    WOWHEAD_NPC_URL,
    WOWHEAD_ITEM_URL,
    WOWHEAD_OBJECT_URL,
    WOWHEAD_ZONE_URL,
)

from .utils import (
    sanitize_filename,
    clean_js_string,
    find_matching_bracket,
    extract_objects_from_array_str,
    compute_depth_at,
)

from .parser import (
    parse_npc_loot_data,
    parse_object_loot_data,
    parse_zone_loot_data,
    parse_item_page,
    extract_percent_from_modes,
)

from .fetcher import (
    RetryableHTTPFetcher,
    NpcLootFetcher,
    ItemInfoFetcher,
    ItemLootFetcher,
    NpcNameFetcher,
    GameObjectLootFetcher,
    ZoneLootFetcher,
    ObjectNameFetcher,
    ZoneNameFetcher,
)

from .enricher import (
    ItemEnricher,
    decide_drop_chance,
)

from .sql_generator import SQLGenerator

__all__ = [
    # Config
    'MAX_ITEM_ID',
    'EXCLUDED_ITEM_IDS',
    'PROFESSIONS',
    'PROFESSION_SKILL_ID',
    'USER_AGENT',
    'HTTP_HEADERS',
    'MAX_RETRIES',
    'RETRY_DELAY',
    'REQUEST_TIMEOUT',
    'QUALITY_LABELS',
    'RECIPE_KEYWORDS',
    'QUEST_ITEM_CLASS',
    'WOWHEAD_BASE_URL',
    'WOWHEAD_NPC_URL',
    'WOWHEAD_ITEM_URL',
    'WOWHEAD_ZONE_URL',

    # Utils
    'sanitize_filename',
    'clean_js_string',
    'find_matching_bracket',
    'extract_objects_from_array_str',
    'compute_depth_at',

    # Parser
    'parse_npc_loot_data',
    'parse_object_loot_data',
    'parse_zone_loot_data',
    'parse_item_page',
    'extract_percent_from_modes',

    # Fetcher
    'RetryableHTTPFetcher',
    'NpcLootFetcher',
    'ItemInfoFetcher',
    'ItemLootFetcher',
    'NpcNameFetcher',
    'ObjectNameFetcher',
    'GameObjectLootFetcher',

    # Enricher
    'ItemEnricher',
    'decide_drop_chance',
    
    # SQL Generator
    'SQLGenerator',
    'GameObjectLootFetcher',
    'ZoneLootFetcher',
    'ObjectNameFetcher',
    'WOWHEAD_OBJECT_URL',
]
