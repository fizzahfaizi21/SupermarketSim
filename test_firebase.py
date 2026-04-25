from src.firebase_service import FirebaseService

firebase = FirebaseService()

email = "testuser123@example.com"
password = "Test1234!"

print("Registering...")
print(firebase.register_user(email, password))

print("Logging in...")
print(firebase.login_user(email, password))

print("Saving sample data...")
sample = {
    "email": email,
    "money": 7000,
    "day": 3,
    "inventory": {
        "milk": 20,
        "bread": 15
    },
    "shelf_stock": {
        "milk": 8,
        "bread": 7
    },
    "employees": [
        {"name": "Alex", "role": "Cashier", "level": 1}
    ],
    "reviews": ["Great store"],
    "stress": 10,
    "fatigue": 12,
    "store_level": 2,
    "followers": 50
}

print(firebase.save_user_data(sample))
print(firebase.load_user_data())
print(firebase.submit_score(7000, "ByteBit Market"))
print(firebase.get_leaderboard())