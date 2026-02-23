from models.register import register_user, login_user
from systems.session import login, logout, get_current_user, is_admin

ADMIN_SECRET_CODE = "supermarket123"  # Change this to something only you know


def registration_menu():
    print("\n=== Register ===")
    username = input("Username: ").strip()
    password = input("Password: ").strip()

    role = "user"
    wants_admin = input("Registering as admin? (y/n): ").strip().lower()
    if wants_admin == "y":
        code = input("Enter admin code: ").strip()
        if code == ADMIN_SECRET_CODE:
            role = "admin"
            print("Admin access granted!")
        else:
            print("Wrong code. Registering as regular user.")

    if register_user(username, password, role):
        print("Registration successful!")
    else:
        print("Username already exists.")


def login_menu():
    print("\n=== Login ===")
    username = input("Username: ").strip()
    password = input("Password: ").strip()

    user = login_user(username, password)

    if user:
        login(user)
        role_label = " (Admin)" if user[2] == "admin" else ""
        print(f"Welcome, {user[1]}{role_label}!")
    else:
        print("Invalid credentials.")


def logout_menu():
    logout()


def admin_panel():
    if not is_admin():
        print("Access denied.")
        return

    print("\n=== Admin Panel ===")
    print("1. View all users (coming soon)")
    print("2. Reset inventory (coming soon)")
    print("3. Back")
    choice = input("> ").strip()
    # Expand this as needed