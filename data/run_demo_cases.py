"""
OpsPilot — Interview Demo Test Suite

Runs curated operational scenarios through the real
FastAPI agent and prints a clean summary.

The cases are intentionally selected to demonstrate:

1. Normal automatic resolution
2. Delayed shipment
3. Damaged item
4. Wrong item
5. Refund request
6. Cancellation
7. Customs escalation + real email
8. Missing order ID escalation

Run the FastAPI server first:

    uvicorn backend.main:app --reload

Then:

    python data/run_demo_cases.py
"""

import json
import time
import requests


API_URL = "http://127.0.0.1:8000/api/requests"


DEMO_CASES = [
    {
        "name": "Normal Delivery",
        "text": (
            "Can you tell me the current status of "
            "order #10003?"
        ),
        "purpose": "Normal shipment status / automatic handling",
    },

    {
        "name": "Delayed Delivery",
        "text": (
            "My order #10005 has not arrived yet. "
            "It is two days late. Can you check it?"
        ),
        "purpose": "Delayed shipment with apology response",
    },

    {
        "name": "Damaged Item",
        "text": (
            "My order #10011 arrived damaged. "
            "The product is broken and I need a replacement."
        ),
        "purpose": "Damaged-item workflow",
    },

    {
        "name": "Wrong Item",
        "text": (
            "I received the wrong product in order #10004. "
            "Please help me return it."
        ),
        "purpose": "Wrong-item workflow",
    },

    {
        "name": "Refund Request",
        "text": (
            "I want a refund for order #10012. "
            "Please process my refund request."
        ),
        "purpose": "Billing/refund workflow",
    },

    {
        "name": "Cancellation",
        "text": (
            "Please cancel my order #10017 "
            "as soon as possible."
        ),
        "purpose": "Order cancellation workflow",
    },

    {
        "name": "Customs Escalation",
        "text": (
            "My order #10001 is stuck in customs "
            "and I need someone from operations to investigate."
        ),
        "purpose": "Human escalation + email notification",
    },

    {
        "name": "Missing Order ID",
        "text": (
            "My package hasn't arrived yet. "
            "Can someone please check what happened?"
        ),
        "purpose": "Missing order ID → human escalation",
    },
]


def print_separator():
    print("=" * 80)


def run_case(case_number, case):
    print()
    print_separator()

    print(
        f"TEST {case_number}: {case['name']}"
    )

    print_separator()

    print("Customer:")
    print(case["text"])

    print()
    print("Purpose:")
    print(case["purpose"])

    print()
    print("Running agent...")

    start = time.perf_counter()

    try:
        response = requests.post(
            API_URL,
            json={
                "text": case["text"]
            },
            timeout=180,
        )

        elapsed = (
            time.perf_counter()
            - start
        )

        if response.status_code != 200:

            print(
                f"❌ FAILED — HTTP {response.status_code}"
            )

            print(
                response.text
            )

            return {
                "name": case["name"],
                "status": "FAILED",
            }

        result = response.json()

        print()
        print("RESULT")
        print("-" * 80)

        print(
            f"Order ID       : "
            f"{result.get('order_id')}"
        )

        print(
            f"Issue Type     : "
            f"{result.get('issue_type')}"
        )

        print(
            f"Confidence     : "
            f"{result.get('confidence')}"
        )

        print(
            f"Decision       : "
            f"{result.get('action')}"
        )

        print(
            f"Reason         : "
            f"{result.get('decision_reason')}"
        )

        print(
            f"Status         : "
            f"{result.get('status')}"
        )

        print(
            f"Notification   : "
            f"{result.get('notified_channel')}"
        )

        print(
            f"Verified       : "
            f"{result.get('verified')}"
        )

        print(
            f"Processing     : "
            f"{result.get('processing_time_ms')} ms"
        )

        print()

        print("Customer Response:")
        print(
            result.get(
                "response_text",
                "",
            )
        )

        print()

        trace = result.get(
            "trace",
            [],
        )

        print(
            f"Agent Trace    : "
            f"{len(trace)} steps"
        )

        for step in trace:

            print(
                f"  {step['step_number']}. "
                f"{step['step_name']}"
            )

        print()

        print(
            f"⏱ Request completed in "
            f"{elapsed:.2f}s"
        )

        return {
            "name": case["name"],
            "status": "PASSED",
            "action": result.get(
                "action"
            ),
            "notification": result.get(
                "notified_channel"
            ),
            "processing_ms": result.get(
                "processing_time_ms"
            ),
        }

    except requests.exceptions.ConnectionError:

        print()
        print(
            "❌ Could not connect to FastAPI."
        )

        print(
            "Start the server with:"
        )

        print(
            "uvicorn backend.main:app --reload"
        )

        return {
            "name": case["name"],
            "status": "FAILED",
        }

    except Exception as exc:

        print()
        print(
            f"❌ Unexpected error: {exc}"
        )

        return {
            "name": case["name"],
            "status": "FAILED",
        }


def main():

    print()
    print("=" * 80)
    print("                 OPSpilot")
    print("             INTERVIEW DEMO SUITE")
    print("=" * 80)

    print()
    print(
        f"Running {len(DEMO_CASES)} curated "
        f"operational scenarios."
    )

    print()
    print(
        "NOTE: The escalation cases may send "
        "real emails."
    )

    print()

    results = []

    for index, case in enumerate(
        DEMO_CASES,
        start=1,
    ):

        result = run_case(
            index,
            case,
        )

        results.append(
            result
        )

        # Small pause so the console remains readable.
        time.sleep(1)

    # ========================================================
    # FINAL SUMMARY
    # ========================================================

    print()
    print()
    print("=" * 80)
    print("                    DEMO SUMMARY")
    print("=" * 80)

    passed = sum(
        1
        for r in results
        if r["status"] == "PASSED"
    )

    failed = len(results) - passed

    print()
    print(
        f"Passed: {passed}/{len(results)}"
    )

    print(
        f"Failed: {failed}/{len(results)}"
    )

    print()

    print(
        f"{'Scenario':<25}"
        f"{'Result':<12}"
        f"{'Decision':<25}"
        f"{'Notification'}"
    )

    print("-" * 80)

    for result in results:

        print(
            f"{result['name']:<25}"
            f"{result['status']:<12}"
            f"{result.get('action', '-'):<25}"
            f"{result.get('notification', '-')}"
        )

    print()
    print("=" * 80)

    print(
        "Demo complete."
    )

    print(
        "Open http://127.0.0.1:8000/dashboard "
        "to view the cases."
    )

    print("=" * 80)


if __name__ == "__main__":
    main()