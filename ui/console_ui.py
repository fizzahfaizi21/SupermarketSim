from models.register import register_user, login_user
from systems.session import UserSession

session = UserSession()

def registration_menu():
    print("\n=== Register ===")
    username = input("Username: ")
    password = input("Password: ")

    if register_user(username, password):
        print("Registration successful!")
    else:
        print("Username already exists.")


def login_menu():
    print("\n=== Login ===")
    username = input("Username: ")
    password = input("Password: ")

    user = login_user(username, password)
    if user:
        session.set_curr_user(user)
        print(f"Welcome, {user[1]}!")
    else:
        print("Invalid credentials.")


def logout_menu():
    session.logout()