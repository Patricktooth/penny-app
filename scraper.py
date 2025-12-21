"""
Home Depot Price Scraper
Fetches product prices from Home Depot using Playwright with stealth mode to avoid 403 errors.
"""

import asyncio
import re
import pandas as pd
from datetime import datetime
from typing import Optional, Dict, Any, List
from playwright.async_api import async_playwright
from playwright_stealth import Stealth


class HomeDepotScraper:
    """Scraper for Home Depot product prices using Playwright with stealth mode."""
    
    def __init__(self):
        """Initialize scraper."""
        self.browser = None
        self.context = None
        self.page = None
        self.playwright = None
    
    async def _init_browser(self):
        """Initialize Playwright browser with stealth mode."""
        if self.browser is None or self.playwright is None:
            if self.playwright is None:
                self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-blink-features=AutomationControlled']
            )
            self.context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            # Apply stealth mode using the new Stealth class API on context
            # This ensures all pages created within this context inherit stealth techniques
            stealth = Stealth()
            await stealth.apply_stealth_async(self.context)
            self.page = await self.context.new_page()
    
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
    
    def _parse_price(self, price_text: str) -> Optional[float]:
        """Parse price string to float."""
        # Remove currency symbols, whitespace, and commas
        price_text = re.sub(r'[^\d.]', '', price_text)
        try:
            price = float(price_text)
            # Validate reasonable price range
            if 0.01 <= price <= 100000:
                return price
        except ValueError:
            pass
        return None
    
    async def _extract_price_from_page(self) -> Optional[float]:
        """Extract price from the current page using multiple strategies."""
        try:
            # Strategy 1: Wait for and extract from 'pricing' element
            # Try multiple common selectors for pricing element
            pricing_selectors = [
                '[data-testid="pricing"]',
                '[data-automation-id="pricing"]',
                '.pricing',
                '[class*="pricing"]',
                '[id*="pricing"]',
                'span[data-testid="price"]',
                '[data-automation-id="product-price"]',
                '.price__dollars',
                '[class*="price"]',
            ]
            
            for selector in pricing_selectors:
                try:
                    # Wait for element with timeout
                    element = await self.page.wait_for_selector(
                        selector,
                        timeout=5000,
                        state='visible'
                    )
                    if element:
                        price_text = await element.inner_text()
                        price = self._parse_price(price_text)
                        if price:
                            return price
                except Exception:
                    continue
            
            # Strategy 2: Look for price in common Home Depot price selectors
            price_selectors = [
                'span[data-testid="price"]',
                '.price__dollars',
                '[data-automation-id="product-price"]',
                'span.price',
                '[class*="price__"]',
            ]
            
            for selector in price_selectors:
                try:
                    element = await self.page.query_selector(selector)
                    if element:
                        price_text = await element.inner_text()
                        price = self._parse_price(price_text)
                        if price:
                            return price
                except Exception:
                    continue
            
            # Strategy 3: Search page content for price patterns
            page_content = await self.page.content()
            price_pattern = r'\$?\s*(\d{1,3}(?:,\d{3})*\.\d{2})'
            matches = re.findall(price_pattern, page_content)
            if matches:
                for match in matches:
                    price = self._parse_price(match)
                    if price:
                        return price
            
        except Exception as e:
            print(f"⚠️  Error extracting price: {e}")
        
        return None
    
    async def _fetch_from_product_page_async(self, url: str, sku: str) -> Optional[Dict[str, Any]]:
        """Fetch price from product page using Playwright."""
        try:
            await self._init_browser()
            
            # Navigate to product page
            await self.page.goto(url, wait_until='networkidle', timeout=30000)
            
            # Wait for pricing element to load
            # Try multiple selectors with increasing timeout
            pricing_found = False
            pricing_selectors = [
                '[data-testid="pricing"]',
                '[data-automation-id="pricing"]',
                '.pricing',
                '[class*="pricing"]',
                '[id*="pricing"]',
            ]
            
            for selector in pricing_selectors:
                try:
                    await self.page.wait_for_selector(
                        selector,
                        timeout=10000,
                        state='visible'
                    )
                    pricing_found = True
                    break
                except Exception:
                    continue
            
            # If pricing element not found, wait a bit for page to fully load
            if not pricing_found:
                await self.page.wait_for_timeout(2000)
            
            # Extract price
            price = await self._extract_price_from_page()
            
            if price:
                return {
                    'sku': sku,
                    'price': price,
                    'url': url,
                    'method': 'product_page'
                }
            
        except Exception as e:
            print(f"❌ Error fetching from product page: {e}")
            return None
        
        return None
    
    def get_price_by_sku(self, sku: str) -> Optional[Dict[str, Any]]:
        """
        Get product price by SKU using Playwright.
        
        Args:
            sku: Product SKU number
            
        Returns:
            Dictionary with price and product info, or None if failed
        """
        product_url = f"https://www.homedepot.com/p/{sku}"
        
        # Run async method in sync context
        try:
            result = asyncio.run(self._fetch_from_product_page_async(product_url, sku))
            return result
        except Exception as e:
            print(f"❌ Error: {e}")
            return None
        finally:
            # Cleanup browser
            try:
                asyncio.run(self._close_browser())
            except Exception:
                pass
    
    def get_price(self, sku: str) -> Optional[float]:
        """
        Simple method to get just the price.
        
        Args:
            sku: Product SKU number
            
        Returns:
            Price as float, or None if failed
        """
        result = self.get_price_by_sku(sku)
        return result['price'] if result else None


def get_product_price(sku: str) -> Optional[float]:
    """
    Convenience function to get product price by SKU.
    
    Args:
        sku: Product SKU number
        
    Returns:
        Price as float, or None if failed
    """
    scraper = HomeDepotScraper()
    return scraper.get_price(sku)


def bulk_update(csv_path: str = "tracked_skus.csv", price_history_path: str = "price_history.csv") -> Dict[str, Any]:
    """
    Bulk update prices for all SKUs in the tracked_skus.csv file.
    
    Args:
        csv_path: Path to the tracked SKUs CSV file
        price_history_path: Path to the price history CSV file
        
    Returns:
        Dictionary with update statistics
    """
    try:
        # Read tracked SKUs
        df = pd.read_csv(csv_path)
        
        if df.empty:
            return {
                'success': False,
                'message': 'No SKUs to track',
                'updated': 0,
                'failed': 0
            }
        
        # Initialize scraper (reuse for efficiency)
        scraper = HomeDepotScraper()
        
        updated_count = 0
        failed_count = 0
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Load or create price history
        try:
            history_df = pd.read_csv(price_history_path)
        except FileNotFoundError:
            history_df = pd.DataFrame(columns=['sku', 'price', 'timestamp'])
        
        # Update each SKU
        for idx, row in df.iterrows():
            sku = str(row['sku']).strip()
            if not sku or sku == 'nan':
                continue
            
            try:
                # Fetch price
                result = scraper.get_price_by_sku(sku)
                
                if result and result.get('price'):
                    price = result['price']
                    
                    # Update the tracked SKUs dataframe
                    df.at[idx, 'last_price'] = price
                    df.at[idx, 'last_updated'] = current_time
                    
                    # Add to price history
                    new_history_row = pd.DataFrame({
                        'sku': [sku],
                        'price': [price],
                        'timestamp': [current_time]
                    })
                    history_df = pd.concat([history_df, new_history_row], ignore_index=True)
                    
                    updated_count += 1
                    print(f"✅ Updated SKU {sku}: ${price:.2f}")
                else:
                    failed_count += 1
                    print(f"❌ Failed to fetch price for SKU {sku}")
                    
            except Exception as e:
                failed_count += 1
                print(f"❌ Error updating SKU {sku}: {e}")
        
        # Save updated tracked SKUs
        df.to_csv(csv_path, index=False)
        
        # Save price history
        history_df.to_csv(price_history_path, index=False)
        
        return {
            'success': True,
            'message': f'Updated {updated_count} SKUs, {failed_count} failed',
            'updated': updated_count,
            'failed': failed_count,
            'total': len(df)
        }
        
    except FileNotFoundError:
        return {
            'success': False,
            'message': f'Tracked SKUs file not found: {csv_path}',
            'updated': 0,
            'failed': 0
        }
    except Exception as e:
        return {
            'success': False,
            'message': f'Error during bulk update: {str(e)}',
            'updated': 0,
            'failed': 0
        }


if __name__ == "__main__":
    # Test the scraper
    import sys
    
    if len(sys.argv) > 1:
        test_sku = sys.argv[1]
        print(f"🔍 Fetching price for SKU: {test_sku}")
        scraper = HomeDepotScraper()
        result = scraper.get_price_by_sku(test_sku)
        
        if result:
            print(f"✅ Success!")
            print(f"   SKU: {result['sku']}")
            print(f"   Price: ${result['price']:.2f}")
            print(f"   Method: {result['method']}")
        else:
            print("❌ Failed to fetch price")
            print("   Check if SKU is valid or if there are network issues")
    else:
        print("Usage: python scraper.py <SKU>")
        print("Example: python scraper.py 100123456")
