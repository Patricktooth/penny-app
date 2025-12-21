# Home Depot Penny Drop Tracker

A Streamlit application that tracks Home Depot product prices and predicts "penny drops" - when clearance items reach $0.01.

## Features

- 🔍 **Price Tracking**: Monitor Home Depot product prices using Playwright with stealth mode
- 📊 **Penny Drop Prediction**: Predict when items will hit the $0.01 markdown stage
- 🔥 **Clearance Importer**: Automatically find clearance items using the NCNI-5 hack
- 📈 **Price History**: Track price changes over time
- ⚠️ **Alert System**: Get notified when items are likely to penny out

## Setup

### Local Development

1. Clone the repository:
```bash
git clone https://github.com/deffiedeff2/penny-app.git
cd penny-app
```

2. Run the setup script:
```bash
chmod +x setup.sh
./setup.sh
```

3. Activate the virtual environment:
```bash
source venv/bin/activate
```

4. Run the Streamlit app:
```bash
streamlit run app.py
```

## How It Works

### Price Markdown Cycle

Home Depot follows a predictable markdown cycle:
- Markdowns occur every **3 weeks** (21 days)
- Items drop to **$0.01** exactly **14 weeks** after first clearance markdown

### Price Ending Indicators

- **.02** = 🔴 **EXTREME ALERT!** Hidden 90% markdown - Penny drop in 7-14 days
- **.03** = 🟠 **HIGH ALERT!** Penny drop likely in 14-21 days
- **.06** = 🟡 **MODERATE ALERT** - Next drop in ~21 days
- **.00/.99** = Regular pricing (not in clearance cycle)

### Clearance Importer

The importer uses the "NCNI-5" hack to filter Home Depot categories for clearance items only. It focuses on:
- **Christmas Trees** - Post-holiday markdowns
- **Power Tool Kits** - Black Friday leftovers
- **Holiday Lights** - High inventory turnover

## Deployment

### Streamlit Community Cloud

1. Ensure your repository is **public** on GitHub
2. Go to [Streamlit Community Cloud](https://share.streamlit.io/)
3. Click "New app" and connect your GitHub repository
4. Select the repository: `deffiedeff2/penny-app`
5. Set the main file path: `app.py`
6. Click "Deploy"

**Note**: The app automatically installs Playwright browser binaries on first launch. This may take 1-2 minutes during the initial deployment. The app will show a message when installation is in progress.

**Important**: If you encounter issues with Playwright on Streamlit Cloud:
- The first deployment may take longer due to browser installation
- If installation fails, try redeploying the app
- Make sure your repository is public (required for Streamlit Community Cloud)

## Project Structure

```
penny-app/
├── app.py              # Streamlit main application
├── scraper.py          # Playwright-based price scraper
├── importer.py         # Clearance item importer (NCNI-5 hack)
├── setup.sh            # Setup script for local development
├── requirements.txt    # Python dependencies
├── tracked_skus.csv    # Tracked SKUs (user-specific, not in repo)
└── price_history.csv   # Price history (user-specific, not in repo)
```

## Requirements

- Python 3.8+
- Playwright (with Chromium browser)
- Streamlit
- Pandas

## License

See LICENSE file for details.
