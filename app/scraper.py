"""
scraper.py
----------
Scrapes the SHL product catalog (Individual Test Solutions only)
and saves everything to catalog.json in the project root.

Run this ONCE before starting the server:
    python app/scraper.py

The catalog has 32 pages of Individual Test Solutions (type=1).
URL pattern: https://www.shl.com/products/product-catalog/?start=0&type=1
Each page lists 12 items. We fetch every page, then visit each detail URL.
"""

import requests
import json
import time
import re
import os
from bs4 import BeautifulSoup

# ── constants ────────────────────────────────────────────────────────────────
BASE_URL    = "https://www.shl.com"
CATALOG_URL = "https://www.shl.com/products/product-catalog/"
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "catalog.json")

# Mimics a real Chrome browser so SHL doesn't block us
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.shl.com/",
}

# Test type codes → human-readable labels
TEST_TYPE_LABELS = {
    "A": "Ability & Aptitude",
    "B": "Biodata & Situational Judgement",
    "C": "Competencies",
    "D": "Development & 360",
    "E": "Assessment Exercises",
    "K": "Knowledge & Skills",
    "P": "Personality & Behavior",
    "S": "Simulations",
}

# ── helpers ──────────────────────────────────────────────────────────────────

def safe_get(url: str, retries: int = 3, delay: float = 2.0) -> requests.Response | None:
    """GET a URL with retries. Returns Response or None on total failure."""
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            if resp.status_code == 200:
                return resp
            print(f"  [warn] {url} → HTTP {resp.status_code} (attempt {attempt+1})")
        except requests.RequestException as e:
            print(f"  [error] {url} → {e} (attempt {attempt+1})")
        time.sleep(delay * (attempt + 1))   # back-off
    return None


def parse_test_types(raw: str) -> list[str]:
    """
    Turn a string like 'A K P' or 'A E B C D P' into ['A','K','P'].
    These are the single-letter codes from the table cell.
    """
    # Keep only uppercase single letters that are valid codes
    tokens = raw.strip().split()
    return [t for t in tokens if t in TEST_TYPE_LABELS]


def scrape_listing_page(start: int) -> list[dict]:
    """
    Fetch one paginated listing page for Individual Test Solutions (type=1).
    Returns a list of dicts: {name, url, raw_test_types, remote_testing, adaptive}.
    """
    url  = f"{CATALOG_URL}?start={start}&type=1"
    resp = safe_get(url)
    if resp is None:
        print(f"  [skip] Could not fetch listing page start={start}")
        return []

    soup   = BeautifulSoup(resp.text, "html.parser")
    items  = []

    # The page has TWO tables: Pre-packaged Job Solutions and Individual Test Solutions.
    # We want the SECOND table (Individual Test Solutions).
    tables = soup.find_all("table")
    target_table = None
    for table in tables:
        header = table.find("th")
        if header and "Individual Test Solutions" in header.get_text():
            target_table = table
            break

    if target_table is None:
        # Fallback: take the last table on the page
        if tables:
            target_table = tables[-1]
        else:
            print(f"  [warn] No tables found on start={start}")
            return []

    rows = target_table.find_all("tr")
    for row in rows:
        cells = row.find_all("td")
        if not cells:
            continue   # skip header row

        # Cell 0: assessment name + link
        link_tag = cells[0].find("a")
        if not link_tag:
            continue
        name      = link_tag.get_text(strip=True)
        href      = link_tag.get("href", "")
        full_url  = BASE_URL + href if href.startswith("/") else href

        # Cell 1: Remote Testing (has an image/icon if yes)
        remote_testing = bool(cells[1].find("img")) if len(cells) > 1 else False

        # Cell 2: Adaptive/IRT
        adaptive = bool(cells[2].find("img")) if len(cells) > 2 else False

        # Cell 3: Test Type letters
        raw_types = cells[3].get_text(strip=True) if len(cells) > 3 else ""
        test_types = parse_test_types(raw_types)

        items.append({
            "name":           name,
            "url":            full_url,
            "test_types":     test_types,
            "remote_testing": remote_testing,
            "adaptive_irt":   adaptive,
        })

    return items


def scrape_detail_page(item: dict) -> dict:
    """
    Visit an individual assessment detail page and extract the description.
    Merges extracted data back into the item dict.
    """
    resp = safe_get(item["url"])
    if resp is None:
        item["description"] = ""
        item["duration_minutes"] = None
        item["languages"] = []
        return item

    soup = BeautifulSoup(resp.text, "html.parser")

    # ── Description ──────────────────────────────────────────────────────────
    # SHL detail pages store the description in <meta name="description">
    # which is more reliable than parsing the body layout
    description = ""
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if meta_desc:
        description = meta_desc.get("content", "").strip()

    # Also try og:description as fallback
    if not description:
        og_desc = soup.find("meta", property="og:description")
        if og_desc:
            description = og_desc.get("content", "").strip()

    # Clean up the "AssessmentName: " prefix SHL puts in meta descriptions
    if ":" in description:
        parts = description.split(":", 1)
        if parts[0].strip().lower() in item["name"].lower() or len(parts[0]) < 60:
            description = parts[1].strip()

    # ── Duration ─────────────────────────────────────────────────────────────
    duration = None
    body_text = soup.get_text(" ", strip=True)
    dur_match = re.search(r"(\d+)\s*(minute|min)", body_text, re.IGNORECASE)
    if dur_match:
        duration = int(dur_match.group(1))

    # ── Languages ────────────────────────────────────────────────────────────
    languages = []
    lang_section = soup.find(string=re.compile(r"Language", re.IGNORECASE))
    if lang_section:
        parent = lang_section.find_parent()
        if parent:
            sibling = parent.find_next_sibling()
            if sibling:
                lang_text = sibling.get_text(separator=",", strip=True)
                languages = [l.strip() for l in lang_text.split(",") if l.strip()]

    item["description"]      = description
    item["duration_minutes"] = duration
    item["languages"]        = languages
    return item


# ── main scraping flow ────────────────────────────────────────────────────────

def discover_total_pages() -> int:
    """
    Fetch page 1 and read the last pagination link to know total pages.
    Individual Test Solutions have type=1.
    """
    resp = safe_get(f"{CATALOG_URL}?start=0&type=1")
    if resp is None:
        print("[warn] Could not fetch first page. Defaulting to 32 pages.")
        return 32

    soup  = BeautifulSoup(resp.text, "html.parser")
    links = soup.find_all("a", href=True)
    max_start = 0
    for link in links:
        m = re.search(r"start=(\d+)&type=1", link["href"])
        if m:
            max_start = max(max_start, int(m.group(1)))

    # Each page shows 12 items; last page start tells us total pages
    total_pages = (max_start // 12) + 1
    print(f"[info] Detected {total_pages} pages (last start={max_start})")
    return total_pages


def run_scraper(fetch_details: bool = True) -> list[dict]:
    """
    Full scrape:
    1. Walk all listing pages to collect names + URLs + test types.
    2. (Optional) Visit each detail page for description + duration + languages.
    3. Save to catalog.json and return the list.

    Set fetch_details=False for a quick run (no descriptions).
    """
    print("=" * 60)
    print("SHL Catalog Scraper — Individual Test Solutions")
    print("=" * 60)

    total_pages = discover_total_pages()
    all_items   = []

    # ── Phase 1: listing pages ────────────────────────────────────────────────
    for page_num in range(total_pages):
        start = page_num * 12
        print(f"\n[listing] Page {page_num + 1}/{total_pages}  (start={start})")
        items = scrape_listing_page(start)
        print(f"  → {len(items)} items found")
        all_items.extend(items)
        time.sleep(1.5)   # be polite to SHL's servers

    # Deduplicate by URL (some items may appear on multiple pages)
    seen_urls = set()
    unique_items = []
    for item in all_items:
        if item["url"] not in seen_urls:
            seen_urls.add(item["url"])
            unique_items.append(item)

    print(f"\n[info] Total unique Individual Test Solutions: {len(unique_items)}")

    # ── Phase 2: detail pages ─────────────────────────────────────────────────
    if fetch_details:
        print("\n[details] Fetching detail pages for descriptions…")
        for i, item in enumerate(unique_items):
            print(f"  [{i+1}/{len(unique_items)}] {item['name']}")
            unique_items[i] = scrape_detail_page(item)
            time.sleep(1.0)   # polite delay
    else:
        # Fill in empty fields so the schema is consistent
        for item in unique_items:
            item.setdefault("description", "")
            item.setdefault("duration_minutes", None)
            item.setdefault("languages", [])

    # ── Save ─────────────────────────────────────────────────────────────────
    output_path = os.path.abspath(OUTPUT_PATH)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(unique_items, f, indent=2, ensure_ascii=False)

    print(f"\n[done] Saved {len(unique_items)} assessments to:\n  {output_path}")
    return unique_items


# ── entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    # Pass --no-details flag to skip detail pages (faster, for testing)
    fetch_details = "--no-details" not in sys.argv
    run_scraper(fetch_details=fetch_details)
