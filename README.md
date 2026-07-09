# MerYDiaN - Multi-Family Travel Coordination Platform

## 🔴 [LIVE] Check it out! &nbsp;&nbsp;&nbsp;&nbsp; [![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://merydian.streamlit.app/)
### The interactive demo of the **Merydian Optimization Engine and Explainability Workflow** is live! Click the badge above or go to [`https://merydian.streamlit.app/`](https://merydian.streamlit.app/) to try it yourself.




MerYDiaN is an agentic travel coordination system designed to manage complex multi-family group trips. The platform combines real-time event handling, human-in-the-loop decision making, and automated booking execution to deliver adaptive travel experiences.

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [API Reference](#api-reference)
- [Authentication](#authentication)
- [Agentic System](#agentic-system)
- [Contracts](#contracts)
- [Development Status](#development-status)

---

## Architecture Overview

The system follows a three-tier architecture with an agentic middleware layer:

```
+------------------+     +------------------+     +------------------+
|    Frontend      |     |     Backend      |     |   Agentic Layer  |
|    (Next.js)     |<--->|    (FastAPI)     |<--->|   (Planned)      |
+------------------+     +------------------+     +------------------+
        |                        |                        |
        v                        v                        v
+------------------+     +------------------+     +------------------+
| Traveller App    |     | REST API         |     | Feedback Agent   |
| Agent Dashboard  |     | JWT Auth         |     | Decision Agent   |
| Map View         |     | Event Ingestion  |     | Optimization     |
| POI Management   |     | Booking Exec     |     | Tools Agent      |
+------------------+     +------------------+     +------------------+
```

### Core Concepts

- **Subgroups**: Families can be dynamically split and merged during trips
- **Events**: Real-time incidents (delays, cancellations) trigger the agentic pipeline
- **Human-in-the-Loop**: Travel agents review and approve AI-generated options
- **POI Requests**: Families can request points of interest with urgency levels

---

## Tech Stack

### Backend
- Python 3.11+
- FastAPI (REST API framework)
- Pydantic (data validation)
- python-jose (JWT authentication)
- SQLModel (ORM - planned)
- Celery + Redis (async tasks - planned)

### Frontend
- Next.js 16.1
- React 19
- TypeScript
- Tailwind CSS 4
- Lucide React (icons)

### Infrastructure
- Docker (containerization - planned)
- PostgreSQL (database - planned)
- Redis (message queue - planned)

---

## Project Structure

```
MerYDiaN/
├── backend/
│   ├── app/
│   │   ├── api/                 # API route handlers
│   │   │   ├── auth.py          # Authentication endpoints
│   │   │   ├── events.py        # Event ingestion
│   │   │   ├── itinerary.py     # Traveller operations
│   │   │   ├── agent_dashboard.py # Agent HITL operations
│   │   │   └── bookings.py      # Booking execution
│   │   ├── core/                # Core utilities
│   │   │   ├── config.py        # Application settings
│   │   │   ├── dependencies.py  # FastAPI dependencies
│   │   │   └── security.py      # JWT utilities
│   │   ├── schemas/             # Pydantic models
│   │   │   ├── auth.py          # Auth schemas
│   │   │   └── events.py        # Event schemas
│   │   ├── agents/              # Agent implementations (planned)
│   │   ├── jobs/                # Background jobs (planned)
│   │   ├── models/              # Database models (planned)
│   │   ├── services/            # Business logic (planned)
│   │   └── main.py              # Application entry point
│   ├── tests/                   # Test suite
│   └── requirements.txt         # Python dependencies
├── frontend/
│   ├── app/                     # Next.js app router
│   │   ├── agent/               # Agent dashboard pages
│   │   ├── bookings/            # Booking pages
│   │   ├── dashboard/           # Main dashboard
│   │   ├── itinerary/           # Itinerary views
│   │   ├── login/               # Authentication
│   │   ├── map/                 # Map interface
│   │   └── poi/                 # POI management
│   ├── components/              # React components
│   │   ├── ItineraryTimeline.tsx
│   │   ├── MapView.tsx
│   │   ├── PhotoGallery.tsx
│   │   ├── POICard.tsx
│   │   └── SubgroupBadge.tsx
│   ├── services/                # API client services
│   ├── sockets/                 # WebSocket handlers
│   └── types/                   # TypeScript definitions
├── contracts/                   # JSON Schema contracts
│   ├── poi_request.schema.json
│   ├── poi_request_response.schema.json
│   ├── booking_execute_request.schema.json
│   ├── booking_execute_response.schema.json
│   ├── approve_request.schema.json
│   ├── approve_response.schema.json
│   └── itinerary_options_response.schema.json
├── ml_or/                       # ML/Optimization module (planned)
└── docs/
    └── BACKEND_API_SPEC.md      # Detailed API documentation
```

---

## Getting Started

### Prerequisites

- Python 3.14+
- Node.js 20+
- npm or yarn

### Backend Setup

```bash
# Navigate to backend directory
cd backend

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run development server
uvicorn app.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`

API documentation: `http://localhost:8000/api/v1/openapi.json`

### Frontend Setup

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Run development server
npm run dev
```

The frontend will be available at `http://localhost:3000`

---

## API Reference

Base URL: `/api/v1`

### Authentication

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/auth/login` | OAuth2 password flow login |

### Events

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/events/` | Create event (incident report) |

### Itinerary (Traveller)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/itinerary/current` | Get active itinerary |
| POST | `/itinerary/feedback` | Submit feedback for POI |
| POST | `/itinerary/poi-request` | Request POI visit |

### Agent Dashboard

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/agent/itinerary/options` | Get optimization options |
| POST | `/agent/itinerary/approve` | Approve selected option |

### Bookings

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/bookings/execute` | Execute booking job |

For detailed API specifications, see [docs/BACKEND_API_SPEC.md](docs/BACKEND_API_SPEC.md).

---

## Authentication

The system uses JWT bearer tokens with role-based access control.

### Roles

- `traveller`: Can view itineraries, submit feedback, request POIs
- `agent`: Can view options, approve decisions, execute bookings

### Test Credentials (Development Only)

```
Traveller:
  username: traveller@example.com
  password: password

Agent:
  username: agent@example.com
  password: password
```

### Token Structure

```json
{
  "sub": "user_id",
  "role": "traveller|agent",
  "family_id": "fam_A",
  "exp": 1234567890
}
```

---

## Agentic System

The platform is designed around a multi-agent architecture (implementation planned):

### Agent Types

1. **Feedback Agent**: Normalizes and categorizes incoming events
2. **Decision Agent**: Evaluates thresholds and determines required actions
3. **Optimization Agent**: Generates alternative itinerary options using ML/OR
4. **Tools Agent**: Executes approved bookings via external APIs
5. **Communication Agent**: Notifies travellers of changes

### Event Flow

```
Event Reported -> Feedback Agent -> Decision Agent -> Optimization Agent
                                                            |
                                                            v
Traveller Notified <- Communication Agent <- Tools Agent <- Agent Approval
```

### Human-in-the-Loop

Critical decisions require agent approval before execution:

1. Optimization Agent generates options with cost/satisfaction scores
2. Travel agent reviews options via dashboard
3. Agent approves selected option
4. Tools Agent executes bookings
5. Communication Agent notifies travellers

---

## Contracts

JSON Schema contracts define the API interfaces between components.

### Defined Contracts

| Contract | Status | Description |
|----------|--------|-------------|
| `poi_request.schema.json` | Complete | POI request input |
| `poi_request_response.schema.json` | Complete | POI request response |
| `booking_execute_request.schema.json` | Complete | Booking request |
| `booking_execute_response.schema.json` | Complete | Booking response |
| `approve_request.schema.json` | Complete | Approval request |
| `approve_response.schema.json` | Complete | Approval response |
| `itinerary_options_response.schema.json` | Complete | Options list |
| `event.schema.json` | Empty | Event input |
| `itinerary.schema.json` | Empty | Itinerary structure |
| `agent_output.schema.json` | Empty | Agent output |

---

## Development Status

### Implemented

- [x] FastAPI application structure
- [x] JWT authentication with role-based access
- [x] All API endpoints defined and routed
- [x] Pydantic schema validation
- [x] Frontend Next.js application structure
- [x] Core React components
- [x] Contract schemas (partial)

### Mocked (Requires Implementation)

- [ ] Database integration (PostgreSQL)
- [ ] User persistence and real authentication
- [ ] Event persistence and querying
- [ ] Celery background task processing
- [ ] Agent system implementation
- [ ] External booking API integrations
- [ ] WebSocket real-time updates
- [ ] ML/OR optimization service

### Security Considerations

The following items require attention before production deployment:

1. Replace hardcoded `SECRET_KEY` in `config.py`
2. Add authentication to `/events/` endpoint
3. Implement rate limiting
4. Add audit logging for agent decisions
5. Implement idempotency keys for booking operations
6. Add ownership validation for resources

---

## Configuration

Environment variables (set in `backend/app/core/config.py`):

| Variable | Default | Description |
|----------|---------|-------------|
| `API_V1_STR` | `/api/v1` | API version prefix |
| `PROJECT_NAME` | `MeiliAi` | Application name |
| `SECRET_KEY` | (hardcoded) | JWT signing key |
| `ALGORITHM` | `HS256` | JWT algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Token expiry |
| `BACKEND_CORS_ORIGINS` | `localhost:3000,8000` | Allowed origins |

---

## Testing

```bash
# Backend tests
cd backend
pytest

# Frontend tests
cd frontend
npm test
```

---

## License

Proprietary - All rights reserved.
