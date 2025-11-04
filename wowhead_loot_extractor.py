#!/usr/bin/env python3
"""
Wowhead Loot Extractor - Main entry point.

Given a comma-separated list of NPC IDs, scrapes Wowhead for their loot tables
and generates SQL blocks for SPP-Legion's database.
"""

import argparse
import os
import re
import traceback

from utils import (
    NpcLootFetcher, ItemInfoFetcher, NpcNameFetcher,
    ItemEnricher, SQLGenerator, sanitize_filename
)
from utils import PROFESSIONS, QUALITY_LABELS

def parse_npc_ids(npc_arg):
    """
    Parse comma-separated NPC ID list from command line argument.
    
    Args:
        npc_arg: Comma-separated string of NPC IDs
        
    Returns:
        List of integer NPC IDs
    """
    npc_list = []

    for part in re.split(r'\s*,\s*', (npc_arg or '').strip()):
        if not part:
            continue
        try:
            npc_list.append(int(part))
        except ValueError:
            print(f"[!] Invalid NPC id in --npc: {part}")

    return npc_list


def parse_exclude_ids(exclude_arg):
    """
    Parse comma-separated list of numeric IDs for --exclude flag.

    Returns a set of ints.
    """
    ids = set()

    for part in re.split(r'\s*,\s*', (exclude_arg or '').strip()):
        if not part:
            continue
        try:
            ids.add(int(part))
        except ValueError:
            print(f"[!] Invalid id in --exclude: {part}")

    return ids


def parse_quality_list(q_arg):
    """
    Parse comma-separated quality names for --exclude-quality.

    Validates against QUALITY_LABELS values. Returns a set of lowercase strings.
    """
    allowed = set(v.lower() for v in QUALITY_LABELS.values())
    quals = set()

    for part in re.split(r'\s*,\s*', (q_arg or '').strip()):
        if not part:
            continue

        p = part.lower()

        if p not in allowed:
            print(f"[!] Invalid quality for --exclude-quality: {part}. Allowed: {', '.join(sorted(allowed))}")
            continue

        quals.add(p)

    return quals


def parse_profession_list(p_arg):
    """
    Parse comma-separated profession names for --exclude-profession.

    Validates against PROFESSIONS keys. Returns a set of normalized profession keys.
    """
    allowed = set(PROFESSIONS.keys())
    profs = set()

    for part in re.split(r'\s*,\s*', (p_arg or '').strip()):
        if not part:
            continue

        p = part.lower()

        if p not in allowed:
            print(f"[!] Invalid profession for --exclude-profession: {part}. Allowed: {', '.join(sorted(allowed))}")
            continue

        profs.add(PROFESSIONS[p])

    return profs


def process_npc(npc_id, outdir, use_cache=True, exclude_ids=None, exclude_qualities=None, exclude_professions=None):
    """
    Process a single NPC: fetch loot, enrich data, generate SQL.
    
    Args:
        npc_id: Numeric NPC ID
        outdir: Output directory for SQL files
        use_cache: Whether to cache item pages
        
    Returns:
        True if successful, False otherwise
    """
    # Initialize fetchers
    loot_fetcher = NpcLootFetcher()
    
    cache_dir = os.path.join(outdir, '.cache') if use_cache else None
    item_fetcher = ItemInfoFetcher(cache_dir=cache_dir)
    
    name_fetcher = NpcNameFetcher()

    # Fetch raw loot data
    items = loot_fetcher.fetch_loot(npc_id)

    if not items:
        print(f"[!] No items found for NPC {npc_id}, skipping.")

        return False

    # Enrich items with computed properties
    items = ItemEnricher.enrich_from_npc_data(items)

    # Fetch item pages for recipes that lack profession detection
    print(f"[+] Using cache directory: {cache_dir}")

    items = ItemEnricher.update_from_item_page(items, item_fetcher)

    # Fetch NPC name and sanitize for filename
    npc_name = name_fetcher.fetch_npc_name(npc_id)
    sanitized = sanitize_filename(npc_name)

    print(f"[+] NPC {npc_id} name: {npc_name} -> {sanitized}")

    # Generate SQL
    # Apply exclusions (ids, qualities, professions)
    exclude_ids = exclude_ids or set()
    exclude_qualities = set(q.lower() for q in (exclude_qualities or set()))
    exclude_professions = set(exclude_professions or set())

    if exclude_ids or exclude_qualities or exclude_professions:
        filtered = []

        for it in items:
            iid = it.get('id')

            # Exclude by explicit id
            if iid in exclude_ids:
                print(f"[~] Excluding item {iid}")
                continue

            # Exclude by quality label
            qlabel = QUALITY_LABELS.get(int(it.get('quality', 0)), '').lower()

            if qlabel and qlabel in exclude_qualities:
                print(f"[~] Excluding item {iid} (quality:{qlabel})")
                continue

            # Exclude by profession
            prof = it.get('profession')

            if prof and prof in exclude_professions:
                print(f"[~] Excluding item {iid} (profession:{prof})")
                continue

            filtered.append(it)

        items = filtered

    sql_output = SQLGenerator.generate_loot_sql(npc_id, items, npc_name=npc_name)

    # Write to file
    fname = os.path.join(outdir, f"loot_{npc_id}_{sanitized}.sql")

    # Ensure output ends with single newline
    if not sql_output.endswith("\n"):
        sql_output = sql_output + "\n"

    with open(fname, "w", encoding="utf-8") as f:
        f.write(sql_output)

    print(f"[+] Written output for NPC {npc_id} → {fname}")

    return True


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Wowhead loot extractor for NPCs - generates SQL blocks for SPP-Legion"
    )
    parser.add_argument(
        "--npc",
        required=True,
        help="Comma-separated list of NPC IDs to process (e.g. --npc 96028 or --npc 96028,12345)"
    )
    parser.add_argument(
        "--outdir",
        default="output",
        help="Directory for output files (default: output)"
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable item page caching"
    )
    parser.add_argument(
        "--exclude",
        help="Comma-separated list of item IDs to exclude from output (e.g. --exclude 123,456)",
        default=""
    )
    parser.add_argument(
        "--exclude-quality",
        help="Comma-separated list of quality names to exclude (e.g. --exclude-quality uncommon,rare)",
        default=""
    )
    parser.add_argument(
        "--exclude-profession",
        help="Comma-separated list of profession names to exclude (e.g. --exclude-profession tailoring)",
        default=""
    )

    args = parser.parse_args()

    # Create output directory
    os.makedirs(args.outdir, exist_ok=True)

    # Parse NPC list
    npc_list = parse_npc_ids(args.npc)

    if not npc_list:
        print("[!] No valid NPC ids provided. Use --npc 96028 or --npc 96028,12345")

        return

    # Process each NPC
    use_cache = not args.no_cache

    # Parse exclusion flags
    exclude_ids = parse_exclude_ids(args.exclude)
    exclude_qualities = parse_quality_list(args.exclude_quality)
    exclude_professions = parse_profession_list(args.exclude_profession)

    for npc in npc_list:
        try:
            process_npc(
                npc,
                args.outdir,
                use_cache=use_cache,
                exclude_ids=exclude_ids,
                exclude_qualities=exclude_qualities,
                exclude_professions=exclude_professions,
            )
        except Exception as e:
            print(f"[!] Unexpected error processing NPC {npc}: {e}")
            traceback.print_exc()

if __name__ == "__main__":
    main()
