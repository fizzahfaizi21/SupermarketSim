from utils.config import get_db_connection


def register_user(username, password_hash, role="user", email=None):
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            "INSERT INTO users (username, email, password_hash, role) VALUES (?, ?, ?, ?)",
            (username, email, password_hash, role)
        )
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()


def login_user(username, password_hash):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT user_id, username, role FROM users WHERE username=? AND password_hash=?",
        (username, password_hash)
    )

    user = cursor.fetchone()
    conn.close()

    return user