from utils.config import get_db_connection


def create_all_tables():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Users table (includes role for admin functionality)
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT,
            password_hash TEXT NOT NULL,
            date_created DATETIME DEFAULT CURRENT_TIMESTAMP,
            role TEXT DEFAULT 'user'
        )
        """
    )

    # Game_Save table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS game_save (
            save_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            day_number INTEGER,
            money_balance DECIMAL(10, 2),
            store_level INTEGER,
            player_stamina INTEGER,
            time_of_day TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
        """
    )

    # Employees table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS employees (
            employee_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            role TEXT,
            wage DECIMAL(6, 2),
            skill_lvl INTEGER,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
        """
    )

    # Products table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS products (
            product_id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_name TEXT NOT NULL,
            category TEXT,
            price DECIMAL(6, 2)
        )
        """
    )

    # Inventory table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS inventory (
            inventory_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER,
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            FOREIGN KEY (product_id) REFERENCES products(product_id)
        )
        """
    )

    # Transactions table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS transactions (
            transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            total_amount DECIMAL(10, 2),
            transaction_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
        """
    )

    # Customers table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS customers (
            customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
            mood TEXT,
            patience_lvl INTEGER
        )
        """
    )

    # Reviews table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS reviews (
            review_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            customer_id INTEGER NOT NULL,
            rating INTEGER,
            comment TEXT,
            review_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
        )
        """
    )

    # Leaderboard table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS leaderboard (
            leaderboard_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            score INTEGER,
            position INTEGER,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
        """
    )

    # Transaction_Items table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS transaction_items (
            item_id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER,
            price_each DECIMAL(6, 2),
            FOREIGN KEY (transaction_id) REFERENCES transactions(transaction_id),
            FOREIGN KEY (product_id) REFERENCES products(product_id)
        )
        """
    )

    conn.commit()
    conn.close()

