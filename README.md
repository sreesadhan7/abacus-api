# Abacus API

This repo contains a FastAPI microservice that keeps a single running sum with consistent updates across multiple app instances, as long as every instance points at the same database.

## Why this design

- `POST /abacus/number` is the hot path, so the service updates a single row directly in the database instead of reading state into process memory.
- Correctness comes from a shared transactional store. For a local demo, two FastAPI nodes can share the same SQLite file. For real multi-container deployment, point all nodes at one PostgreSQL instance instead.
- Startup is idempotent across multiple nodes. If several instances start together, they race safely on inserting the initial row instead of corrupting state.
- `GET /abacus/sum` is a simple read and stays cheap.

## Recommended deployment choice

- Use SQLite only for the local two-node demonstration on one machine, where both processes can access the same database file.
- Use PostgreSQL for real multi-node or multi-container deployment, because every node can safely share the same transactional database without relying on a shared filesystem.

## API

- `POST /abacus/number` with body `{ "number": N }` adds `N` to the running sum and returns the new total.
- `GET /abacus/sum` returns the current total.
- `DELETE /abacus/sum` resets the total to `0` and returns it.

## Local setup

The project targets Python 3.12+, per the task. If your machine still defaults to 3.11, create the environment with a 3.12 interpreter explicitly.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .[dev]
```

## Fastest demo path

If you do not want to install Python 3.12 locally first, use Docker. The repo includes a complete two-node setup with PostgreSQL.

```powershell
docker compose up --build -d
docker compose ps
```

Once the services are healthy, verify both nodes:

```powershell
Invoke-RestMethod -Method Get -Uri http://127.0.0.1:8000/healthz
Invoke-RestMethod -Method Get -Uri http://127.0.0.1:8001/healthz
```

Expected responses include different node names:

```json
{"status":"ok","node":"api-1"}
{"status":"ok","node":"api-2"}
```

## Run one node

```powershell
$env:ABACUS_DB_URL = "sqlite:///./data/abacus.db"
python -m uvicorn abacus_api.main:app --host 127.0.0.1 --port 8000
```

## Run two local nodes against the same state

Terminal 1:

```powershell
$env:ABACUS_DB_URL = "sqlite:///./data/abacus.db"
python -m uvicorn abacus_api.main:app --host 127.0.0.1 --port 8000
```

Terminal 2:

```powershell
$env:ABACUS_DB_URL = "sqlite:///./data/abacus.db"
python -m uvicorn abacus_api.main:app --host 127.0.0.1 --port 8001
```

Quick smoke test:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/abacus/number -ContentType "application/json" -Body '{"number": 7}'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8001/abacus/number -ContentType "application/json" -Body '{"number": 5}'
Invoke-RestMethod -Method Get -Uri http://127.0.0.1:8000/abacus/sum
Invoke-RestMethod -Method Delete -Uri http://127.0.0.1:8001/abacus/sum
```

If you need real container-to-container consistency on separate hosts, switch `ABACUS_DB_URL` to a PostgreSQL DSN shared by all nodes, for example:

```powershell
$env:ABACUS_DB_URL = "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/abacus"
```

## Two-node container demo

Bring up PostgreSQL and two API nodes:

```powershell
docker compose up --build -d
```

Send writes to both nodes and read from either one:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/abacus/number -ContentType "application/json" -Body '{"number": 7}'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8001/abacus/number -ContentType "application/json" -Body '{"number": 5}'
Invoke-RestMethod -Method Get -Uri http://127.0.0.1:8000/abacus/sum
```

The expected total is `12` no matter which node you read from.

## Load and consistency simulation

You can simulate heavier POST traffic against both nodes while checking the final total:

From your host, after installing the dev dependencies:

```powershell
python scripts/simulate_load.py --requests 200 --concurrency 40 --number 1
```

Or entirely inside Docker, without relying on local Python packages:

```powershell
docker compose run --rm api-1 python scripts/simulate_load.py --endpoints http://api-1:8000 http://api-2:8000 --requests 200 --concurrency 40 --number 1
```

The script prints both the expected and observed totals and exits non-zero if they differ.

## Tests

```powershell
python -m pytest
```

## Submission notes

- Local same-machine demo: SQLite is enough and keeps the setup minimal.
- Real multi-node deployment: PostgreSQL is the intended backing store, because all nodes share one transactional source of truth.
- The service API remains simple, but correctness is enforced at the database write path rather than in process memory.
