#!/bin/bash
#
# Kanban Board - Start Script
# Usage: ./start.sh [development|production]
#

set -e

MODE="${1:-development}"

echo "🚀 Starting Kanban Board Application in $MODE mode..."

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Install/upgrade dependencies
echo "📥 Installing dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

# Create necessary directories
echo "📁 Creating directories..."
mkdir -p uploads backups

# Start application
echo "✅ Starting application..."
if [ "$MODE" = "production" ]; then
    echo "🌐 Production mode - using Gunicorn..."
    pip install -q gunicorn
    gunicorn -w 4 -b 0.0.0.0:8000 app:app
else
    echo "🔧 Development mode - using Flask dev server..."
    python app.py
fi
