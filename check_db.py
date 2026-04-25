import sqlite3

conn = sqlite3.connect('store_sim.db')
users = conn.execute("SELECT * FROM users").fetchall()

if users:
    for user in users:
        print(user)
else:
    print("No users found in database.")

conn.close()