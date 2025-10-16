@echo off
REM Start script for DES Web Backend (Windows)

echo 🚀 Starting DES Formulation System Web Backend...

REM Check if .env exists
if not exist ".env" (
    echo ⚠️ Warning: .env file not found. Creating from .env.example...
    copy .env.example .env
    echo ✓ Please edit .env file with your configuration
    exit /b 1
)

REM Check if virtual environment exists
if not exist "venv" (
    echo 📦 Creating virtual environment...
    python -m venv venv
)

REM Activate virtual environment
echo 🔌 Activating virtual environment...
call venv\Scripts\activate.bat

REM Install dependencies
echo 📥 Installing dependencies...
pip install -r requirements.txt

REM Check for API key (simplified for Windows)
findstr /C:"DASHSCOPE_API_KEY" .env >nul
if errorlevel 1 (
    findstr /C:"OPENAI_API_KEY" .env >nul
    if errorlevel 1 (
        echo ❌ Error: No API key found in .env
        echo    Please set DASHSCOPE_API_KEY or OPENAI_API_KEY
        exit /b 1
    )
)

REM Start server
echo ✓ Starting FastAPI server...
python main.py
