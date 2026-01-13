import streamlit as st
import asyncio
import pandas as pd
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
from typing import List, Dict, Any

st.set_page_config(page_title="Home Depot Clearance Scraper", layout="wide")

class ClearanceImporter:
    def __init__(self, store_id: str = "1106"):
        self.store_id = store_id
        self.browser = None
        self.context = None
        self.page = None
        self.playwright = None

    async def _init_browser(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=True, args=['--no-sandbox'])
        self.context = await self.browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        stealth = Stealth()
        await stealth.apply_stealth_async(self.context)
        self.page = await self.context.new_page()
        await self.context.add_cookies([{
            "name": "THD_STORES",
            "value": self.store_id,
            "domain": ".homedepot.com",
            "path": "/"
        }])

    async def _close_browser(self):
        if self.page: await self.page.close()
        if self.context: await self.context.close()
        if self.browser: await self.browser.close()
        if self.playwright: await self.playwright.stop()

    async def get_products(self, category_url: str, max_items: int = 100) -> List[Dict[str, Any]]:
        await self._init_browser()
        skus = []
        seen_skus = set()
        try:
            await self.page.goto(category_url, wait_until='networkidle', timeout=60000)
            # Scroll to load lazy-loaded products
            for _ in range(10):
                await self.page.evaluate("window.scrollBy(0, window.innerHeight)")
                await asyncio.sleep(1)
            products = await self.page.query_selector_all('div[data-testid*="product-tile"], div.ProductCard')
            for product in products:
                if len(skus) >= max_items:
                    break
                try:
                    link = await product.query_selector('a[href*="/p/"]')
                    if not link:
                        continue
                    href = await link.get_attribute('href')
                    if not href:
                        continue
                    if href.startswith('/'):
                        href = f"https://www.homedepot.com{href}"
                    sku = href.split('/p/')[1].split('/')[0].split('?')[0].strip()
                    if sku in seen_skus:
                        continue
                    seen_skus.add(sku)
                    name_elem = await product.query_selector('h2, h3, span[data-testid*="title"]')
                    name = await name_elem.inner_text() if name_elem else f"Product {sku}"
                    skus.append({"sku": sku, "name": name.strip(), "store_id": self.store_id, "url": href})
                except Exception:
                    continue
        finally:
            await self._close_browser()
        return skus[:max_items]

    def save_to_csv(self, skus: List[Dict[str, Any]], csv_path: str = "tracked_skus.csv") -> None:
        try:
            try:
                df_existing = pd.read_csv(csv_path)
            except FileNotFoundError:
                df_existing = pd.DataFrame(columns=['sku', 'store_id', 'name', 'url'])
            df_new = pd.DataFrame(skus)
            df_combined = pd.concat([df_existing, df_new], ignore_index=True).drop_duplicates(subset=['sku'])
            df_combined.to_csv(csv_path, index=False)
            st.success(f"Saved {len(skus)} SKUs to {csv_path}")
        except Exception as e:
            st.error(f"Error saving CSV: {e}")

# Streamlit interface
st.title("🏠 Home Depot Product Scraper")
st.write("Enter any Home Depot category URL and fetch SKUs for store 1106.")

category_url = st.text_input("Category URL", "")

max_items = st.number_input("Max items to fetch", min_value=10, max_value=500, value=100, step=10)

if st.button("Fetch Products"):
    if not category_url.strip():
        st.error("Please enter a valid category URL.")
    else:
        st.info("Fetching products… this may take a minute.")
        importer = ClearanceImporter(store_id="1106")
        skus = asyncio.run(importer.get_products(category_url, max_items))
        if skus:
            st.success(f"Found {len(skus)} products")
            df = pd.DataFrame(skus)
            st.dataframe(df)
            importer.save_to_csv(skus)
        else:
            st.warning("No products found. Make sure the URL is correct and products are visible.")
