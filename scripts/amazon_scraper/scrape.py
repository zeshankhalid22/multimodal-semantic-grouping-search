from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any

import pandas as pd
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By

from scripts.amazon_scraper._driver import make_driver


def _load_existing_asins(csv_file: str = "final_product_data.csv") -> set[str]:
    """Load existing ASINs from a CSV file to prevent re-scraping."""
    asins: set[str] = set()
    if not os.path.exists(csv_file):
        print(f"Note: '{csv_file}' not found. Starting with no existing data.")
        return asins

    try:
        df = pd.read_csv(csv_file)
        if "url" not in df.columns:
            print(f"Warning: 'url' column not in {csv_file}. Cannot load existing ASINs.")
            return asins

        for url in df["url"]:
            match = re.search(r"/dp/([A-Z0-9]{10})", str(url))
            if match:
                asins.add(match.group(1))

        print(f"Loaded {len(asins)} existing ASINs from {csv_file}.")
    except Exception as e:
        print(f"Error loading {csv_file}: {e}. Starting fresh.")

    return asins


def search_products(
    queries_dict: dict[str, list[str]],
    data_dir: str = "Data",
    sleep: float = 2.0,
    csv_file: str = "final_product_data.csv",
) -> list[dict[str, Any]]:
    """
    Search Amazon for each query and collect listing card data.

    Saves card HTML to Data/<Category>/<asin>.html.
    Skips ASINs that already exist in final_product_data.csv (idempotent).
    Returns a list of {asin, title, link, price, image_link, category}.
    """
    base = Path(data_dir)
    products: list[dict[str, Any]] = []
    driver = make_driver()

    scraped_asins = _load_existing_asins(csv_file)

    try:
        for category, queries in queries_dict.items():
            category_dir = base / category
            category_dir.mkdir(parents=True, exist_ok=True)

            for query in queries:
                page_num = 1
                print(f"  Searching: '{query}' [{category}]")

                while True:
                    try:
                        url = f"https://www.amazon.com/s?k={query.replace(' ', '+')}&page={page_num}"
                        driver.get(url)
                        time.sleep(sleep)

                        elems = driver.find_elements(By.CSS_SELECTOR, "div[data-asin]")

                        if not elems:
                            print(f"    Page {page_num}: No products found.")
                            break

                        print(f"    Page {page_num}: Found {len(elems)} potential products.")

                        found_new_on_page = False
                        for elem in elems:
                            asin = elem.get_attribute("data-asin") or ""

                            if not asin or not re.match(r"^[A-Z0-9]{10}$", asin):
                                continue

                            if asin in scraped_asins:
                                continue

                            found_new_on_page = True
                            html_content = elem.get_attribute("outerHTML") or ""

                            card_path = category_dir / f"{asin}.html"
                            card_path.write_text(html_content, encoding="utf-8")
                            scraped_asins.add(asin)

                            title = ""
                            link = ""
                            price = ""
                            image_link = ""

                            try:
                                title = elem.find_element(By.CSS_SELECTOR, "h2 span").text.strip()
                            except Exception:
                                pass

                            try:
                                href = (
                                    elem.find_element(By.CSS_SELECTOR, "h2 a").get_attribute("href") or ""
                                )
                                link = href.split("?")[0]
                            except Exception:
                                link = f"https://www.amazon.com/dp/{asin}"

                            try:
                                price = (
                                    elem.find_element(By.CSS_SELECTOR, ".a-price .a-offscreen")
                                    .get_attribute("textContent")
                                    .strip()
                                )
                            except Exception:
                                pass

                            try:
                                image_link = (
                                    elem.find_element(By.CSS_SELECTOR, "img.s-image").get_attribute("src") or ""
                                )
                            except Exception:
                                pass

                            products.append(
                                {
                                    "asin": asin,
                                    "title": title,
                                    "link": link,
                                    "price": price,
                                    "image_link": image_link,
                                    "category": category,
                                    "card_path": str(card_path),
                                }
                            )
                            print(f"      + {asin}: {title[:60] if title else 'N/A'}")

                        if not found_new_on_page and elems:
                            print(f"    Page {page_num}: No new products found. Moving to next query.")
                            break

                        try:
                            next_btn = driver.find_element(By.CSS_SELECTOR, ".s-pagination-next")

                            if "s-pagination-disabled" in (next_btn.get_attribute("class") or ""):
                                print("  - 'Next' button is disabled.")
                                break

                            if not next_btn.get_attribute("href"):
                                print("  - 'Next' button has no link.")
                                break

                        except NoSuchElementException:
                            print("  - No 'Next' button found.")
                            break

                        page_num += 1

                        if page_num > 50:
                            print(f"  - Reached max pages (50) for query '{query}'.")
                            break

                    except Exception as exc:
                        print(f"    Error on page {page_num}: {exc}")
                        break

    finally:
        driver.quit()

    print(f"Search complete — {len(products)} new cards collected.")
    return products
