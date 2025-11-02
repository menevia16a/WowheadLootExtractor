# Wowhead Loot Extractor

A Python script that scrapes Wowhead for NPC loot tables and generates SQL blocks for SPP-Legions database.

## Features

- Scrapes NPC loot tables from Wowhead
- Automatically detects quest items and applies negative drop rates
- Identifies profession recipes and generates appropriate loot conditions
- Filters items by Legion expansion (MAX_ITEM_ID_LEGION: 157831)
- Excludes specific problematic item IDs
- Intelligent retry logic with exponential backoff for rate limiting
- Local caching to avoid repeated requests
- Supports multiple NPCs in a single run

## Requirements

- Python 3.7+
- requests
- beautifulsoup4

## Installation

1. Clone or download this repository
2. Install dependencies:

```bash
pip install -r requirements.txt
```

## Usage

### Basic Usage

Extract loot for a single NPC:

```bash
python3 wowhead_loot_extractor.py --npc 96028
```

### Multiple NPCs

Extract loot for multiple NPCs (comma-separated):

```bash
python3 wowhead_loot_extractor.py --npc 96028,12345,67890
```

### Custom Output Directory

Specify a custom output directory:

```bash
python3 wowhead_loot_extractor.py --npc 96028 --outdir my_loot_tables
```

## Output

The script generates SQL files in the output directory (default: `output/`):

- `loot_<npc_id>.sql` - Contains the loot table SQL with comments

### SQL Output Format

Each SQL file contains:

1. **Comment block** with item IDs and metadata:
   - Drop chance percentage
   - Quest item indicator
   - Item quality
   - Recipe profession (if applicable)
   - Legendary status

2. **REPLACE INTO** statement for `creature_loot_template` table

3. **Loot conditions** (if applicable) for profession recipes:
   - DELETE existing conditions
   - INSERT profession requirement conditions
   - INSERT "no item" fallback conditions

### Example Output

```sql
/* NPC 96028 loot list
127048 -- chance:-4.11% -- quest -- quality:common
127929 -- chance:1.33% -- quality:common -- alchemy (recipe)
134225 -- chance:2.42% -- quality:green
*/

SET @NPC := 96028;
REPLACE INTO creature_loot_template (`entry`,`item`,`ChanceOrQuestChance`,`lootmode`,`groupid`,`mincountOrRef`,`maxcount`,`shared`) VALUES
(@NPC,127048,-4.11,23,0,1,1,0),
(@NPC,127929,1.33,23,0,1,1,0),
(@NPC,134225,2.42,23,0,1,1,0);

-- loot conditions
DELETE FROM conditions WHERE `SourceTypeOrReferenceId`=1
    AND `SourceGroup`=@NPC
    AND `SourceEntry` IN (127929); -- item IDs
INSERT INTO conditions (...) VALUES
(1, @NPC, 127929, 0, 1, 7, 0, 171, 1, 0, 0, 0, '', 'Item Drop - Has Alchemy'),
(1, @NPC, 127929, 0, 1, 2, 0, 127929, 1, 1, 1, 0, '', 'Item Drop - No Item');
```

## Features Details

### Quest Item Detection

Quest items are automatically detected using:
- Item class field (classs=12 in Wowhead data)
- Item name containing "quest"
- Item flags metadata

Quest items receive **negative drop rates** in the SQL output (e.g., 2% becomes -2%).

### Recipe Profession Detection

The script identifies profession recipes by:
- Recipe keywords in item names (recipe, pattern, formula, etc.)
- Profession names in item descriptions
- Fallback to individual item page fetching if needed

Supported professions:
- Alchemy
- Enchanting
- Jewelcrafting
- Inscription
- Leatherworking
- Blacksmithing
- Engineering
- Tailoring
- Herbalism

### Excluded Items

The following item IDs are automatically excluded from output:
```
124124, 138482, 138786, 141689, 141690, 147579, 138781, 138782,
140221, 140222, 140224, 140225, 140226, 140227, 144345, 147869, -1275
```

### Caching System

The script uses a local cache directory (`output/.cache/`) to store fetched item pages. This:
- Prevents unnecessary repeated requests
- Speeds up subsequent runs
- Helps avoid rate limiting

Cache files are HTML pages stored as `<item_id>.html`.

### Rate Limiting Handling

The script includes intelligent retry logic:
- Maximum 3 retry attempts per item
- Exponential backoff (1s, 2s, 4s)
- Detects HTTP 429 (rate limited) responses
- Informative console output for retries and successes
- 0.5s minimum delay between successful requests

## Console Output

Example console output:

```
[+] Fetching loot data for NPC 96028 from https://www.wowhead.com/npc=96028#drops
[+] Need to fetch 1 item pages to identify recipe professions and quest flags...
[+] Using cache directory: output/.cache
[+] Fetching item 141592 (1/1)...
[!] Error fetching item 141592: Connection timeout, retrying in 1.0s
[+] Successfully fetched item 141592 on retry attempt 2
[+] Written output for NPC 96028 → output/loot_96028.sql
```

## Configuration

You can modify the following constants in the script:

- `MAX_ITEM_ID_LEGION` (line 14): Maximum item ID for Legion expansion
- `EXCLUDED_ITEM_IDS` (line 17): Set of item IDs to exclude
- `PROFESSIONS` (line 19): Supported profession names
- `PROFESSION_SPELL_ID` (line 31): Profession spell IDs for conditions

## License

This script is provided as-is.

## Credits

- Scrapes data from [Wowhead.com](https://www.wowhead.com)
- Single Player Project - Legion (SPP-Legion's) database format
- Skeezix for original script concept
