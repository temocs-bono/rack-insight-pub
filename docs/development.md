# Development

How to run and work on Rack Insight locally. For deploying to Kubernetes see
[deployment.md](deployment.md).

## Project layout

```
backend/                FastAPI app (:8000, health at /api/health)
frontend/               React SPA (Vite dev :5173, prod nginx :80, calls /api)
plugins/example-plugin/ Reference plugin (independent container)
deploy/local/           Docker Compose (the local stack)
docs/                   These docs
```

## Option A — full stack with Docker Compose (simplest)

```bash
cd deploy/local
# Build images once on an internet-connected machine, then run:
docker compose -f docker-compose.yml -f docker-compose.build.yml build
docker compose up -d
```

Open **http://localhost/** — login `admin` / `admin123!`.
API docs at **http://localhost/docs**.

## Option B — backend & frontend directly (fast iteration)

Backend (Python 3.13) — needs Postgres + Redis reachable (e.g. from the compose
stack, or point `DATABASE_URL`/`REDIS_URL` at your own):

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env          # adjust DATABASE_URL / REDIS_URL
uvicorn main:app --reload     # http://localhost:8000
```

Frontend (Node 22):

```bash
cd frontend
npm install
VITE_API_TARGET=http://localhost:8000 npm run dev   # http://localhost:5173, proxies /api
```

## Tests & build

```bash
cd backend  && python -m pytest -q          # backend tests
cd frontend && npm run build                # type-check + production build
```

## Database migrations (Alembic)

The schema is managed **exclusively by Alembic** (never `create_all`). The
backend runs `alembic upgrade head` on startup, and legacy databases are adopted
in place. **Whenever you change a model you must add a migration:**

```bash
cd backend
alembic revision --autogenerate -m "describe the change"
alembic upgrade head
python -m pytest tests/test_migrations.py   # fails if models drift from migrations
```

Inspecting the DB from a running container:

```bash
# Local Docker Compose
cd deploy/local
docker compose exec backend alembic current
docker compose exec postgres psql -U rackinsight -c '\d clusters'

# Kubernetes
kubectl exec -n rack-insight deploy/backend -- alembic current
```

## Configuration

All configuration is environment-driven — see [`../backend/.env.example`](../backend/.env.example)
for the full list. Before any real environment, set `JWT_SECRET_KEY`,
`ENCRYPTION_KEY` and `DEFAULT_ADMIN_PASSWORD`. Generate a Fernet key with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Contribution flow

```
feature/*  →  Pull Request  →  CI (build + test)  →  merge to main
main       →  CI builds & pushes images  →  ArgoCD syncs the testbed
```

Feature branches are never auto-deployed. See [deployment.md](deployment.md).
