#!/usr/bin/env python3
"""
Given a list of NPC (or GameObject) IDs, scrape Wowhead for their loot tables and generate SQL blocks.
"""

import requests
import re
import json
import argparse
import os
from bs4 import BeautifulSoup
import time

MAX_ITEM_ID_LEGION     = 157831

# Item IDs to exclude from loot tables
EXCLUDED_ITEM_IDS = {124124, 138482, 138786, 141689, 141690, 147579, 138781, 138782, 140221, 140222, 140224, 140225, 140226, 140227, 144345, 147869, -1275}

PROFESSIONS = {
    'alchemy':    'alchemy',
    'enchanting': 'enchanting',
    'jewelcrafting':'jewelcrafting',
    'inscription': 'inscription',
    'leatherworking':'leatherworking',
    'blacksmithing':'blacksmithing',
    'engineering':'engineering',
    'tailoring':'tailoring',
    'herbalism':'herbalism',
}

# Mapping from profession key to a representative profession spell/skill id used
# in conditions (used by the generated conditions INSERTs). These IDs match
# common profession spell ids used in conditions (example: Alchemy=171).
PROFESSION_SPELL_ID = {
    'alchemy': 171,
    'enchanting': 333,
    'jewelcrafting': 755,
    'inscription': 773,
    'leatherworking': 165,
    'blacksmithing': 164,
    'engineering': 202,
    'tailoring': 197,
    'herbalism': 182,
}

def fetch_loot(npc_id):
    """ Fetch loot table items for given NPC ID from Wowhead. Returns list of dicts. """
    url = f"https://www.wowhead.com/npc={npc_id}#drops"

    print(f"[+] Fetching loot data for NPC {npc_id} from {url}")

    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
    except Exception as e:
        print(f"[!] Error fetching NPC {npc_id}: {e}")

        return []
    
    if resp.status_code != 200:
        print(f"[!] HTTP {resp.status_code} when fetching NPC {npc_id}")

        return []
    
    html = resp.text

    # Single robust approach: find the new Listview(...) block with id:'drops',
    # extract the `data: [ ... ]` array using bracket-matching, then extract each
    # top-level object using brace-matching aware of quoted strings. This avoids
    # trying to json.loads a possibly non-strict-JS payload and recovers all items.
    loot = []

    def find_matching_bracket(s, start_idx, open_ch='[', close_ch=']'):
        i = start_idx
        depth = 0
        in_str = None
        esc = False
        n = len(s)

        for idx in range(i, n):
            ch = s[idx]

            if in_str:
                if esc:
                    esc = False
                elif ch == '\\':
                    esc = True
                elif ch == in_str:
                    in_str = None
            else:
                if ch == '"' or ch == "'":
                    in_str = ch
                elif ch == open_ch:
                    depth += 1
                elif ch == close_ch:
                    depth -= 1

                    if depth == 0:

                        return idx
        return -1

    def extract_objects_from_array_str(s):
        objs = []
        i = 0
        n = len(s)

        while i < n:
            ch = s[i]

            if ch == '{':
                start = i
                i += 1
                depth = 1
                in_str = None
                esc = False

                while i < n and depth > 0:
                    c = s[i]

                    if in_str:
                        if esc:
                            esc = False
                        elif c == '\\':
                            esc = True
                        elif c == in_str:
                            in_str = None
                    else:
                        if c == '"' or c == "'":
                            in_str = c
                        elif c == '{':
                            depth += 1
                        elif c == '}':
                            depth -= 1
                    
                    i += 1
                
                objs.append(s[start:i])
            else:
                i += 1
            
        return objs

    def clean_js_string(s):
        if not s:
            return ''
        
        # strip surrounding quotes if present
        if len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'"):
            s = s[1:-1]
        
        # unescape some common sequences and collapse whitespace
        s = s.replace('\\n', ' ').replace('\\r', ' ').replace('\\t', ' ')
        s = s.replace('\\"', '"').replace("\\'", "'").replace('\\\\', '\\')

        # strip HTML tags
        s = re.sub(r'<[^>]+>', '', s)
        s = re.sub(r'\s+', ' ', s).strip()

        return s

    # find new Listview(...) occurrences and parse the object body reliably
    # Collect all candidate `drops` blocks and pick the one with the most objects.
    candidates = []

    for m in re.finditer(r'new Listview\s*\(', html):
        start_paren = m.end()
        brace_idx = html.find('{', start_paren)

        if brace_idx == -1:
            continue

        end_brace = find_matching_bracket(html, brace_idx, '{', '}')

        if end_brace == -1:
            continue

        block = html[brace_idx:end_brace+1]

        if not re.search(r"id\s*:\s*['\"]drops['\"]", block):
            continue

        # locate data: [ ... ] inside the block
        data_key = re.search(r'data\s*:\s*\[', block)

        if not data_key:
            continue

        data_start = block.find('[', data_key.start())
        data_end = find_matching_bracket(block, data_start, '[', ']')

        if data_end == -1:
            continue

        data_str = block[data_start+1:data_end]

        # extract each top-level object from the array body
        obj_strs = extract_objects_from_array_str(data_str)
        candidate_loot = []

        for o in obj_strs:
            idm = re.search(r"['\"]id['\"]\s*:\s*(\d+)", o)

            if not idm:
                continue

            item_id = int(idm.group(1))
            name_m = re.search(r"['\"](?:name|displayName)['\"]\s*:\s*('(?:[^']|\\\\')*'|\"(?:[^\"\\\"]|\\\\\")*\")", o, flags=re.S)
            name = clean_js_string(name_m.group(1)) if name_m else ''
            quality_m = re.search(r"['\"]quality['\"]\s*:\s*(\d+)", o)
            quality = int(quality_m.group(1)) if quality_m else 0

            # try to capture flags/metadata if present in the object (may be string, number, array or object)
            flags_m = re.search(r"['\"]flags['\"]\s*:\s*('(?:[^']|\\\\')*'|\"(?:[^\"\\\"]|\\\\\")*\"|\{[^}]*\}|\[[^\]]*\]|[0-9]+)", o, flags=re.S)
            flags_raw = clean_js_string(flags_m.group(1)) if flags_m else ''
            
            # Also check for classs field (common for quest items) - note the triple 's' is intentional for Wowhead data
            classs_m = re.search(r"['\"]classs['\"]\s*:\s*(\d+)", o)
            classs_val = int(classs_m.group(1)) if classs_m else None
            
            # Check subclass field as well
            subclass_m = re.search(r"['\"]subclass['\"]\s*:\s*(\d+)", o)
            subclass_val = int(subclass_m.group(1)) if subclass_m else None

            # try to capture drop chance if present (percentage, may be float)
            chance_m = re.search(r"['\"](?:dropChance|drop_chance|chance|pct|percent)['\"]\s*:\s*([0-9]+(?:\.[0-9]+)?)", o, flags=re.I)
            drop_chance = None

            if chance_m:
                try:
                    # keep the raw float value (preserve precision up to 2 decimals)
                    drop_chance = round(float(chance_m.group(1)), 2)
                except Exception:
                    drop_chance = None

            # fallback: try to compute percent from modes: { ... "0": {"count":X,"outof":Y}, ... }
            def extract_percent_from_modes(obj_str):
                """Extract percent shown on the NPC drops table.

                Strategy (robust and conservative):
                1. Prefer the top-level `count`/`outof` pair (the last such pair
                   in the object text) — this matches the value shown for the
                   current Listview filter on the NPC page.
                3. Fallback to the numeric mode entry with the largest sample
                   (largest outof).
                Returns a float percentage or None.
                """
                # 1) Find any count/outof matches and pick the first one that
                # appears at brace-depth==1 (a direct member of the object).
                matches = list(re.finditer(r'"count"\s*:\s*(-?\d+)\s*,\s*"outof"\s*:\s*(\d+)', obj_str))

                def compute_depth_at(s, idx):
                    depth = 0
                    in_str = None
                    esc = False
                    i = 0

                    while i < idx:
                        ch = s[i]

                        if in_str:
                            if esc:
                                esc = False
                            elif ch == '\\':
                                esc = True
                            elif ch == in_str:
                                in_str = None
                            i += 1
                            continue

                        if ch == '"' or ch == "'":
                            in_str = ch
                            i += 1
                            continue

                        if ch == '{':
                            depth += 1
                        elif ch == '}':
                            depth -= 1

                        i += 1

                    return depth

                # collect one top-level (depth==1) count/outof if present, but
                # don't return immediately because we prefer the "all" mode (0)
                top_level = None

                for m in matches:
                    try:
                        idx = m.start()
                        depth = compute_depth_at(obj_str, idx)

                        if depth == 1:
                            cnt = int(m.group(1))
                            outof = int(m.group(2))

                            if outof > 0 and cnt >= 0:
                                top_level = (cnt, outof)
                                break
                    except Exception:
                        continue

                # 2) parse the `modes` block and prefer mode '0' (all-data) first
                mm = re.search(r'["\']?modes["\']?\s*:\s*\{', obj_str)

                if not mm:
                    # if no modes block, fall back to any top-level we found
                    if top_level:
                        cnt, outof = top_level

                        return (float(cnt) / float(outof)) * 100.0
                    
                    return None

                start_idx = obj_str.find('{', mm.end()-1)

                if start_idx == -1:
                    if top_level:
                        cnt, outof = top_level

                        return (float(cnt) / float(outof)) * 100.0
                    
                    return None

                end_idx = find_matching_bracket(obj_str, start_idx, '{', '}')

                if end_idx == -1:
                    if top_level:
                        cnt, outof = top_level

                        return (float(cnt) / float(outof)) * 100.0
                    
                    return None

                modes_body = obj_str[start_idx+1:end_idx]

                pattern = re.compile(r'["\']?(\d+)["\']?\s*:\s*\{[^}]*?"count"\s*:\s*(-?\d+)[^}]*?"outof"\s*:\s*(-?\d+)[^}]*?\}', flags=re.S)
                entries = {}

                for m2 in pattern.finditer(modes_body):
                    try:
                        key = m2.group(1)
                        cnt = int(m2.group(2))
                        outof = int(m2.group(3))
                    except Exception:
                        continue

                    if outof and outof > 0 and cnt >= 0:
                        entries[key] = (cnt, outof)

                if not entries:
                    # fallback to top-level if modes present but no usable entries
                    if top_level:
                        cnt, outof = top_level

                        return (float(cnt) / float(outof)) * 100.0
                    
                    return None

                # prefer key '0' (all data) when available
                if '0' in entries:
                    cnt, outof = entries['0']

                    return (float(cnt) / float(outof)) * 100.0

                # otherwise pick the mode with the largest sample
                key, (cnt, outof) = max(entries.items(), key=lambda kv: kv[1][1])

                return (float(cnt) / float(outof)) * 100.0

            if drop_chance is None:
                try:
                    drop_chance = extract_percent_from_modes(o)
                except Exception:
                    drop_chance = None

            candidate_loot.append({
                'id': item_id, 
                'name': name, 
                'quality': quality, 
                'flags': flags_raw, 
                'classs': classs_val,
                'subclass': subclass_val,
                'drop_chance': drop_chance
            })
        if candidate_loot:
            candidates.append(candidate_loot)

    # pick the candidate with the most items (if any)
    if candidates:
        loot = max(candidates, key=lambda c: len(c))

    if not loot:
        print(f"[!] Could not locate listviewitems JSON for NPC {npc_id}")

        return []

    items = []

    for item in loot:
        item_id   = item.get("id")
        name      = item.get("name", "")
        quality   = item.get("quality", 0)

        if item_id is None:
            continue
        if item_id > MAX_ITEM_ID_LEGION:
            # skip newer-than-Legion item
            continue
        if item_id in EXCLUDED_ITEM_IDS:
            # skip excluded item
            continue

        is_recipe = False
        profession = None
        lower_name = name.lower()

        for prof in PROFESSIONS:
            if f"recipe: " in lower_name and prof in lower_name:
                is_recipe = True
                profession = PROFESSIONS[prof]
                break

        # Quest item detection: classs=12 is Quest item class in WoW
        is_quest = (item.get("classs") == 12) or "quest item" in lower_name or ("quest" in item.get("flags", "").lower())
        is_legendary = (quality >= 5)

        items.append({
            "id":          item_id,
            "name":        name,
            "quality":     quality,
            "is_recipe":   is_recipe,
            "profession":  profession,
            "is_quest":     is_quest,
            "is_legendary": is_legendary,
            "drop_chance":  item.get('drop_chance'),
            "classs":      item.get('classs'),
            "subclass":    item.get('subclass')
        })

    return items


def fetch_item_info(item_id, cache_dir=None, timeout=10):
    """Fetch item page and extract basic info (name, quality, recipe/profession, quest, legendary).
    Uses a simple file cache if cache_dir is provided.
    Returns a dict with keys: id, name, quality, is_recipe, profession, is_quest, is_legendary
    """
    info = {
        "id": item_id,
        "name": "",
        "quality": 0,
        "is_recipe": False,
        "profession": None,
        "is_quest": False,
        "is_legendary": False,
    }

    cache_path = None

    if cache_dir:
        try:
            os.makedirs(cache_dir, exist_ok=True)

            cache_path = os.path.join(cache_dir, f"{item_id}.html")

            if os.path.exists(cache_path):
                html = open(cache_path, 'r', encoding='utf-8').read()
            else:
                raise FileNotFoundError()
        except FileNotFoundError:
            html = None
    else:
        html = None

    if html is None:
        url = f"https://www.wowhead.com/item={item_id}"

        # Retry logic with exponential backoff to handle rate limiting
        max_retries = 3
        retry_delay = 1.0
        
        for attempt in range(max_retries):
            try:
                # Use more complete headers to appear as a legitimate browser
                headers = {
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.5",
                    "Accept-Encoding": "gzip, deflate",
                    "Connection": "keep-alive",
                    "Upgrade-Insecure-Requests": "1"
                }
                
                resp = requests.get(url, headers=headers, timeout=timeout)

                if resp.status_code == 200:
                    html = resp.text

                    if cache_path:
                        try:
                            with open(cache_path, 'w', encoding='utf-8') as f:
                                f.write(html)
                        except Exception:
                            pass

                    # Report successful retry if this wasn't the first attempt
                    if attempt > 0:
                        print(f"[+] Successfully fetched item {item_id} on retry attempt {attempt + 1}")

                    # be polite to remote host - longer delay between requests
                    time.sleep(0.5 + (attempt * 0.2))
                    break
                elif resp.status_code == 429:  # Rate limited
                    if attempt < max_retries - 1:
                        wait_time = retry_delay * (2 ** attempt)

                        print(f"[!] Rate limited on item {item_id}, waiting {wait_time}s before retry {attempt + 1}/{max_retries}")
                        time.sleep(wait_time)
                        continue
                    else:
                        print(f"[!] Rate limit exceeded for item {item_id} after {max_retries} attempts")
                        
                        return info
                else:
                    print(f"[!] HTTP {resp.status_code} when fetching item {item_id}")
                    
                    return info
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = retry_delay * (2 ** attempt)
                    
                    print(f"[!] Error fetching item {item_id}: {e}, retrying in {wait_time}s")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"[!] Failed to fetch item {item_id} after {max_retries} attempts: {e}")
                    
                    return info
    
    if html is None:
        return info

    # parse
    try:
        soup = BeautifulSoup(html, 'html.parser')
    except Exception:
        return info

    # Try to find a JSON blob in known script IDs
    json_text = None

    for sid in ('data.page.info', 'data.pageMeta', 'data.page'):
        tag = soup.find('script', {'type': 'application/json', 'id': sid})

        if tag and tag.string:
            json_text = tag.string
            break

    if json_text:
        try:
            parsed = json.loads(json_text)

            # possible locations for name/quality vary; try common keys
            if isinstance(parsed, dict):
                if 'name' in parsed:
                    info['name'] = parsed.get('name') or info['name']

                # sometimes tooltip/data contains nested structures
                if 'tooltip' in parsed and isinstance(parsed['tooltip'], dict):
                    t = parsed['tooltip']
                    info['name'] = t.get('name', info['name'])

                if 'quality' in parsed:
                    try:
                        info['quality'] = int(parsed.get('quality', info['quality']))
                    except Exception:
                        pass
        except Exception:
            pass

    # Also look for generic LD+JSON blocks which often contain a description
    # that mentions the profession for recipes (e.g., "This alchemy recipe is used for the Alchemy profession.")
    try:
        for tag in soup.find_all('script', {'type': 'application/ld+json'}):
            try:
                ld = json.loads(tag.string or '{}')
            except Exception:
                continue

            # ld might be a dict or list
            if isinstance(ld, dict):
                if not info['name'] and 'name' in ld:
                    info['name'] = ld.get('name') or info['name']
                if 'description' in ld and ld.get('description'):
                    desc = ld.get('description') or ''
                    ldesc = str(desc).lower()

                    # check for recipe/profession mention
                    for prof in PROFESSIONS:
                        if prof in ldesc:
                            info['profession'] = PROFESSIONS[prof]
                            info['is_recipe'] = info['is_recipe'] or ('recipe' in ldesc or 'recette' in ldesc)
                            break
            elif isinstance(ld, list):
                for entry in ld:
                    if isinstance(entry, dict) and 'description' in entry:
                        ldesc = str(entry.get('description') or '').lower()

                        for prof in PROFESSIONS:
                            if prof in ldesc:
                                info['profession'] = PROFESSIONS[prof]
                                info['is_recipe'] = info['is_recipe'] or ('recipe' in ldesc)
                                break
    except Exception:
        pass

    # Meta description and Open Graph description often include profession/recipe cues
    try:
        m = soup.find('meta', {'name': 'description'})

        if m and m.get('content'):
            c = str(m.get('content') or '').lower()

            for prof in PROFESSIONS:
                if prof in c:
                    info['profession'] = PROFESSIONS[prof]
                    info['is_recipe'] = info['is_recipe'] or ('recipe' in c or 'recette' in c)
                    break
        
        og = soup.find('meta', {'property': 'og:description'})

        if og and og.get('content'):
            c = str(og.get('content') or '').lower()

            for prof in PROFESSIONS:
                if prof in c:
                    info['profession'] = PROFESSIONS[prof]
                    info['is_recipe'] = info['is_recipe'] or ('recipe' in c)
                    break
    except Exception:
        pass

    # fallback: heading or title
    if not info['name']:
        h1 = soup.find(['h1', 'h2'])

        if h1:
            info['name'] = h1.get_text(strip=True)
        else:
            # title tag fallback
            t = soup.find('title')

            if t and t.string:
                info['name'] = t.string.split('—')[0].split('-')[0].strip()

    # quality heuristics: look for "quality" in the HTML JSON or q-class near the name
    if info['quality'] == 0:
        m = re.search(r'"quality"\s*:\s*(\d+)', html)

        if m:
            try:
                info['quality'] = int(m.group(1))
            except Exception:
                pass

    # check for CSS quality class (e.g., class="q3") near the name
    try:
        if info['name']:
            # find element containing the item name text (use 'string' argument; 'text' is deprecated)
            el = soup.find(string=re.compile(re.escape(info['name'])))
            parent = el.parent if el and getattr(el, 'parent', None) else None

            if parent:
                cls = parent.get('class') or []
                for c in cls:
                    m = re.match(r'q(\d)', c)
                    if m:
                        info['quality'] = int(m.group(1))
                        break
    except Exception:
        pass

    lname = (info['name'] or '').lower()

    # recipe detection (common prefixes)
    recipe_keywords = ['recipe', 'pattern', 'plans', 'technique', 'design', 'formula', 'schematic']

    for kw in recipe_keywords:
        if kw in lname:
            info['is_recipe'] = True
            break

    # profession detection using name clues
    for prof in PROFESSIONS:
        if prof in lname:
            info['profession'] = PROFESSIONS[prof]
            if info['is_recipe']:
                break

    # quest detection
    if 'quest' in lname or 'quest item' in html.lower():
        info['is_quest'] = True

    # legendary heuristics
    try:
        info['is_legendary'] = int(info.get('quality', 0)) >= 5
    except Exception:
        info['is_legendary'] = False

    return info


def enrich_items(items, cache_dir=None):
    """Given a list of item dicts (with at least 'id'), fetch each item's page and enrich fields.
    Returns a new list with enriched items.
    """
    enriched = []

    for it in items:
        iid = it.get('id')

        if iid is None:
            continue

        details = fetch_item_info(iid, cache_dir=cache_dir)
        name = details.get('name') or it.get('name') or ''
        quality = details.get('quality', it.get('quality', 0))
        is_recipe = details.get('is_recipe', False)
        profession = details.get('profession')
        is_quest = details.get('is_quest', False)
        is_legendary = details.get('is_legendary', False)

        enriched.append({
            'id': iid,
            'name': name,
            'quality': quality,
            'is_recipe': is_recipe,
            'profession': profession,
            'is_quest': is_quest,
            'is_legendary': is_legendary,
        })
    return enriched

def decide_chance(item):
    """ Decide the drop-chance column value based on heuristics. 
    Quest items get negative drop rates.
    """
    # Only use NPC-provided drop chance. If missing, return None so callers
    # can decide to skip emitting SQL rows for that item.
    dc = item.get('drop_chance')

    if dc is None:
        return None
    
    try:
        # return a float rounded to 2 decimal places (keeps precision if provided)
        f = round(float(dc), 2)
        # if explicit 0.0% is present, treat it as a small non-zero fallback
        # so the item remains usable in game (use 0.1% as requested)
        if f == 0.0:
            f = 0.1
        
        # Quest items should have negative drop rates
        if item.get('is_quest'):
            f = -abs(f)
        
        return f
    except Exception:
        return None

def produce_sql(npc_id, items, lootmode=23, groupid=0, mincount=1, maxcount=1, shared=0):
    """ Produce the SQL REPLACE block and commented list."""
    # map numeric quality to human label
    quality_labels = {
        0: 'poor',
        1: 'common',
        2: 'green',
        3: 'rare',
        4: 'epic',
        5: 'legendary'
    }

    # Build comment lines and SQL values only for items that have an
    # NPC-provided drop chance. Items without a provided chance are
    # skipped (with a message) and not included in the output.
    comment_lines = [f"/* NPC {npc_id} loot list"]
    vals = []
    skipped = []

    for it in items:
        iid = it['id']
        chance = decide_chance(it)

        if chance is None:
            skipped.append(iid)
            continue

        # comment parts for this emitted item
        q = int(it.get('quality', 0) or 0)
        qlabel = quality_labels.get(q, f'q{q}')
        parts = []

        # include the computed NPC drop chance (after zero->0.1 fallback)
        try:
            fval = float(chance)
            if abs(fval - round(fval)) < 1e-9:
                parts.append(f"chance:{int(round(fval))}%")
            else:
                parts.append(f"chance:{round(fval,2)}%")
        except Exception:
            pass

        # mark quest items in the comment
        if it.get('is_quest'):
            parts.append('quest')

        # quality
        parts.append(f"quality:{qlabel}")

        # recipe / profession
        if it.get('is_recipe'):
            prof = it.get('profession') or 'unknown'
            parts.append(f"{prof} (recipe)")

        # legendary
        if it.get('is_legendary'):
            parts.append('legendary')
			
		# name
        parts.append(f"name:{it.get('name')}")

        comment = f"{iid}"

        if parts:
            comment += " -- " + " -- ".join(parts)

        comment_lines.append(comment)

        # format chance for SQL: integer if whole number, otherwise up to 2 decimals
        if abs(chance - round(chance)) < 1e-9:
            chance_sql = str(int(round(chance)))
        else:
            chance_sql = ('{:.2f}'.format(chance)).rstrip('0').rstrip('.')

        vals.append(f"(@NPC,{iid},{chance_sql},{lootmode},{groupid},{mincount},{maxcount},{shared})")

    comment_lines.append("*/\n")

    sql_lines = []
    sql_lines.append(f"SET @NPC := {npc_id};")
    sql_lines.append("REPLACE INTO creature_loot_template (`entry`,`item`,`ChanceOrQuestChance`,`lootmode`,`groupid`,`mincountOrRef`,`maxcount`,`shared`) VALUES")

    if skipped:
        print(f"[!] Skipping {len(skipped)} items with no NPC-provided drop chance: {skipped}")

    sql_lines.append(",\n".join(vals) + ";")

    # Generate loot conditionals for recipe items that require a profession check.
    # We create a DELETE for any existing entries for these items and then
    # INSERT the standard "Has Profession" and "No Item" conditions per item.
    recipe_items = [it for it in items if it.get('is_recipe') and it.get('profession') and it.get('id')]

    # map to those with a known spell id
    recipe_with_spell = [(it['id'], it['profession']) for it in recipe_items if PROFESSION_SPELL_ID.get(it['profession'])]

    if recipe_with_spell:
        ids = ",".join(str(i) for i, _ in recipe_with_spell)
        sql_lines.append("\n-- loot conditions")
        sql_lines.append(f"DELETE FROM conditions WHERE `SourceTypeOrReferenceId`=1\n    AND `SourceGroup`=@NPC\n    AND `SourceEntry` IN ({ids}); -- item IDs")
        sql_lines.append("INSERT INTO conditions (`SourceTypeOrReferenceId`, `SourceGroup`, `SourceEntry`, `SourceId`, `ElseGroup`, `ConditionTypeOrReference`, `ConditionTarget`, `ConditionValue1`, `ConditionValue2`, `ConditionValue3`, `NegativeCondition`, `ErrorTextId`, `ScriptName`, `Comment`) VALUES")
        cond_vals = []

        for iid, prof in recipe_with_spell:
            spell = PROFESSION_SPELL_ID.get(prof)

            # Has profession condition (ConditionType 7 using profession spell id)
            cond_vals.append(f"(1, @NPC, {iid}, 0, 1, 7, 0, {spell}, 1, 0, 0, 0, '', 'Item Drop - Has {prof.capitalize()}')")
            
            # No-item fallback condition (ConditionType 2 pointing at item)
            cond_vals.append(f"(1, @NPC, {iid}, 0, 1, 2, 0, {iid}, 1, 1, 1, 0, '', 'Item Drop - No Item')")

        sql_lines.append(",\n".join(cond_vals) + ";")

    return "\n".join(comment_lines + sql_lines)

def main():
    parser = argparse.ArgumentParser(description="Wowhead loot extractor for NPCs")
    parser.add_argument("--npc", required=True, help="Comma-separated list of NPC IDs to process (e.g. --npc 96028 or --npc 96028,12345)")
    parser.add_argument("--outdir", default="output", help="Directory for output files")

    args = parser.parse_args()

    os.makedirs(args.outdir, exist_ok=True)

    # parse comma-separated npc list
    npc_arg = args.npc or ''
    npc_list = []

    for part in re.split(r'\s*,\s*', npc_arg.strip()):
        if not part:
            continue
        try:
            npc_list.append(int(part))
        except Exception:
            print(f"[!] Invalid NPC id in --npc: {part}")

    if not npc_list:
        print("[!] No valid NPC ids provided. Use --npc 96028 or --npc 96028,12345")
        return

    for npc in npc_list:
        items = fetch_loot(npc)

        if not items:
            print(f"[!] No items found for NPC {npc}, skipping.")
            continue

        # Enrich items using NPC-embedded data only (default). We keep the
        # per-item fetch functions in the file for future use, but do not call
        # them by default to avoid rate-limits.
        def local_enrich(items_in):
            enriched_local = []
            recipe_keywords = ['recipe', 'pattern', 'plans', 'technique', 'design', 'formula', 'schematic']

            for it in items_in:
                iid = it.get('id')
                name = it.get('name', '') or ''
                lname = name.lower()
                quality = it.get('quality', 0)
                is_recipe = any(kw in lname for kw in recipe_keywords)
                profession = None

                if is_recipe:
                    for prof in PROFESSIONS:
                        if prof in lname:
                            profession = PROFESSIONS[prof]
                            break

                # Quest detection: classs=12 is the Quest item class
                is_quest = (it.get('classs') == 12) or 'quest' in lname or ('quest item' in (it.get('flags') or '').lower())
                is_legendary = int(quality) >= 5 if isinstance(quality, int) or (isinstance(quality, str) and quality.isdigit()) else False
                enriched_local.append({
                    'id': iid,
                    'name': name,
                    'quality': int(quality) if isinstance(quality, int) or (isinstance(quality, str) and quality.isdigit()) else 0,
                    'is_recipe': is_recipe,
                    'profession': profession,
                    'is_quest': is_quest,
                    'is_legendary': is_legendary,
                    'drop_chance': it.get('drop_chance'),
                    'classs': it.get('classs'),
                    'subclass': it.get('subclass')
                })

            return enriched_local

        items = local_enrich(items)

        # If some recipe items lack a detected profession, fetch their item pages
        # to determine the profession (and pick up quest flags / better quality/name).
        # Use a cache directory to avoid refetching on subsequent runs.
        cache_dir = os.path.join(args.outdir, '.cache')
        to_fetch = [it for it in items if it.get('is_recipe') and not it.get('profession')]

        if to_fetch:
            print(f"[+] Need to fetch {len(to_fetch)} item pages to identify recipe professions and quest flags...")
            print(f"[+] Using cache directory: {cache_dir}")

            for idx, it in enumerate(to_fetch, 1):
                iid = it.get('id')

                if iid is None:
                    continue

                print(f"[+] Fetching item {iid} ({idx}/{len(to_fetch)})...")
                details = fetch_item_info(iid, cache_dir=cache_dir)

                # update missing fields conservatively
                if details.get('profession'):
                    it['profession'] = details.get('profession')
                if details.get('name'):
                    it['name'] = details.get('name')
                if details.get('quality'):
                    it['quality'] = details.get('quality')
                if details.get('is_quest'):
                    it['is_quest'] = details.get('is_quest')
                if details.get('is_legendary'):
                    it['is_legendary'] = details.get('is_legendary')
        
        # Always produce SQL output
        out = produce_sql(npc, items)

        fname = os.path.join(args.outdir, f"loot_{npc}.sql")

        # Ensure the output file ends with a single newline
        if not out.endswith("\n"):
            out = out + "\n"
        with open(fname, "w", encoding="utf-8") as f:
            f.write(out)

        print(f"[+] Written output for NPC {npc} → {fname}")

if __name__ == "__main__":
    main()
