class Simulation:
    def __init__(self):
        self.running = True
        self.score = 0
        self.day = 1
        self.max_days = 5
        self.customers_served = 0
        self.money = 500.0  # Starting budget

        # Supermarket inventory
        self.inventory = {
            "apple": {"price": 1.50, "stock": 20},
            "bread": {"price": 2.00, "stock": 15},
            "milk":  {"price": 1.80, "stock": 10},
            "eggs":  {"price": 3.00, "stock": 12},
        }

    def is_running(self):
        return self.running and self.day <= self.max_days

    def update(self):
        print(f"\n--- Day {self.day} ---")
        print(f"Budget: ${self.money:.2f} | Score: {self.score} | Customers Served: {self.customers_served}")
        self._show_inventory()

        print("\nWhat would you like to do?")
        print("1. Serve next customer")
        print("2. Restock an item")
        print("3. End day")
        print("4. Quit game")

        choice = input("> ").strip()

        if choice == "1":
            self._serve_customer()
        elif choice == "2":
            self._restock_item()
        elif choice == "3":
            self._end_day()
        elif choice == "4":
            self._quit()
        else:
            print("Invalid choice, try again.")

    def _show_inventory(self):
        print("\nInventory:")
        for item, data in self.inventory.items():
            print(f"  {item.capitalize():<10} | Price: ${data['price']:.2f} | Stock: {data['stock']}")

    def _serve_customer(self):
        import random
        item_name = random.choice(list(self.inventory.keys()))
        item = self.inventory[item_name]

        if item["stock"] <= 0:
            print(f"Customer wanted {item_name} but it's out of stock! Customer left unhappy.")
            self.score -= 5
        else:
            quantity = random.randint(1, 3)
            quantity = min(quantity, item["stock"])
            earned = item["price"] * quantity
            item["stock"] -= quantity
            self.money += earned
            self.customers_served += 1
            self.score += 10
            print(f"Customer bought {quantity}x {item_name} for ${earned:.2f}. Nice!")
        input("Press enter to continue...")

    def _restock_item(self):
        print("Which item to restock?")
        items = list(self.inventory.keys())
        for i, name in enumerate(items, 1):
            print(f"{i}. {name.capitalize()}")

        try:
            choice = int(input("> ")) - 1
            if 0 <= choice < len(items):
                item_name = items[choice]
                qty = int(input(f"How many units of {item_name} to restock? (cost: $1.00 each): "))
                cost = qty * 1.00
                if cost > self.money:
                    print("Not enough budget!")
                else:
                    self.inventory[item_name]["stock"] += qty
                    self.money -= cost
                    print(f"Restocked {qty}x {item_name}. Spent ${cost:.2f}.")
            else:
                print("Invalid selection.")
        except ValueError:
            print("Please enter a number.")
        input("Press enter to continue...")

    def _end_day(self):
        print(f"\nDay {self.day} complete! Customers served today: {self.customers_served}")
        self.day += 1
        if self.day > self.max_days:
            self._game_over()
        else:
            input("Press enter to continue...")

    def _game_over(self):
        print("\n=== Game Over ===")
        print(f"Final Score:      {self.score}")
        print(f"Total Earned:     ${self.money:.2f}")
        print(f"Customers Served: {self.customers_served}")
        self.running = False

    def _quit(self):
        print("Thanks for playing!")
        self.running = False