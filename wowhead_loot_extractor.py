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


def process_npc(npc_id, outdir, use_cache=True):
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

    for npc in npc_list:
        try:
            process_npc(npc, args.outdir, use_cache=use_cache)
        except Exception as e:
            print(f"[!] Unexpected error processing NPC {npc}: {e}")
            traceback.print_exc()

if __name__ == "__main__":
    main()
