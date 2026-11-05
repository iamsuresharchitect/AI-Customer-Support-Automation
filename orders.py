"""Sample orders for the customer portal (data/orders.json).

Dates are stored relative to today so the demo always looks current.
"""

import json
from datetime import date, timedelta
from pathlib import Path

ORDERS_FILE = Path(__file__).resolve().parent / "data" / "orders.json"

STATUSES = ["On the way", "Delivered", "Cancelled", "Returned"]


def _fmt(day: date) -> str:
    return day.strftime("%b %d").replace(" 0", " ")


def _describe(order: dict, today: date) -> dict:
    """Add the date fields and the status line shown on the order card."""
    ordered = today - timedelta(days=order["ordered_days_ago"])
    event = order["event_days"]
    status = order["status"]
    if status == "On the way":
        expected = today + timedelta(days=event)
        if event < 0:
            headline, note, tone = f"Delivery was expected by {_fmt(expected)}", "Running late. Your item is still in transit", "warn"
        else:
            headline, note, tone = f"Delivery expected by {_fmt(expected)}", "Your item has been shipped", "good"
    elif status == "Delivered":
        headline, note, tone = f"Delivered on {_fmt(today - timedelta(days=event))}", "Your item has been delivered", "good"
    elif status == "Cancelled":
        headline, note, tone = f"Cancelled on {_fmt(today - timedelta(days=event))}", "Your order was cancelled and the payment refunded", "bad"
    else:
        headline, note, tone = f"Refund completed on {_fmt(today - timedelta(days=event))}", "Your item was returned", "neutral"
    return {**order, "ordered_on": ordered, "headline": headline, "note": note, "tone": tone}


def load_orders() -> list[dict]:
    raw = json.loads(ORDERS_FILE.read_text(encoding="utf-8"))["orders"]
    today = date.today()
    return sorted((_describe(o, today) for o in raw), key=lambda o: o["ordered_on"], reverse=True)


def orders_for(username: str) -> list[dict]:
    return [o for o in load_orders() if o["customer"] == username]


def get_order(order_id: str) -> dict | None:
    return next((o for o in load_orders() if o["order_id"] == order_id), None)


def order_summary(order: dict) -> str:
    """Order details passed to the agents with the complaint."""
    return (
        f"{order['product']} ({order['variant']}), ₹{order['price']:,}, ordered on {order['ordered_on']:%d %b %Y}. "
        f"Status: {order['status']}. {order['headline']}."
    )
