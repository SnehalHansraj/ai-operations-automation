"""
Order/Shipment API service.

In a real integration this would call Seven-Senders-style carrier/shipment
APIs over HTTP. Here it's a deterministic simulator seeded off the order_id
so results are stable across runs (useful for reproducible test metrics),
but it's wired exactly like a real httpx.get() call would be — swap the
body of get_order_status() for a real request and nothing else changes.
"""
import hashlib
import datetime
import random


STATUSES = ["in_transit", "delayed", "delivered", "out_for_delivery", "customs_hold"]
LOCATIONS = ["Frankfurt Hub", "Paris Sorting Center", "Local Depot", "Origin Warehouse", "Border Customs"]


def get_order_status(order_id: str) -> dict:
    if not order_id:
        return {"order_id": None, "status": "not_found", "last_location": None, "eta": None}

    seed = int(hashlib.sha256(order_id.encode()).hexdigest(), 16) % (2**32)
    rng = random.Random(seed)

    status = rng.choice(STATUSES)
    location = rng.choice(LOCATIONS)
    days_offset = rng.randint(-2, 4)
    eta = (datetime.date.today() + datetime.timedelta(days=days_offset)).isoformat()

    return {
        "order_id": order_id,
        "status": status,
        "last_location": location,
        "eta": eta,
        "days_since_expected": max(0, -days_offset) if days_offset < 0 else 0,
    }


def check_business_rules(order_status: dict) -> dict:
    """
    Simple business-rule layer the agent consults after getting order status.
    Returns an action recommendation the agent can act on.
    """
    if order_status.get("order_id") is None:
        return {"action": "escalate", "reason": "no_order_id_found"}

    days_late = order_status.get("days_since_expected", 0)
    status = order_status.get("status")

    if status == "customs_hold":
        return {"action": "escalate", "reason": "customs_hold_requires_human_review"}
    if days_late >= 3:
        return {"action": "escalate", "reason": f"severely_delayed_{days_late}_days"}
    if days_late > 0:
        return {"action": "auto_respond_with_apology", "reason": f"delayed_{days_late}_days"}
    return {"action": "auto_respond", "reason": "within_normal_parameters"}
