"""Orchestration: BO-MCP loop for the deterministic 6D Ackley benchmark."""

import time
from datetime import datetime, timezone
from pathlib import Path

import logfire
from domains.bo_mcp.client import BoMcpClient

from .harness import evaluate_candidates
from .intake import BATCH_SIZE, CAMPAIGN_MARKER, build_intake
from .objective import OBJECTIVE_NAME, evaluate
from .reporting import append_rows, final_report, print_result
from .space import PARAM_NAMES

GENERATE = "bo_generate_suggestions"


def _key(params: dict) -> tuple:
    return tuple(round(float(params[n]), 6) for n in PARAM_NAMES)


class Run:
    """Stdout carries tagged lines only; everything else goes to the run log."""

    def __init__(self, artifacts: Path):
        artifacts.mkdir(parents=True, exist_ok=True)
        self.results_path = artifacts / "results.jsonl"
        self.log_path = artifacts / "run.log"

    def _write(self, line: str) -> None:
        with self.log_path.open("a") as fh:
            fh.write(f"{datetime.now(timezone.utc).isoformat()} {line}\n")

    def out(self, line: str) -> None:
        print(line, flush=True)
        self._write(line)

    def log(self, line: str) -> None:
        logfire.debug("{detail}", detail=line)
        self._write(line)


def _ensure_campaign(client: BoMcpClient, campaign_id: str | None, run: Run) -> str:
    if campaign_id:
        info = client.next_action(campaign_id)
        name = client.get_campaign(campaign_id).get("name", "")
        if CAMPAIGN_MARKER not in name:
            raise SystemExit(f"[ALERT] campaign {campaign_id} lacks required marker")
        if info["status"] == "paused":
            client.lifecycle(campaign_id, action="resume")
            run.out(f"[EVENT] resumed campaign {campaign_id}")
        elif info["status"] == "completed":
            client.lifecycle(campaign_id, action="reopen")
            run.out(f"[EVENT] reopened campaign {campaign_id}")
        else:
            run.out(f"[EVENT] continuing campaign {campaign_id} ({info['status']})")
        return campaign_id
    suffix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    intake = build_intake(suffix)
    client.validate_intake(intake)
    created = client.create_campaign(
        intake, idempotency_key=BoMcpClient.make_idempotency_key("create", suffix)
    )
    new_id = created["campaign_id"]
    run.out(f"[EVENT] created campaign {new_id} (backend=baybe)")
    return new_id


def _server_rows(client: BoMcpClient, campaign_id: str) -> list[dict]:
    rows = []
    for i, res in enumerate(client.get_results(campaign_id), start=1):
        params = {n: float(res["parameter_values"][n]) for n in PARAM_NAMES}
        rows.append(
            {
                "evaluation_index": i,
                "suggestion_id": res.get("suggestion_id"),
                "parameter_values": params,
                "values": evaluate(params),
                "status": "success",
                "failure_reason": None,
            }
        )
    return rows


def run_campaign(
    *,
    campaign_id: str | None,
    max_evaluations: int,
    artifacts_dir: Path,
    stop_file: Path,
    poll_s: float,
    heartbeat_s: float,
) -> str:
    run = Run(artifacts_dir)
    client = BoMcpClient.from_env()
    campaign_id = _ensure_campaign(client, campaign_id, run)
    run.out(f"[EVENT] BO_MCP_CAMPAIGN_ID={campaign_id}")

    prior = _server_rows(client, campaign_id)
    seen = {_key(r["parameter_values"]) for r in prior}
    attempted = len(prior)
    failures: list[dict] = []
    run.out(f"[EVENT] budget {attempted}/{max_evaluations} evaluations already stored")
    last_beat = time.monotonic()

    while attempted < max_evaluations:
        if stop_file.exists():
            stop_file.unlink()
            run.out("[EVENT] stop file found -> shutting down after this point")
            break
        if time.monotonic() - last_beat >= heartbeat_s:
            last_beat = time.monotonic()
            run.out(f"[HEARTBEAT] {attempted}/{max_evaluations} evaluations attempted")

        decision = client.next_action(campaign_id)
        run.log(f"next_action: {decision}")
        if decision["action"] != GENERATE:
            run.out(f"[ALERT] server stopped the loop: {decision['action']} "
                    f"({decision.get('reason')})")
            break

        batch = min(BATCH_SIZE, max_evaluations - attempted)
        suggestions = client.generate_suggestions(campaign_id, batch_size=batch)
        candidates = suggestions.get("suggestions") or []
        if not candidates:
            candidates = client.query_suggestions(campaign_id, status_filter="pending")
        if not candidates:
            run.out(f"[ALERT] no suggestions returned; retrying in {poll_s:.0f}s")
            time.sleep(poll_s)
            continue

        fresh = []
        for cand in candidates[:batch]:
            if _key(cand["parameter_values"]) in seen:
                client.update_suggestion_status(cand["suggestion_id"], "rejected")
                run.out("[ALERT] duplicate point suggested -> rejected, not evaluated")
                continue
            seen.add(_key(cand["parameter_values"]))
            fresh.append(cand)
        if not fresh:
            continue

        rows = evaluate_candidates(fresh, evaluate, attempted + 1)
        attempted += len(rows)
        append_rows(run.results_path, rows)
        for row in rows:
            print_result(row, run.out)

        ok = [r for r in rows if r["status"] == "success"]
        for bad in [r for r in rows if r["status"] == "failed"]:
            failures.append(bad)
            client.update_suggestion_status(bad["suggestion_id"], "rejected")
            run.out(f"[ALERT] evaluation failed: {bad['failure_reason']}")
        if ok:
            client.submit_results(
                campaign_id,
                results=[
                    {
                        "suggestion_id": r["suggestion_id"],
                        "parameter_values": r["parameter_values"],
                        "objective_values": {
                            OBJECTIVE_NAME: r["values"][OBJECTIVE_NAME]
                        },
                    }
                    for r in ok
                ],
                idempotency_key=BoMcpClient.make_idempotency_key(
                    "submit", campaign_id, str(rows[0]["evaluation_index"])
                ),
            )
            run.out(f"[EVENT] submitted {len(ok)} results "
                    f"({attempted}/{max_evaluations} attempted)")

    if client.next_action(campaign_id)["status"] == "running":
        client.lifecycle(campaign_id, action="pause")
        run.out("[EVENT] campaign paused (resume by re-running with --campaign-id)")

    final_report(campaign_id, _server_rows(client, campaign_id) + failures,
                 attempted, run.out)
    run.out(f"[EVENT] artifacts: {run.results_path} | log: {run.log_path}")
    run.out(f"[EVENT] final BO_MCP_CAMPAIGN_ID={campaign_id}")
    run.out(f"BO_MCP_CAMPAIGN_ID={campaign_id}")
    return campaign_id
