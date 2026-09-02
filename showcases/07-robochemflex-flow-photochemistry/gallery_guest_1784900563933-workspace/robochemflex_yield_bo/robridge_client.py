from __future__ import annotations

import json
import os
import subprocess
import time

from domains.roboflex.tools import fetch_roboflex_text


class RobridgeClient:
    def get_json(self, path: str) -> dict:
        return json.loads(fetch_roboflex_text(path))

    def post_json(self, path: str, payload: dict | None = None) -> dict:
        adapter = os.environ.get("ROBRIDGE_POST_ADAPTER")
        if not adapter:
            raise RuntimeError(
                "Real RoboFlex mutation requires ROBRIDGE_POST_ADAPTER. "
                "The canonical RoboFlex helper is GET-only in this environment; provide an operator-approved adapter "
                "that sends the exact OpenAPI JSON body and required X-API-Key/User-Agent headers."
            )
        proc = subprocess.run(
            [adapter, "POST", path],
            input=json.dumps(payload or {}),
            text=True,
            capture_output=True,
            check=False,
            timeout=120,
        )
        if proc.returncode:
            raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or f"adapter exited {proc.returncode}")
        return json.loads(proc.stdout or "{}")

    def start_campaign(self, experiment_type: str, analytical_method: str, campaign_name: str) -> dict:
        return self.post_json(
            "/v1/campaigns",
            {"experiment_type": experiment_type, "analytical_method": analytical_method, "campaign_name": campaign_name},
        )

    def submit_run(self, parameters: list[dict], note: str) -> dict:
        return self.post_json("/v1/runs", {"parameters": parameters, "note": note})

    def list_runs(self) -> dict:
        return self.get_json("/v1/runs")

    def run_record(self, run_id: str) -> dict:
        return self.get_json(f"/v1/runs/{run_id}")

    def result(self, run_id: str) -> dict:
        return self.get_json(f"/v1/results/{run_id}")

    def current_campaign(self) -> dict:
        return self.get_json("/v1/campaigns/current")

    def status(self) -> dict:
        return self.get_json("/v1/status")

    def stop_current(self) -> dict:
        return self.post_json("/v1/campaigns/current/stop")


def wait_for_run(client: RobridgeClient, run_id: str, timeout_s: float, poll_s: float = 30.0, heartbeat_s: float = 900.0) -> dict:
    deadline = time.monotonic() + timeout_s
    last_error = None
    last_run_state = None
    last_platform_state = None
    last_heartbeat = 0.0
    while time.monotonic() < deadline:
        now = time.monotonic()
        try:
            rec = client.run_record(run_id)
            state = rec.get("status")
            if state != last_run_state:
                print(f"RoboFlex run {run_id}: {state}")
                last_run_state = state
            if state in {"completed", "failed"}:
                return rec
            if now - last_heartbeat >= heartbeat_s:
                print(f"RoboFlex run {run_id}: still {state}; polling quietly")
                last_heartbeat = now
        except Exception as exc:  # transient 502/503/504-like GET failures are retried
            last_error = exc
            print(f"RoboFlex run {run_id}: transient poll error; retrying")
        try:
            progress = client.status().get("progress", {})
            platform_state = (progress.get("state"), progress.get("blocked_on"), progress.get("overdue"))
            if platform_state != last_platform_state:
                print(f"RoboFlex platform: state={platform_state[0]}, blocked_on={platform_state[1]}, overdue={platform_state[2]}")
                last_platform_state = platform_state
        except Exception:
            pass
        time.sleep(poll_s)
    if last_error:
        raise TimeoutError(f"run {run_id} did not finish before timeout; last poll error: {last_error}")
    raise TimeoutError(f"run {run_id} did not finish before timeout")
