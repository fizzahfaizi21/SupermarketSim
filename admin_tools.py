import firebase_admin
from firebase_admin import credentials, db

cred = credentials.Certificate("/Users/raiyanhaque/Desktop/Spring2026/SoftwareEng/GroupProject/bytebit_market/serviceAccountKey.json")

firebase_admin.initialize_app(cred, {
    "databaseURL": "https://bytebit-market-default-rtdb.firebaseio.com"
})

ref = db.reference("leaderboard")
print(ref.get())