from game.game_engine import GameEngine
from models.register import create_user_table

create_user_table()
def main():
    game = GameEngine()
    game.run()

if __name__ == "__main__":
    main()

