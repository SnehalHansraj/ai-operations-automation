"""
Generates data/test_cases.csv — 100 simulated customer requests spanning
the issue types the agent recognizes. Run once before run_test_cases.py.

    python data/generate_test_cases.py
"""
import csv
import random
import os

random.seed(42)

TEMPLATES = {
    "delayed_delivery": [
        "My package hasn't arrived yet. Order #{oid} was supposed to arrive yesterday.",
        "Still waiting on order #{oid}, it's now 3 days late.",
        "Where is my order #{oid}? It hasn't shown up.",
    ],
    "damaged_item": [
        "The item in order #{oid} arrived damaged.",
        "Order #{oid} came in a smashed box, the product is broken.",
    ],
    "wrong_item": [
        "I received the wrong item for order #{oid}.",
        "Order #{oid} shipped the incorrect product.",
    ],
    "refund_request": [
        "I'd like a refund for order #{oid} please.",
        "Please reimburse order #{oid}, I want my money back.",
    ],
    "cancellation": [
        "Please cancel my order #{oid}, I no longer need it.",
        "I want to cancel order #{oid} before it ships.",
    ],
    "general_inquiry": [
        "Can you tell me more about order #{oid}?",
        "Question about order #{oid}, when will it ship?",
    ],
}

WEIGHTS = {
    "delayed_delivery": 35,
    "damaged_item": 15,
    "wrong_item": 10,
    "refund_request": 15,
    "cancellation": 10,
    "general_inquiry": 15,
}


def main(n=100):
    out_path = os.path.join(os.path.dirname(__file__), "test_cases.csv")
    rows = []
    issue_types = list(WEIGHTS.keys())
    weights = list(WEIGHTS.values())

    for i in range(n):
        issue_type = random.choices(issue_types, weights=weights, k=1)[0]
        template = random.choice(TEMPLATES[issue_type])
        order_id = str(random.randint(10000, 99999))
        text = template.format(oid=order_id)
        rows.append({"case_num": i + 1, "expected_issue_type": issue_type, "expected_order_id": order_id, "text": text})

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["case_num", "expected_issue_type", "expected_order_id", "text"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {n} test cases to {out_path}")


if __name__ == "__main__":
    main()
