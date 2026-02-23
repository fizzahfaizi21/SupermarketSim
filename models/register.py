<<<<<<< HEAD
from utils.config import get_db_connection

def create_user_table():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT DEFAULT 'user'
        )
    """)

    conn.commit()
    conn.close()
=======
class UserSession:
    def __init__(self):
        self.curr_user = None
    
    # to store active user
    def set_curr_user(self, user):
        self.curr_user=user

    # to end session
    def logout(self):
        if self.curr_user is None:
            print(f"No user is currently logged in.")
        else:
            print(f"{self.curr_user} has been logged out.")
            self.curr_user=None

    # to check who is logged in
    def get_curr_user(self):
        return self.curr_user
>>>>>>> db1db08658144301a509aebf1da46143413970f7
