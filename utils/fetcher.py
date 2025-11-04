"""
Wowhead fetcher module for retrieving NPC loot and item data via HTTP requests.
"""

import requests
import time
import os

from bs4 import BeautifulSoup
from .config import (
    HTTP_HEADERS, MAX_RETRIES, RETRY_DELAY, REQUEST_TIMEOUT,
    WOWHEAD_NPC_URL, WOWHEAD_OBJECT_URL, WOWHEAD_ITEM_URL
)
from .parser import parse_npc_loot_data, parse_item_page, parse_object_loot_data, parse_item_loot_data
from .utils import find_matching_bracket, extract_objects_from_array_str, clean_js_string


class GameObjectLootFetcher:
    """Fetches and parses GameObject loot data from Wowhead."""

    def __init__(self, http_fetcher=None):
        self.http_fetcher = http_fetcher or RetryableHTTPFetcher()

    def fetch_loot(self, obj_id):
        """
        Fetch loot table items for a given GameObject ID from Wowhead.
        """
        url = WOWHEAD_OBJECT_URL(obj_id)
        print(f"[+] Fetching loot data for GameObject {obj_id} from {url}")

        html = self.http_fetcher.fetch_url(url, description=f"GameObject {obj_id}")

        if html is None:
            return []

        return parse_object_loot_data(html, obj_id)


class RetryableHTTPFetcher:
    """Handles HTTP requests with exponential backoff retry logic."""

    def __init__(self, max_retries=MAX_RETRIES, retry_delay=RETRY_DELAY, timeout=REQUEST_TIMEOUT):
        """
        Initialize the fetcher with retry parameters.
        
        Args:
            max_retries: Maximum number of retry attempts
            retry_delay: Initial retry delay in seconds
            timeout: Request timeout in seconds
        """
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.timeout = timeout

    def fetch_url(self, url, headers=None, description="resource"):
        """
        Fetch URL content with automatic retry on failure.
        
        Args:
            url: URL to fetch
            headers: HTTP headers (uses defaults if None)
            description: Description for logging
            
        Returns:
            Response text on success, None on failure
        """
        if headers is None:
            headers = HTTP_HEADERS

        for attempt in range(self.max_retries):
            try:
                resp = requests.get(url, headers=headers, timeout=self.timeout)

                if resp.status_code == 200:
                    if attempt > 0:
                        print(f"[+] Successfully fetched {description} on retry attempt {attempt + 1}")

                    # polite delay before returning
                    time.sleep(0.2 + (attempt * 0.1))

                    return resp.text

                elif resp.status_code == 429:
                    if attempt < self.max_retries - 1:
                        wait_time = self.retry_delay * (2 ** attempt)
                        print(f"[!] Rate limited when fetching {description}, waiting {wait_time}s before retry {attempt + 1}/{self.max_retries}")
                        time.sleep(wait_time)
                        continue
                    else:
                        print(f"[!] Rate limit exceeded for {description} after {self.max_retries} attempts")

                        return None

                else:
                    print(f"[!] HTTP {resp.status_code} when fetching {description}")

                    return None

            except Exception as e:
                if attempt < self.max_retries - 1:
                    wait_time = self.retry_delay * (2 ** attempt)

                    print(f"[!] Error fetching {description}: {e}, retrying in {wait_time}s")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"[!] Failed to fetch {description} after {self.max_retries} attempts: {e}")
                    return None

        return None


class NpcLootFetcher:
    """Fetches and parses NPC loot data from Wowhead."""

    def __init__(self, http_fetcher=None):
        """
        Initialize the NPC loot fetcher.
        
        Args:
            http_fetcher: RetryableHTTPFetcher instance (creates default if None)
        """
        self.http_fetcher = http_fetcher or RetryableHTTPFetcher()

    def fetch_loot(self, npc_id):
        """
        Fetch loot table items for a given NPC ID from Wowhead.
        
        Args:
            npc_id: Numeric NPC ID
            
        Returns:
            List of dicts with item data, or empty list on failure
        """
        url = WOWHEAD_NPC_URL(npc_id)
        print(f"[+] Fetching loot data for NPC {npc_id} from {url}")

        html = self.http_fetcher.fetch_url(url, description=f"NPC {npc_id}")

        if html is None:
            return []

        return parse_npc_loot_data(html, npc_id)


class ItemInfoFetcher:
    """Fetches and parses individual item information from Wowhead."""

    def __init__(self, cache_dir=None, http_fetcher=None):
        """
        Initialize the item fetcher with optional caching.
        
        Args:
            cache_dir: Directory for HTML caching (disables caching if None)
            http_fetcher: RetryableHTTPFetcher instance (creates default if None)
        """
        self.cache_dir = cache_dir
        self.http_fetcher = http_fetcher or RetryableHTTPFetcher()

    def fetch_item_info(self, item_id):
        """
        Fetch item page and extract basic info.
        
        Args:
            item_id: Numeric item ID
            
        Returns:
            Dict with keys: id, name, quality, is_recipe, profession, is_quest, is_legendary
        """
        # Default empty info structure
        info = {
            "id": item_id,
            "name": "",
            "quality": 0,
            "is_recipe": False,
            "profession": None,
            "is_quest": False,
            "is_legendary": False,
            "min_count": None,
            "max_count": None,
        }

        # Check cache first
        cache_path = None
        html = None

        if self.cache_dir:
            try:
                os.makedirs(self.cache_dir, exist_ok=True)
                cache_path = os.path.join(self.cache_dir, f"{item_id}.html")

                if os.path.exists(cache_path):
                    with open(cache_path, 'r', encoding='utf-8') as f:
                        html = f.read()
            except Exception:
                pass

        # Fetch if not in cache
        if html is None:
            url = WOWHEAD_ITEM_URL(item_id)
            html = self.http_fetcher.fetch_url(url, description=f"item {item_id}")

            if html and cache_path:
                try:
                    with open(cache_path, 'w', encoding='utf-8') as f:
                        f.write(html)
                except Exception:
                    pass

        if html is None:
            return info

        return parse_item_page(html, info)


class ItemLootFetcher:
    """Fetches and parses 'contains' loot data for container item pages."""

    def __init__(self, http_fetcher=None):
        self.http_fetcher = http_fetcher or RetryableHTTPFetcher()

    def fetch_loot(self, item_id):
        """
        Fetch contained loot for a given item ID from Wowhead.
        """
        url = WOWHEAD_ITEM_URL(item_id)
        print(f"[+] Fetching contained loot data for Item {item_id} from {url}")

        html = self.http_fetcher.fetch_url(url, description=f"Item {item_id} contains")

        if html is None:
            return []

        # Parse the item page for contains/drops listview data
        return parse_item_loot_data(html, item_id)


class NpcNameFetcher:
    """Fetches human-friendly NPC names from Wowhead."""

    def __init__(self, http_fetcher=None):
        """
        Initialize the NPC name fetcher.
        
        Args:
            http_fetcher: RetryableHTTPFetcher instance (creates default if None)
        """
        self.http_fetcher = http_fetcher or RetryableHTTPFetcher()

    def fetch_npc_name(self, npc_id):
        """
        Fetch NPC page and extract a human-friendly NPC name.
        
        Args:
            npc_id: Numeric NPC ID
            
        Returns:
            Human-readable NPC name
        """
        url = f"{WOWHEAD_NPC_URL(npc_id).split('#')[0]}"  # Remove #drops fragment
        html = self.http_fetcher.fetch_url(url, description=f"NPC page {npc_id}")

        if html is None:
            return str(npc_id)

        try:
            soup = BeautifulSoup(html, 'html.parser')
        except Exception:
            return str(npc_id)

        # 1) prefer the OpenGraph title
        og = soup.find('meta', {'property': 'og:title'})

        if og and og.get('content'):
            name = og.get('content')
        else:
            # 2) try H1 headings
            h1 = soup.find('h1')

            if h1 and h1.get_text(strip=True):
                name = h1.get_text(strip=True)
            else:
                # 3) fallback to title tag
                t = soup.find('title')
                name = t.string if (t and t.string) else str(npc_id)

        # clean common suffixes (site name), split on em-dash or hyphen
        name = str(name).strip()
        
        for sep in ['—', ' - ', ' – ']:
            if sep in name:
                name = name.split(sep)[0].strip()

        # strip trailing punctuation
        name = name.rstrip(' -–—')

        return name or str(npc_id)


class ObjectNameFetcher:
    """Fetches human-friendly GameObject names from Wowhead."""

    def __init__(self, http_fetcher=None):
        self.http_fetcher = http_fetcher or RetryableHTTPFetcher()

    def fetch_object_name(self, obj_id):
        url = f"{WOWHEAD_OBJECT_URL(obj_id).split('#')[0]}"
        html = self.http_fetcher.fetch_url(url, description=f"GameObject page {obj_id}")

        if html is None:
            return str(obj_id)

        try:
            soup = BeautifulSoup(html, 'html.parser')
        except Exception:
            return str(obj_id)

        og = soup.find('meta', {'property': 'og:title'})

        if og and og.get('content'):
            name = og.get('content')
        else:
            h1 = soup.find('h1')

            if h1 and h1.get_text(strip=True):
                name = h1.get_text(strip=True)
            else:
                t = soup.find('title')
                name = t.string if (t and t.string) else str(obj_id)

        name = str(name).strip()

        for sep in ['—', ' - ', ' – ']:
            if sep in name:
                name = name.split(sep)[0].strip()

        name = name.rstrip(' -–—')

        return name or str(obj_id)
