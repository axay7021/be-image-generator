# Barber Shop Appointment Agent

An AI-powered voice agent for Barber Shop appointments, built with FastAPI, LiveKit, and Clean Architecture.

## Features

- 🤖 **AI Voice Agent** - Context-aware voice interaction using LiveKit & LLMs.
- 📅 **Appointment Management** - Real-time booking, updating, and cancellation.
- 🐳 **Docker Ready** - Fully containerized for production.
- ✅ **Production Grade** - SQLAlchemy 2.0, Alembic, Pydantic v2, and Strict Linting.
- 🔒 **Secure** - JWT Authentication and Rate Limiting.

## Project Structure

```
.
├── app/
│   ├── agents/         # AI Agent Logic (LiveKit)
│   ├── core/           # Config, Logging, Security
│   ├── db/             # Database Session & Models
│   ├── routers/        # API Endpoints
│   ├── services/       # Business Logic
│   └── main.py         # App Entry Point
├── alembic/            # Database Migrations
├── tests/              # Pytest Suite
├── docker-compose.yml  # Local Development Setup
├── Dockerfile          # Production Image
└── pyproject.toml      # Dependencies & Tool Config
```

## Quick Start (Docker)

The easiest way to run the project is with Docker Compose.

1.  **Configure Environment**
    Copy `.env.example` to `.env` (create one if missing) and set your keys.
    ```bash
    # See app/core/settings.py for required variables
    APP_NAME="Barber Shop Agent"
    DATABASE_URL="postgresql://postgres:postgres@db:5432/barber_db"
    ```

2.  **Run with Docker Compose**
    ```bash
    docker compose up --build
    ```
    - API: http://localhost:8000/docs
    - DB: localhost:5432

## Development (Local)

1.  **Install `uv`** (modern python package manager)
    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

2.  **Install Dependencies**
    ```bash
    uv sync
    ```

3.  **Run Migrations**
    ```bash
    uv run alembic upgrade head
    ```

4.  **Run Server**
    ```bash
    uv run uvicorn app.main:app --reload
    ```

## Code Quality

Run the following to check code quality:

```bash
# Linting
uv run ruff check .

# Formatting
uv run ruff format .

# Tests
uv run pytest
```
