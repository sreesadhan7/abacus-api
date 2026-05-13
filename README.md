# Abacus API

Abacus API is a FastAPI microservice that maintains a single running sum and keeps that sum consistent across multiple application instances, as long as every instance points at the same database.

The task requirements were:

- `POST /abacus/number` adds a number to the current running sum.
- `GET /abacus/sum` returns the current running sum.
- `DELETE /abacus/sum` resets the running sum to `0`.
- The service should handle frequent writes, lighter reads, and remain correct across multiple nodes or containers.
- At least two nodes must be demonstrable locally.

This repository satisfies those requirements with:

- FastAPI for the HTTP API.
- SQLAlchemy for database access.
- A single shared-row transactional storage model.
- SQLite for the simplest same-machine two-node demo.
- PostgreSQL for the stronger real multi-container deployment story.

## Table of contents

- [Architecture overview](#architecture-overview)
- [Why this design](#why-this-design)
- [API reference](#api-reference)
- [Project structure](#project-structure)
- [Requirements and prerequisites](#requirements-and-prerequisites)
- [Quick start](#quick-start)
- [Run locally with Python](#run-locally-with-python)
- [Run with Docker Compose](#run-with-docker-compose)
- [How to verify the service](#how-to-verify-the-service)
- [Load and consistency simulation](#load-and-consistency-simulation)
- [Testing](#testing)
- [Environment variables](#environment-variables)
- [How the consistency model works](#how-the-consistency-model-works)
- [Troubleshooting](#troubleshooting)

## Architecture overview

At a high level, every application node talks to the same database.

```text
Client
	|
	+--> FastAPI node 1 ----+
	|                       |
	+--> FastAPI node 2 ----+--> Shared database --> single row holding the running total
	|                       |
	+--> FastAPI node N ----+
```

The running total is not stored in Python memory. It is stored in the database, which means:

- any node can accept a write,
- any node can read the latest committed total,
- restarting one node does not lose the sum,
- correctness depends on the shared database transaction behavior, not on in-process state.

## Why this design

This service is write-heavy on `POST /abacus/number`, so the design prioritizes correctness and a short critical path.

- The running sum lives in one database row.
- `POST /abacus/number` performs an atomic database update: `total = total + N`.
- `GET /abacus/sum` performs a direct read from the same row.
- `DELETE /abacus/sum` updates the same row back to `0`.
- Node startup safely initializes the row even if multiple nodes start at the same time.

Why this matters:

- If the sum were stored in process memory, different nodes would diverge.
- If the code performed read-modify-write in Python, concurrent writes could lose updates.
- By pushing the increment into the database update statement, the storage layer enforces consistency.

Recommended storage choice:

- Use SQLite only for a same-machine demo where multiple processes share the same file.
- Use PostgreSQL for real multi-node or multi-container deployment.

## API reference

### `POST /abacus/number`

Adds a number to the running total.

Request body:

```json
{
	"number": 7
}
```

Response:

```json
{
	"total": 12
}
```

### `GET /abacus/sum`

Returns the current running total.

Response:

```json
{
	"total": 12
}
```

### `DELETE /abacus/sum`

Resets the running total to `0`.

Response:

```json
{
	"total": 0
}
```

### `GET /healthz`

Simple health endpoint used for local checks and container health checks.

Response:

```json
{
	"status": "ok",
	"node": "api-1"
}
```

## Project structure

```text
.
|-- src/
|   `-- abacus_api/
|       |-- __init__.py
|       |-- config.py
|       |-- db.py
|       `-- main.py
|-- tests/
|   `-- test_api.py
|-- scripts/
|   `-- simulate_load.py
|-- Dockerfile
|-- compose.yaml
|-- pyproject.toml
`-- README.md
```

Main files and what they do:

### `src/abacus_api/main.py`

This is the FastAPI entrypoint.

It is responsible for:

- creating the FastAPI application,
- loading runtime settings,
- creating the storage layer,
- initializing the shared database state during app startup,
- exposing the API routes.

Important behavior:

- `create_app()` builds the app so tests can create isolated app instances.
- the lifespan handler initializes the database row before serving traffic,
- the route handlers delegate all state mutation and reads to the store.

### `src/abacus_api/db.py`

This is the core consistency layer.

It is responsible for:

- creating the SQLAlchemy engine,
- defining the `abacus_state` table,
- configuring SQLite pragmas for the local demo,
- implementing atomic add, read, and reset operations,
- making startup initialization safe under concurrent node startup.

Important behavior:

- `build_engine()` creates the database connection.
- SQLite mode enables WAL and a busy timeout to improve concurrent behavior for the same-machine demo.
- `AbacusStore.add()` uses one SQL update statement to increment the total.
- `_ensure_row()` attempts to insert the initial row and ignores duplicate-key races, which makes initialization idempotent.

### `src/abacus_api/config.py`

This file contains runtime configuration.

It is responsible for:

- reading `ABACUS_DB_URL`,
- reading `ABACUS_NODE_NAME`,
- exposing settings through a small dataclass.

### `scripts/simulate_load.py`

This is a simple verification script for the task.

It is responsible for:

- resetting the sum,
- sending many POST requests across multiple nodes,
- reading the final total,
- comparing expected and observed values,
- failing with a non-zero exit code if consistency breaks.

Use it when you want to demonstrate:

- two nodes are sharing state,
- concurrent writes do not lose updates,
- the final total matches the number of successful writes.

### `tests/test_api.py`

This file covers the most important behavior:

- state is shared across two app instances,
- concurrent increments preserve the expected total,
- concurrent store initialization is safe.

### `compose.yaml`

This file defines a ready-to-run multi-container demo:

- one PostgreSQL container,
- two API containers,
- health checks for the database and both app nodes.

### `Dockerfile`

This packages the application into a Python 3.12 container image and starts Uvicorn.

## Requirements and prerequisites

Choose one of the following paths.

### Option 1: Python-only local run

You need:

- Python 3.12+
- PowerShell or another terminal

### Option 2: Docker run

You need:

- Docker Desktop or another working Docker environment
- Docker Compose support

## Quick start

If you want the fastest route to seeing the project work, use Docker:

```powershell
docker compose up --build -d
docker compose ps
Invoke-RestMethod -Uri http://127.0.0.1:8000/healthz
Invoke-RestMethod -Uri http://127.0.0.1:8001/healthz
```

If you want to run it directly on your machine with Python, go to the next section.

## Run locally with Python

### 1. Create and activate a virtual environment

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .[dev]
```

### 2. Run one node

```powershell
$env:ABACUS_DB_URL = "sqlite:///./data/abacus.db"
$env:ABACUS_NODE_NAME = "local-1"
python -m uvicorn abacus_api.main:app --host 127.0.0.1 --port 8000
```

### 3. Run a second node in another terminal

```powershell
$env:ABACUS_DB_URL = "sqlite:///./data/abacus.db"
$env:ABACUS_NODE_NAME = "local-2"
python -m uvicorn abacus_api.main:app --host 127.0.0.1 --port 8001
```

Both nodes point at the same SQLite database file, so they should observe the same total.

## Run with Docker Compose

Docker Compose runs the stronger deployment shape:

- PostgreSQL as the shared database,
- `api-1` on port `8000`,
- `api-2` on port `8001`.

### 1. Start the stack

```powershell
docker compose up --build -d
```

### 2. Check container status

```powershell
docker compose ps
```

### 3. Verify both app nodes

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/healthz
Invoke-RestMethod -Uri http://127.0.0.1:8001/healthz
```

Expected shape:

```json
{"status":"ok","node":"api-1"}
{"status":"ok","node":"api-2"}
```

### 4. Stop the stack

```powershell
docker compose down -v
```

## How to verify the service

Once one or more nodes are running, use these commands.

### Add a number

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/abacus/number -ContentType "application/json" -Body '{"number": 7}'
```

### Add a number through the second node

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8001/abacus/number -ContentType "application/json" -Body '{"number": 5}'
```

### Read the sum

```powershell
Invoke-RestMethod -Method Get -Uri http://127.0.0.1:8000/abacus/sum
Invoke-RestMethod -Method Get -Uri http://127.0.0.1:8001/abacus/sum
```

At this point both nodes should return the same total.

### Reset the sum

```powershell
Invoke-RestMethod -Method Delete -Uri http://127.0.0.1:8001/abacus/sum
```

## Load and consistency simulation

The repository includes a small script that sends many POST requests across multiple nodes and checks the final total.

### Run it from your host machine

```powershell
python scripts/simulate_load.py --requests 200 --concurrency 40 --number 1
```

### Run it against Docker containers

```powershell
docker compose run --rm api-1 python scripts/simulate_load.py --endpoints http://api-1:8000 http://api-2:8000 --requests 200 --concurrency 40 --number 1
```

What the flags mean:

- `--requests`: total number of POST calls to send.
- `--concurrency`: how many requests may be in flight at once.
- `--number`: the increment value for each POST.
- `--endpoints`: which nodes to distribute requests across.

Example result:

```text
Expected total: 200
Observed total: 200
Consistency check passed.
```

## Testing

Run the test suite with:

```powershell
python -m pytest
```

The tests cover:

- shared state between two app instances,
- concurrent increments,
- concurrent initialization.

## Environment variables

### `ABACUS_DB_URL`

Controls which database every node uses.

Examples:

```powershell
$env:ABACUS_DB_URL = "sqlite:///./data/abacus.db"
$env:ABACUS_DB_URL = "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/abacus"
```

### `ABACUS_NODE_NAME`

Sets the node identity returned by `/healthz`.

Examples:

```powershell
$env:ABACUS_NODE_NAME = "local-1"
$env:ABACUS_NODE_NAME = "api-2"
```

## How the consistency model works

The critical correctness property is that increments happen in the database, not in Python memory.

Instead of doing this:

1. read total,
2. add in Python,
3. write total back,

the service does this:

1. execute one SQL update that says `total = total + number`,
2. commit the transaction,
3. return the committed value.

That avoids lost updates under concurrent writes.

Startup is also guarded:

- every node ensures the state row exists,
- if two nodes try to create it at the same time, one succeeds and the other ignores the duplicate insert race.

Local demo note:

- SQLite works for the same-machine multi-process demonstration.

Production note:

- for separate containers or hosts, PostgreSQL is the intended backing store because all nodes share one transactional database.

## Troubleshooting

### Python version error during install

If you see an error like this:

```text
Package 'abacus-api' requires a different Python: 3.11.x not in '>=3.12'
```

install Python 3.12 and recreate the virtual environment:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .[dev]
```

### Virtual environment is active and you want to leave it

```powershell
deactivate
```

### Docker commands fail to connect

Make sure Docker Desktop is running and the Docker daemon is accessible from your shell.

### Port 8000 or 8001 is already in use

Start the app on different ports:

```powershell
python -m uvicorn abacus_api.main:app --host 127.0.0.1 --port 8010
python -m uvicorn abacus_api.main:app --host 127.0.0.1 --port 8011
```

Then pass those endpoints to the load script:

```powershell
python scripts/simulate_load.py --endpoints http://127.0.0.1:8010 http://127.0.0.1:8011
```

## Summary

For a same-machine demo, run two FastAPI nodes against the same SQLite file.

For a stronger multi-container setup, run the Docker Compose stack so both nodes share PostgreSQL.

In both cases, correctness comes from one shared transactional source of truth rather than in-memory state.
