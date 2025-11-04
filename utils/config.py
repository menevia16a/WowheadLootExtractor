"""
Configuration constants for the Wowhead Loot Extractor.
"""

# Maximum item ID for Legion expansion
MAX_ITEM_ID_LEGION = 157831

# Item IDs to exclude from loot tables
EXCLUDED_ITEM_IDS = {
    124124, 138482, 138786, 141689, 141690, 147579, 138781, 138782,
    140220, 140221, 140222, 140224, 140225, 140226, 140227, 144345,
    147869, 138019, -1275
}

# Supported professions mapping
PROFESSIONS = {
    'alchemy': 'alchemy',
    'enchanting': 'enchanting',
    'jewelcrafting': 'jewelcrafting',
    'inscription': 'inscription',
    'leatherworking': 'leatherworking',
    'blacksmithing': 'blacksmithing',
    'engineering': 'engineering',
    'tailoring': 'tailoring',
    'herbalism': 'herbalism',
    'cooking': 'cooking',
}

# Mapping from profession key to representative profession spell/skill id
# used in conditions. These IDs match common profession spell ids from SkillLine.db2
PROFESSION_SKILL_ID = {
    'alchemy': 171,
    'enchanting': 333,
    'jewelcrafting': 755,
    'inscription': 773,
    'leatherworking': 165,
    'blacksmithing': 164,
    'engineering': 202,
    'tailoring': 197,
    'herbalism': 182,
    'cooking': 185,
}

# Browser user agent for HTTP requests
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# Common HTTP headers
HTTP_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# Retry settings
MAX_RETRIES = 3
RETRY_DELAY = 1.0
REQUEST_TIMEOUT = 10

# Quality labels mapping
QUALITY_LABELS = {
    0: 'poor',
    1: 'common',
    2: 'green',
    3: 'rare',
    4: 'epic',
    5: 'legendary',
    6: 'artifact'
}

# Recipe keywords for detection
RECIPE_KEYWORDS = ['recipe', 'pattern', 'plans', 'technique', 'design', 'formula', 'schematic']

# WoW item class for quest items
QUEST_ITEM_CLASS = 12

# Wowhead URLs
WOWHEAD_BASE_URL = "https://www.wowhead.com"
WOWHEAD_NPC_URL = lambda npc_id: f"{WOWHEAD_BASE_URL}/npc={npc_id}#drops"
WOWHEAD_ITEM_URL = lambda item_id: f"{WOWHEAD_BASE_URL}/item={item_id}#contains"
WOWHEAD_OBJECT_URL = lambda obj_id: f"{WOWHEAD_BASE_URL}/object={obj_id}#contains"
