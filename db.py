import sqlite3
import time

conn = sqlite3.connect("guardian.db")
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS stats (
    timestamp REAL,
    cpu REAL,
    ram REAL
)
""")

def save(cpu, ram):
    cur.execute(
        "INSERT INTO stats VALUES (?, ?, ?)",
        (time.time(), cpu, ram)
    )
    conn.commit()