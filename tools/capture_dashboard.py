#!/usr/bin/env python3
"""Capture the authenticated local ThingsBoard dashboard through Chrome CDP.

Credentials are used only against 127.0.0.1 and are never printed or saved.
"""

from __future__ import annotations

import base64
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "report" / ".runtime"))

import websocket

CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
OUT = ROOT / "docs" / "screenshots"


def load_env() -> dict[str, str]:
    values = {}
    for line in (ROOT / ".env.local").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


def login(username: str, password: str) -> dict[str, str]:
    body = json.dumps({"username": username, "password": password}).encode()
    request = urllib.request.Request(
        "http://127.0.0.1:8080/api/auth/login",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        payload = json.load(response)
    if not payload.get("token") or not payload.get("refreshToken"):
        raise RuntimeError("Local ThingsBoard login did not return tokens")
    return payload


def token_duration_ms(token: str) -> int:
    encoded = token.split(".")[1]
    encoded += "=" * (-len(encoded) % 4)
    payload = json.loads(base64.urlsafe_b64decode(encoded).decode())
    return max(60_000, int(payload["exp"] - payload["iat"]) * 1000)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class CDP:
    def __init__(self, url: str):
        self.ws = websocket.create_connection(url, timeout=20, origin="http://localhost")
        self.counter = 0
        self.events: list[dict] = []

    def call(self, method: str, params: dict | None = None):
        self.counter += 1
        request_id = self.counter
        self.ws.send(json.dumps({"id": request_id, "method": method, "params": params or {}}))
        while True:
            message = json.loads(self.ws.recv())
            if message.get("id") == request_id:
                if "error" in message:
                    raise RuntimeError(f"CDP {method}: {message['error']}")
                return message.get("result", {})
            self.events.append(message)

    def close(self):
        self.ws.close()


def main() -> int:
    if not CHROME.exists():
        raise RuntimeError(f"Chrome not found: {CHROME}")
    env = load_env()
    dashboard_id = env["TB_DASHBOARD_ID"]
    username = os.environ.get("TB_USERNAME") or env.get("TB_USERNAME")
    password = os.environ.get("TB_PASSWORD") or env.get("TB_PASSWORD")
    if not username or not password:
        raise RuntimeError("Set TB_USERNAME and TB_PASSWORD before capturing the dashboard")
    auth = login(username, password)
    OUT.mkdir(parents=True, exist_ok=True)
    port = free_port()
    with tempfile.TemporaryDirectory(prefix="tb-dashboard-cdp-") as profile:
        process = subprocess.Popen(
            [
                str(CHROME),
                "--headless=new",
                "--disable-gpu",
                "--hide-scrollbars",
                "--no-first-run",
                "--no-default-browser-check",
                "--remote-allow-origins=*",
                f"--remote-debugging-port={port}",
                f"--user-data-dir={profile}",
                "--window-size=1920,1080",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            tabs = None
            for _ in range(100):
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=1) as response:
                        tabs = json.load(response)
                    break
                except Exception:
                    time.sleep(0.1)
            if not tabs:
                raise RuntimeError("Chrome DevTools endpoint did not become ready")
            page = next(tab for tab in tabs if tab.get("type") == "page")
            cdp = CDP(page["webSocketDebuggerUrl"])
            try:
                cdp.call("Page.enable")
                cdp.call("Runtime.enable")
                cdp.call("Network.enable")
                cdp.call("Log.enable")
                cdp.call("Page.navigate", {"url": "http://127.0.0.1:8080"})
                time.sleep(2)
                token = json.dumps(auth["token"])
                refresh = json.dumps(auth["refreshToken"])
                token_exp = token_duration_ms(auth["token"])
                refresh_exp = token_duration_ms(auth["refreshToken"])
                expression = (
                    f"localStorage.setItem('jwt_token',{token});"
                    f"localStorage.setItem('jwt_token_expiration',String(Date.now()+{token_exp}));"
                    f"localStorage.setItem('refresh_token',{refresh});"
                    f"localStorage.setItem('refresh_token_expiration',String(Date.now()+{refresh_exp}));"
                    "true;"
                )
                cdp.call("Runtime.evaluate", {"expression": expression})
                target = f"http://127.0.0.1:8080/dashboards/{dashboard_id}"
                cdp.call("Page.navigate", {"url": target})
                text = ""
                for _ in range(40):
                    time.sleep(0.5)
                    result = cdp.call(
                        "Runtime.evaluate",
                        {"expression": "document.body ? document.body.innerText : ''", "returnByValue": True},
                    )
                    text = result.get("result", {}).get("value", "")
                    if "Produce Warehouse" in text and "Sơ đồ kho tương tác" in text:
                        break
                if "Produce Warehouse" not in text:
                    raise RuntimeError("Dashboard title was not visible after authentication")
                # Close side navigation when it is expanded to maximize dashboard area.
                cdp.call(
                    "Runtime.evaluate",
                    {
                        "expression": """
                        (() => {
                          const buttons=[...document.querySelectorAll('button')];
                          const b=buttons.find(x => /menu/i.test(x.getAttribute('aria-label')||''));
                          if (b && document.body.innerText.includes('Home\\n')) b.click();
                          return true;
                        })()
                        """
                    },
                )
                time.sleep(2)

                scroll_result = cdp.call(
                    "Runtime.evaluate",
                    {
                        "expression": """
                        (() => {
                          const candidates = [document.scrollingElement, ...document.querySelectorAll('*')]
                            .filter(Boolean)
                            .filter(e => e.scrollHeight > e.clientHeight + 200)
                            .filter(e => /auto|scroll/.test(getComputedStyle(e).overflowY));
                          const el = candidates.sort((a, b) =>
                            (b.scrollHeight - b.clientHeight) - (a.scrollHeight - a.clientHeight))[0]
                            || document.scrollingElement;
                          window.__tbScrollElement = el;
                          el.scrollTop = 0;
                          return {scrollHeight: el.scrollHeight, clientHeight: el.clientHeight};
                        })()
                        """,
                        "returnByValue": True,
                    },
                )
                scroll_info = scroll_result.get("result", {}).get("value", {})

                def capture(name: str) -> None:
                    shot = cdp.call(
                        "Page.captureScreenshot",
                        {"format": "png", "fromSurface": True, "captureBeyondViewport": False},
                    )
                    (OUT / name).write_bytes(base64.b64decode(shot["data"]))

                capture("dashboard-overview.png")
                marker_count = cdp.call(
                    "Runtime.evaluate",
                    {
                        "expression": "document.querySelectorAll('.leaflet-marker-icon').length",
                        "returnByValue": True,
                    },
                ).get("result", {}).get("value", 0)
                if marker_count < 3:
                    raise RuntimeError(
                        f"Expected three separate warehouse markers, found {marker_count}"
                    )

                verified_popups: set[str] = set()
                for marker_index in range(marker_count):
                    marker_click = cdp.call(
                        "Runtime.evaluate",
                        {
                            "expression": f"""
                            (() => {{
                              const marker = document.querySelectorAll('.leaflet-marker-icon')[{marker_index}];
                              if (!marker) return false;
                              marker.dispatchEvent(new MouseEvent('click', {{bubbles: true, cancelable: true}}));
                              return true;
                            }})()
                            """,
                            "returnByValue": True,
                        },
                    )
                    if not marker_click.get("result", {}).get("value"):
                        continue
                    time.sleep(0.7)
                    popup_text = cdp.call(
                        "Runtime.evaluate",
                        {
                            "expression": "document.querySelector('.leaflet-popup-content')?.innerText || ''",
                            "returnByValue": True,
                        },
                    ).get("result", {}).get("value", "")
                    if "Nhiệt độ" in popup_text and "Độ ẩm" in popup_text:
                        capture("dashboard-warehouse-environment-popup.png")
                        capture("dashboard-warehouse-popup.png")
                        verified_popups.add("environment")
                    elif "Chuyển động" in popup_text:
                        capture("dashboard-warehouse-motion-popup.png")
                        verified_popups.add("motion")
                    elif "Trạng thái đèn" in popup_text and "bật/tắt" in popup_text:
                        capture("dashboard-warehouse-led-popup.png")
                        verified_popups.add("led")

                expected_popups = {"environment", "motion", "led"}
                if verified_popups != expected_popups:
                    raise RuntimeError(
                        "Warehouse marker popups were incomplete: "
                        f"expected {sorted(expected_popups)}, got {sorted(verified_popups)}"
                    )
                max_scroll = max(0, int(scroll_info.get("scrollHeight", 0)) - int(scroll_info.get("clientHeight", 0)))
                cdp.call(
                    "Runtime.evaluate",
                    {"expression": f"window.__tbScrollElement.scrollTop={round(max_scroll * 0.55)}; true;"},
                )
                time.sleep(1)
                capture("dashboard-history.png")
                cdp.call(
                    "Runtime.evaluate",
                    {"expression": "window.__tbScrollElement.scrollTop=window.__tbScrollElement.scrollHeight; true;"},
                )
                time.sleep(1)
                capture("dashboard-lower-panel.png")
                (OUT / "dashboard-visible-text.txt").write_text(text, encoding="utf-8")
                diagnostics = []
                for event in cdp.events:
                    method = event.get("method")
                    params = event.get("params", {})
                    if method == "Network.responseReceived":
                        response = params.get("response", {})
                        url = response.get("url", "")
                        if "/api/plugins/telemetry/" in url:
                            diagnostics.append(
                                {"kind": "network", "status": response.get("status"), "url": url}
                            )
                    elif method in {"Log.entryAdded", "Runtime.exceptionThrown"}:
                        diagnostics.append({"kind": method, "details": params})
                (OUT / "dashboard-network-diagnostics.json").write_text(
                    json.dumps(diagnostics, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                print(
                    "dashboard_capture_ok overview environment-popup motion-popup "
                    "led-popup history lower-panel"
                )
            finally:
                cdp.close()
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
