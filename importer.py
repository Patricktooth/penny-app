"""
Home Depot Clearance Item Importer
Uses the NCNI-5 hack to find clearance items from Home Depot categories.
"""

import asyncio
import time
import pandas as pd
from datetime import datetime
from typing import List, Dict, Any, Optional
from playwright.async_api import async_playwright
from playwright_stealth import Stealth


class ClearanceImporter:
    """Importer for finding clearance items using the NCNI-5 hack."""
    
    def __init__(self, store_id: str = "0121"):
        """
        Initialize importer.
        
        Args:
            store_id: Home Depot store ID (default: 0121)
        """
        self.store_id = store_id
        self.browser = None
        self.context = None
        self.page = None
        self.playwright = None
    
    async def _init_browser(self):
        """Initialize Playwright browser with stealth mode."""
        if self.browser is None or self.playwright is None:
            if self.playwright is None:
                self.playwright = await async_playwright().start()
            try:
                self.browser = await self.playwright.chromium.launch(
                    headless=True,
                    args=['--no-sandbox', '--disable-blink-features=AutomationControlled']
                )
            except Exception as e:
                error_msg = str(e)
                if "Executable doesn't exist" in error_msg or "playwright install" in error_msg.lower():
                    raise Exception(
                        "Playwright browsers are not installed. "
                        "Please wait for the automatic installation to complete, or refresh the page."
                    ) from e
                raise
            self.context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                ignore_https_errors=True
            )
            # Apply stealth mode
            stealth = Stealth()
            await stealth.apply_stealth_async(self.context)
            self.page = await self.context.new_page()
            
            # Suppress console warnings from the website (not our code)
            async def handle_console(msg):
                # Filter out common website warnings that don't affect our scraping
                text = msg.text.lower()
                ignored_patterns = [
                    'content security policy',
                    'csp',
                    'eval',
                    'autocomplete',
                    'unrecognized feature',
                    'iframe',
                    'sandbox'
                ]
                
                # Only log actual errors, ignore warnings and CSP messages
                if msg.type == 'error' and not any(pattern in text for pattern in ignored_patterns):
                    print(f"Browser console error: {msg.text}")
            
            self.page.on('console', handle_console)
            
            # Suppress page errors (like CSP violations)
            async def handle_page_error(error):
                # Filter out CSP and other website-side errors
                error_text = str(error).lower()
                if 'content security policy' not in error_text and 'csp' not in error_text:
                    print(f"Page error: {error}")
            
            self.page.on('pageerror', handle_page_error)
            
            # Set store cookie
            await self.context.add_cookies([{
                'name': 'THD_STORES',
                'value': self.store_id,
                'domain': '.homedepot.com',
                'path': '/'
            }])
    
    async def _close_browser(self):
        """Close browser and cleanup resources."""
        if self.page:
            try:
                await self.page.close()
            except Exception:
                pass
        if self.context:
            try:
                await self.context.close()
            except Exception:
                pass
        if self.browser:
            try:
                await self.browser.close()
            except Exception:
                pass
        if self.playwright:
            try:
                await self.playwright.stop()
            except Exception:
                pass
        self.browser = None
        self.context = None
        self.page = None
        self.playwright = None
    
    async def get_clearance_skus(self, category_url: str, max_items: int = 15) -> List[Dict[str, Any]]:
        """
        Get clearance SKUs from a category using the NCNI-5 hack.
        
        Args:
            category_url: Base category URL
            max_items: Maximum number of items to return
            
        Returns:
            List of dictionaries with SKU and product info
        """
        # The hack: appending &NCNI-5 forces the site to show clearance only
        # Handle both URLs with and without existing query parameters
        if '?' in category_url:
            clearance_url = f"{category_url}&NCNI-5"
        else:
            clearance_url = f"{category_url}?NCNI-5"
        
        try:
            await self._init_browser()
            
            # Navigate to clearance URL
            await self.page.goto(clearance_url, wait_until='networkidle', timeout=30000)
            
            # Wait for page to fully load - try waiting for product containers
            try:
                # Wait for product grid or product tiles to appear
                await self.page.wait_for_selector(
                    'a[href*="/p/"], [data-testid*="product"], [class*="product"]',
                    timeout=10000,
                    state='attached'
                )
            except Exception:
                # If specific selector doesn't appear, just wait a bit
                pass
            
            # Scroll down to load lazy-loaded products
            await self.page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            await self.page.wait_for_timeout(2000)
            
            # Scroll back up
            await self.page.evaluate('window.scrollTo(0, 0)')
            await self.page.wait_for_timeout(1000)
            
            skus = []
            seen_skus = set()  # Track SKUs we've already found
            
            # Strategy 1: Look for product links with /p/ pattern (most reliable)
            print(f"   Searching for product links...")
            product_links = await self.page.query_selector_all('a[href*="/p/"]')
            print(f"   Found {len(product_links)} product links")
            
            for link in product_links:
                if len(skus) >= max_items:
                    break
                try:
                    href = await link.get_attribute('href')
                    if href and '/p/' in href:
                        # Handle both relative and absolute URLs
                        if href.startswith('/'):
                            href = f"https://www.homedepot.com{href}"
                        elif not href.startswith('http'):
                            continue
                            
                        # Extract SKU from URL like /p/SKU/... or /p/SKU
                        parts = href.split('/p/')
                        if len(parts) > 1:
                            sku = parts[1].split('/')[0].split('?')[0].strip()
                            
                            # Validate SKU (should be alphanumeric, typically 6-10 chars)
                            if sku and len(sku) >= 4 and sku not in seen_skus:
                                seen_skus.add(sku)
                                
                                # Try to get product name
                                name = ""
                                try:
                                    # Try to get name from link text or nearby elements
                                    name = await link.inner_text()
                                    if not name or len(name.strip()) < 3:
                                        # Try parent container
                                        parent = await link.evaluate_handle('el => el.closest("[data-testid*=\"product\"], .product, [class*=\"Product\"]")')
                                        if parent:
                                            name_elem = await parent.query_selector('h2, h3, [data-testid="product-title"], .product-title')
                                            if name_elem:
                                                name = await name_elem.inner_text()
                                except Exception:
                                    pass
                                
                                skus.append({
                                    'sku': sku,
                                    'name': name.strip() if name and name.strip() else f"Product {sku}",
                                    'store_id': self.store_id
                                })
                                print(f"   Found SKU: {sku}")
                except Exception as e:
                    continue
            
            # Strategy 2: Look for product tiles/containers with data attributes
            if len(skus) < max_items:
                print(f"   Searching for product containers...")
                product_containers = await self.page.query_selector_all(
                    '[data-testid*="product"], [data-automation-id*="product"], [class*="product-tile"], [class*="ProductTile"]'
                )
                print(f"   Found {len(product_containers)} product containers")
                
                for container in product_containers:
                    if len(skus) >= max_items:
                        break
                    try:
                        # Try to find link within container
                        link = await container.query_selector('a[href*="/p/"]')
                        if link:
                            href = await link.get_attribute('href')
                            if href and '/p/' in href:
                                if href.startswith('/'):
                                    href = f"https://www.homedepot.com{href}"
                                elif not href.startswith('http'):
                                    continue
                                    
                                parts = href.split('/p/')
                                if len(parts) > 1:
                                    sku = parts[1].split('/')[0].split('?')[0].strip()
                                    
                                    if sku and len(sku) >= 4 and sku not in seen_skus:
                                        seen_skus.add(sku)
                                        
                                        # Get product name
                                        name = ""
                                        try:
                                            name_elem = await container.query_selector('h2, h3, [data-testid*="title"], [data-automation-id*="title"]')
                                            if name_elem:
                                                name = await name_elem.inner_text()
                                        except Exception:
                                            pass
                                        
                                        skus.append({
                                            'sku': sku,
                                            'name': name.strip() if name and name.strip() else f"Product {sku}",
                                            'store_id': self.store_id
                                        })
                                        print(f"   Found SKU from container: {sku}")
                    except Exception:
                        continue
            
            # Strategy 3: Look for any elements with product IDs in data attributes
            if len(skus) < max_items:
                print(f"   Searching for product IDs in data attributes...")
                elements_with_ids = await self.page.query_selector_all(
                    '[data-productid], [data-sku], [data-item-id]'
                )
                print(f"   Found {len(elements_with_ids)} elements with product IDs")
                
                for element in elements_with_ids:
                    if len(skus) >= max_items:
                        break
                    try:
                        product_id = await element.get_attribute('data-productid')
                        if not product_id:
                            product_id = await element.get_attribute('data-sku')
                        if not product_id:
                            product_id = await element.get_attribute('data-item-id')
                        
                        if product_id and product_id not in seen_skus:
                            seen_skus.add(product_id)
                            
                            # Try to get name
                            name = ""
                            try:
                                name_elem = await element.query_selector('h2, h3, [data-testid*="title"]')
                                if name_elem:
                                    name = await name_elem.inner_text()
                            except Exception:
                                pass
                            
                            skus.append({
                                'sku': product_id,
                                'name': name.strip() if name and name.strip() else f"Product {product_id}",
                                'store_id': self.store_id
                            })
                            print(f"   Found SKU from attribute: {product_id}")
                    except Exception:
                        continue
            
            print(f"   Total SKUs extracted: {len(skus)}")
            
            return skus[:max_items]
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"❌ Error fetching clearance SKUs from {category_url}: {e}")
            print(f"   Details: {error_details}")
            return []
    
    async def import_from_categories(self, categories: List[Dict[str, str]], max_per_category: int = 15) -> List[Dict[str, Any]]:
        """
        Import clearance SKUs from multiple categories.
        
        Args:
            categories: List of category dictionaries with 'name' and 'url' keys
            max_per_category: Maximum items to fetch per category
            
        Returns:
            List of all discovered SKUs
        """
        all_skus = []
        
        try:
            await self._init_browser()
            
            for i, category in enumerate(categories):
                print(f"🔍 Scanning {category['name']}...")
                
                skus = await self.get_clearance_skus(category['url'], max_per_category)
                all_skus.extend(skus)
                
                print(f"   Found {len(skus)} items")
                
                # Add delay between categories to avoid detection (except for last one)
                if i < len(categories) - 1:
                    await asyncio.sleep(2)
            
        finally:
            await self._close_browser()
        
        return all_skus
    
    def save_to_csv(self, skus: List[Dict[str, Any]], csv_path: str = "tracked_skus.csv") -> Dict[str, Any]:
        """
        Save discovered SKUs to CSV file, merging with existing data.
        
        Args:
            skus: List of SKU dictionaries
            csv_path: Path to CSV file
            
        Returns:
            Dictionary with save statistics
        """
        try:
            # Load existing tracked SKUs if file exists
            try:
                existing_df = pd.read_csv(csv_path)
                existing_skus = set(existing_df['sku'].astype(str))
            except FileNotFoundError:
                existing_df = pd.DataFrame(columns=['sku', 'store_id', 'name', 'last_price', 'last_updated'])
                existing_skus = set()
            
            # Create new rows for SKUs not already tracked
            new_rows = []
            for sku_info in skus:
                sku = str(sku_info['sku'])
                if sku not in existing_skus:
                    new_rows.append({
                        'sku': sku,
                        'store_id': sku_info.get('store_id', self.store_id),
                        'name': sku_info.get('name', ''),
                        'last_price': '',
                        'last_updated': ''
                    })
            
            if new_rows:
                new_df = pd.DataFrame(new_rows)
                # Combine with existing data
                combined_df = pd.concat([existing_df, new_df], ignore_index=True)
                # Remove duplicates (keep first occurrence)
                combined_df = combined_df.drop_duplicates(subset=['sku'], keep='first')
                # Save to CSV
                combined_df.to_csv(csv_path, index=False)
                
                return {
                    'success': True,
                    'message': f'Added {len(new_rows)} new SKUs to {csv_path}',
                    'new_skus': len(new_rows),
                    'total_skus': len(combined_df),
                    'skus': new_rows
                }
            else:
                return {
                    'success': True,
                    'message': 'No new SKUs to add (all already tracked)',
                    'new_skus': 0,
                    'total_skus': len(existing_df),
                    'skus': []
                }
                
        except Exception as e:
            return {
                'success': False,
                'message': f'Error saving to CSV: {str(e)}',
                'new_skus': 0,
                'total_skus': 0,
                'skus': []
            }


def find_clearance_items(store_id: str = "0121", max_per_category: int = 15) -> Dict[str, Any]:
    """
    Find clearance items from high-probability categories for December 2025.
    
    Args:
        store_id: Home Depot store ID
        max_per_category: Maximum items per category
        
    Returns:
        Dictionary with import results
    """
    # High-probability categories for late December 2025
    categories = [
        {
            'name': 'Christmas Trees',
            'url': 'https://www.homedepot.com/b/Holiday-Decor-Christmas-Decorations-Christmas-Trees/N-5yc1vZc3tf'
        },
        {
            'name': 'Power Tool Kits',
            'url': 'https://www.homedepot.com/b/Tools-Power-Tools/N-5yc1vZc298'
        },
        {
            'name': 'Holiday Lights',
            'url': 'https://www.homedepot.com/b/Holiday-Decor-Christmas-Decorations-Christmas-Lights/N-5yc1vZc3tb'
        }
    ]
    
    importer = ClearanceImporter(store_id=store_id)
    
    try:
        # Import SKUs from all categories
        skus = asyncio.run(importer.import_from_categories(categories, max_per_category))
        
        # Debug: Print what we found
        print(f"🔍 Import completed. Found {len(skus)} total SKUs")
        if skus:
            print(f"   Sample SKUs: {[s.get('sku', 'N/A') for s in skus[:5]]}")
        else:
            print("   ⚠️  No SKUs found. This could mean:")
            print("      - The NCNI-5 parameter isn't working")
            print("      - Home Depot's page structure has changed")
            print("      - No clearance items in these categories")
            print("      - The page didn't load properly")
        
        # Save to CSV
        result = importer.save_to_csv(skus)
        
        return {
            'success': result['success'],
            'message': result['message'],
            'categories_scanned': len(categories),
            'total_found': len(skus),
            'new_skus_added': result['new_skus'],
            'total_tracked': result['total_skus'],
            'new_sku_list': result.get('skus', [])
        }
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"❌ Error during import: {e}")
        print(f"   Details: {error_details}")
        return {
            'success': False,
            'message': f'Error during import: {str(e)}',
            'categories_scanned': 0,
            'total_found': 0,
            'new_skus_added': 0,
            'total_tracked': 0,
            'new_sku_list': []
        }


if __name__ == "__main__":
    # Test the importer
    print("🔍 Home Depot Clearance Importer")
    print("=" * 50)
    print("Scanning high-probability categories for December 2025...")
    print()
    
    result = find_clearance_items()
    
    if result['success']:
        print(f"✅ {result['message']}")
        print(f"   Categories scanned: {result['categories_scanned']}")
        print(f"   Total items found: {result['total_found']}")
        print(f"   New SKUs added: {result['new_skus_added']}")
        print(f"   Total SKUs tracked: {result['total_tracked']}")
        
        if result['new_sku_list']:
            print("\n📋 New SKUs added:")
            for sku_info in result['new_sku_list'][:10]:  # Show first 10
                print(f"   - {sku_info['sku']}: {sku_info['name']}")
            if len(result['new_sku_list']) > 10:
                print(f"   ... and {len(result['new_sku_list']) - 10} more")
    else:
        print(f"❌ {result['message']}")

