"""
Sends every row in test_cases.csv to the running API (POST /api/requests),
then reports the ACTUAL measured metrics: processing time, classification
accuracy against the expected label, and cases/day throughput implied by
the measured average. This is what turns "built an AI agent" into a
resume line backed by numbers.

Prereqs: the API must be running (docker compose up, or uvicorn locally)
and data/test_cases.csv must exist (run generate_test_cases.py first).

    python data/run_test_cases.py --base-url http://localhost:8000
"""
import argparse
import csv
import os
import statistics
import time

import httpx


def main(base_url: str, csv_path: str):
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    correct = 0
    processing_times = []
    escalations = 0

    print(f"Running {len(rows)} test cases against {base_url} ...")
    start = time.time()

    for row in rows:
        resp = httpx.post(f"{base_url}/api/requests", json={"text": row["text"]}, timeout=30)
        resp.raise_for_status()
        result = resp.json()

        if result.get("issue_type") == row["expected_issue_type"]:
            correct += 1
        if result.get("status") == "escalated":
            escalations += 1
        if result.get("processing_time_ms") is not None:
            processing_times.append(result["processing_time_ms"])

    wall_clock_s = time.time() - start
    n = len(rows)
    accuracy = 100 * correct / n if n else 0
    avg_ms = statistics.mean(processing_times) if processing_times else 0
    p95_ms = statistics.quantiles(processing_times, n=20)[18] if len(processing_times) >= 20 else max(processing_times, default=0)

    manual_baseline_s = 300  # 5 minutes, stated manual baseline for this workflow
    time_saved_pct = 100 * (1 - (avg_ms / 1000) / manual_baseline_s)

    print("\n=== Results ===")
    print(f"Cases processed:            {n}")
    print(f"Classification accuracy:    {accuracy:.1f}%")
    print(f"Avg. processing time:       {avg_ms/1000:.2f}s")
    print(f"P95 processing time:        {p95_ms/1000:.2f}s")
    print(f"Escalation rate:            {100*escalations/n:.1f}%")
    print(f"Time saved vs 5-min manual: {time_saved_pct:.1f}%")
    print(f"Total wall-clock time:      {wall_clock_s:.1f}s for {n} cases")
    print("\nSuggested CV line:")
    print(
        f'"Measured processing time and classification accuracy across {n} test cases: '
        f'{accuracy:.0f}% classification accuracy, avg. {avg_ms/1000:.1f}s per case '
        f'vs. a {manual_baseline_s//60}-minute manual baseline ({time_saved_pct:.0f}% time reduction)."'
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--csv", default=os.path.join(os.path.dirname(__file__), "test_cases.csv"))
    args = parser.parse_args()
    main(args.base_url, args.csv)
