# Wowhead Loot Extractor

A Python script that scrapes Wowhead for NPC loot tables and generates SQL blocks for SPP-Legion's database.

## Features

- Scrapes NPC loot tables
- Scrapes Item loot tables
- Scrapes GameObject (chest/container) loot tables
- Automatically detects quest items and applies negative drop rates
- Identifies profession recipes and generates appropriate loot conditions
- Filters items by Legion expansion (MAX_ITEM_ID_LEGION: 157831)
- Excludes specific problematic item IDs
- Intelligent retry logic with exponential backoff for rate limiting
- Local caching to avoid repeated requests
- Supports multiple NPCs/Objects/Items in a single run

## Requirements

- Python 3.7+
- requests
- beautifulsoup4

## Installation

1. Install dependencies:

```bash
pip install -r requirements.txt
```

## Usage

### Basic Usage

Extract loot for a single NPC:

```bash
python wowhead_loot_extractor.py --npc 96028
```

Extract loot for a single GameObject (e.g. chest):

```bash
python wowhead_loot_extractor.py --object 252452
```

Extract contained loot for an Item (container/sack):

```bash
python wowhead_loot_extractor.py --item 44663
```

### Multiple NPCs

Extract loot for multiple NPCs (comma-separated):

```bash
python wowhead_loot_extractor.py --npc 96028,12345,67890
```

### Custom Output Directory

Specify a custom output directory:

```bash
python wowhead_loot_extractor.py --npc 96028 --outdir my_loot_tables
```

### Exclusion flags

You can fine-tune which items are included in the generated SQL using the following CLI flags:

- `--exclude` — Comma-separated list of item IDs to always exclude. Example:

```bash
python wowhead_loot_extractor.py --npc 96028 --exclude 127048,127929
```

- `--exclude-quality` — Comma-separated list of quality names (case-insensitive) to exclude. Valid quality names are:
   `poor`, `common`, `green`, `rare`, `epic`, `legendary`, `artifact`.

Example excluding epic and legendary items:

```bash
python wowhead_loot_extractor.py --npc 96028 --exclude-quality epic,legendary
```

- `--exclude-profession` — Comma-separated list of profession names to exclude recipe drops from. Supported professions (case-insensitive):
   `alchemy`, `enchanting`, `jewelcrafting`, `inscription`, `leatherworking`, `blacksmithing`, `engineering`, `tailoring`, `herbalism`, `cooking`.

Example excluding tailoring and alchemy recipes:

```bash
python wowhead_loot_extractor.py --npc 96028 --exclude-profession tailoring,alchemy
```

Notes:

- Input values are validated and case-insensitive; invalid tokens will print a warning and be ignored.
- Exclusions are applied after item enrichment and any item-page lookups, so profession detection from item pages is respected.
- You can combine flags to filter by id, quality and/or profession in a single run.

## Output

The script generates SQL files in the output directory (default: `output/`):

- `loot_<npc_id>_<npc-name>.sql` - Contains the loot table SQL with comments
- `loot_<npc_id>_<npc-name>.sql` - Contains the NPC loot table SQL with comments
- `loot_object_<obj_id>_<object-name>.sql` - Contains GameObject (chest) loot SQL
- `loot_item_<item_id>_<item-name>.sql` - Contains Item container (contains) loot SQL

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
/* NPC 96028 - Wrath of Azshara loot list
127048 -- chance:-4.11% -- quest -- quality:common -- name:Heart of the Storm
127929 -- chance:1.33% -- quality:common -- alchemy (recipe) -- name:Recipe: Leytorrent Potion
*/

SET @NPC := 96028;
REPLACE INTO creature_loot_template (`entry`,`item`,`ChanceOrQuestChance`,`lootmode`,`groupid`,`mincountOrRef`,`maxcount`,`shared`) VALUES
(@NPC,127048,-4.11,23,0,1,1,0),
(@NPC,127929,1.33,23,0,1,1,0);

-- loot conditions (example)
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
- Cooking

### Excluded Items

The following item IDs are automatically excluded from output:
```
124124, 138482, 138786, 141689, 141690, 147579, 138781, 138782, 140220, 140221, 140222, 140224, 140225, 140226, 140227, 144345, 147869, 138019, -1275
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
[+] Written output for NPC 96028 → output/loot_96028_Wrath_of_Azshara.sql
```

## Configuration

You can modify the following constants in the script:

- `MAX_ITEM_ID_LEGION` (line 14): Maximum item ID for Legion expansion
- `EXCLUDED_ITEM_IDS` (line 17): Set of item IDs to exclude
- `PROFESSIONS` (line 19): Supported profession names
- `PROFESSION_SKILL_ID` (line 31): Profession skill IDs from SkillLine.db2 for conditions

## License

This script is provided as-is.

## Credits

- Scrapes data from [Wowhead.com](https://www.wowhead.com)
- Single Player Project - Legion (SPP-Legion's) database format
- Skeezix for original script concept
- Veil - SPP Developer, and the Godfather's Right Hand
