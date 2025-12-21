"""
Home Depot Price Tracker - Streamlit App
Predicts likelihood of 'penny drop' based on price endings.
"""

import streamlit as st
import pandas as pd
from scraper import HomeDepotScraper, bulk_update
from importer import find_clearance_items
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import asyncio
import time
import os


def calculate_penny_drop_probability(price: float) -> Dict[str, Any]:
    """
    Calculate the likelihood of a penny drop based on price ending.
    
    Home Depot markdown cycle rules:
    - Markdowns occur every 3 weeks (21 days)
    - Items drop to $0.01 exactly 14 weeks after first clearance markdown
    - .06 ending → Next drop in ~21 days
    - .03 ending → High alert! Penny drop likely in 14-21 days
    - .02 ending → Extreme alert! Hidden 90% markdown
    
    Args:
        price: Product price as float
        
    Returns:
        Dictionary with prediction details including timeline
    """
    price_str = f"{price:.2f}"
    cents = price_str[-2:]
    today = datetime.now()
    
    # Markdown cycle logic based on price ending
    if cents == "02":
        # Extreme alert - hidden 90% markdown
        probability = 0.95
        confidence = "Extreme Alert"
        alert_level = "extreme"
        reasoning = "Price ends in .02 - This is a HIDDEN 90% markdown! Extreme alert!"
        days_until_drop = 7  # Very soon
        next_drop_date = today + timedelta(days=days_until_drop)
        timeline = f"Penny drop expected within 7-14 days (by {next_drop_date.strftime('%B %d, %Y')})"
        
    elif cents == "03":
        # High alert - penny drop likely soon
        probability = 0.90
        confidence = "High Alert"
        alert_level = "high"
        reasoning = "Price ends in .03 - High alert! Penny drop likely in 14-21 days"
        days_until_drop = 14  # 2 weeks
        next_drop_date = today + timedelta(days=days_until_drop)
        timeline = f"Penny drop likely in 14-21 days (around {next_drop_date.strftime('%B %d, %Y')})"
        
    elif cents == "06":
        # Next markdown in ~21 days (3 weeks)
        probability = 0.75
        confidence = "Moderate Alert"
        alert_level = "moderate"
        reasoning = "Price ends in .06 - Next markdown expected in ~21 days (3 weeks)"
        days_until_drop = 21  # 3 weeks
        next_drop_date = today + timedelta(days=days_until_drop)
        timeline = f"Next markdown expected in ~21 days (around {next_drop_date.strftime('%B %d, %Y')})"
        
    elif cents == "00" or cents == "99":
        # Regular pricing
        probability = 0.10
        confidence = "Low"
        alert_level = "low"
        reasoning = f"Price ends in .{cents} - Typical of regular pricing, not in clearance cycle"
        days_until_drop = None
        next_drop_date = None
        timeline = "Not currently in clearance cycle"
        
    else:
        # Unclear pattern
        probability = 0.30
        confidence = "Unclear"
        alert_level = "low"
        reasoning = f"Price ends in .{cents} - Unclear pattern, may or may not be in clearance cycle"
        days_until_drop = None
        next_drop_date = None
        timeline = "Pattern unclear - monitor for changes"
    
    return {
        'probability': probability,
        'confidence': confidence,
        'alert_level': alert_level,
        'reasoning': reasoning,
        'price_ending': cents,
        'full_price': price,
        'days_until_drop': days_until_drop,
        'next_drop_date': next_drop_date,
        'timeline': timeline
    }


def format_price(price: float) -> str:
    """Format price for display."""
    return f"${price:,.2f}"


def fetch_price_safely(sku: str) -> Optional[Dict[str, Any]]:
    """
    Safely fetch price using async scraper in Streamlit context.
    Handles event loop issues that can occur with asyncio.run() in Streamlit.
    
    Args:
        sku: Product SKU number
        
    Returns:
        Dictionary with price and product info, or None if failed
    """
    try:
        # Check if there's already an event loop running
        try:
            loop = asyncio.get_running_loop()
            # If we're in an async context, run in a separate thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(_run_scraper_sync, sku)
                return future.result(timeout=60)
        except RuntimeError:
            # No event loop running, safe to use asyncio.run()
            return _run_scraper_sync(sku)
    except Exception as e:
        st.error(f"Error fetching price: {e}")
        return None


def _run_scraper_sync(sku: str) -> Optional[Dict[str, Any]]:
    """
    Run the scraper synchronously using asyncio.run().
    This is a helper function that can be called from a thread if needed.
    
    Args:
        sku: Product SKU number
        
    Returns:
        Dictionary with price and product info, or None if failed
    """
    scraper = HomeDepotScraper()
    return scraper.get_price_by_sku(sku)


def load_tracked_skus() -> pd.DataFrame:
    """Load tracked SKUs from CSV file."""
    try:
        if os.path.exists("tracked_skus.csv"):
            df = pd.read_csv("tracked_skus.csv")
            # Ensure required columns exist
            required_cols = ['sku', 'store_id', 'name', 'last_price', 'last_updated']
            for col in required_cols:
                if col not in df.columns:
                    df[col] = ''
            return df
        else:
            return pd.DataFrame(columns=['sku', 'store_id', 'name', 'last_price', 'last_updated'])
    except Exception as e:
        st.error(f"Error loading tracked SKUs: {e}")
        return pd.DataFrame(columns=['sku', 'store_id', 'name', 'last_price', 'last_updated'])


def save_tracked_skus(df: pd.DataFrame):
    """Save tracked SKUs to CSV file."""
    try:
        df.to_csv("tracked_skus.csv", index=False)
    except Exception as e:
        st.error(f"Error saving tracked SKUs: {e}")


def add_sku_to_tracking(sku: str, name: str = "", store_id: str = ""):
    """Add a new SKU to the tracking list."""
    df = load_tracked_skus()
    
    # Check if SKU already exists
    if not df.empty and sku in df['sku'].values:
        st.warning(f"SKU {sku} is already being tracked!")
        return
    
    # Add new row
    new_row = pd.DataFrame({
        'sku': [sku],
        'store_id': [store_id],
        'name': [name],
        'last_price': [''],
        'last_updated': ['']
    })
    
    df = pd.concat([df, new_row], ignore_index=True)
    save_tracked_skus(df)


def load_price_history() -> pd.DataFrame:
    """Load price history from CSV file."""
    try:
        if os.path.exists("price_history.csv"):
            df = pd.read_csv("price_history.csv")
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            return df
        else:
            return pd.DataFrame(columns=['sku', 'price', 'timestamp'])
    except Exception as e:
        st.error(f"Error loading price history: {e}")
        return pd.DataFrame(columns=['sku', 'price', 'timestamp'])


# Page configuration
st.set_page_config(
    page_title="Home Depot Penny Drop Predictor",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Title and description
st.title("🏠 Home Depot Price Tracker")
st.markdown("### Penny Drop Dashboard")

# Create tabs for different views
tab1, tab2, tab3 = st.tabs(["📋 Tracked Items", "🔍 Single SKU Search", "📊 Price History"])

# Sidebar
with st.sidebar:
    st.header("ℹ️ About Penny Drops")
    st.markdown("""
    **Home Depot Markdown Cycle:**
    
    - Markdowns occur every **3 weeks** (21 days)
    - Items drop to **$0.01** exactly **14 weeks** after first clearance markdown
    
    **Price Ending Indicators:**
    
    - **.02** = 🔴 **EXTREME ALERT!** Hidden 90% markdown - Penny drop in 7-14 days
    - **.03** = 🟠 **HIGH ALERT!** Penny drop likely in 14-21 days
    - **.06** = 🟡 **MODERATE ALERT** - Next drop in ~21 days
    - **.00/.99** = Regular pricing (not in clearance cycle)
    
    **Timeline:** Items typically follow a predictable markdown schedule
    before reaching the final $0.01 price.
    """)
    
    st.header("📝 Instructions")
    st.markdown("""
    **Tracked Items Tab:**
    - View all tracked SKUs
    - Add new SKUs to track
    - Refresh all prices
    
    **Single SKU Search:**
    - Quick price check
    - Penny drop prediction
    
    **Price History:**
    - View price trends
    - Track markdown progress
    """)
    
    # Find New Clearance button
    st.markdown("---")
    st.header("🔥 Find New Clearance")
    st.markdown("""
    Automatically scan Home Depot clearance sections for items likely to hit penny drops.
    
    **Current Focus (Dec 2025):**
    - Christmas Trees (post-holiday markdowns)
    - Power Tool Kits (Black Friday leftovers)
    - Holiday Lights (high inventory turnover)
    """)
    
    if st.button("🔍 Scan for Clearance Items", type="primary", use_container_width=True):
        with st.spinner("🔍 Scanning clearance sections... This may take 1-2 minutes."):
            result = find_clearance_items()
            
            if result['success']:
                st.success(f"✅ {result['message']}")
                st.info(f"""
                **Results:**
                - Categories scanned: {result['categories_scanned']}
                - Total items found: {result['total_found']}
                - New SKUs added: {result['new_skus_added']}
                - Total SKUs tracked: {result['total_tracked']}
                """)
                
                if result.get('new_sku_list'):
                    st.markdown("**New SKUs discovered:**")
                    for sku_info in result['new_sku_list'][:5]:  # Show first 5
                        st.caption(f"  • {sku_info['sku']}: {sku_info.get('name', 'N/A')}")
                    if len(result['new_sku_list']) > 5:
                        st.caption(f"  ... and {len(result['new_sku_list']) - 5} more")
                
                st.rerun()
            else:
                st.error(f"❌ {result['message']}")
    
    st.markdown("---")
    
    # Add SKU to tracking
    st.header("➕ Add SKU to Track")
    new_sku = st.text_input("SKU:", key="new_sku", placeholder="e.g., 100123456")
    new_name = st.text_input("Name (optional):", key="new_name", placeholder="Product name")
    if st.button("➕ Add to Tracking", use_container_width=True):
        if new_sku and new_sku.strip():
            add_sku_to_tracking(new_sku.strip(), new_name.strip() if new_name else "")
            st.success(f"✅ Added SKU {new_sku} to tracking!")
            st.rerun()
        else:
            st.warning("⚠️ Please enter a valid SKU")

# Tab 1: Tracked Items Dashboard
with tab1:
    st.subheader("📋 Your Penny Watchlist")
    
    # Load tracked SKUs
    df = load_tracked_skus()
    
    # Refresh All button
    col_refresh, col_stats = st.columns([1, 3])
    with col_refresh:
        if st.button("🔄 Sync Prices", type="primary", use_container_width=True):
            with st.spinner("🔄 Updating all prices... This may take a while."):
                result = bulk_update()
                if result['success']:
                    st.success(f"✅ {result['message']}")
                    st.rerun()
                else:
                    st.error(f"❌ {result['message']}")
    
    with col_stats:
        if not df.empty:
            st.caption(f"Tracking {len(df)} items | Last updated: {df['last_updated'].max() if not df['last_updated'].isna().all() else 'Never'}")
    
    # Display tracked items table
    if not df.empty:
        # Add prediction columns
        display_df = df.copy()
        
        # Calculate predictions for each item
        predictions = []
        for idx, row in df.iterrows():
            if pd.notna(row['last_price']) and row['last_price'] != '':
                try:
                    price = float(row['last_price'])
                    pred = calculate_penny_drop_probability(price)
                    predictions.append({
                        'alert_level': pred['alert_level'],
                        'probability': pred['probability'],
                        'days_until_drop': pred.get('days_until_drop', 'N/A')
                    })
                except (ValueError, TypeError):
                    predictions.append({
                        'alert_level': 'unknown',
                        'probability': 0,
                        'days_until_drop': 'N/A'
                    })
            else:
                predictions.append({
                    'alert_level': 'unknown',
                    'probability': 0,
                    'days_until_drop': 'N/A'
                })
        
        pred_df = pd.DataFrame(predictions)
        display_df = pd.concat([display_df, pred_df], axis=1)
        
        # Format display
        display_df['last_price'] = display_df['last_price'].apply(
            lambda x: f"${float(x):,.2f}" if pd.notna(x) and x != '' else "Not fetched"
        )
        
        # Display table
        st.dataframe(
            display_df[['sku', 'name', 'last_price', 'last_updated', 'alert_level', 'probability', 'days_until_drop']],
            column_config={
                "sku": "SKU",
                "name": "Product Name",
                "last_price": st.column_config.TextColumn("Price", width="medium"),
                "last_updated": "Last Updated",
                "alert_level": "Alert Level",
                "probability": st.column_config.NumberColumn("Penny Drop Probability", format="%.0f%%", width="medium"),
                "days_until_drop": "Days Until Drop"
            },
            hide_index=True,
            use_container_width=True
        )
        
        # Delete SKU functionality
        st.markdown("---")
        st.subheader("🗑️ Remove SKU from Tracking")
        skus_to_delete = st.multiselect(
            "Select SKUs to remove:",
            options=df['sku'].tolist(),
            key="delete_skus"
        )
        if st.button("🗑️ Remove Selected", type="secondary"):
            if skus_to_delete:
                df = df[~df['sku'].isin(skus_to_delete)]
                save_tracked_skus(df)
                st.success(f"✅ Removed {len(skus_to_delete)} SKU(s)")
                st.rerun()
    else:
        st.info("📝 No items being tracked yet. Add SKUs using the sidebar or the form below.")
        st.markdown("""
        **To get started:**
        1. Use the sidebar to add a SKU
        2. Click "🔄 Sync Prices" to fetch current prices
        3. Monitor price changes and penny drop predictions
        """)

# Tab 2: Single SKU Search
with tab2:
    st.subheader("🔍 Single SKU Search")
    st.markdown("Enter a product SKU to check the current price and predict the likelihood of a 'penny drop'.")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        sku_input = st.text_input(
            "Product SKU:",
            placeholder="e.g., 100123456",
            help="Enter the Home Depot product SKU number",
            key="single_sku"
        )
    
    with col2:
        st.write("")  # Spacing
        predict_button = st.button("🔍 Predict", type="primary", use_container_width=True)
    
    # Initialize session state for history
    if 'price_history' not in st.session_state:
        st.session_state.price_history = []

    # Process prediction
    if predict_button:
        if not sku_input or not sku_input.strip():
            st.warning("⚠️ Please enter a valid SKU")
        else:
            sku = sku_input.strip()
            
            with st.spinner(f"🔍 Fetching price for SKU {sku}..."):
                result = fetch_price_safely(sku)
            
            if result:
                price = result['price']
                prediction = calculate_penny_drop_probability(price)
                
                # Display results
                st.success("✅ Price fetched successfully!")
            
                # Price display
                st.markdown("---")
                col_price, col_method = st.columns([2, 1])
                
                with col_price:
                    st.metric("Current Price", format_price(price))
                
                with col_method:
                    st.caption(f"Method: {result['method']}")
                
                # Prediction display
                st.markdown("### 📊 Penny Drop Prediction")
            
                # Probability gauge
                probability = prediction['probability']
                confidence = prediction['confidence']
                alert_level = prediction.get('alert_level', 'low')
                
                # Color coding based on alert level
                if alert_level == "extreme":
                    color = "🔴"
                    bar_color = "red"
                    alert_emoji = "🚨"
                elif alert_level == "high":
                    color = "🟠"
                    bar_color = "orange"
                    alert_emoji = "⚠️"
                elif alert_level == "moderate":
                    color = "🟡"
                    bar_color = "yellow"
                    alert_emoji = "📅"
                else:
                    color = "⚪"
                    bar_color = "gray"
                    alert_emoji = "ℹ️"
                
                st.progress(probability, text=f"{color} {alert_emoji} {confidence}: {probability*100:.0f}%")
                
                # Alert box based on level
                if alert_level == "extreme":
                    st.error(f"🚨 **{confidence}** - {prediction['reasoning']}")
                elif alert_level == "high":
                    st.warning(f"⚠️ **{confidence}** - {prediction['reasoning']}")
                elif alert_level == "moderate":
                    st.info(f"📅 **{confidence}** - {prediction['reasoning']}")
                else:
                    st.info(f"ℹ️ **{confidence}** - {prediction['reasoning']}")
                
                # Timeline information
                st.markdown("---")
                st.markdown("### ⏰ Timeline Prediction")
                
                if prediction.get('days_until_drop'):
                    days = prediction['days_until_drop']
                    drop_date = prediction['next_drop_date']
                    
                    col_days, col_date = st.columns(2)
                    with col_days:
                        st.metric("Days Until Next Drop", f"{days} days")
                    with col_date:
                        st.metric("Expected Date", drop_date.strftime("%b %d, %Y"))
                    
                    st.success(f"📅 **{prediction['timeline']}**")
                else:
                    st.info(f"ℹ️ {prediction['timeline']}")
                
                # Price ending highlight
                st.markdown("---")
                st.markdown(f"**Price Ending:** `.{prediction['price_ending']}`")
                
                # Detailed interpretation
                if alert_level == "extreme":
                    st.error("""
                    🚨 **EXTREME ALERT!** 
                    
                    This is a **HIDDEN 90% markdown**! The .02 ending indicates the item is 
                    in the final stages of clearance. Check back frequently - penny drop 
                    could happen within 7-14 days!
                    """)
                elif alert_level == "high":
                    st.warning("""
                    ⚠️ **HIGH ALERT!**
                    
                    Price ending in .03 indicates you're in the critical window. Based on 
                    Home Depot's 14-week cycle, this item is likely to drop to $0.01 within 
                    14-21 days. Monitor closely!
                    """)
                elif alert_level == "moderate":
                    st.info("""
                    📅 **MODERATE ALERT**
                    
                    Price ending in .06 suggests the item is in the clearance cycle. The next 
                    markdown should occur in approximately 21 days (3 weeks). Keep tracking!
                    """)
                else:
                    st.info("""
                    ℹ️ **Regular Pricing**
                    
                    This price ending suggests the item is not currently in a clearance cycle. 
                    Continue monitoring for price changes that might indicate entry into clearance.
                    """)
                
                # Add to history
                history_entry = {
                    'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'sku': sku,
                    'price': price,
                    'probability': probability,
                    'confidence': confidence,
                    'days_until_drop': prediction.get('days_until_drop', 'N/A'),
                    'alert_level': alert_level
                }
                st.session_state.price_history.insert(0, history_entry)
                
                # Show product URL if available
                if 'url' in result:
                    st.markdown(f"[View Product Page]({result['url']})")
            
            else:
                st.error("❌ Failed to fetch price. Possible reasons:")
                st.markdown("""
                - Invalid SKU
                - Product page not accessible
                - Anti-bot protection (may need to update headers/cookies)
                - Network error
                
                **Tip:** Try checking the SKU on Home Depot's website first.
                """)

# Tab 3: Price History
with tab3:
    st.subheader("📊 Price History & Trends")
    
    # Load price history
    history_df = load_price_history()
    
    if not history_df.empty:
        # SKU selector
        available_skus = history_df['sku'].unique().tolist()
        selected_sku = st.selectbox(
            "Select SKU to view price history:",
            options=available_skus,
            key="history_sku"
        )
        
        if selected_sku:
            # Filter history for selected SKU
            sku_history = history_df[history_df['sku'] == selected_sku].copy()
            sku_history = sku_history.sort_values('timestamp')
            
            if not sku_history.empty:
                # Display chart
                chart_data = sku_history[['timestamp', 'price']].set_index('timestamp')
                st.line_chart(chart_data, use_container_width=True)
                
                # Display table
                st.markdown("### 📋 Price History Table")
                display_history = sku_history.copy()
                display_history['price'] = display_history['price'].apply(lambda x: f"${x:,.2f}")
                display_history['timestamp'] = display_history['timestamp'].dt.strftime("%Y-%m-%d %H:%M:%S")
                display_history.columns = ['SKU', 'Price', 'Timestamp']
                
                st.dataframe(
                    display_history[['Timestamp', 'Price']],
                    hide_index=True,
                    use_container_width=True
                )
                
                # Statistics
                col_stat1, col_stat2, col_stat3 = st.columns(3)
                with col_stat1:
                    st.metric("Current Price", f"${sku_history['price'].iloc[-1]:,.2f}")
                with col_stat2:
                    price_change = sku_history['price'].iloc[-1] - sku_history['price'].iloc[0]
                    st.metric("Total Change", f"${price_change:,.2f}", 
                             delta=f"{((price_change / sku_history['price'].iloc[0]) * 100):.1f}%")
                with col_stat3:
                    st.metric("Data Points", len(sku_history))
            else:
                st.info("No price history available for this SKU.")
    else:
        st.info("📊 No price history data yet. Prices will be tracked after you sync your tracked items.")
        st.markdown("""
        **To build price history:**
        1. Add SKUs to tracking (sidebar)
        2. Click "🔄 Sync Prices" in the Tracked Items tab
        3. Return here to view trends
        """)

# Footer
st.markdown("---")
st.caption("⚠️ This tool is for informational purposes only. Always verify prices on Home Depot's official website.")

