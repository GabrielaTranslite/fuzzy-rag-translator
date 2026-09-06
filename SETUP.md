# Setup and usage

Detailed setup, configuration, run steps, and troubleshooting for the
Fuzzy-Repair MT Assistant. For the overview and the why, see [README.md](README.md).

## Prerequisites

- Docker and Docker Compose (for the full stack), or Python 3.12 (to run the app
  alone).
- An OpenAI API key.

## Environment variables

Copy `.env.example` to `.env` and fill it in. `.env` is gitignored; never commit it.

| Variable | Purpose | Example |
|----------|---------|---------|
| `OPENAI_API_KEY` | OpenAI key used for translation/repair | `sk-...` |
| `OPENAI_MODEL` | Model id | `gpt-4o` (or `gpt-4o-mini` for a cheap demo) |
| `POSTGRES_DB` | Monitoring database name | `fuzzy_repair` |
| `POSTGRES_USER` | Postgres user | `postgres` |
| `POSTGRES_PASSWORD` | Postgres password | `postgres` (change for deploy) |
| `POSTGRES_HOST` | Host for tools run on the host (seed, local app) | `localhost` |
| `POSTGRES_PORT` | Host port mapped to the db container | `5433` |
| `GRAFANA_ADMIN_PASSWORD` | Grafana admin login | change before any public deploy |

For a local or Docker run you only need to set `OPENAI_API_KEY`. Every other variable already has a working value in `.env.example`, so you can leave it as is. Change `POSTGRES_PASSWORD` and `GRAFANA_ADMIN_PASSWORD` before any public deploy.

Note on host vs container networking. Inside Docker Compose the app and Grafana
reach Postgres at `db:5432` (the service name), which is set for them in
`docker-compose.yaml`. Tools you run on your own machine (the seed script, or the
app started with `streamlit run`) reach the same database at
`localhost:${POSTGRES_PORT}`. The host port is `5433` here on purpose, to avoid a
clash with a local Postgres that may already own `5432` (see Troubleshooting).

## Python environment (venv) and packages

You need this only to run something on your own machine directly: the seed script,
the ingestion pipeline (Prefect), or the app started with `streamlit run`. If you
use only the Docker Compose stack (Option A), you can skip this section, because
Docker builds its own environment inside the image.

A virtual environment (venv) is an isolated Python install just for this project,
so its packages do not clash with other projects or your system Python. Create it
once, then activate it in every new terminal before running the scripts. Requires
Python 3.12 (check with `python --version`).

Create it once, in the project folder:

```
python -m venv .venv
```

Activate it (do this in each new terminal):

- Windows PowerShell: `.venv\Scripts\Activate.ps1`
- Windows cmd: `.venv\Scripts\activate.bat`
- macOS / Linux: `source .venv/bin/activate`

When it is active your prompt shows `(.venv)`. Install the packages once per venv:

```
pip install -r requirements.txt
```

Leave the venv any time with `deactivate`. The `.venv/` folder is gitignored, so it
is never committed.

## Option A: full stack with Docker Compose (recommended)

```bash
cp .env.example .env          # then edit .env and set OPENAI_API_KEY
docker compose up -d          # builds the app image; starts qdrant, db, app, grafana
docker compose ps             # wait until db is healthy
python scripts/seed_monitoring.py   # optional: seed the dashboard (needs the venv; see "Python environment")
```

Services:

| Service | URL / port | Notes |
|---------|-----------|-------|
| App (Streamlit) | http://localhost:8501 | the product |
| Grafana | http://localhost:3000 | login `admin` / `GRAFANA_ADMIN_PASSWORD` |
| Postgres | localhost:5433 | monitoring database |
| Qdrant | localhost:6333 | semantic index (used by eval / pipeline) |

The database schema is created automatically on first boot from
`db/init/01_schema.sql`. The Grafana datasource and dashboard are provisioned
automatically from `grafana/provisioning/`.

## Option B: run the app without Docker

```bash
# Create and activate the venv, then install packages
# (see "Python environment (venv) and packages" above):
pip install -r requirements.txt

# For feedback logging you still need Postgres. Easiest: start just the db container:
docker compose up -d db

# Run the app:
streamlit run app.py
```

With `POSTGRES_HOST=localhost` and `POSTGRES_PORT=5433` in `.env`, the app logs to
the db container. If Postgres is not reachable, the app still runs and falls back to
writing logs to `eval/app_logs.jsonl`, so it never crashes on a missing database.

## Using the app

Two modes, chosen with the radio at the top:

- **Live repair**: type an English game string (or pick one from the gold set),
  press Repair. The app retrieves the closest approved translation, and either
  repairs it (edit only what changed) or, if no close match exists, translates from
  scratch and tells you so. You see the retrieved match, the output with the changed
  words highlighted against the approved target, the retrieval score, the
  preservation score, latency, and a feedback control (good / needs fixing, with an
  optional correction). Feedback is logged and shows up in Grafana.
- **Evaluation explorer**: pick a gold case and see all three conditions
  (scratch, scratch_context, repair) side by side, each diffed against the human
  reference, with chrF and preservation. This mode reads cached results and makes no
  API calls, so it is free and instant.

## Rebuild the knowledge base (ingestion pipeline)

The translation memory and the semantic index are built by a Prefect flow.

```bash
docker compose up -d qdrant     # index step needs Qdrant running
python scripts/build_tm_flow.py
```

The flow runs two steps in order: `ingest` (parse the `.po` files into
`data/tm/translation_memory.jsonl`, with context normalization applied) and `index`
(embed and upsert into Qdrant). It reads the committed `.po` files, so it
reproduces exactly the memory the evaluation was run on. You can verify:

```bash
git diff data/tm/translation_memory.jsonl   # should be empty after a run
```

`scripts/fetch_data.py` is an optional utility that re-downloads the `.po` from
upstream Wesnoth at a pinned tag; see its docstring for the reproducibility notes.

## Monitoring

Grafana reads the `repair_logs` table in Postgres. Rows come from two places: the
seed script (historical eval rows, so the charts are not empty on a fresh clone) and
the live app (each translation and each feedback click). Panels for retrieval score,
preservation, and request volume populate immediately after seeding; latency and
feedback fill in as you use the app. Bring-up order if you start pieces manually:

```bash
docker compose up -d db
docker compose ps                    # wait for healthy
python scripts/seed_monitoring.py
docker compose up -d grafana
```

## Troubleshooting

- **`no such service: db`** when running compose: your `docker-compose.yaml` is out
  of date; pull the latest, it defines `db`, `app`, and `grafana`.
- **`UnicodeDecodeError: 'utf-8' codec can't decode byte 0xb3`** from the seed or
  app on Windows: this is a failed Postgres connection whose error message is in the
  Polish system locale. The real cause is that the connection did not succeed. Check
  the next two items.
- **Port 5432 already in use / connects to the wrong database**: a local Postgres
  installed on Windows may already own `5432`. This project maps the container to
  host port **5433** to avoid that. Make sure `.env` has `POSTGRES_PORT=5433` and
  reach the db at `localhost:5433`. Check listeners with
  `netstat -ano | findstr :5432`.
- **`relation "repair_logs" does not exist`**: the database initialized before the
  schema file was in place. Recreate it cleanly:
  `docker compose down -v && docker compose up -d db` (this wipes the db volume and
  re-runs `db/init/01_schema.sql`).
- **Grafana panels empty**: run `python scripts/seed_monitoring.py` (needs the venv),
  and use the app to generate live rows. The seeded rows fill retrieval score,
  preservation, and volume; cost, latency, and feedback fill in from live app usage.
- **App image build is slow**: the image installs the full dependency set (including
  the embedding stack used by the pipeline and eval). This is a one-time build cost.

## Deploy (optional bonus)

The whole stack is one `docker compose up` on any Docker host. A small VPS (about
4 GB RAM) is enough because the running app uses fuzzy retrieval and does not load
the embedding model. For a public demo: put secrets in the host environment (never
in the repo), use a dedicated OpenAI key with a hard spending cap, do not expose
Postgres publicly, and set a real `GRAFANA_ADMIN_PASSWORD`. A step-by-step VPS guide
can be added when you deploy.
