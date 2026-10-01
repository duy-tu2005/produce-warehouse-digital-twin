#!/usr/bin/env python3
"""End-to-end acceptance tests for the local ThingsBoard Digital Twin.

The test uses the same HTTP device transport as a real ESP32, so every sample
passes through the deployed device profile and Rule Engine.  It never prints
the access token or API key.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = PROJECT_ROOT / "tests" / "results"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def load_env() -> dict[str, str]:
    result: dict[str, str] = {}
    path = PROJECT_ROOT / ".env.local"
    if not path.exists():
        raise RuntimeError("Missing .env.local. Run thingsboard/setup.ps1 first.")
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            result[key] = value
    required = {"TB_API_KEY", "TB_DEVICE_TOKEN", "TB_DEVICE_ID", "TB_ASSET_ID"}
    missing = required.difference(result)
    if missing:
        raise RuntimeError(f"Missing local environment keys: {', '.join(sorted(missing))}")
    return result


@dataclass
class TrialResult:
    scenario: str
    trial: int
    expected_anomaly: str
    observed_anomaly: str
    observed_state: str
    severity: str
    detected: bool
    alarm_active: bool
    latency_ms: int
    notes: str


class Harness:
    def __init__(self, env: dict[str, str], settle_seconds: float = 0.10) -> None:
        base = env.get("TB_BASE_URL", "http://localhost:8080")
        parsed = urllib.parse.urlsplit(base)
        port = f":{parsed.port}" if parsed.port else ""
        host = "127.0.0.1" if parsed.hostname == "localhost" else parsed.hostname
        self.base = urllib.parse.urlunsplit((parsed.scheme, f"{host}{port}", "", "", ""))
        self.api_key = env["TB_API_KEY"]
        self.device_token = env["TB_DEVICE_TOKEN"]
        self.device_id = env["TB_DEVICE_ID"]
        self.asset_id = env["TB_ASSET_ID"]
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.settle_seconds = settle_seconds
        self.sequence = 1000
        self.uptime = 1000
        self.virtual_ts = int(time.time() * 1000)
        self.posts_attempted = 0
        self.posts_succeeded = 0
        self.normal_sequence_checks = 0
        self.normal_sequence_ok = 0
        self.baseline_checks = 0
        self.false_alarms = 0
        self._synchronize_counters()

    def _synchronize_counters(self) -> None:
        """Continue sequence counters without exposing credentials in output."""
        response = self.request(
            "GET",
            f"/api/plugins/telemetry/DEVICE/{self.device_id}/values/timeseries?"
            "keys=sequence,uptime_s,last_seen",
        )
        for key, values in response.items():
            if not values:
                continue
            item = values[0]
            if item.get("value") is None:
                continue
            self.virtual_ts = max(self.virtual_ts, int(item.get("ts", 0)))
            if key == "sequence":
                self.sequence = int(float(item.get("value", self.sequence)))
            elif key == "uptime_s":
                self.uptime = int(float(item.get("value", self.uptime)))
            elif key == "last_seen":
                self.virtual_ts = max(self.virtual_ts, int(float(item.get("value", 0))))
        self.virtual_ts += 5000

    def reset_test_data(self) -> None:
        """Remove generated telemetry/alarms and start in a safe past window.

        The accelerated suite advances a logical five seconds per sample. Starting
        three hours behind wall time prevents alarm timestamps from entering the
        future while preserving the production 5 s sampling semantics.
        """
        for entity_type, entity_id in (
            ("DEVICE", self.device_id),
            ("ASSET", self.asset_id),
        ):
            keys = self.request(
                "GET", f"/api/plugins/telemetry/{entity_type}/{entity_id}/keys/timeseries"
            )
            if keys:
                encoded = urllib.parse.quote(",".join(keys), safe=",")
                self.request(
                    "DELETE",
                    f"/api/plugins/telemetry/{entity_type}/{entity_id}/timeseries/delete?"
                    f"keys={encoded}&deleteAllDataForKeys=false&startTs=0&"
                    f"endTs=32503680000000&deleteLatest=true",
                )
        while True:
            alarms = self.alarms(active_only=False)
            if not alarms:
                break
            for alarm in alarms:
                self.request("DELETE", f"/api/alarm/{alarm['id']['id']}")
        self.sequence = 1000
        self.uptime = 1000
        self.virtual_ts = int(time.time() * 1000) - 3 * 60 * 60 * 1000

    def request(
        self,
        method: str,
        path: str,
        body: Any | None = None,
        authenticated: bool = True,
        timeout: float = 20,
    ) -> Any:
        headers = {"Accept": "application/json", "Connection": "close"}
        payload = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            payload = json.dumps(body).encode("utf-8")
        if authenticated:
            headers["X-Authorization"] = "ApiKey " + self.api_key
        request = urllib.request.Request(self.base + path, data=payload, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=timeout) as response:
                raw = response.read()
                return json.loads(raw.decode("utf-8-sig")) if raw else None
        except urllib.error.HTTPError as error:
            details = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{method} {path} failed ({error.code}): {details}") from error

    def set_device_attributes(self, values: dict[str, Any]) -> None:
        self.request(
            "POST",
            f"/api/plugins/telemetry/DEVICE/{self.device_id}/attributes/SERVER_SCOPE",
            values,
        )

    def send(
        self,
        overrides: dict[str, Any] | None = None,
        *,
        sequence_delta: int = 1,
        uptime_value: int | None = None,
        timestamp_step_ms: int = 5000,
        timestamp_ms: int | None = None,
        pause: bool = True,
    ) -> int:
        if timestamp_ms is None:
            self.virtual_ts += timestamp_step_ms
        else:
            self.virtual_ts = timestamp_ms
        previous_sequence = self.sequence
        self.sequence += sequence_delta
        self.uptime += 5
        values: dict[str, Any] = {
            "temperature": 22.0 + (self.sequence % 5 - 2) * 0.02,
            "humidity": 65.0 - (self.sequence % 5 - 2) * 0.03,
            "motion": False,
            "rssi": -52,
            "sequence": self.sequence,
            "uptime_s": self.uptime if uptime_value is None else uptime_value,
            "led_state": False,
            "sensor_valid": True,
            "firmware_version": "acceptance-test",
        }
        if overrides:
            values.update(overrides)
        self.posts_attempted += 1
        self.request(
            "POST",
            "/api/v1/" + urllib.parse.quote(self.device_token, safe="") + "/telemetry",
            {"ts": self.virtual_ts, "values": values},
            authenticated=False,
        )
        self.posts_succeeded += 1
        if sequence_delta == 1:
            self.normal_sequence_checks += 1
            if self.sequence == previous_sequence + 1:
                self.normal_sequence_ok += 1
        if pause:
            time.sleep(self.settle_seconds)
        return self.virtual_ts

    @staticmethod
    def flatten_latest(response: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
        return {key: values[0]["value"] for key, values in response.items() if values}

    def twin(self) -> dict[str, Any]:
        keys = (
            "last_seen,observed_state,expected_state,health_score,anomaly_score,"
            "anomaly_type,anomaly,severity,online,state_match,recovery_count,"
            "actuator_mismatch_count"
        )
        response = self.request(
            "GET", f"/api/plugins/telemetry/ASSET/{self.asset_id}/values/timeseries?keys={keys}"
        )
        return self.flatten_latest(response)

    def wait_for_anomaly(
        self, expected: str, minimum_last_seen: int | None, timeout: float = 4.0
    ) -> tuple[dict[str, Any], int]:
        start = time.perf_counter()
        latest: dict[str, Any] = {}
        while time.perf_counter() - start < timeout:
            latest = self.twin()
            seen = int(float(latest.get("last_seen") or 0))
            fresh = minimum_last_seen is None or seen >= minimum_last_seen
            if fresh and str(latest.get("anomaly_type", "")) == expected:
                return latest, round((time.perf_counter() - start) * 1000)
            time.sleep(0.08)
        return latest, round((time.perf_counter() - start) * 1000)

    def wait_for_state(self, state: str, timeout: float) -> tuple[dict[str, Any], int]:
        start = time.perf_counter()
        latest: dict[str, Any] = {}
        while time.perf_counter() - start < timeout:
            latest = self.twin()
            if str(latest.get("observed_state", "")) == state:
                return latest, round((time.perf_counter() - start) * 1000)
            time.sleep(0.20)
        return latest, round((time.perf_counter() - start) * 1000)

    def wait_for_last_seen(self, minimum_last_seen: int, timeout: float = 2.0) -> dict[str, Any]:
        """Wait until one sample has completed the full device-to-asset flow."""
        end = time.perf_counter() + timeout
        latest: dict[str, Any] = {}
        while time.perf_counter() < end:
            latest = self.twin()
            if int(float(latest.get("last_seen") or 0)) >= minimum_last_seen:
                return latest
            time.sleep(0.05)
        return latest

    def alarms(self, active_only: bool = False) -> list[dict[str, Any]]:
        suffix = "&searchStatus=ACTIVE" if active_only else ""
        page = self.request(
            "GET",
            f"/api/alarm/ASSET/{self.asset_id}?pageSize=200&page=0&sortOrder=DESC{suffix}",
        )
        return page.get("data", [])

    def alarm_is_active(self, alarm_type: str, timeout: float = 3.0) -> bool:
        end = time.perf_counter() + timeout
        while time.perf_counter() < end:
            if any(alarm.get("type") == alarm_type for alarm in self.alarms(active_only=True)):
                return True
            time.sleep(0.10)
        return False

    def clear_active_alarms(self) -> None:
        for alarm in self.alarms(active_only=True):
            self.request("POST", f"/api/alarm/{alarm['id']['id']}/clear", {})

    def stabilize(self, samples: int = 6, clear_stale: bool = True) -> dict[str, Any]:
        self.set_device_attributes(
            {"security_mode": "DISARMED", "expected_led_state": False}
        )
        latest: dict[str, Any] = {}
        for _ in range(samples):
            ts = self.send()
            latest, _ = self.wait_for_anomaly("NONE", ts, timeout=2.0)
        self.baseline_checks += 1
        if str(latest.get("anomaly_type", "NONE")) != "NONE":
            self.false_alarms += 1
        if clear_stale:
            self.clear_active_alarms()
        return latest


def execute_trial(
    harness: Harness,
    scenario: str,
    trial: int,
    expected: str,
    injector: Callable[[Harness], int],
) -> TrialResult:
    harness.stabilize()
    started = time.perf_counter()
    target_ts = injector(harness)
    twin, poll_latency = harness.wait_for_anomaly(expected, target_ts, timeout=4.0)
    alarm_active = harness.alarm_is_active(expected, timeout=2.0)
    total_latency = max(poll_latency, round((time.perf_counter() - started) * 1000))
    observed = str(twin.get("anomaly_type", "MISSING"))
    detected = observed == expected
    notes = ""
    if not detected:
        notes = f"last twin={json.dumps(twin, ensure_ascii=True)}"
    print(
        f"[{scenario}] trial {trial}: expected={expected} observed={observed} "
        f"alarm={'yes' if alarm_active else 'no'} latency={total_latency}ms",
        flush=True,
    )
    return TrialResult(
        scenario=scenario,
        trial=trial,
        expected_anomaly=expected,
        observed_anomaly=observed,
        observed_state=str(twin.get("observed_state", "MISSING")),
        severity=str(twin.get("severity", "MISSING")),
        detected=detected,
        alarm_active=alarm_active,
        latency_ms=total_latency,
        notes=notes,
    )


def run_detection_suite(harness: Harness, trials: int, include_offline: bool) -> list[TrialResult]:
    results: list[TrialResult] = []

    def one(values: dict[str, Any], **send_options: Any) -> Callable[[Harness], int]:
        return lambda h: h.send(values, **send_options)

    scenarios: list[tuple[str, str, Callable[[Harness], int]]] = [
        ("high_temperature", "HIGH_TEMPERATURE", one({"temperature": 36.0})),
        ("low_temperature", "LOW_TEMPERATURE", one({"temperature": 10.0})),
        ("high_humidity", "HIGH_HUMIDITY", one({"humidity": 95.0})),
        ("low_humidity", "LOW_HUMIDITY", one({"humidity": 30.0})),
        ("temperature_rate", "TEMPERATURE_RATE_ANOMALY", one({"temperature": 25.0})),
        ("humidity_rate", "HUMIDITY_RATE_ANOMALY", one({"humidity": 72.0})),
        ("weak_signal", "WEAK_SIGNAL", one({"rssi": -96})),
        ("sequence_gap", "SEQUENCE_GAP", one({}, sequence_delta=4)),
        ("device_restart", "DEVICE_RESTART", one({}, uptime_value=1)),
    ]

    def unexpected_motion(h: Harness) -> int:
        h.set_device_attributes({"security_mode": "ARMED"})
        return h.send({"motion": True})

    def invalid_sensor(h: Harness) -> int:
        target = 0
        for _ in range(3):
            target = h.send(
                {"temperature": 999.0, "humidity": 999.0, "sensor_valid": False}
            )
        return target

    def sensor_stuck(h: Harness) -> int:
        target = 0
        for _ in range(13):
            target = h.send({"temperature": 22.5, "humidity": 65.5})
            h.wait_for_last_seen(target)
        return target

    def actuator_mismatch(h: Harness) -> int:
        h.set_device_attributes({"expected_led_state": True})
        target = 0
        for _ in range(3):
            target = h.send({"led_state": False})
        return target

    scenarios.extend(
        [
            ("unexpected_motion", "UNEXPECTED_MOTION", unexpected_motion),
            ("invalid_sensor", "INVALID_SENSOR", invalid_sensor),
            ("sensor_stuck", "SENSOR_STUCK", sensor_stuck),
            ("actuator_mismatch", "ACTUATOR_MISMATCH", actuator_mismatch),
        ]
    )

    for scenario, expected, injector in scenarios:
        for trial in range(1, trials + 1):
            results.append(execute_trial(harness, scenario, trial, expected, injector))

    if include_offline:
        for trial in range(1, trials + 1):
            # Lifecycle events use server wall time. Switch this phase from the
            # accelerated historical timeline to real timestamps and verify the
            # previous OFFLINE state has recovered before starting each clock.
            activity_ts = harness.send(
                {"temperature": 22.0, "humidity": 65.0},
                timestamp_ms=int(time.time() * 1000),
                pause=False,
            )
            last_activity = time.perf_counter()
            recovered, _ = harness.wait_for_anomaly("NONE", activity_ts, timeout=3.0)
            harness.clear_active_alarms()
            remaining = max(0.2, 15.2 - (time.perf_counter() - last_activity))
            twin, latency = harness.wait_for_state("OFFLINE", timeout=remaining)
            measured = round((time.perf_counter() - last_activity) * 1000)
            alarm_active = harness.alarm_is_active("CONNECTION_LOST", timeout=2.0)
            recovery_ok = str(recovered.get("observed_state")) != "OFFLINE"
            detected = (
                str(twin.get("observed_state")) == "OFFLINE"
                and str(twin.get("anomaly_type")) == "CONNECTION_LOST"
            )
            print(
                f"[connection_lost] trial {trial}: state={twin.get('observed_state')} "
                f"alarm={'yes' if alarm_active else 'no'} latency={measured}ms",
                flush=True,
            )
            results.append(
                TrialResult(
                    scenario="connection_lost",
                    trial=trial,
                    expected_anomaly="CONNECTION_LOST",
                    observed_anomaly=str(twin.get("anomaly_type", "MISSING")),
                    observed_state=str(twin.get("observed_state", "MISSING")),
                    severity=str(twin.get("severity", "MISSING")),
                    detected=detected,
                    alarm_active=alarm_active,
                    latency_ms=measured,
                    notes=(
                        "Recovery precondition failed"
                        if not recovery_ok
                        else ("" if measured <= 15000 else "Connection alert exceeded 15 s")
                    ),
                )
            )
            time.sleep(0.2)

    harness.set_device_attributes({"security_mode": "DISARMED", "expected_led_state": False})
    for _ in range(4):
        ts = harness.send(
            {"temperature": 22.0, "humidity": 65.0},
            timestamp_ms=int(time.time() * 1000),
            pause=False,
        )
        harness.wait_for_last_seen(ts, timeout=2.0)
        time.sleep(0.2)
    harness.clear_active_alarms()
    return results


def percentile(values: list[int], fraction: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(len(ordered) * fraction) - 1))
    return ordered[index]


def save_results(harness: Harness, results: list[TrialResult]) -> dict[str, Any]:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = RESULTS_DIR / "anomaly_trials.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(asdict(results[0]).keys()))
        writer.writeheader()
        writer.writerows(asdict(result) for result in results)

    detected = sum(result.detected for result in results)
    alarms = sum(result.alarm_active for result in results)
    tdr = detected / len(results) * 100 if results else 0.0
    alarm_rate = alarms / len(results) * 100 if results else 0.0
    far = harness.false_alarms / harness.baseline_checks * 100 if harness.baseline_checks else 0.0
    continuity = harness.posts_succeeded / harness.posts_attempted * 100 if harness.posts_attempted else 0.0
    sequence_consistency = (
        harness.normal_sequence_ok / harness.normal_sequence_checks * 100
        if harness.normal_sequence_checks
        else 0.0
    )
    connection_latencies = [
        result.latency_ms for result in results if result.scenario == "connection_lost" and result.detected
    ]
    metrics = {
        "generated_at": int(time.time() * 1000),
        "trial_count": len(results),
        "detected_count": detected,
        "alarm_active_count": alarms,
        "true_detection_rate_pct": round(tdr, 2),
        "alarm_creation_rate_pct": round(alarm_rate, 2),
        "false_alarm_rate_pct": round(far, 2),
        "data_continuity_pct": round(continuity, 2),
        "sequence_consistency_pct": round(sequence_consistency, 2),
        "latency_ms": {
            "median": percentile([r.latency_ms for r in results], 0.50),
            "p95": percentile([r.latency_ms for r in results], 0.95),
            "max": max((r.latency_ms for r in results), default=0),
            "connection_max": max(connection_latencies, default=0),
        },
        "acceptance": {
            "tdr_at_least_90": tdr >= 90,
            "far_at_most_5": far <= 5,
            "connection_at_most_15s": not connection_latencies or max(connection_latencies) <= 15000,
            "continuity_at_least_95": continuity >= 95,
            "sequence_at_least_99": sequence_consistency >= 99,
        },
    }
    (RESULTS_DIR / "metrics.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    lines = [
        "# Kết quả kiểm thử chấp nhận",
        "",
        f"- Số ca thử bất thường: **{len(results)}**",
        f"- Tỷ lệ phát hiện đúng (TDR): **{tdr:.2f}%**",
        f"- Tỷ lệ tạo alarm tương ứng: **{alarm_rate:.2f}%**",
        f"- Tỷ lệ cảnh báo giả trên cửa sổ baseline (FAR): **{far:.2f}%**",
        f"- Độ liên tục gửi dữ liệu: **{continuity:.2f}%**",
        f"- Nhất quán sequence ở luồng bình thường: **{sequence_consistency:.2f}%**",
        f"- Độ trễ p95: **{metrics['latency_ms']['p95']} ms**",
        f"- Độ trễ mất kết nối lớn nhất: **{metrics['latency_ms']['connection_max']} ms**",
        "",
        "## Đối chiếu tiêu chí",
        "",
    ]
    for key, passed in metrics["acceptance"].items():
        lines.append(f"- {'PASS' if passed else 'FAIL'} — `{key}`")
    lines.extend(
        [
            "",
            "> Các ca trên dùng HTTP Device API nhưng đi qua đúng Device Profile và Rule Engine như ESP32/MQTT. "
            "Kiểm tra Wokwi vật lý được thực hiện riêng theo checklist demo.",
            "",
        ]
    )
    (RESULTS_DIR / "acceptance-summary.md").write_text("\n".join(lines), encoding="utf-8")
    return metrics


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=10)
    parser.add_argument("--skip-offline", action="store_true")
    parser.add_argument("--settle-seconds", type=float, default=0.10)
    parser.add_argument(
        "--reset-test-data",
        action="store_true",
        help="Delete prior generated telemetry/alarms before an accelerated run.",
    )
    args = parser.parse_args()
    if args.trials < 1:
        parser.error("--trials must be positive")

    harness = Harness(load_env(), settle_seconds=args.settle_seconds)
    if args.reset_test_data:
        harness.reset_test_data()
    else:
        harness.clear_active_alarms()
    results = run_detection_suite(harness, args.trials, include_offline=not args.skip_offline)
    metrics = save_results(harness, results)
    print(json.dumps(metrics, indent=2, ensure_ascii=False), flush=True)
    return 0 if all(metrics["acceptance"].values()) else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"[integration-test] ERROR: {error}", file=sys.stderr, flush=True)
        raise SystemExit(1)
