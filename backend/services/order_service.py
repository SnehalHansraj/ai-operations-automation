"""
Order/Shipment API service.

In production this service could call real carrier/shipment APIs.
For the MVP, deterministic simulated data is used so that the same
order ID produces reproducible results.

The service also contains the operational policy layer used by the agent.
"""

import datetime
import hashlib
import random


STATUSES = [
    "in_transit",
    "delayed",
    "delivered",
    "out_for_delivery",
    "customs_hold",
]

LOCATIONS = [
    "Frankfurt Hub",
    "Paris Sorting Center",
    "Local Depot",
    "Origin Warehouse",
    "Border Customs",
]


# -------------------------------------------------------------------
# ORDER STATUS TOOL
# -------------------------------------------------------------------

def get_order_status(order_id: str) -> dict:
    """
    Retrieve shipment information.

    The simulator is deterministic: the same order ID always produces
    the same shipment characteristics.
    """

    if not order_id:
        return {
            "order_id": None,
            "status": "not_found",
            "last_location": None,
            "eta": None,
            "days_since_expected": 0,
        }

    seed = (
        int(
            hashlib.sha256(
                order_id.encode()
            ).hexdigest(),
            16,
        )
        % (2**32)
    )

    rng = random.Random(seed)

    status = rng.choice(STATUSES)
    location = rng.choice(LOCATIONS)

    days_offset = rng.randint(-2, 4)

    eta = (
        datetime.date.today()
        + datetime.timedelta(days=days_offset)
    ).isoformat()

    days_since_expected = (
        max(0, -days_offset)
        if days_offset < 0
        else 0
    )

    return {
        "order_id": order_id,
        "status": status,
        "last_location": location,
        "eta": eta,
        "days_since_expected": days_since_expected,
    }


# -------------------------------------------------------------------
# BUSINESS POLICY TOOL
# -------------------------------------------------------------------

def check_business_rules(
    order_status: dict,
    customer_issue: str | None = None,
) -> dict:
    """
    Evaluate operational policy.

    The policy considers:
    1. Missing order information
    2. Customer/system contradictions
    3. Customs holds
    4. Severe delays
    5. Normal delays
    6. Normal shipment status

    Returns an action recommendation for the agent.
    """

    # ---------------------------------------------------------------
    # 1. Missing order
    # ---------------------------------------------------------------

    if order_status.get("order_id") is None:
        return {
            "action": "escalate",
            "reason": "no_order_id_found",
        }

    status = order_status.get(
        "status",
        "unknown",
    )

    days_late = order_status.get(
        "days_since_expected",
        0,
    )

    # ---------------------------------------------------------------
    # 2. Customer/system contradiction
    # ---------------------------------------------------------------

    if (
        customer_issue == "delayed_delivery"
        and days_late == 0
        and status not in {
            "delivered",
            "customs_hold",
        }
    ):
        return {
            "action": "escalate",
            "reason": "customer_reports_delay_but_system_shows_on_time",
        }

    # ---------------------------------------------------------------
    # 3. Customs hold
    # ---------------------------------------------------------------

    if status == "customs_hold":
        return {
            "action": "escalate",
            "reason": "customs_hold_requires_human_review",
        }

    # ---------------------------------------------------------------
    # 4. Severe delay
    # ---------------------------------------------------------------

    if days_late >= 3:
        return {
            "action": "escalate",
            "reason": (
                f"severely_delayed_{days_late}_days"
            ),
        }

    # ---------------------------------------------------------------
    # 5. Normal delay
    # ---------------------------------------------------------------

    if days_late > 0:
        return {
            "action": "auto_respond_with_apology",
            "reason": (
                f"delayed_{days_late}_days"
            ),
        }

    # ---------------------------------------------------------------
    # 6. Normal shipment
    # ---------------------------------------------------------------

    return {
        "action": "auto_respond",
        "reason": "within_normal_parameters",
    }