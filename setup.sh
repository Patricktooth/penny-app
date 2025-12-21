#!/bin/bash

# Home Depot Price Tracker - Setup Script
# This script creates a virtual environment and installs all required dependencies

set -e  # Exit on any error

echo "🏠 Home Depot Price Tracker - Environment Setup"
echo "================================================"

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: Python 3 is not installed. Please install Python 3.8 or higher."
    exit 1
fi

# Get Python version
PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
echo "✓ Found Python $PYTHON_VERSION"

# Check if virtual environment already exists
if [ -d "venv" ]; then
    echo "⚠️  Virtual environment 'venv' already exists."
    read -p "Do you want to recreate it? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "🗑️  Removing existing virtual environment..."
        rm -rf venv
    else
        echo "📦 Using existing virtual environment..."
        source venv/bin/activate
        echo "⬆️  Upgrading pip..."
        pip install --upgrade pip --quiet
        echo "📥 Installing/updating dependencies..."
        pip install streamlit pandas playwright playwright-stealth --quiet
        echo "🌐 Installing Playwright Chromium browser..."
        playwright install chromium
        echo "✅ Setup complete!"
        exit 0
    fi
fi

# Create virtual environment
echo "📦 Creating virtual environment..."
python3 -m venv venv

# Activate virtual environment
echo "🔌 Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "⬆️  Upgrading pip..."
pip install --upgrade pip --quiet

# Install required packages
echo "📥 Installing dependencies..."
echo "   - streamlit (web UI framework)"
echo "   - pandas (data manipulation)"
echo "   - playwright (browser automation)"
echo "   - playwright-stealth (stealth mode for Playwright)"

pip install streamlit pandas playwright playwright-stealth

# Install Playwright browser binaries
echo ""
echo "🌐 Installing Playwright Chromium browser..."
playwright install chromium

# Verify installations
echo ""
echo "🔍 Verifying installations..."
python3 -c "import streamlit; import pandas; from playwright.async_api import async_playwright; from playwright_stealth import Stealth; print('✅ All packages installed successfully!')"

echo ""
echo "✅ Setup complete!"
echo ""
echo "To activate the virtual environment, run:"
echo "  source venv/bin/activate"
echo ""
echo "To run the Streamlit app, use:"
echo "  streamlit run app.py"
echo ""

