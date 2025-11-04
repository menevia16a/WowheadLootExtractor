"""
Item enrichment module for detecting and classifying item properties.
"""

from .config import PROFESSIONS, RECIPE_KEYWORDS, QUEST_ITEM_CLASS


class ItemEnricher:
    """Enriches items with computed properties like recipe detection and profession."""

    @staticmethod
    def enrich_from_npc_data(items):
        """
        Enrich items using data provided by NPC page parsing.
        
        Uses NPC-embedded data only to avoid rate limiting. Computes:
        - Recipe detection from name
        - Profession identification
        - Quest item classification
        - Legendary status from quality
        
        Args:
            items: List of raw item dicts from NPC loot parsing
            
        Returns:
            List of enriched item dicts
        """
        enriched = []
        
        for it in items:
            iid = it.get('id')
            
            if iid is None:
                continue
            
            name = it.get('name', '') or ''
            lname = name.lower()
            quality = it.get('quality', 0)
            
            # Recipe detection
            is_recipe = any(kw in lname for kw in RECIPE_KEYWORDS)
            
            # Profession detection
            profession = None
            if is_recipe:
                for prof in PROFESSIONS:
                    if prof in lname:
                        profession = PROFESSIONS[prof]
                        break
            
            # Quest detection: classs=12 is the Quest item class in WoW
            is_quest = (
                (it.get('classs') == QUEST_ITEM_CLASS) or
                'quest' in lname or
                ('quest item' in (it.get('flags') or '').lower())
            )
            
            # Legendary detection
            try:
                is_legendary = int(quality) >= 5
            except (ValueError, TypeError):
                is_legendary = False
            
            # Ensure quality is int
            try:
                quality_int = int(quality) if isinstance(quality, (int, str)) else 0
            except (ValueError, TypeError):
                quality_int = 0
            
            enriched.append({
                'id': iid,
                'name': name,
                'quality': quality_int,
                'is_recipe': is_recipe,
                'profession': profession,
                'is_quest': is_quest,
                'is_legendary': is_legendary,
                'drop_chance': it.get('drop_chance'),
                'classs': it.get('classs'),
                'subclass': it.get('subclass')
            })
        
        return enriched

    @staticmethod
    def update_from_item_page(items, item_fetcher):
        """
        Update items with data fetched from individual item pages.
        
        Fetches only recipe items that lack a detected profession.
        Uses caching to avoid repeated requests.
        
        Args:
            items: List of enriched item dicts
            item_fetcher: ItemInfoFetcher instance
            
        Returns:
            Updated items list
        """
        # Find recipes without profession detection
        to_fetch = [it for it in items if it.get('is_recipe') and not it.get('profession')]
        
        if not to_fetch:
            return items
        
        print(f"[+] Need to fetch {len(to_fetch)} item pages to identify recipe professions...")
        
        for idx, it in enumerate(to_fetch, 1):
            iid = it.get('id')
            if iid is None:
                continue
            
            print(f"[+] Fetching item {iid} ({idx}/{len(to_fetch)})...")
            details = item_fetcher.fetch_item_info(iid)
            
            # Update fields conservatively (only if fetched data provides better info)
            if details.get('profession'):
                it['profession'] = details.get('profession')
            if details.get('name') and not it.get('name'):
                it['name'] = details.get('name')
            if details.get('quality') and not it.get('quality'):
                it['quality'] = details.get('quality')
            if details.get('is_quest'):
                it['is_quest'] = details.get('is_quest')
            if details.get('is_legendary'):
                it['is_legendary'] = details.get('is_legendary')
        
        return items


def decide_drop_chance(item):
    """
    Decide the drop-chance column value based on item properties.
    
    Quest items receive negative drop rates. Items without an
    NPC-provided drop chance return None and will be skipped.
    
    Args:
        item: Item dict with drop_chance and is_quest fields
        
    Returns:
        Float drop chance or None if not available
    """
    dc = item.get('drop_chance')
    
    if dc is None:
        return None
    
    try:
        # return a float rounded to 2 decimal places
        f = round(float(dc), 2)
        
        # if explicit 0.0% is present, treat it as a small non-zero fallback
        # so the item remains usable in game (use 0.1% as requested)
        if f == 0.0:
            f = 0.1
        
        # Quest items should have negative drop rates
        if item.get('is_quest'):
            f = -abs(f)
        
        return f
    except (ValueError, TypeError):
        return None
