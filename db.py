import time
from contextlib import contextmanager
from threading import Lock

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
import os

load_dotenv()

DB_CONFIG = {
    "host":     os.getenv("DB_HOST", "localhost"),
    "port":     int(os.getenv("DB_PORT", 5432)),
    "dbname":   os.getenv("DB_NAME", "guardian"),
    "user":     os.getenv("DB_USER", "guardian_user"),
    "password": os.getenv("DB_PASSWORD", ""),
}

DB_LOCK = Lock()


@contextmanager
def _get_conn():
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with DB_LOCK:
        with _get_conn() as conn:
            cur = conn.cursor()

            cur.execute("""
                CREATE TABLE IF NOT EXISTS stats (
                    id          BIGSERIAL PRIMARY KEY,
                    timestamp   DOUBLE PRECISION UNIQUE NOT NULL,
                    cpu         REAL NOT NULL,
                    ram         REAL NOT NULL,
                    created_at  TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_stats_timestamp
                ON stats (timestamp DESC)
            """)

            # Anomaly log table — ready for when we build detection
            cur.execute("""
                CREATE TABLE IF NOT EXISTS anomalies (
                    id          BIGSERIAL PRIMARY KEY,
                    timestamp   DOUBLE PRECISION NOT NULL,
                    metric      TEXT NOT NULL,
                    value       REAL NOT NULL,
                    baseline    REAL,
                    stddev      REAL,
                    severity    TEXT,
                    created_at  TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_anomalies_timestamp
                ON anomalies (timestamp DESC)
            """)

    print("[DB] PostgreSQL connected and tables ready.")


def save(cpu: float, ram: float):
    with DB_LOCK:
        try:
            with _get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO stats (timestamp, cpu, ram)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (timestamp) DO NOTHING
                """, (time.time(), cpu, ram))
        except Exception as e:
            print(f"[ERROR] Database save failed: {e}")


def get_recent_stats(minutes: int = 60) -> list:
    with DB_LOCK:
        try:
            with _get_conn() as conn:
                cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cutoff = time.time() - (minutes * 60)
                cur.execute("""
                    SELECT timestamp, cpu, ram
                    FROM stats
                    WHERE timestamp > %s
                    ORDER BY timestamp DESC
                    LIMIT 3600
                """, (cutoff,))
                return cur.fetchall()
        except Exception as e:
            print(f"[ERROR] Database read failed: {e}")
            return []


def get_stats_summary(minutes: int = 60) -> dict:
    with DB_LOCK:
        try:
            with _get_conn() as conn:
                cur = conn.cursor()
                cutoff = time.time() - (minutes * 60)
                cur.execute("""
                    SELECT
                        COUNT(*)        AS samples,
                        AVG(cpu)        AS avg_cpu,
                        AVG(ram)        AS avg_ram,
                        MAX(cpu)        AS max_cpu,
                        MAX(ram)        AS max_ram,
                        STDDEV(cpu)     AS stddev_cpu,
                        STDDEV(ram)     AS stddev_ram
                    FROM stats
                    WHERE timestamp > %s
                """, (cutoff,))
                row = cur.fetchone()

            if row and row[0] > 0:
                return {
                    "samples":    row[0],
                    "avg_cpu":    float(row[1] or 0),
                    "avg_ram":    float(row[2] or 0),
                    "max_cpu":    float(row[3] or 0),
                    "max_ram":    float(row[4] or 0),
                    "stddev_cpu": float(row[5] or 0),
                    "stddev_ram": float(row[6] or 0),
                }
        except Exception as e:
            print(f"[ERROR] Statistics query failed: {e}")

    return {
        "samples": 0, "avg_cpu": 0.0, "avg_ram": 0.0,
        "max_cpu": 0.0, "max_ram": 0.0,
        "stddev_cpu": 0.0, "stddev_ram": 0.0,
    }


def get_baseline(minutes: int = 30) -> dict:
    """
    Returns mean + stddev for CPU and RAM over the last N minutes.
    Used by anomaly detection to define 'normal' behaviour.
    """
    with DB_LOCK:
        try:
            with _get_conn() as conn:
                cur = conn.cursor()
                cutoff = time.time() - (minutes * 60)
                cur.execute("""
                    SELECT
                        AVG(cpu)    AS avg_cpu,
                        STDDEV(cpu) AS std_cpu,
                        AVG(ram)    AS avg_ram,
                        STDDEV(ram) AS std_ram,
                        COUNT(*)    AS samples
                    FROM stats
                    WHERE timestamp > %s
                """, (cutoff,))
                row = cur.fetchone()

            if row and row[4] and row[4] >= 10:
                return {
                    "avg_cpu": float(row[0] or 0),
                    "std_cpu": float(row[1] or 1),
                    "avg_ram": float(row[2] or 0),
                    "std_ram": float(row[3] or 1),
                    "samples": row[4],
                    "ready":   True,
                }
        except Exception as e:
            print(f"[ERROR] Baseline query failed: {e}")

    return {
        "avg_cpu": 0.0, "std_cpu": 1.0,
        "avg_ram": 0.0, "std_ram": 1.0,
        "samples": 0,   "ready":   False,
    }


def log_anomaly(metric: str, value: float, baseline: float,
                stddev: float, severity: str):
    with DB_LOCK:
        try:
            with _get_conn() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO anomalies
                        (timestamp, metric, value, baseline, stddev, severity)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (time.time(), metric, value, baseline, stddev, severity))
        except Exception as e:
            print(f"[ERROR] Anomaly log failed: {e}")


def cleanup_old_data(days: int = 7):
    with DB_LOCK:
        try:
            with _get_conn() as conn:
                cur = conn.cursor()
                cutoff = time.time() - (days * 86400)
                cur.execute("DELETE FROM stats WHERE timestamp < %s", (cutoff,))
                cur.execute("DELETE FROM anomalies WHERE timestamp < %s", (cutoff,))
        except Exception as e:
            print(f"[ERROR] Cleanup failed: {e}")