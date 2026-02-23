from game.simulation import Simulation

class GameEngine:
    def __init__(self):
        self.simulation = Simulation()

    def run(self):
        while self.simulation.is_running():
            self.simulation.update()
            