import sqlite3

DB_NAME = "store_sim.db"

def get_db_connection():
    return sqlite3.connect(DB_NAME)