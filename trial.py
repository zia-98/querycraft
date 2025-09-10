import sqlite3

conn = sqlite3.connect("users.db")
c = conn.cursor()

c.execute("PRAGMA table_info(users)")
for row in c.fetchall():
    print(row)
