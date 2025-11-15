#!/bin/bash
# ============================================
# DES System - Quick Deploy Script
# ============================================

set -e

echo "======================================"
echo "DES System Deployment"
echo "======================================"
echo ""

# Check if .env.production exists
if [ ! -f ".env.production" ]; then
    echo "❌ Error: .env.production not found"
    echo "   Please create .env.production with your configuration"
    exit 1
fi

# Check if config files exist
if [ ! -f "config/production/largerag_settings.yaml" ]; then
    echo "❌ Error: config/production/largerag_settings.yaml not found"
    exit 1
fi

if [ ! -f "config/production/corerag_settings.yaml" ]; then
    echo "❌ Error: config/production/corerag_settings.yaml not found"
    exit 1
fi

echo "✓ Configuration files found"
echo ""

# Create necessary directories
echo "📁 Creating data directories..."
mkdir -p data/ontology
mkdir -p data/recommendations
mkdir -p data/memory
mkdir -p logs
mkdir -p src/tools/largerag/data/chroma_db_prod
mkdir -p src/tools/largerag/data/prod_cache
echo "✓ Directories created"
echo ""

# Build and start
echo "🐳 Building and starting Docker containers..."
docker compose --env-file .env.production up -d --build

echo ""
echo "⏳ Waiting for services to be healthy..."
sleep 10

echo ""
echo "======================================"
echo "Deployment Complete!"
echo "======================================"
echo ""
echo "Services:"
echo "  - Frontend: http://localhost (or configured port)"
echo "  - Backend API: http://localhost:8000"
echo "  - API Docs: http://localhost:8000/docs"
echo ""
echo "Useful commands:"
echo "  - View logs: docker compose logs -f"
echo "  - Stop services: docker compose down"
echo "  - Restart: docker compose restart"
echo "  - Health check: ./deploy/healthcheck.sh"
echo ""
echo "Running health check..."
./deploy/healthcheck.sh
