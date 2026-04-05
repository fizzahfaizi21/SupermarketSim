import os
from pathlib import Path
import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class FirebaseService:
    def __init__(self):
        self.api_key = os.getenv("FIREBASE_API_KEY", "").strip()
        self.database_url = os.getenv("FIREBASE_DATABASE_URL", "").strip().rstrip("/")

        self.configured = bool(self.api_key and self.database_url)

        if not self.configured:
            raise ValueError("Firebase is not configured. Check your .env file.")

    # ---------------- AUTH ----------------
    def register(self, email, password, username):
        url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={self.api_key}"
        payload = {
            "email": email,
            "password": password,
            "returnSecureToken": True
        }

        response = requests.post(url, json=payload, timeout=15)
        data = response.json()

        if response.status_code != 200:
            raise Exception(data.get("error", {}).get("message", "Registration failed"))

        uid = data["localId"]
        id_token = data["idToken"]

        profile = {
            "uid": uid,
            "username": username,
            "email": email,
            "created_at": __import__("time").time()
        }

        profile_url = f"{self.database_url}/profiles/{uid}.json?auth={id_token}"
        save_res = requests.put(profile_url, json=profile, timeout=15)
        if save_res.status_code != 200:
            raise Exception(f"Failed to save profile: {save_res.text}")

        return {
            "uid": uid,
            "idToken": id_token,
            "email": email,
            "username": username
        }

    def login(self, email, password):
        url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={self.api_key}"
        payload = {
            "email": email,
            "password": password,
            "returnSecureToken": True
        }

        response = requests.post(url, json=payload, timeout=15)
        data = response.json()

        if response.status_code != 200:
            raise Exception(data.get("error", {}).get("message", "Login failed"))

        uid = data["localId"]
        id_token = data["idToken"]

        profile_url = f"{self.database_url}/profiles/{uid}.json?auth={id_token}"
        profile_res = requests.get(profile_url, timeout=15)

        username = email.split("@")[0]
        if profile_res.status_code == 200 and profile_res.json():
            username = profile_res.json().get("username", username)

        return {
            "uid": uid,
            "idToken": id_token,
            "email": data["email"],
            "username": username
        }

    # ---------------- GAME SAVE/LOAD ----------------
    def save_game(self, uid, id_token, game_data):
        url = f"{self.database_url}/users/{uid}.json?auth={id_token}"
        response = requests.put(url, json=game_data, timeout=15)

        if response.status_code != 200:
            raise Exception(f"Save failed: {response.text}")

        leaderboard_entry = {
            "username": game_data.get("username", "Player"),
            "email": game_data.get("email", ""),
            "score": game_data.get("score", 0),
            "money": game_data.get("money", 0),
            "day": game_data.get("day", 1)
        }

        lb_url = f"{self.database_url}/leaderboard/{uid}.json?auth={id_token}"
        lb_res = requests.put(lb_url, json=leaderboard_entry, timeout=15)
        if lb_res.status_code != 200:
            raise Exception(f"Leaderboard update failed: {lb_res.text}")

        return True

    def load_game(self, uid, id_token):
        url = f"{self.database_url}/users/{uid}.json?auth={id_token}"
        response = requests.get(url, timeout=15)

        if response.status_code != 200:
            raise Exception(f"Load failed: {response.text}")

        return response.json()

    # ---------------- EXTRA DATA ----------------
    def add_transaction(self, uid, id_token, transaction):
        url = f"{self.database_url}/transactions/{uid}.json?auth={id_token}"
        response = requests.post(url, json=transaction, timeout=15)
        if response.status_code != 200:
            raise Exception(f"Transaction save failed: {response.text}")
        return True

    def add_review(self, uid, id_token, review):
        url = f"{self.database_url}/reviews/{uid}.json?auth={id_token}"
        response = requests.post(url, json=review, timeout=15)
        if response.status_code != 200:
            raise Exception(f"Review save failed: {response.text}")
        return True

    def add_report(self, uid, id_token, report):
        url = f"{self.database_url}/reports/{uid}.json?auth={id_token}"
        response = requests.post(url, json=report, timeout=15)
        if response.status_code != 200:
            raise Exception(f"Report save failed: {response.text}")
        return True

    def get_leaderboard(self, id_token):
        url = f"{self.database_url}/leaderboard.json?auth={id_token}"
        response = requests.get(url, timeout=15)
        if response.status_code != 200:
            raise Exception(f"Leaderboard fetch failed: {response.text}")
        return response.json() or {}