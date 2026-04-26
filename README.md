# ByteBit Market — Pygame + Firebase Supermarket Simulator

A polished supermarket simulator with Firebase authentication, cloud saves, AI customer dialogue, and a vibrant pixel-art visual style.

## Features
- Firebase email/password registration, login, and logout
- Save/load game state to Firebase Realtime Database
- Top-down supermarket scene with smooth movement and animated UI
- Stock shelves from storage (keys 1–9, R, T, Y)
- Separate shelf slots for Phone, Laptop, and Wi-Fi Router (tech section)
- Checkout customers and calculate change
- AI customer dialogue powered by Google Gemini
- Customer complaints and dialogue choices
- Hire / fire / promote staff
- AI-style daily price suggestions based on demand and stock
- Stress/fatigue, breaks, upgrades, social promotion
- End-of-day reports, reviews, leaderboard sync
- Vibrant pixel-art visual style consistent across all screens

## Folder Structure
```
SupermarketSim/
├── main.py                  # Entry point
├── config/
│   └── settings.py          # Constants and config
├── src/
│   ├── firebase_service.py  # Firebase Auth + Realtime Database REST API
│   ├── models.py            # Game dataclasses and default data
│   ├── ui.py                # Buttons, panels, drawing helpers
│   └── game.py              # Main game, screens, logic
├── requirements.txt
└── .env                     # Your private keys (not committed)
```
## IMPORTANT NOTE INSTALL PYTHON 3.12 OR EARLIER PYGAME DOES NOT WORK WITH 3.13+
##IF MULTIPLE PYTHON VERSIONS ARE INSTALLED, RUN MAIN USING python3.11 main.py or py -3.11 main.py
## Step 1 — Create Firebase Project
1. Go to [Firebase Console](https://console.firebase.google.com) and create a project.
2. Add a **Realtime Database** — choose your region and start in test mode.
3. In **Authentication**, enable **Email/Password** sign-in.
4. In **Project Settings → General**, copy your **Web API Key**.
5. Copy your **Realtime Database URL** (looks like `https://your-project-default-rtdb.firebaseio.com`).

## Step 2 — Set Database Rules
In Firebase Console → Realtime Database → Rules, paste:

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

## Step 3 — Get a Gemini API Key
1. Go to [Google AI Studio](https://aistudio.google.com/app/apikey).
2. Create an API key and copy it.
3. This powers the AI customer dialogue in-game.

## Step 4 — Environment Setup

```bash
python -m venv .venv
```

### Windows PowerShell
```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install google-genai
```

### macOS / Linux
```bash
source .venv/bin/activate
pip install -r requirements.txt
pip install google-genai
```

## Step 5 — Configure Environment Variables
Create a `.env` file in the project root with the following:

```env
FIREBASE_API_KEY=your_firebase_web_api_key
FIREBASE_DATABASE_URL=https://your-project-default-rtdb.firebaseio.com
GEMINI_API_KEY=your_gemini_api_key
```

## Step 6 — Run
```bash
python main.py
```

## Controls

### Movement
| Key | Action |
|-----|--------|
| `W A S D` or Arrow Keys | Move player |

### Interaction
| Key | Action |
|-----|--------|
| `E` | Interact with nearby zone (Stock, Checkout, Manager, Prices, Break) |
| `F` | Talk to a nearby customer (AI dialogue) |
| `ESC` | Close overlay or return to menu |

### Stocking Shelves (inside Stock overlay)
| Key | Product |
|-----|---------|
| `1` | Chips |
| `2` | Milk |
| `3` | Bread |
| `4` | Apple |
| `5` | Donut |
| `6` | Cake |
| `7` | Frozen Fruit |
| `8` | Frozen Veg |
| `9` | Frozen Protein |
| `R` | Phone |
| `T` | Laptop |
| `Y` | Wi-Fi Router |
| `A` | Apply all suggested prices (Prices overlay) |

### Overlays
| Key | Action |
|-----|--------|
| `1` / `2` | Confirm/decline dialogue or complaint response |
| `ESC` | Close any overlay |

## Notes
- Logout clears the local session and returns to the auth screen.
- Each tech product (Phone, Laptop, Router) has its own independent shelf slot — stocking one does not affect the others.
- The overhead aisle signs show a live stock meter that updates as you restock shelves.
- The art style uses per-row gradients, beveled shelves, animated characters, and dynamic lighting — no external image assets required.
- AI customer dialogue requires a valid Gemini API key. Without it the dialogue feature will not function but the rest of the game will run normally.
