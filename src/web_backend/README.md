# DES Formulation System - Web Backend

FastAPI-based REST API for Deep Eutectic Solvent (DES) formulation recommendation and experimental feedback management.

## 📋 Features

- ✅ **Task Creation**: Submit tasks to generate DES formulation recommendations
- ✅ **Recommendation Management**: List, view, and manage recommendations
- ✅ **Experimental Feedback**: Submit real lab results and learn from them
- ✅ **Statistics Dashboard**: View system performance and trends
- ✅ **Auto-generated API Documentation**: Swagger UI at `/docs`

## 🚀 Quick Start

### Prerequisites

- Python 3.13+
- API Key for LLM provider (DashScope or OpenAI)
- Agent configuration file at `../agent/config/reasoningbank_config.yaml`

### Installation

#### Option 1: Using Start Script (Recommended)

**Linux/Mac**:
```bash
cd src/web_backend
chmod +x start.sh
./start.sh
```

**Windows**:
```cmd
cd src\web_backend
start.bat
```

#### Option 2: Manual Setup

```bash
# 1. Create virtual environment
cd src/web_backend
python -m venv venv

# 2. Activate virtual environment
# Linux/Mac:
source venv/bin/activate
# Windows:
venv\Scripts\activate.bat

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env and set your API key

# 5. Start server
python main.py
```

### Configuration

Edit `.env` file:

```ini
# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
API_RELOAD=true

# CORS Origins (comma-separated)
CORS_ORIGINS=http://localhost:3000,http://localhost:3001

# LLM API Key (choose one)
DASHSCOPE_API_KEY=your_dashscope_api_key
# OPENAI_API_KEY=your_openai_api_key

# Agent Configuration
AGENT_CONFIG_PATH=../agent/config/reasoningbank_config.yaml
RECOMMENDATIONS_PATH=../../data/recommendations
MEMORY_PATH=../../data/memory

# Logging
LOG_LEVEL=INFO
```

## 📡 API Endpoints

### Health Check

```bash
GET /
GET /health
```

### Tasks

```bash
POST /api/v1/tasks
```

**Request Body**:
```json
{
  "description": "Design a DES formulation to dissolve cellulose at room temperature (25°C)",
  "target_material": "cellulose",
  "target_temperature": 25.0,
  "constraints": {
    "max_viscosity": "500 cP",
    "component_availability": "common chemicals only"
  }
}
```

**Response**:
```json
{
  "status": "success",
  "message": "Recommendation REC_20251016_123456 created successfully",
  "data": {
    "task_id": "task_20251016_123456",
    "recommendation_id": "REC_20251016_123456_task_20251016_123456",
    "formulation": {
      "HBD": "Urea",
      "HBA": "Choline chloride",
      "molar_ratio": "1:2"
    },
    "reasoning": "Based on literature precedents...",
    "confidence": 0.85,
    "supporting_evidence": ["...", "..."],
    "status": "PENDING",
    "created_at": "2025-10-16T12:34:56",
    "memories_used": ["Memory 1", "Memory 2"],
    "next_steps": "Please perform experiment and submit feedback..."
  }
}
```

### Recommendations (✅ Week 1 Day 3 Completed)

```bash
GET /api/v1/recommendations
GET /api/v1/recommendations/{id}
PATCH /api/v1/recommendations/{id}/cancel
```

**List Recommendations**:
```bash
curl "http://localhost:8000/api/v1/recommendations?status=PENDING&page=1&page_size=20"
```

**Get Recommendation Detail**:
```bash
curl http://localhost:8000/api/v1/recommendations/REC_20251016_123456_task_001
```

**Cancel Recommendation**:
```bash
curl -X PATCH http://localhost:8000/api/v1/recommendations/REC_20251016_123456_task_001/cancel
```

### Feedback (✅ Week 1 Day 4 Completed)

```bash
POST /api/v1/feedback
```

**Submit Experimental Feedback**:
```bash
curl -X POST http://localhost:8000/api/v1/feedback \
  -H "Content-Type: application/json" \
  -d '{
    "recommendation_id": "REC_20251016_123456_task_001",
    "experiment_result": {
      "is_liquid_formed": true,
      "solubility": 6.5,
      "solubility_unit": "g/L",
      "properties": {
        "viscosity": "45 cP",
        "density": "1.15 g/mL",
        "appearance": "clear liquid"
      },
      "experimenter": "Dr. Zhang",
      "notes": "DES formed successfully at room temperature."
    }
  }'
```

**Response**:
```json
{
  "status": "success",
  "message": "Experimental feedback processed successfully. Performance: 6.5/10.0. Extracted 2 new memories.",
  "data": {
    "recommendation_id": "REC_20251016_123456_task_001",
    "performance_score": 6.5,
    "memories_extracted": [
      "ChCl:Urea (1:2) Achieves 6.5 g/L Cellulose Solubility at 25°C",
      "Room Temperature DES Formation Success with ChCl-Urea System"
    ],
    "num_memories": 2
  }
}
```

### Statistics (✅ Week 1 Day 5 Completed)

```bash
GET /api/v1/statistics
GET /api/v1/statistics/performance-trend
```

**Get System Statistics**:
```bash
curl http://localhost:8000/api/v1/statistics
```

**Response**:
```json
{
  "status": "success",
  "message": "Statistics retrieved successfully. Total: 150 recommendations, Avg Performance: 7.2/10.0",
  "data": {
    "summary": {
      "total_recommendations": 150,
      "pending_experiments": 45,
      "completed_experiments": 95,
      "cancelled": 10,
      "average_performance_score": 7.2,
      "liquid_formation_rate": 0.89
    },
    "by_material": {
      "cellulose": 80,
      "lignin": 45,
      "chitin": 25
    },
    "by_status": {
      "PENDING": 45,
      "COMPLETED": 95,
      "CANCELLED": 10
    },
    "performance_trend": [
      {
        "date": "2025-10-14",
        "avg_solubility": 6.8,
        "avg_performance_score": 7.1,
        "experiment_count": 12,
        "liquid_formation_rate": 0.92
      }
    ],
    "top_formulations": [
      {
        "formulation": "Choline chloride:Urea (1:2)",
        "avg_performance": 8.5,
        "success_count": 12
      }
    ]
  }
}
```

**Get Performance Trend by Date Range**:
```bash
curl "http://localhost:8000/api/v1/statistics/performance-trend?start_date=2025-10-01&end_date=2025-10-16"
```

**Response**:
```json
{
  "status": "success",
  "message": "Performance trend retrieved: 15 data points from 2025-10-01 to 2025-10-16",
  "data": [
    {
      "date": "2025-10-01",
      "avg_solubility": 5.8,
      "avg_performance_score": 6.5,
      "experiment_count": 8,
      "liquid_formation_rate": 0.88
    },
    {
      "date": "2025-10-02",
      "avg_solubility": 6.2,
      "avg_performance_score": 6.9,
      "experiment_count": 10,
      "liquid_formation_rate": 0.90
    }
  ]
}
```

## 📚 API Documentation

Once the server is running:

- **Swagger UI**: http://localhost:8000/docs (Interactive API testing)
- **ReDoc**: http://localhost:8000/redoc (API reference)

All endpoints support:
- ✅ Automatic request validation (Pydantic)
- ✅ Auto-generated documentation
- ✅ Type-safe responses
- ✅ Standard error responses

## 🏗️ Project Structure

```
src/web_backend/
├── main.py                    # FastAPI application entry point
├── config.py                  # Configuration management
├── requirements.txt           # Python dependencies
├── .env.example              # Environment template
├── api/                      # API route handlers
│   ├── __init__.py
│   ├── tasks.py              # Task endpoints (✅ Implemented)
│   ├── recommendations.py    # Recommendation endpoints (✅ Implemented)
│   ├── feedback.py           # Feedback endpoints (✅ Implemented)
│   └── statistics.py         # Statistics endpoints (✅ Implemented)
├── services/                 # Business logic layer
│   ├── __init__.py
│   ├── task_service.py       # Task service (✅ Implemented)
│   ├── recommendation_service.py  # Recommendation service (✅ Implemented)
│   ├── feedback_service.py   # Feedback service (✅ Implemented)
│   └── statistics_service.py # Statistics service (✅ Implemented)
├── models/                   # Pydantic data models
│   ├── __init__.py
│   └── schemas.py            # Request/response schemas (✅ Implemented)
└── utils/                    # Utility functions
    ├── __init__.py
    ├── agent_loader.py       # DESAgent initialization (✅ Implemented)
    └── response.py           # Response helpers (✅ Implemented)
```

## 🧪 Testing

### Test with curl

```bash
# Health check
curl http://localhost:8000/health

# Create task
curl -X POST http://localhost:8000/api/v1/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "description": "Design DES for cellulose at 25°C",
    "target_material": "cellulose",
    "target_temperature": 25.0
  }'
```

### Test with Python requests

```python
import requests

# Create task
response = requests.post(
    "http://localhost:8000/api/v1/tasks",
    json={
        "description": "Design DES for cellulose at 25°C",
        "target_material": "cellulose",
        "target_temperature": 25.0
    }
)

print(response.json())
```

## 🔧 Development

### Run with auto-reload

```bash
# Already enabled in .env by default (API_RELOAD=true)
python main.py
```

### View logs

Logs are printed to console with format:
```
2025-10-16 12:34:56 - module_name - INFO - message
```

## 🐛 Troubleshooting

### Issue: "Agent not initialized"

**Solution**: Ensure `../agent/config/reasoningbank_config.yaml` exists and is valid.

### Issue: "LLM initialization failed"

**Solution**: Check your API key in `.env` file. Make sure you have either `DASHSCOPE_API_KEY` or `OPENAI_API_KEY` set.

### Issue: "Module not found"

**Solution**:
```bash
# Make sure parent directories are in Python path
cd src/web_backend
python -c "import sys; sys.path.insert(0, '..'); from agent.des_agent import DESAgent"
```

### Issue: "CORS error from frontend"

**Solution**: Add your frontend URL to `CORS_ORIGINS` in `.env`:
```ini
CORS_ORIGINS=http://localhost:3000,http://your-frontend-url:port
```

## 📈 Performance

- **Cold start**: ~5-10 seconds (Agent initialization)
- **Task creation**: ~3-10 seconds (includes LLM calls)
- **Health check**: < 50ms

## 🛡️ Security Notes

- API keys are loaded from environment variables (never commit `.env`)
- CORS is configured for specific origins only
- Input validation via Pydantic models
- No authentication in MVP (add in Phase 2)

## 📝 Development Roadmap

### Week 1 (✅ Completed)
- [x] Day 1-2: Project setup + Task creation API
- [x] Day 3: Recommendation management APIs
- [x] Day 4: Feedback submission API
- [x] Day 5: Statistics API

### Week 2-3
- [ ] Frontend development
- [ ] Integration testing
- [ ] Deployment preparation

## 🤝 Contributing

This is an internal research project. For questions or issues, contact the development team.

## 📄 License

Proprietary - Research Use Only

---

**Last Updated**: 2025-10-16
**Version**: 1.0.0 (MVP - Week 1 Complete ✅)
