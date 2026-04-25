from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List
import random

PRODUCT_CATALOG = {
    "chips":       {"name": "Chips",          "category": "snack",   "base_price": 3.50,  "color": (245, 180,  80), "section": "grocery"},
    "milk":        {"name": "Milk",           "category": "dairy",   "base_price": 4.25,  "color": (195, 225, 255), "section": "grocery"},
    "bread":       {"name": "Bread",          "category": "bakery",  "base_price": 2.95,  "color": (214, 169, 111), "section": "deli"},
    "apple":       {"name": "Apple",          "category": "produce", "base_price": 1.25,  "color": (232,  86,  86), "section": "grocery"},
    "donut":       {"name": "Donut",          "category": "deli",    "base_price": 2.50,  "color": (255, 200, 120), "section": "deli"},
    "cake":        {"name": "Cake",           "category": "deli",    "base_price": 8.99,  "color": (210, 140, 160), "section": "deli"},
    "frz_fruit":   {"name": "Frozen Fruit",   "category": "frozen",  "base_price": 5.49,  "color": (160, 210, 255), "section": "frozen"},
    "frz_veg":     {"name": "Frozen Veg",     "category": "frozen",  "base_price": 4.75,  "color": (180, 240, 200), "section": "frozen"},
    "frz_protein": {"name": "Frozen Protein", "category": "frozen",  "base_price": 7.99,  "color": (255, 200, 180), "section": "frozen"},
    "phone":       {"name": "Phone",          "category": "phone",   "base_price": 299.0, "color": ( 90, 170, 255), "section": "tech"},
    "laptop":      {"name": "Laptop",         "category": "laptop",  "base_price": 799.0, "color": (130, 215, 255), "section": "tech"},
    "router":      {"name": "Wi-Fi Router",   "category": "router",  "base_price": 89.0,  "color": ( 70, 190, 255), "section": "tech"},
}

SHELF_LAYOUT = {
    "snack":   "chips",
    "dairy":   "milk",
    "bakery":  "bread",
    "produce": "apple",
    "deli":    "donut",
    "frozen":  "frz_fruit",
    "phone":   "phone",
    "laptop":  "laptop",
    "router":  "router",
}

SECTION_PRODUCTS = {
    "grocery": ["chips", "milk", "apple"],
    "deli":    ["bread", "donut", "cake"],
    "frozen":  ["frz_fruit", "frz_veg", "frz_protein"],
    "tech":    ["phone", "laptop", "router"],
}

ALL_SECTION_KEYS = list(SECTION_PRODUCTS.keys())

COMPLAINTS = [
    ("This line is taking too long.",      ["Apologize and speed up", "Ignore it"],                 8),
    ("That price looks too high.",         ["Explain today's demand", "Tell them to deal with it"], 10),
    ("Your shelf was almost empty.",       ["Promise a restock", "Say it is not your problem"],     9),
    ("I can't find what I'm looking for.", ["Help them navigate", "Point vaguely"],                 7),
    ("This product looks expired.",        ["Replace it immediately", "Tell them it's fine"],      11),
]

AD_CAMPAIGNS = {
    "flyer":     {"name": "Flyer Drop", "cost": 60,  "spawn_multiplier": 0.78, "duration_hours": 4,  "desc": "Low-budget leaflets. Modest traffic bump.",         "color": (140, 200, 100)},
    "billboard": {"name": "Billboard",  "cost": 180, "spawn_multiplier": 0.58, "duration_hours": 8,  "desc": "City billboard. Strong traffic boost all morning.", "color": ( 80, 160, 230)},
    "tv_ad":     {"name": "TV Ad",      "cost": 420, "spawn_multiplier": 0.38, "duration_hours": 24, "desc": "Prime-time television. Maximum customer surge.",    "color": (220, 120,  60)},
}

UPGRADES = {
    "scanner": {"name": "Fast Scanner",    "cost": 180, "desc": "Reduces checkout errors"},
    "shelves":  {"name": "Premium Shelves","cost": 220, "desc": "Increases shelf capacity"},
    "decor":    {"name": "Store Decor",    "cost": 150, "desc": "Boosts review quality"},
}

STAFF_POOL = [
    {"name": "Mia",   "role": "cashier",   "wage": 55, "skill": 3},
    {"name": "Noah",  "role": "stocker",   "wage": 50, "skill": 2},
    {"name": "Ava",   "role": "cashier",   "wage": 65, "skill": 4},
    {"name": "Ethan", "role": "stocker",   "wage": 60, "skill": 4},
    {"name": "Luna",  "role": "assistant", "wage": 72, "skill": 5},
]

CUSTOMER_ARCHETYPES = {
    "happy":   "You are a cheerful, friendly shopper. Upbeat and easy to deal with.",
    "neutral": "You are a tired but polite shopper. You just want your items and to leave.",
    "angry":   "You are an impatient, irritable shopper. Quick to complain.",
}

AI_DIALOGUE_SYSTEM = (
    "You are a customer in a grocery/tech store simulation game called Bytebit Market. "
    "Respond with ONE short sentence of natural in-character dialogue (max 18 words). "
    "No quotation marks, no stage directions, no emojis. Just the spoken line."
)

REVIEW_TEMPLATES = {
    "great": ["Fast service and a spotless store — will be back!", "Loved the checkout experience. Everything was stocked.", "Great prices, helpful staff, and clean aisles."],
    "ok":    ["Decent visit, but room for improvement.", "The store was okay. Could be faster at checkout.", "Prices felt a bit high but the range was good."],
    "bad":   ["Long lines and poor service — very frustrating.", "Shelves were understocked and checkout took forever.", "Not impressed. Several items were unavailable."],
}


@dataclass
class Staff:
    name: str; role: str; wage: float; skill: int; promoted: int = 0
    def to_dict(self): return asdict(self)


@dataclass
class Customer:
    id: int; mood: str; patience: int; items: Dict[str, int]
    section: str = "grocery"; complaint: str = ""; expected_total: float = 0.0
    pay_with: str = "cash"; cash_given: float = 0.0


@dataclass
class ShiftReport:
    day: int; funds: float; sales: float; customers_served: int
    satisfaction: int; stocking_efficiency: int; stress: int; fatigue: int; notes: str
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    def to_dict(self): return asdict(self)


@dataclass
class GameState:
    username: str; uid: str
    day: int = 1; money: float = 600.0; store_level: int = 1; stamina: int = 100
    time_of_day: str = "day"; score: int = 0
    storage: Dict[str, int]  = field(default_factory=lambda: {k: 18 for k in PRODUCT_CATALOG})
    shelves: Dict[str, int]  = field(default_factory=lambda: {c: 6  for c in SHELF_LAYOUT})
    prices:  Dict[str, float]= field(default_factory=lambda: {k: v["base_price"] for k,v in PRODUCT_CATALOG.items()})
    demand:  Dict[str, float]= field(default_factory=lambda: {k: 1.0 for k in PRODUCT_CATALOG})
    staff: List[dict] = field(default_factory=list)
    upgrades: Dict[str, bool] = field(default_factory=lambda: {k: False for k in UPGRADES})
    stress: int = 12; fatigue: int = 8; satisfaction: int = 78
    popularity_boost_until: float = 0.0; day_phase: float = 0.0
    active_campaign: str = ""; campaign_ends_at: float = 0.0
    customers_served: int = 0; sales_today: float = 0.0
    reviews: List[dict] = field(default_factory=list)
    reports: List[dict] = field(default_factory=list)
    email: str = ""

    def to_dict(self):
        return {
            "username": self.username, "uid": self.uid, "email": self.email,
            "day": self.day, "money": round(self.money, 2), "store_level": self.store_level,
            "stamina": self.stamina, "time_of_day": self.time_of_day, "score": self.score,
            "storage": self.storage, "shelves": self.shelves, "prices": self.prices,
            "demand": self.demand, "staff": self.staff, "upgrades": self.upgrades,
            "stress": self.stress, "fatigue": self.fatigue, "satisfaction": self.satisfaction,
            "popularity_boost_until": self.popularity_boost_until, "day_phase": self.day_phase,
            "active_campaign": self.active_campaign, "campaign_ends_at": self.campaign_ends_at,
            "customers_served": self.customers_served, "sales_today": round(self.sales_today, 2),
            "reviews": self.reviews, "reports": self.reports,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GameState":
        data.setdefault("day_phase", 0.0); data.setdefault("active_campaign", "")
        data.setdefault("campaign_ends_at", 0.0); data.setdefault("email", "")
        for k in PRODUCT_CATALOG:
            data.setdefault("storage", {})[k] = data.get("storage", {}).get(k, 18)
            data.setdefault("prices",  {})[k] = data.get("prices",  {}).get(k, PRODUCT_CATALOG[k]["base_price"])
            data.setdefault("demand",  {})[k] = data.get("demand",  {}).get(k, 1.0)
        for c in SHELF_LAYOUT:
            data.setdefault("shelves", {})[c] = data.get("shelves", {}).get(c, 6)
        fields = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in fields})


def random_customer(customer_id: int, prices: Dict[str, float], demand: Dict[str, float]) -> Customer:
    section = random.choice(ALL_SECTION_KEYS)
    keys    = SECTION_PRODUCTS[section]
    n       = min(random.randint(1, 3), len(keys))
    chosen  = random.sample(keys, n)
    items: Dict[str, int] = {}
    total = 0.0
    for k in chosen:
        qty = random.randint(1, 2)
        items[k] = qty
        total += prices.get(k, PRODUCT_CATALOG[k]["base_price"]) * qty
    pay_with   = random.choice(["cash", "card"])
    cash_given = round(total + random.choice([0,0,0,1,2,5,10,20]), 2) if pay_with == "cash" else total
    complaint  = random.choice(COMPLAINTS)[0] if random.random() < 0.28 else ""
    mood       = random.choice(["happy", "neutral", "angry"])
    patience   = random.randint(60, 100)   # full patience; only ticks at checkout
    return Customer(id=customer_id, mood=mood, patience=patience, items=items,
                    section=section, complaint=complaint,
                    expected_total=round(total, 2), pay_with=pay_with, cash_given=cash_given)


def generate_review(satisfaction: int, accuracy_bonus: int, decor_bonus: int) -> dict:
    total = satisfaction + accuracy_bonus + decor_bonus
    if total >= 90:   stars, bucket = 5, "great"
    elif total >= 75: stars, bucket = 4, "great"
    elif total >= 60: stars, bucket = 3, "ok"
    elif total >= 45: stars, bucket = 2, "bad"
    else:             stars, bucket = 1, "bad"
    return {"stars": stars, "comment": random.choice(REVIEW_TEMPLATES[bucket]),
            "created_at": datetime.utcnow().isoformat()}


def price_suggestion(current: float, stock: int, demand_value: float) -> float:
    pressure = 1.05 + (demand_value - 1.0) * 0.18
    if stock < 5:   pressure += 0.05
    elif stock > 12: pressure -= 0.08
    return round(max(current * 0.80, current * pressure), 2)