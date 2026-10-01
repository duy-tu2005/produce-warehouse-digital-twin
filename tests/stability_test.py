#!/usr/bin/env python3
"""Run a real-time normal-operation stability test against ThingsBoard."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from pathlib import Path

from integration_test import Harness, RESULTS_DIR, load_env


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--minutes", type=float, default=30.0)
    parser.add_argument("--period-seconds", type=float, default=5.0)
    args = parser.parse_args()
    harness = Harness(load_env(), settle_seconds=0)
    harness.clear_active_alarms()
    harness.set_device_attributes({"security_mode": "DISARMED", "expected_led_state": False})

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    start = time.perf_counter()
    end = start + args.minutes * 60
    index = 0
    while True:
        due = start + index * args.period_seconds
        if due >= end:
            break
        delay = due - time.perf_counter()
        if delay > 0:
            time.sleep(delay)
        temperature = 22.0 + math.sin(index / 18.0) * 0.4
        humidity = 65.0 + math.cos(index / 22.0) * 1.2
        sent_at = time.time()
        ts = harness.send(
            {"temperature": round(temperature, 2), "humidity": round(humidity, 2)},
            timestamp_ms=int(sent_at * 1000),
            pause=False,
        )
        twin, latency = harness.wait_for_anomaly("NONE", ts, timeout=2.0)
        rows.append(
            {
                "sample": index + 1,
                "wall_time": int(sent_at * 1000),
                "temperature": round(temperature, 2),
                "humidity": round(humidity, 2),
                "observed_state": twin.get("observed_state"),
                "anomaly_type": twin.get("anomaly_type"),
                "online": twin.get("online"),
                "latency_ms": latency,
            }
        )
        index += 1
        if index % 60 == 0:
            print(f"[stability] {index} samples sent", flush=True)

    expected = max(1, round(args.minutes * 60 / args.period_seconds))
    normal = sum(row["anomaly_type"] == "NONE" for row in rows)
    online = sum(str(row["online"]).lower() == "true" for row in rows)
    metrics = {
        "duration_minutes": args.minutes,
        "period_seconds": args.period_seconds,
        "expected_samples": expected,
        "received_twin_samples": len(rows),
        "data_continuity_pct": round(len(rows) / expected * 100, 2),
        "normal_state_pct": round(normal / len(rows) * 100, 2) if rows else 0,
        "online_pct": round(online / len(rows) * 100, 2) if rows else 0,
        "max_latency_ms": max((int(row["latency_ms"]) for row in rows), default=0),
        "passed": len(rows) / expected >= 0.95 and normal / max(1, len(rows)) >= 0.95,
    }
    with (RESULTS_DIR / "stability-samples.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0].keys()) if rows else ["sample"])
        writer.writeheader()
        writer.writerows(rows)
    (RESULTS_DIR / "stability-metrics.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(metrics, indent=2, ensure_ascii=False), flush=True)
    return 0 if metrics["passed"] else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"[stability-test] ERROR: {error}", file=sys.stderr, flush=True)
        raise SystemExit(1)
