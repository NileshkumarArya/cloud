#!/usr/bin/env python3
"""Optional headless browser smoke test for the CWMS dashboard."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

try:
    from playwright.sync_api import sync_playwright
except ImportError as exc:
    raise SystemExit(
        "Playwright is not installed. Install requirements-browser.txt first."
    ) from exc


def available_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for_server(url: str, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError(f"API did not become ready: {url}")


def main() -> int:
    port = available_port()
    base_url = f"http://127.0.0.1:{port}"
    with tempfile.TemporaryDirectory() as tmp:
        env = os.environ.copy()
        env["CWMS_API_PORT"] = str(port)
        env["CWMS_DB_PATH"] = str(Path(tmp) / "browser-smoke.db")
        server = subprocess.Popen(
            [sys.executable, "run_api.py"],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            wait_for_server(f"{base_url}/health")
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="msedge", headless=True)
                page = browser.new_page()
                page_errors: list[str] = []
                page.on("pageerror", lambda exc: page_errors.append(str(exc)))

                page.goto(f"{base_url}/dashboard", wait_until="networkidle")
                assert "CWMS Dashboard" in page.title()
                page.click('button[data-tab="scenarios"]')
                page.click('.scenario-card[data-scenario="normal"] .run-scenario')
                page.wait_for_function(
                    "document.getElementById('sim-status').textContent === 'Completed'",
                    timeout=15000,
                )
                page.wait_for_function(
                    "document.querySelectorAll('#forecast-table tbody tr').length > 0",
                    timeout=15000,
                )
                rows = page.locator("#forecast-table tbody tr").count()
                accuracy = page.locator("#accuracy-metrics").inner_text()
                assert rows == 20
                assert "MAE" in accuracy

                page.click('.scenario-card[data-scenario="overload"] .run-scenario')
                page.wait_for_function(
                    "document.getElementById('sim-status').textContent === 'Completed'",
                    timeout=15000,
                )
                page.wait_for_function(
                    "parseInt(document.getElementById('summary-overload').textContent.replace(/,/g, ''), 10) > 0",
                    timeout=15000,
                )
                overload = int(
                    page.locator("#summary-overload").inner_text().replace(",", "")
                )
                timeouts = int(
                    page.locator("#summary-failed").inner_text().replace(",", "")
                )
                assert overload > 0
                assert timeouts > 0
                assert not page_errors, page_errors
                browser.close()
            print(
                "Browser smoke passed: "
                f"{rows} forecast rows; overload={overload}, timeouts={timeouts}"
            )
            return 0
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()


if __name__ == "__main__":
    raise SystemExit(main())
