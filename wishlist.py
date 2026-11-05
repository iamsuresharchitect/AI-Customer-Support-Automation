"""Customer wishlists, kept in data/wishlists.json (created on first use, not committed)."""

import json
import zlib
from pathlib import Path

WISHLIST_FILE = Path(__file__).resolve().parent / "data" / "wishlists.json"

# Made-up catalogue items used to give each demo customer a starting wishlist.
CATALOGUE = [
    {"id": "P101", "icon": "💻", "product": "ProBook 14 Laptop", "variant": "16 GB RAM · 512 GB SSD", "price": 58990},
    {"id": "P102", "icon": "🔊", "product": "BassBar 2.1 Soundbar", "variant": "120 W · Wireless subwoofer", "price": 9749},
    {"id": "P103", "icon": "📱", "product": "Nova X5 Smartphone", "variant": "8 GB · 128 GB · Glacier White", "price": 21999},
    {"id": "P104", "icon": "⌚", "product": "FitPulse Smartwatch", "variant": "AMOLED · Black strap", "price": 3499},
    {"id": "P105", "icon": "🎒", "product": "TrailPack 30L Backpack", "variant": "Water resistant · Grey", "price": 1599},
    {"id": "P106", "icon": "☕", "product": "BrewMate Coffee Maker", "variant": "Drip · 6 cups", "price": 2799},
    {"id": "P107", "icon": "👟", "product": "StrideRun Running Shoes", "variant": "UK 9 · Navy", "price": 2899},
]


def _load() -> dict:
    if WISHLIST_FILE.exists():
        return json.loads(WISHLIST_FILE.read_text(encoding="utf-8"))
    return {}


def _save(data: dict) -> None:
    WISHLIST_FILE.parent.mkdir(parents=True, exist_ok=True)
    WISHLIST_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def get_wishlist(username: str) -> list[dict]:
    data = _load()
    if username not in data:  # first visit: three sample items, different for each customer
        start = zlib.crc32(username.encode()) % len(CATALOGUE)
        data[username] = [CATALOGUE[(start + i) % len(CATALOGUE)] for i in range(3)]
        _save(data)
    return data[username]


def add_item(username: str, item: dict) -> bool:
    """Add an item (product, variant, price, icon, id); returns False if it was already there."""
    items = get_wishlist(username)
    if any(i["id"] == item["id"] for i in items):
        return False
    data = _load()
    data[username] = items + [{k: item[k] for k in ("id", "icon", "product", "variant", "price")}]
    _save(data)
    return True


def remove_item(username: str, item_id: str) -> None:
    data = _load()
    data[username] = [i for i in get_wishlist(username) if i["id"] != item_id]
    _save(data)
