from game.game_engine import GameEngine
from models.register import create_user_table
from ui.console_ui import registration_menu, login_menu, logout_menu, admin_panel
from systems.session import get_current_user, is_admin

create_user_table()

while True:
    if not get_current_user():
        print("\n1. Register\n2. Login\n3. Exit")
        choice = input("> ").strip()

        if choice == "1":
            registration_menu()
        elif choice == "2":
            login_menu()
        elif choice == "3":
            break

    else:
        if is_admin():
            print("\n1. Play Game\n2. Admin Panel\n3. Logout")
        else:
            print("\n1. Play Game\n2. Logout")

        choice = input("> ").strip()

        if choice == "1":
            game = GameEngine()
            game.run()
        elif choice == "2" and is_admin():
            admin_panel()
        elif choice == "2" and not is_admin():
            logout_menu()
        elif choice == "3" and is_admin():
            logout_menu()