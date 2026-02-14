import sqlite3
import datetime

conn = sqlite3.connect("guardian.db")
cur = conn.cursor()

for row in cur.execute("SELECT * FROM stats LIMIT 5"):
    ts, cpu, ram = row
    readable = datetime.datetime.fromtimestamp(ts)
    print(readable, cpu, ram)