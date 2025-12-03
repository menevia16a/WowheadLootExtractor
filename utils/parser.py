"""
Parser module for extracting data from HTML and JavaScript objects.
"""

import re
import json
from bs4 import BeautifulSoup

from .config import (
    MAX_ITEM_ID, EXCLUDED_ITEM_IDS, PROFESSIONS,
    QUEST_ITEM_CLASS, RECIPE_KEYWORDS
)
from .utils import find_matching_bracket, extract_objects_from_array_str, clean_js_string, compute_depth_at


def extract_percent_from_modes(obj_str):
    """
    Extract drop percentage from modes object in item data.

    Strategy (robust and conservative):
    1. Prefer the top-level `count`/`outof` pair (direct member of object)
    2. Fallback to numeric mode entry with largest sample (largest outof)
    
    Args:
        obj_str: Object string containing modes data
        
    Returns:
        Float percentage or None if not found
    """
    matches = list(re.finditer(r'"count"\s*:\s*(-?\d+)\s*,\s*"outof"\s*:\s*(\d+)', obj_str))

    # Collect one top-level (depth==1) count/outof if present
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

    # parse the `modes` block and prefer mode '0' (all-data) first
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


def parse_npc_loot_data(html, npc_id):
    """
    Parse NPC loot data from Wowhead HTML page.
    
    Finds the Listview block with id:'drops', extracts the data array,
    and parses each item object.
    
    Args:
        html: HTML content from Wowhead NPC page
        npc_id: NPC ID (for logging)
        
    Returns:
        List of item dicts with id, name, quality, flags, classs, subclass, drop_chance
    """
    loot = []

    # Find new Listview(...) occurrences and parse the object body
    # Collect all candidate `drops` blocks and pick the one with the most objects
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

        # We're looking for the Listview block that contains npc drops
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
            item_data = _parse_item_object(o)

            if item_data:
                candidate_loot.append(item_data)

        if candidate_loot:
            candidates.append(candidate_loot)

    # pick the candidate with the most items (if any)
    if candidates:
        loot = max(candidates, key=lambda c: len(c))

    if not loot:
        print(f"[!] Could not locate listviewitems JSON for NPC {npc_id}")

        return []

    # Filter items by expansion, exclusion list, and extract final item data
    items = []

    for item in loot:
        item_id = item.get("id")
        name = item.get("name", "")
        quality = item.get("quality", 0)

        if item_id is None:
            continue
        if item_id > MAX_ITEM_ID:
            # skip any items above this value (limit expansion drops)
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
        is_quest = (item.get("classs") == QUEST_ITEM_CLASS) or "quest item" in lower_name or ("quest" in item.get("flags", "").lower())
        is_legendary = (quality >= 5)

        items.append({
            "id": item_id,
            "name": name,
            "quality": quality,
            "is_recipe": is_recipe,
            "profession": profession,
            "is_quest": is_quest,
            "is_legendary": is_legendary,
            "drop_chance": item.get('drop_chance'),
            "min_count": item.get('min_count'),
            "max_count": item.get('max_count'),
            "classs": item.get('classs'),
            "subclass": item.get('subclass')
        })

    return items


def parse_object_loot_data(html, obj_id):
    """
    Parse GameObject loot data from Wowhead HTML page.

    Args:
        html: HTML content from Wowhead object page
        obj_id: GameObject ID (for logging)

    Returns:
        List of item dicts with id, name, quality, flags, classs, subclass, drop_chance
    """
    loot = []

    # Find new Listview(...) occurrences and parse the object body
    # We'll mirror the item-page logic: prefer Listview blocks whose id
    # contains 'contains' (object containers), accept inline data arrays or
    # variable references, and fall back to the largest candidate.
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

        # Prefer blocks labelled 'contains' but accept any with data: [ ... ]
        if not re.search(r"id\s*:\s*['\"][^'\"]*(contains)[^'\"]*['\"]", block, flags=re.I):
            if not re.search(r'data\s*:\s*\[', block):
                continue

        # data may be inline (data: [ ... ]) or a variable reference (data: someVar)
        mdata = re.search(r"data\s*:\s*(\[|[A-Za-z0-9_\$\.]+)", block)

        if not mdata:
            continue

        data_str = None

        if mdata.group(1) == '[':
            # inline array inside the Listview block
            data_start = block.find('[', mdata.start())
            data_end = find_matching_bracket(block, data_start, '[', ']')

            if data_end == -1:
                continue

            data_str = block[data_start+1:data_end]
        else:
            # data references a variable name; try to find its array assignment elsewhere
            varname = mdata.group(1).strip()

            pat = re.compile(r'(?:var\s+|window\.)?' + re.escape(varname) + r'\s*=\s*\[', flags=re.I)
            mvar = pat.search(html)

            if not mvar:
                scan_start = max(0, brace_idx - 5000)
                scan_end = min(len(html), end_brace + 5000)
                mvar = pat.search(html[scan_start:scan_end])

                if not mvar:
                    continue

                var_idx = scan_start + mvar.start()
            else:
                var_idx = mvar.start()

            arr_start = html.find('[', var_idx)

            if arr_start == -1:
                continue

            arr_end = find_matching_bracket(html, arr_start, '[', ']')

            if arr_end == -1:
                continue

            data_str = html[arr_start+1:arr_end]

        if not data_str:
            continue

        obj_strs = extract_objects_from_array_str(data_str)
        candidate_loot = []

        for o in obj_strs:
            item_data = _parse_item_object(o)

            if item_data:
                candidate_loot.append(item_data)

        if candidate_loot:
            is_contains = bool(re.search(r"id\s*:\s*['\"][^'\"]*(contains)[^'\"]*['\"]", block, flags=re.I))
            candidates.append((candidate_loot, is_contains))

    if candidates:
        contains_candidates = [c for c in candidates if c[1]]

        if contains_candidates:
            loot = max(contains_candidates, key=lambda c: len(c[0]))[0]
        else:
            loot = max(candidates, key=lambda c: len(c[0]))[0]

    if not loot:
        print(f"[!] Could not locate listviewitems JSON for GameObject {obj_id}")
        return []

    # Filter items by expansion, exclusion list, and extract final item data
    items = []

    for item in loot:
        item_id = item.get("id")
        name = item.get("name", "")
        quality = item.get("quality", 0)

        if item_id is None:
            continue
        if item_id > MAX_ITEM_ID:
            # skip any items above this value (limit expansion drops)
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
        is_quest = (item.get("classs") == QUEST_ITEM_CLASS) or "quest item" in lower_name or ("quest" in item.get("flags", "").lower())
        is_legendary = (quality >= 5)

        items.append({
            "id": item_id,
            "name": name,
            "quality": quality,
            "is_recipe": is_recipe,
            "profession": profession,
            "is_quest": is_quest,
            "is_legendary": is_legendary,
            "drop_chance": item.get('drop_chance'),
            "min_count": item.get('min_count'),
            "max_count": item.get('max_count'),
            "classs": item.get('classs'),
            "subclass": item.get('subclass')
        })

    return items


def _parse_item_object(obj_str):
    """
    Parse a single item object from Wowhead JavaScript.
    
    Args:
        obj_str: Object string
        
    Returns:
        Dict with item data, or None if ID not found
    """
    idm = re.search(r"['\"]id['\"]\s*:\s*(\d+)", obj_str)

    if not idm:
        return None

    item_id = int(idm.group(1))
    
    # Extract name
    name_m = re.search(r"['\"](?:name|displayName)['\"]\s*:\s*('(?:[^']|\\\\')*'|\"(?:[^\"\\\"]|\\\\\")*\")", obj_str, flags=re.S)
    name = clean_js_string(name_m.group(1)) if name_m else ''
    
    # Extract quality
    quality_m = re.search(r"['\"]quality['\"]\s*:\s*(\d+)", obj_str)
    quality = int(quality_m.group(1)) if quality_m else 0

    # Extract flags/metadata
    flags_m = re.search(r"['\"]flags['\"]\s*:\s*('(?:[^']|\\\\')*'|\"(?:[^\"\\\"]|\\\\\")*\"|\{[^}]*\}|\[[^\]]*\]|[0-9]+)", obj_str, flags=re.S)
    flags_raw = clean_js_string(flags_m.group(1)) if flags_m else ''

    # Extract classs field (note: triple 's' is intentional for Wowhead data)
    classs_m = re.search(r"['\"]classs['\"]\s*:\s*(\d+)", obj_str)
    classs_val = int(classs_m.group(1)) if classs_m else None

    # Extract subclass field
    subclass_m = re.search(r"['\"]subclass['\"]\s*:\s*(\d+)", obj_str)
    subclass_val = int(subclass_m.group(1)) if subclass_m else None

    # Extract drop chance
    chance_m = re.search(r"['\"](?:dropChance|drop_chance|chance|pct|percent)['\"]\s*:\s*([0-9]+(?:\.[0-9]+)?)", obj_str, flags=re.I)
    drop_chance = None

    if chance_m:
        try:
            drop_chance = round(float(chance_m.group(1)), 2)
        except Exception:
            drop_chance = None

    # fallback: try to compute percent from modes
    if drop_chance is None:
        # First try to find top-level `count` and `outof` fields even if they're
        # not immediately adjacent (some Wowhead Listview objects include
        # intermediate fields like `pctstack` between them). We prefer top-level
        # occurrences (depth == 1).
        try:
            count_matches = list(re.finditer(r'"count"\s*:\s*(-?\d+)', obj_str))
            outof_matches = list(re.finditer(r'"outof"\s*:\s*(\d+)', obj_str))

            pair_found = False

            for cm in count_matches:
                cidx = cm.start()
                cdepth = compute_depth_at(obj_str, cidx)

                if cdepth != 1:
                    continue

                # find the first outof match after this count
                next_out = None

                for om in outof_matches:
                    if om.start() > cm.start():
                        od = compute_depth_at(obj_str, om.start())

                        if od == 1:
                            next_out = om
                            break

                if next_out:
                    try:
                        cnt = int(cm.group(1))
                        outof = int(next_out.group(1))

                        if outof > 0 and cnt >= 0:
                            drop_chance = (float(cnt) / float(outof)) * 100.0
                            pair_found = True
                            break
                    except Exception:
                        continue

            # Fallback to existing modes-based extraction if no simple pair found
            if not pair_found:
                drop_chance = extract_percent_from_modes(obj_str)
        except Exception:
            try:
                drop_chance = extract_percent_from_modes(obj_str)
            except Exception:
                drop_chance = None

    # Extract stack/min-max quantities for contained items (e.g. [20,40])
    min_count = None
    max_count = None

    try:
        # accept quoted or unquoted key names (Wowhead data sometimes omits quotes)
        stack_m = re.search(r"(?:['\"]?stack['\"]?)\s*:\s*\[\s*(\d+)\s*,\s*(\d+)\s*\]", obj_str)

        if stack_m:
            try:
                min_count = int(stack_m.group(1))
                max_count = int(stack_m.group(2))
            except Exception:
                min_count = None
                max_count = None
        else:
            # some pages may present single-value stacks (e.g. [20])
            stack_single = re.search(r"(?:['\"]?stack['\"]?)\s*:\s*\[\s*(\d+)\s*\]", obj_str)

            if stack_single:
                try:
                    min_count = int(stack_single.group(1))
                    max_count = int(stack_single.group(1))
                except Exception:
                    min_count = None
                    max_count = None
    except Exception:
        min_count = None
        max_count = None

    return {
        'id': item_id,
        'name': name,
        'quality': quality,
        'flags': flags_raw,
        'classs': classs_val,
        'subclass': subclass_val,
        'drop_chance': drop_chance,
        'min_count': min_count,
        'max_count': max_count
    }


def parse_item_page(html, info):
    """
    Parse individual item page from Wowhead.
    
    Extracts name, quality, profession, recipe status, and quest status
    from various HTML elements and JSON blocks.
    
    Args:
        html: HTML content from Wowhead item page
        info: Base info dict to populate
        
    Returns:
        Updated info dict
    """
    try:
        soup = BeautifulSoup(html, 'html.parser')
    except Exception:
        return info

    # Try to find JSON blob in known script IDs
    json_text = None

    for sid in ('data.page.info', 'data.pageMeta', 'data.page'):
        tag = soup.find('script', {'type': 'application/json', 'id': sid})

        if tag and tag.string:
            json_text = tag.string
            break

    if json_text:
        try:
            parsed = json.loads(json_text)

            if isinstance(parsed, dict):
                if 'name' in parsed:
                    info['name'] = parsed.get('name') or info['name']
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

    # Look for LD+JSON blocks with description
    try:
        for tag in soup.find_all('script', {'type': 'application/ld+json'}):
            try:
                ld = json.loads(tag.string or '{}')
            except Exception:
                continue

            if isinstance(ld, dict):
                if not info['name'] and 'name' in ld:
                    info['name'] = ld.get('name') or info['name']
                if 'description' in ld and ld.get('description'):
                    _extract_profession_from_description(ld.get('description'), info)
            elif isinstance(ld, list):
                for entry in ld:
                    if isinstance(entry, dict) and 'description' in entry:
                        _extract_profession_from_description(entry.get('description'), info)
    except Exception:
        pass

    # Extract from meta descriptions
    try:
        m = soup.find('meta', {'name': 'description'})

        if m and m.get('content'):
            _extract_profession_from_description(m.get('content'), info)

        og = soup.find('meta', {'property': 'og:description'})

        if og and og.get('content'):
            _extract_profession_from_description(og.get('content'), info)
    except Exception:
        pass

    # fallback: heading or title
    if not info['name']:
        h1 = soup.find(['h1', 'h2'])

        if h1:
            info['name'] = h1.get_text(strip=True)
        else:
            t = soup.find('title')

            if t and t.string:
                info['name'] = t.string.split('—')[0].split('-')[0].strip()

    # Extract quality from HTML JSON or CSS class
    if info['quality'] == 0:
        m = re.search(r'"quality"\s*:\s*(\d+)', html)

        if m:
            try:
                info['quality'] = int(m.group(1))
            except Exception:
                pass

    try:
        if info['name']:
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

    # Recipe detection
    for kw in RECIPE_KEYWORDS:
        if kw in lname:
            info['is_recipe'] = True
            break

    # Profession detection
    for prof in PROFESSIONS:
        if prof in lname:
            info['profession'] = PROFESSIONS[prof]
            
            if info['is_recipe']:
                break

    # Quest detection
    if 'quest' in lname or 'quest item' in html.lower():
        info['is_quest'] = True

    # Legendary detection
    try:
        info['is_legendary'] = int(info.get('quality', 0)) >= 5
    except Exception:
        info['is_legendary'] = False

    return info


def _extract_profession_from_description(description, info):
    """
    Extract profession and recipe info from a description string.
    
    Args:
        description: Text to search
        info: Info dict to update
    """
    if not description:
        return

    desc = str(description).lower()

    for prof in PROFESSIONS:
        if prof in desc:
            info['profession'] = PROFESSIONS[prof]
            info['is_recipe'] = info['is_recipe'] or ('recipe' in desc or 'recette' in desc)
            return


def parse_item_loot_data(html, item_id):
    """
    Parse loot/contains data for an item page.

    Scans all new Listview(...) blocks in the HTML and picks the
    candidate array (data: [ ... ]) that contains the most item objects
    and looks like a contains block.

    Returns a list of item dicts compatible with the enricher expectation
    (id, name, quality, etc.).
    """
    loot = []

    # candidates: list of tuples (candidate_loot_list, is_contains_block)
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

        # Find contains block
        if not re.search(r"id\s*:\s*['\"][^'\"]*(contains)[^'\"]*['\"]", block, flags=re.I):
            # still accept blocks that simply have a data: [ ... ] and item objects
            if not re.search(r'data\s*:\s*\[', block):
                continue

        # data may be inline (data: [ ... ]) or a variable reference (data: someVar)
        mdata = re.search(r"data\s*:\s*(\[|[A-Za-z0-9_\$\.]+)", block)

        if not mdata:
            continue

        data_str = None

        if mdata.group(1) == '[':
            # inline array inside the Listview block
            data_start = block.find('[', mdata.start())
            data_end = find_matching_bracket(block, data_start, '[', ']')

            if data_end == -1:
                continue

            data_str = block[data_start+1:data_end]
        else:
            # data references a variable name; try to find its array assignment elsewhere
            varname = mdata.group(1).strip()

            # look for patterns like: var varname = [ ... ] or window.varname = [ ... ] or varname = [ ... ]
            pat = re.compile(r'(?:var\s+|window\.)?' + re.escape(varname) + r'\s*=\s*\[', flags=re.I)
            mvar = pat.search(html)

            if not mvar:
                # limit scan to a reasonable window around this listview to avoid false positives
                scan_start = max(0, brace_idx - 5000)
                scan_end = min(len(html), end_brace + 5000)
                mvar = pat.search(html[scan_start:scan_end])

                if not mvar:
                    continue

                var_idx = scan_start + mvar.start()
            else:
                var_idx = mvar.start()

            arr_start = html.find('[', var_idx)

            if arr_start == -1:
                continue

            arr_end = find_matching_bracket(html, arr_start, '[', ']')

            if arr_end == -1:
                continue

            data_str = html[arr_start+1:arr_end]

        if not data_str:
            continue

        obj_strs = extract_objects_from_array_str(data_str)
        candidate_loot = []

        for o in obj_strs:
            item_data = _parse_item_object(o)

            if item_data:
                candidate_loot.append(item_data)

        if candidate_loot:
            # detect whether this listview's id contains the word 'contains'
            is_contains = bool(re.search(r"id\s*:\s*['\"][^'\"]*(contains)[^'\"]*['\"]", block, flags=re.I))

            candidates.append((candidate_loot, is_contains))

    if candidates:
        # Prefer candidates that explicitly look like a 'contains' block
        contains_candidates = [c for c in candidates if c[1]]

        if contains_candidates:
            # choose the contains candidate with the most items
            loot = max(contains_candidates, key=lambda c: len(c[0]))[0]
        else:
            # fall back to the largest candidate overall
            loot = max(candidates, key=lambda c: len(c[0]))[0]

    if not loot:
        print(f"[!] Could not locate listview/contains JSON for item {item_id}")
        
        return []

    # Filter and normalize
    items = []

    for item in loot:
        item_id_val = item.get("id")
        name = item.get("name", "")
        quality = item.get("quality", 0)

        if item_id_val is None:
            continue
        if item_id_val > MAX_ITEM_ID:
            continue
        if item_id_val in EXCLUDED_ITEM_IDS:
            continue

        is_recipe = False
        profession = None
        lower_name = (name or '').lower()

        for prof in PROFESSIONS:
            if f"recipe: " in lower_name and prof in lower_name:
                is_recipe = True
                profession = PROFESSIONS[prof]
                break

        is_quest = (item.get("classs") == QUEST_ITEM_CLASS) or "quest item" in lower_name or ("quest" in str(item.get('flags', '')).lower())
        is_legendary = (quality >= 5)

        items.append({
            "id": item_id_val,
            "name": name,
            "quality": quality,
            "is_recipe": is_recipe,
            "profession": profession,
            "is_quest": is_quest,
            "is_legendary": is_legendary,
            "drop_chance": item.get('drop_chance'),
            "min_count": item.get('min_count'),
            "max_count": item.get('max_count'),
            "classs": item.get('classs'),
            "subclass": item.get('subclass')
        })

    return items
