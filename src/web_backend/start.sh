#!/bin/bash
# Start script for DES Web Backend (Linux/Mac)

echo "🚀 Starting DES Formulation System Web Backend..."

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "⚠️  Warning: .env file not found. Creating from .env.example..."
    cp .env.example .env
    echo "✓ Please edit .env file with your configuration"
    exit 1
fi

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python -m venv venv
fi

# Activate virtual environment
echo "🔌 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install -r requirements.txt

# Check for API key
if ! grep -q "DASHSCOPE_API_KEY\|OPENAI_API_KEY" .env; then
    echo "❌ Error: No API key found in .env"
    echo "   Please set DASHSCOPE_API_KEY or OPENAI_API_KEY"
    exit 1
fi

# Start server
echo "✓ Starting FastAPI server..."
python main.py
