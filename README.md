# ByteBit Market - Pygame + Firebase Supermarket Simulator

This is a polished class-project implementation of the supermarket simulator described in your sprint docs.

## Included features
- Firebase email/password registration, login, and local logout
- Save/load game state to Firebase Realtime Database
- Top-down supermarket scene with smooth movement and animated UI
- Stock shelves from storage
- Checkout customers and calculate change
- Customer complaints/dialogue choices
- Hire / fire / promote staff
- AI-style daily price suggestions based on demand and stock
- Stress/fatigue, breaks, upgrades, social promotion
- End-of-day reports, reviews, leaderboard sync

## Folder structure
- `main.py` - entry point
- `config/settings.py` - constants and config
- `src/firebase_service.py` - Firebase Auth + Realtime Database REST API
- `src/models.py` - game dataclasses and default data
- `src/ui.py` - buttons, panels, drawing helpers
- `src/game.py` - main game, screens, logic

## Step 1 - Create Firebase project
1. Go to Firebase Console and create a project.
2. Add a **Realtime Database**.
3. Choose your region and start in test mode for initial setup.
4. In **Authentication**, enable **Email/Password** sign-in.
5. In **Project Settings**, copy the **Web API Key**.
6. Copy your Realtime Database URL.

## Step 2 - Set database rules
Use rules like this for a class assignment:

```json
{
  "rules": {
    ".read": "auth != null",
    ".write": "auth != null",
    "users": {
      "$uid": {
        ".read": "$uid === auth.uid",
        ".write": "$uid === auth.uid"
      }
    },
    "leaderboard": {
      ".read": "auth != null",
      ".write": "auth != null"
    }
  }
}
```

## Step 3 - Environment setup
```bash
python -m venv .venv
```

### Windows PowerShell
```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

### macOS / Linux
```bash
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Now open `.env` and paste your values.

## Step 4 - Run
```bash
python main.py
```

## Controls
- `WASD` / Arrow keys: move
- `E`: interact with nearby zone
- `TAB`: next overlay tab
- `ESC`: close overlay or logout to menu

## Notes
- Logout clears local session and returns to the auth screen.
- Firebase Auth is used for registration/login, and Realtime Database stores game data.
- The art style is drawn with gradients, cards, shadows, glow, and animated UI so you do not need external assets.
