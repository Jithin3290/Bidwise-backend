# BidWise AI Service (FastAPI)

A high-performance, async AI service for freelancer scoring and job matching using FastAPI, ChromaDB, and RabbitMQ.

## Features

- 🚀 **FastAPI** - High-performance async Python framework
- 🧠 **AI Scoring** - Gemini-powered freelancer scoring
- 🔍 **Semantic Search** - ChromaDB vector search with HuggingFace embeddings
- 📨 **RabbitMQ** - Event-driven architecture with async consumers
- ⚡ **Fully Async** - Non-blocking database and message queue operations

## Quick Start

### 1. Install Dependencies

```bash
cd ai_service_fastapi
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your settings
```

Required environment variables:
- `GEMINI_API_KEY` - Google Gemini API key
- `DATABASE_URL` - PostgreSQL connection string
- `RABBITMQ_URL` - RabbitMQ connection string

### 3. Start RabbitMQ (Docker)

```bash
docker run -d --name rabbitmq \
  -p 5672:5672 \
  -p 15672:15672 \
  rabbitmq:management
```

### 4. Run the Service

```bash
# Development (with auto-reload)
uvicorn main:app --reload --port 8006

# Production
uvicorn main:app --host 0.0.0.0 --port 8006 --workers 4
```

### 5. Access API Documentation

- Swagger UI: http://localhost:8006/docs
- ReDoc: http://localhost:8006/redoc

## API Endpoints

### Scoring

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/scoring/health` | Health check |
| POST | `/api/scoring/calculate` | Calculate score for a freelancer |
| GET | `/api/scoring/score/{user_id}` | Get cached score |
| POST | `/api/scoring/bulk-calculate` | Calculate multiple scores |
| GET | `/api/scoring/top-freelancers` | Get top-rated freelancers |
| GET | `/api/scoring/stats` | Get scoring statistics |

### Job Matching

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/scoring/match-job` | Find best matches for a job |
| GET | `/api/scoring/job-matches/{job_id}` | Get existing matches |
| POST | `/api/scoring/index-freelancer` | Index a freelancer |
| POST | `/api/scoring/bulk-index` | Bulk index freelancers |
| POST | `/api/scoring/delete-freelancer` | Remove from index |
| POST | `/api/scoring/reindex-all` | Reindex all freelancers |

## RabbitMQ Events

### Incoming Events (Consumed)

| Event | Queue | Action |
|-------|-------|--------|
| `freelancer.registered` | ai.freelancer.index | Auto-index and calculate score |
| `freelancer.updated` | ai.freelancer.index | Re-index and recalculate |
| `freelancer.deleted` | ai.freelancer.index | Remove from index |
| `job.posted` | ai.job.match | Find matches, publish results |

### Outgoing Events (Published)

| Event | Description |
|-------|-------------|
| `score.calculated` | Freelancer score was calculated |
| `matches.found` | Job matches were found |
| `freelancer.indexed` | Freelancer was indexed successfully |
| `freelancer.index_failed` | Indexing failed |

## Project Structure

```
ai_service_fastapi/
├── main.py                 # FastAPI app entry point
├── config.py               # Pydantic settings
├── database.py             # Async database connection
├── requirements.txt        # Dependencies
├── .env.example            # Environment template
├── models/
│   └── schemas.py          # Pydantic models
├── services/
│   ├── scoring_engine.py   # AI scoring logic
│   ├── vector_search.py    # ChromaDB operations
│   └── cache.py            # TTL caching
├── routes/
│   ├── scoring.py          # Scoring endpoints
│   └── matching.py         # Job matching endpoints
└── rabbitmq/
    ├── connection.py       # RabbitMQ connection
    ├── events.py           # Event definitions
    ├── publisher.py        # Event publisher
    └── consumer.py         # Event consumers
```

## Example Usage

### Calculate Score

```bash
curl -X POST http://localhost:8006/api/scoring/calculate \
  -H "Content-Type: application/json" \
  -d '{"user_id": 1}'
```

### Match Job

```bash
curl -X POST http://localhost:8006/api/scoring/match-job \
  -H "Content-Type: application/json" \
  -d '{
    "job_id": "job-123",
    "job_description": "Looking for a Python developer with Django experience",
    "required_skills": ["Python", "Django", "REST API"],
    "top_k": 5
  }'
```

### Index Freelancer

```bash
curl -X POST http://localhost:8006/api/scoring/index-freelancer \
  -H "Content-Type: application/json" \
  -d '{"user_id": 1}'
```

## License

MIT
