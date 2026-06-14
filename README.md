# ⚡ Dev Dashboard - Celery Task Queue Manager

Dev Dashboard is a premium, real-time distributed task manager and monitor built on **FastAPI**, **Celery**, **Redis**, **pgvector PostgreSQL**, and **React (Vite) + TailwindCSS v4**.

It supports advanced job scheduling, priority queue routing, secure API key scoping, pgvector-based text chunking & embedding, and cooperative task cancellation, with all status and log feeds streamed live over WebSockets.

---

## 🏗️ Architecture

```
                 ┌───────────────────────────────────────┐
                 │          Vite React Frontend          │
                 │   (API Key, Stats Panel, Log Console)  │
                 └──────────────────┬────────────────────┘
                                    │ HTTP / WebSockets
                                    ▼
                 ┌───────────────────────────────────────┐
                 │            FastAPI Backend            │
                 │    (REST API & WebSocket handlers)    │
                 └──────────┬──────────────────┬─────────┘
                            │ Writes           │ Publishes Status
                            │                  ▼
                            │           ┌──────────────┐
                            │           │    Redis     │ (Message Broker, Pub/Sub,
                            │           │  Broker/PS   │  & Celery Result Backend)
                            │           └──────┬───────┘
                            │                  │
                            ▼                  ▼ Picks up Tasks
                 ┌──────────────────┐   ┌──────────────────────┐
                 │    PostgreSQL    │   │    Celery Workers    │
                 │   (with pgvector │◄──┤ (Custom Log Handler, │
                 │    extension)    │   │  Cooperative Loops)  │
                 └──────────────────┘   └──────────────────────┘
```

---

## 🚀 Key Features

* **Dual-Channel WebSocket Streaming**: Logs are streamed in real-time on a job-specific WebSocket (`/api/jobs/{id}/stream`), while job statuses and progress percentages are broadcasted globally (`/api/jobs/stream`) to update the table immediately without polling.
* **Cooperative Cancellation**: Submitting `DELETE /api/jobs/{id}` revokes the Celery task, updates Postgres to `CANCELLED`, and writes a Redis flag. Task worker loops periodically check this flag to exit cleanly, preventing database session leaks or orphaned processes.
* **Custom Logging Handler**: Attached via Celery's `after_setup_task_logger` signal, duplication of all standard logger (`logger.info`/`logger.error`) calls occurs automatically to both Postgres storage and Redis Pub/Sub channels.
* **pgvector Database Integration**: The database base image uses `pgvector/pgvector:pg16`. An Alembic startup migration registers the vector extension, supporting document embedding tasks by chunking and persisting actual **1536-dimensional float vectors**.
* **Priority Queue Routing**: Celery is configured with `high`, `celery` (default), and `low` queues. API submissions can specify priorities, which are routed to the corresponding worker priority queue dynamically.
* **API Key Authorization & Scopes**: Endpoints are locked behind bearer authentication. API keys are stored in the DB with scopes (e.g. `["task:sleep_task", "priority:low"]`) restricting task execution.
* **Operations Dashboard**: Real-time metrics tracking total throughput, average execution duration for successful tasks, and task failure rates.

---

## 📁 Project Directory Structure

```
d:\Dev Dashboard/
├── docker-compose.yml            # Multi-container orchestrator (pgvector, Redis, API, Worker, Beat, Vite)
├── start.bat                     # Windows launch script (checks Docker, runs stack, opens browser)
├── start.sh                      # macOS/Linux launch script (checks Docker, runs stack, opens browser)
├── .gitignore                    # Global git ignore configuration
├── backend/
│   ├── Dockerfile
│   ├── .dockerignore             # Excludes pycache, env, and virtual environments from build
│   ├── entrypoint.sh             # Waits for DB & applies Alembic migrations
│   ├── requirements.txt
│   ├── alembic.ini
│   ├── app/
│   │   ├── main.py               # FastAPI App & startup seeding
│   │   ├── core/
│   │   │   ├── config.py         # Pydantic Settings
│   │   │   ├── database.py       # Hybrid Async (FastAPI) and Sync (Celery) session pooling
│   │   │   ├── celery_app.py     # Celery app, queues, signals, and Beat schedule
│   │   │   └── logging_handler.py# Custom Log interceptor (SQL + Redis Pub/Sub)
│   │   ├── models/
│   │   │   ├── base.py
│   │   │   ├── job.py            # Job status and priority metadata
│   │   │   ├── job_log.py        # Indexed logs
│   │   │   ├── api_key.py        # Scoped auth keys
│   │   │   └── document.py       # pgvector document embeddings
│   │   ├── schemas/              # Pydantic validation schemas
│   │   ├── api/
│   │   │   ├── dependencies.py   # API key bearer token verification & scopes check
│   │   │   └── endpoints/
│   │   │       ├── jobs.py       # Job REST & WebSocket endpoints
│   │   │       └── metrics.py    # Metrics aggregator
│   │   └── tasks/
│   │       ├── registry.py       # Task mapping registry
│   │       ├── dummy.py          # Sleep task loop
│   │       ├── ingest.py         # Codebase ingestion loop
│   │       └── embed.py          # pgvector text embedding pipeline
│   └── migrations/               # Alembic database migration revisions
└── frontend/
    ├── Dockerfile
    ├── .dockerignore             # Excludes local node_modules and build output from build
    ├── package.json
    ├── vite.config.js            # Tailwind v4 plugin & API + WebSocket Proxy mapping
    ├── src/
    │   ├── main.jsx
    │   ├── App.jsx               # Dashboard, WebSocket connections & stats panels
    │   ├── index.css             # Tailwind v4 directives & Google Font Outfit
    │   └── components/
    │       ├── JobSubmitForm.jsx # Dynamic form fields & priority selector
    │       └── JobTable.jsx      # Job list with indicator state badges & progress bars
```

---

## 🛠️ Quick Start (One-Click Launch)

To run the entire stack (FastAPI, Celery workers, Celery beat, PostgreSQL with pgvector, Redis, and React Frontend), ensure **Docker Desktop** is installed and running, then use the appropriate launcher for your OS:

### Windows
Double-click `start.bat` or run it from the command line:
```cmd
start.bat
```

### macOS / Linux
Run the shell script:
```bash
chmod +x start.sh
./start.sh
```

These scripts will automatically:
1. Verify Docker is running.
2. Build and start the container stack in the background (`docker compose up --build -d`).
3. Open the Frontend UI (`http://localhost:5173`) in your default web browser.

### Mapped Ports & Access
* **Frontend UI**: [http://localhost:5173](http://localhost:5173) (Uses a unified WebSocket and HTTP proxy).
* **Backend API Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
* **PostgreSQL Vector Database**: Mapped to host port **`5435`** to prevent collisions with any native host PostgreSQL services.
* **Default Scoped API Key**: `dev-dashboard-super-key`

---

## ⚙️ Manual Control

### Starting the Stack manually:
```bash
docker compose up --build -d
```

### Stopping the Stack:
```bash
docker compose down
```

### Viewing Container Logs:
```bash
docker compose logs -f
```

### Scaling Celery Workers:
To scale out task workers horizontally:
```bash
docker compose up -d --scale worker=3
```

---

## 🧪 Running Integration Tests

An automated Python script is provided to test API Key security, WebSockets, priority queueing, pgvector inserts, and cooperative cancellation.

### Prerequisites (Host)
Initialize your virtual environment and install test dependencies:
```bash
myenv\Scripts\pip install -r backend/requirements.txt
myenv\Scripts\pip install requests
```