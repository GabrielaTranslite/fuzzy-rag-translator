"""Seed the monitoring table with the repair rows from the evaluation run.

So the Grafana dashboard is not empty on a fresh clone: this loads the 75 repair
records from eval/llm_runs.jsonl into repair_logs, computing preservation from the
retrieved approved target. It fills only the fields the eval actually produced
(retrieval_score, preservation, model, condition); latency, cost, and feedback are
left NULL on purpose and populate from real app usage (do not fabricate metrics).

Idempotent: each seed row uses id = "seed-<case_id>" with ON CONFLICT DO NOTHING,
so re-running does not duplicate.

Run after Postgres is up and the schema exists (compose init or db.ensure_schema):
    python scripts/seed_monitoring.py
Connection comes from the POSTGRES_* env vars (same as the app/db).
"""

from __future__ import annotations

import json
import os
import datetime as dt
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()  # read repo .env if present

import psycopg2
from rapidfuzz.distance import Levenshtein

RUNS = Path("eval/llm_runs.jsonl")
GOLD = Path("eval/gold_set.jsonl")
SPREAD_DAYS = 14  # spread synthetic timestamps so time-series panels have shape


def connect():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", 5432)),
        dbname=os.getenv("POSTGRES_DB", "fuzzy_repair"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "postgres"),
    )


def load_repair_rows():
    runs = [json.loads(l) for l in RUNS.open(encoding="utf-8") if l.strip()]
    gold = {r["case_id"]: r for r in
            (json.loads(l) for l in GOLD.open(encoding="utf-8") if l.strip())}
    rows = [r for r in runs if r.get("condition") == "repair"]
    return rows, gold


def main() -> None:
    rows, gold = load_repair_rows()
    if not rows:
        print("No repair rows found in", RUNS)
        return

    now = dt.datetime.now(dt.timezone.utc)
    step = dt.timedelta(days=SPREAD_DAYS) / max(len(rows), 1)

    records = []
    for i, r in enumerate(rows):
        cid = r["case_id"]
        tm_target = r.get("tm_target") or ""
        output = r.get("output") or ""
        preservation = (Levenshtein.normalized_distance(output, tm_target)
                        if tm_target else None)
        ts = now - dt.timedelta(days=SPREAD_DAYS) + step * i
        records.append((
            f"seed-{cid}",
            ts,
            gold.get(cid, {}).get("query", output),  # source_text
            output,                                   # output_text
            r.get("tm_source_norm"),
            tm_target or None,
            r.get("retrieval_score"),
            preservation,
            None,                                     # context (not stored per run row)
            r.get("model"),
            None, None, None,                         # prompt_tokens, completion_tokens, cost_usd
            None,                                     # latency_ms
            "repair",                                 # condition
            False,                                    # fell_back
            None, None,                               # feedback, user_correction
        ))

    sql = """
        INSERT INTO repair_logs
          (id, ts, source_text, output_text, tm_source, tm_target,
           retrieval_score, preservation, context, model,
           prompt_tokens, completion_tokens, cost_usd, latency_ms,
           condition, fell_back, feedback, user_correction)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (id) DO NOTHING
    """
    try:
        conn = connect()
    except Exception as exc:
        host = os.getenv('POSTGRES_HOST', 'localhost')
        port = os.getenv('POSTGRES_PORT', '5432')
        print(
            f"Could not connect to Postgres at {host}:{port}. "
            f"Check: is the db container up and healthy (docker compose ps)? "
            f"is another Postgres using the port? do the POSTGRES_* creds match? "
            f"(underlying error type: {type(exc).__name__})"
        )
        raise SystemExit(1)
    try:
        with conn.cursor() as cur:
            cur.executemany(sql, records)
            conn.commit()
            print(f"Seeded {cur.rowcount if cur.rowcount != -1 else len(records)} "
                  f"repair rows into repair_logs (idempotent).")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
