import os
import json
import datetime
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", 5432))
POSTGRES_DB = os.getenv("POSTGRES_DB", "fuzzy_repair")
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")

# Relative to this file so it works regardless of the process cwd.
FALLBACK_LOG_PATH = os.path.join(os.path.dirname(__file__), "..", "eval", "app_logs.jsonl")

# Columns written by log_inference. Must match db/init/01_schema.sql.
INSERT_COLUMNS = [
    "id", "source_text", "output_text", "tm_source", "tm_target",
    "retrieval_score", "preservation", "context", "model",
    "prompt_tokens", "completion_tokens", "cost_usd",
    "latency_ms", "condition", "fell_back",
]

try:
    import psycopg2
except ImportError:
    psycopg2 = None


def get_connection() -> Optional["psycopg2.extensions.connection"]:
    if psycopg2 is None:
        raise ImportError("psycopg2-binary is required for Postgres integration")

    return psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
    )


def ensure_schema() -> None:
    """Create repair_logs if missing. Matches db/init/01_schema.sql column-for-column,
    so the app works even against a Postgres that did not run the init script."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS repair_logs (
                    id                TEXT PRIMARY KEY,
                    ts                TIMESTAMPTZ NOT NULL DEFAULT now(),
                    source_text       TEXT NOT NULL,
                    output_text       TEXT NOT NULL,
                    tm_source         TEXT,
                    tm_target         TEXT,
                    retrieval_score   DOUBLE PRECISION,
                    preservation      DOUBLE PRECISION,
                    context           TEXT,
                    model             TEXT,
                    prompt_tokens     INTEGER,
                    completion_tokens INTEGER,
                    cost_usd          DOUBLE PRECISION,
                    latency_ms        INTEGER,
                    condition         TEXT,
                    fell_back         BOOLEAN DEFAULT FALSE,
                    feedback          TEXT,
                    user_correction   TEXT
                )
                """
            )
            conn.commit()
    finally:
        conn.close()


def _append_fallback(record: dict) -> None:
    """Append one JSON line, used when Postgres is unreachable."""
    os.makedirs(os.path.dirname(FALLBACK_LOG_PATH), exist_ok=True)
    with open(FALLBACK_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def log_inference(record: dict) -> None:
    """Insert one inference row. Missing keys default to NULL, so callers can omit
    optional fields. Falls back to a JSONL file if Postgres is unreachable so the
    app never crashes."""
    params = {col: record.get(col) for col in INSERT_COLUMNS}
    cols = ", ".join(INSERT_COLUMNS)
    placeholders = ", ".join(f"%({col})s" for col in INSERT_COLUMNS)
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"INSERT INTO repair_logs ({cols}) VALUES ({placeholders})",
                    params,
                )
                conn.commit()
        finally:
            conn.close()
    except Exception:
        fallback = dict(record)
        fallback["event"] = "inference"
        fallback["ts"] = datetime.datetime.now().isoformat(timespec="seconds")
        _append_fallback(fallback)


def log_feedback(record_id: str, feedback: str, user_correction: Optional[str] = None) -> None:
    """Update a row with the user's feedback. Falls back to a JSONL file if
    Postgres is unreachable, or if the row does not exist there."""
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE repair_logs SET feedback = %s, user_correction = %s WHERE id = %s",
                    (feedback, user_correction, record_id),
                )
                conn.commit()
        finally:
            conn.close()
    except Exception:
        _append_fallback({
            "event": "feedback",
            "ts": datetime.datetime.now().isoformat(timespec="seconds"),
            "id": record_id,
            "feedback": feedback,
            "user_correction": user_correction,
        })


if __name__ == "__main__":
    ensure_schema()
    print("Database schema ensured")
