#!/bin/bash

# Navigate to your project folder
cd ~/Documents/ConversionRatesAutomationGithub || {
    echo "❌ Folder not found"
    exit 1
}

# Run the Python script
echo "🚀 Starting automation..."
python3 AutomateAll.py

echo "✅ Done"

