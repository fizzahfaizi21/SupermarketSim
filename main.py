from game.game_engine import GameEngine
from models.register import create_user_table

create_user_table()
def main():
    game = GameEngine()
    game.run()

if __name__ == "__main__":
    main()

from ui.console_ui import registration_menu, login_menu, logout_menu
from systems.session import get_current_user

while True:
    if not get_current_user():
        print("\n1. Register\n2. Login\n3. Exit")
        choice = input("> ")

        if choice == "1":
            registration_menu()
        elif choice == "2":
            login_menu()
        else:
            break
    else:
        print("\n1. Play Game\n2. Logout")
        choice = input("> ")

        if choice == "1":
            print("Game starting...")
        elif choice == "2":
            logout_menu()