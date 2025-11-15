#!/bin/bash
# ============================================
# DES System Health Check Script
# ============================================
# 用于 Docker 部署后验证服务健康状态

set -e

echo "======================================"
echo "DES System Health Check"
echo "======================================"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Backend URL
BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"
FRONTEND_URL="${FRONTEND_URL:-http://localhost}"

# Check counter
PASSED=0
FAILED=0

# Function to check endpoint
check_endpoint() {
    local name=$1
    local url=$2
    local expected_code=${3:-200}

    echo -n "Checking $name... "

    http_code=$(curl -s -o /dev/null -w "%{http_code}" "$url" 2>&1)

    if [ "$http_code" == "$expected_code" ]; then
        echo -e "${GREEN}✓ OK${NC} (HTTP $http_code)"
        ((PASSED++))
        return 0
    else
        echo -e "${RED}✗ FAILED${NC} (HTTP $http_code, expected $expected_code)"
        ((FAILED++))
        return 1
    fi
}

# Function to check container
check_container() {
    local name=$1
    echo -n "Checking container $name... "

    if docker ps --filter "name=$name" --filter "status=running" | grep -q "$name"; then
        echo -e "${GREEN}✓ Running${NC}"
        ((PASSED++))
        return 0
    else
        echo -e "${RED}✗ Not running${NC}"
        ((FAILED++))
        return 1
    fi
}

echo "=== Container Status ==="
check_container "des-backend"
check_container "des-frontend"
echo ""

echo "=== Backend Health ==="
check_endpoint "Health Check" "$BACKEND_URL/health"
check_endpoint "Root Endpoint" "$BACKEND_URL/"
check_endpoint "API Docs" "$BACKEND_URL/docs"
echo ""

echo "=== Frontend Health ==="
check_endpoint "Frontend Root" "$FRONTEND_URL"
echo ""

echo "=== API Endpoints ==="
check_endpoint "Tasks API" "$BACKEND_URL/api/v1/tasks" 200
check_endpoint "Statistics API" "$BACKEND_URL/api/v1/statistics" 200
echo ""

echo "======================================"
echo "Health Check Summary"
echo "======================================"
echo -e "Passed: ${GREEN}$PASSED${NC}"
echo -e "Failed: ${RED}$FAILED${NC}"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}All checks passed! ✓${NC}"
    exit 0
else
    echo -e "${RED}Some checks failed. Please check the logs.${NC}"
    echo ""
    echo "View logs with:"
    echo "  docker compose logs -f backend"
    echo "  docker compose logs -f frontend"
    exit 1
fi
