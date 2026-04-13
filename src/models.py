from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List
import random

PRODUCT_CATALOG = {
    "chips": {"name": "Chips", "category": "snack", "base_price": 3.50, "color": (245, 180, 80)},
    "milk": {"name": "Milk", "category": "dairy", "base_price": 4.25, "color": (195, 225, 255)},
    "bread": {"name": "Bread", "category": "bakery", "base_price": 2.95, "color": (214, 169, 111)},
    "apple": {"name": "Apple", "category": "produce", "base_price": 1.25, "color": (232, 86, 86)},
}

SHELF_LAYOUT = {
    "snack": "chips",
    "dairy": "milk",
    "bakery": "bread",
    "produce": "apple",
}

COMPLAINTS = [
    ("This line is taking too long.", ["Apologize and speed up", "Ignore it"], 8),
    ("That price looks too high.", ["Explain today’s demand", "Tell them to deal with it"], 10),
    ("Your shelf was almost empty.", ["Promise a restock", "Say it is not your problem"], 9),
]

AD_CAMPAIGNS = {
    "flyer": {
        "name": "Flyer Drop",
        "cost": 60,
        "spawn_multiplier": 0.78,   # lower spawn_timer = more frequent customers
        "duration_hours": 4,        # in game-hours (real seconds = duration * DAY_LENGTH / 24)
        "desc": "Low-budget leaflets. Modest traffic bump for a few hours.",
        "color": (140, 200, 100),
    },
    "billboard": {
        "name": "Billboard",
        "cost": 180,
        "spawn_multiplier": 0.58,
        "duration_hours": 8,
        "desc": "City billboard. Strong traffic boost all morning.",
        "color": (80, 160, 230),
    },
    "tv_ad": {
        "name": "TV Ad",
        "cost": 420,
        "spawn_multiplier": 0.38,
        "duration_hours": 24,
        "desc": "Prime-time television. Maximum customer surge all day.",
        "color": (220, 120, 60),
    },
}

UPGRADES = {
    "scanner": {"name": "Fast Scanner", "cost": 180, "desc": "Reduces checkout errors"},
    "shelves": {"name": "Premium Shelves", "cost": 220, "desc": "Increases shelf capacity"},
    "decor": {"name": "Store Decor", "cost": 150, "desc": "Boosts review quality"},
}

STAFF_POOL = [
    {"name": "Mia", "role": "cashier", "wage": 55, "skill": 3},
    {"name": "Noah", "role": "stocker", "wage": 50, "skill": 2},
    {"name": "Ava", "role": "cashier", "wage": 65, "skill": 4},
    {"name": "Ethan", "role": "stocker", "wage": 60, "skill": 4},
    {"name": "Luna", "role": "assistant", "wage": 72, "skill": 5},
]

# ── AI dialogue ───────────────────────────────────────────────────────────────
# Maps customer mood to a brief personality archetype fed to the Anthropic API.
CUSTOMER_ARCHETYPES = {
    "happy":   "You are a cheerful, friendly grocery shopper. You are upbeat and easy to deal with.",
    "neutral": "You are a tired but polite grocery shopper. You just want to get your items and go.",
    "angry":   "You are an impatient, irritable grocery shopper. You are quick to complain.",
}

AI_DIALOGUE_SYSTEM = (
    "You are a customer in a grocery store simulation game called Bytebit Market. "
    "Respond with a single short sentence of natural in-character dialogue (max 18 words). "
    "No quotation marks, no stage directions, no emojis. Just the spoken line."
)

REVIEW_TEMPLATES = {
    "great": ["Fast service and a clean store.", "Loved the checkout experience.", "Great prices and stocked shelves."],
    "ok": ["Decent visit, but there is room to improve.", "The store was okay overall.", "Could be faster at checkout."],
    "bad": ["Long lines and poor service.", "I was frustrated with the wait.", "Shelves looked understocked."],
}

@dataclass
class Staff:
    name: str
    role: str
    wage: float
    skill: int
    promoted: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Customer:
    id: int
    mood: str
    patience: int
    items: Dict[str, int]
    complaint: str = ""
    expected_total: float = 0.0
    pay_with: str = "cash"
    cash_given: float = 0.0


@dataclass
class ShiftReport:
    day: int
    funds: float
    sales: float
    customers_served: int
    satisfaction: int
    stocking_efficiency: int
    stress: int
    fatigue: int
    notes: str
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class GameState:
    username: str
    uid: str
    day: int = 1
    money: float = 600.0
    store_level: int = 1
    stamina: int = 100
    time_of_day: str = "day"
    score: int = 0
    storage: Dict[str, int] = field(default_factory=lambda: {k: 18 for k in PRODUCT_CATALOG})
    shelves: Dict[str, int] = field(default_factory=lambda: {cat: 6 for cat in SHELF_LAYOUT})
    prices: Dict[str, float] = field(default_factory=lambda: {k: v["base_price"] for k, v in PRODUCT_CATALOG.items()})
    demand: Dict[str, float] = field(default_factory=lambda: {k: 1.0 for k in PRODUCT_CATALOG})
    staff: List[dict] = field(default_factory=list)
    upgrades: Dict[str, bool] = field(default_factory=lambda: {k: False for k in UPGRADES})
    stress: int = 12
    fatigue: int = 8
    satisfaction: int = 78
    popularity_boost_until: float = 0.0
    # day/night cycle: 0.0–1.0 fraction through the current day (driven by day_timer)
    day_phase: float = 0.0          # 0 = dawn, 0.5 = midday, 1 = night
    # active ad campaign
    active_campaign: str = ""                   # key into AD_CAMPAIGNS or ""
    campaign_ends_at: float = 0.0               # time.time() value when campaign expires
    customers_served: int = 0
    sales_today: float = 0.0
    reviews: List[dict] = field(default_factory=list)
    reports: List[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "username": self.username,
            "uid": self.uid,
            "day": self.day,
            "money": round(self.money, 2),
            "store_level": self.store_level,
            "stamina": self.stamina,
            "time_of_day": self.time_of_day,
            "score": self.score,
            "storage": self.storage,
            "shelves": self.shelves,
            "prices": self.prices,
            "demand": self.demand,
            "staff": self.staff,
            "upgrades": self.upgrades,
            "stress": self.stress,
            "fatigue": self.fatigue,
            "satisfaction": self.satisfaction,
            "popularity_boost_until": self.popularity_boost_until,
            "day_phase": self.day_phase,
            "active_campaign": self.active_campaign,
            "campaign_ends_at": self.campaign_ends_at,
            "customers_served": self.customers_served,
            "sales_today": round(self.sales_today, 2),
            "reviews": self.reviews,
            "reports": self.reports,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GameState":
        data.setdefault("day_phase", 0.0)
        data.setdefault("active_campaign", "")
        data.setdefault("campaign_ends_at", 0.0)
        return cls(**data)


def random_customer(customer_id: int, prices: Dict[str, float], demand: Dict[str, float]) -> Customer:
    product_keys = list(PRODUCT_CATALOG.keys())
    item_count = random.randint(1, 3)
    chosen = random.sample(product_keys, item_count)
    items = {}
    total = 0.0
    for product_key in chosen:
        qty = random.randint(1, 2)
        items[product_key] = qty
        total += prices[product_key] * qty
    complaint = ""
    if random.random() < 0.35:
        complaint = random.choice(COMPLAINTS)[0]
    pay_with = random.choice(["cash", "card"])
    cash_given = round(total + random.choice([0, 0, 0, 1, 2, 5, 10]), 2) if pay_with == "cash" else total
    mood = random.choice(["happy", "neutral", "angry"])
    patience = random.randint(40, 100)
    return Customer(
        id=customer_id,
        mood=mood,
        patience=patience,
        items=items,
        complaint=complaint,
        expected_total=round(total, 2),
        pay_with=pay_with,
        cash_given=cash_given,
    )


def generate_review(satisfaction: int, accuracy_bonus: int, decor_bonus: int) -> dict:
    total = satisfaction + accuracy_bonus + decor_bonus
    if total >= 90:
        stars = 5
        bucket = "great"
    elif total >= 75:
        stars = 4
        bucket = "great"
    elif total >= 60:
        stars = 3
        bucket = "ok"
    elif total >= 45:
        stars = 2
        bucket = "bad"
    else:
        stars = 1
        bucket = "bad"
    return {
        "stars": stars,
        "comment": random.choice(REVIEW_TEMPLATES[bucket]),
        "created_at": datetime.utcnow().isoformat(),
    }


def price_suggestion(current: float, stock: int, demand_value: float) -> float:
    pressure = 1.05 + (demand_value - 1.0) * 0.18
    if stock < 5:
        pressure += 0.05
    elif stock > 12:
        pressure -= 0.08
    suggestion = max(0.85, current * pressure)
    return round(suggestion, 2)