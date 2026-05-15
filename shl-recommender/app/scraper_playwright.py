"""
scraper_playwright.py
---------------------
Browser-based scraper using Playwright — works on Windows 11.
Use this if the basic requests-based scraper gets blocked (HTTP 403).

Setup (run ONCE):
    pip install playwright
    playwright install chromium

Then run:
    python app/scraper_playwright.py

This opens a real Chromium browser, navigates the SHL catalog,
and saves all Individual Test Solutions to catalog.json.
"""

import json
import time
import os
import re

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "catalog.json")

BASE_URL    = "https://www.shl.com"
CATALOG_URL = "https://www.shl.com/products/product-catalog/"

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


def scrape_with_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("ERROR: Playwright not installed.")
        print("Run: pip install playwright && playwright install chromium")
        return []

    all_items = []

    with sync_playwright() as p:
        # Launch Chromium (headless=False lets you see what's happening)
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        )
        page = context.new_page()

        # ── Phase 1: discover total pages ────────────────────────────────────
        print("[scraper] Loading catalog page 1…")
        page.goto(f"{CATALOG_URL}?start=0&type=1", wait_until="networkidle")
        time.sleep(2)

        # Find max pagination link
        links = page.query_selector_all("a[href*='start=']")
        max_start = 0
        for link in links:
            href = link.get_attribute("href") or ""
            m = re.search(r"start=(\d+)&type=1", href)
            if m:
                max_start = max(max_start, int(m.group(1)))

        total_pages = (max_start // 12) + 1
        print(f"[scraper] {total_pages} pages detected (last start={max_start})")

        # ── Phase 2: scrape each listing page ────────────────────────────────
        for page_num in range(total_pages):
            start = page_num * 12
            url   = f"{CATALOG_URL}?start={start}&type=1"
            print(f"\n[listing] Page {page_num + 1}/{total_pages}  (start={start})")

            try:
                page.goto(url, wait_until="networkidle", timeout=30000)
                time.sleep(1.5)
            except Exception as e:
                print(f"  [error] {e}")
                continue

            # Find the Individual Test Solutions table
            # It's the second table on the page
            tables = page.query_selector_all("table")
            target_table = None
            for table in tables:
                th_text = table.inner_text()
                if "Individual Test Solutions" in th_text:
                    target_table = table
                    break

            if not target_table and tables:
                target_table = tables[-1]
            if not target_table:
                print("  [warn] No table found on this page")
                continue

            rows = target_table.query_selector_all("tr")
            count = 0
            for row in rows:
                cells = row.query_selector_all("td")
                if not cells:
                    continue

                link_el = cells[0].query_selector("a")
                if not link_el:
                    continue

                name     = link_el.inner_text().strip()
                href     = link_el.get_attribute("href") or ""
                full_url = BASE_URL + href if href.startswith("/") else href

                # Check for images in remote/adaptive columns
                remote   = bool(cells[1].query_selector("img")) if len(cells) > 1 else False
                adaptive = bool(cells[2].query_selector("img")) if len(cells) > 2 else False

                # Test type letters from last cell
                raw_types = cells[3].inner_text().strip() if len(cells) > 3 else ""
                types     = [t for t in raw_types.split() if t in TEST_TYPE_LABELS]

                all_items.append({
                    "name":           name,
                    "url":            full_url,
                    "test_types":     types,
                    "remote_testing": remote,
                    "adaptive_irt":   adaptive,
                    "description":    "",
                    "duration_minutes": None,
                    "languages":      [],
                })
                count += 1

            print(f"  {count} items found (running total: {len(all_items)})")

        # ── Phase 3: fetch descriptions from detail pages ─────────────────────
        print(f"\n[details] Fetching descriptions for {len(all_items)} assessments…")
        for i, item in enumerate(all_items):
            print(f"  [{i+1}/{len(all_items)}] {item['name']}")
            try:
                page.goto(item["url"], wait_until="domcontentloaded", timeout=20000)
                time.sleep(0.8)

                # Extract meta description
                desc = page.evaluate(
                    "() => { "
                    "  const m = document.querySelector('meta[name=\"description\"]'); "
                    "  return m ? m.content : ''; "
                    "}"
                )
                # Clean the "Name: " prefix
                if ":" in desc and desc.index(":") < 60:
                    desc = desc.split(":", 1)[1].strip()
                item["description"] = desc

                # Try to get duration from page text
                body = page.inner_text("body")
                dur_m = re.search(r"(\d+)\s*(?:minute|min)", body, re.IGNORECASE)
                if dur_m:
                    item["duration_minutes"] = int(dur_m.group(1))

            except Exception as e:
                print(f"    [warn] {e}")

        browser.close()

    # Deduplicate
    seen  = set()
    unique = []
    for item in all_items:
        if item["url"] not in seen:
            seen.add(item["url"])
            unique.append(item)

    # Save
    output_path = os.path.abspath(OUTPUT_PATH)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(unique, f, indent=2, ensure_ascii=False)

    print(f"\n[done] Saved {len(unique)} assessments → {output_path}")
    return unique


if __name__ == "__main__":
    items = scrape_with_playwright()
    print(f"\nSample (first 3 items):")
    for item in items[:3]:
        print(json.dumps(item, indent=2))
