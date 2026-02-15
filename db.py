import sqlite3
import time
from threading import Lock

DB_PATH = "guardian.db"
DB_LOCK = Lock()


def init_db():
    with DB_LOCK:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()

        cur.execute("""
        CREATE TABLE IF NOT EXISTS stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL UNIQUE,
            cpu REAL,
            ram REAL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)

        cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_stats_timestamp 
        ON stats(timestamp)
        """)

        conn.commit()
        conn.close()


def save(cpu: float, ram: float):
    with DB_LOCK:
        try:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()

            timestamp = time.time()
            cur.execute("""
            INSERT INTO stats 
            (timestamp, cpu, ram)
            VALUES (?, ?, ?)
            """, (timestamp, cpu, ram))

            conn.commit()
            conn.close()
        except sqlite3.IntegrityError:
            pass
        except Exception as e:
            print(f"[ERROR] Database save failed: {e}")


def get_recent_stats(minutes: int = 60) -> list:
    with DB_LOCK:
        try:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()

            cutoff_time = time.time() - (minutes * 60)
            cur.execute("""
            SELECT timestamp, cpu, ram
            FROM stats
            WHERE timestamp > ?
            ORDER BY timestamp DESC
            LIMIT 3600
            """, (cutoff_time,))

            rows = cur.fetchall()
            conn.close()
            return rows
        except Exception as e:
            print(f"[ERROR] Database read failed: {e}")
            return []


def get_stats_summary() -> dict:
    with DB_LOCK:
        try:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()

            cur.execute("""
            SELECT COUNT(*) as samples,
                   AVG(cpu) as avg_cpu,
                   AVG(ram) as avg_ram,
                   MAX(cpu) as max_cpu,
                   MAX(ram) as max_ram
            FROM stats
            WHERE timestamp > datetime('now', '-1 hour')
            """)

            result = cur.fetchone()
            conn.close()

            if result and result[0] > 0:
                return {
                    'samples': result[0] if result[0] else 0,
                    'avg_cpu': result[1] if result[1] else 0.0,
                    'avg_ram': result[2] if result[2] else 0.0,
                    'max_cpu': result[3] if result[3] else 0.0,
                    'max_ram': result[4] if result[4] else 0.0
                }
            return {
                'samples': 0,
                'avg_cpu': 0.0,
                'avg_ram': 0.0,
                'max_cpu': 0.0,
                'max_ram': 0.0
            }
        except Exception as e:
            print(f"[ERROR] Statistics query failed: {e}")
            return {
                'samples': 0,
                'avg_cpu': 0.0,
                'avg_ram': 0.0,
                'max_cpu': 0.0,
                'max_ram': 0.0
            }


def cleanup_old_data(days: int = 7):
    with DB_LOCK:
        try:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()

            cutoff_time = time.time() - (days * 86400)
            cur.execute("DELETE FROM stats WHERE timestamp < ?", (cutoff_time,))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[ERROR] Cleanup failed: {e}")