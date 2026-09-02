from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

import logfire
from domains.bo_mcp.client import BoMcpClient, BoMcpClientError, BoMcpOperationError

from .evaluation import append_jsonl, evaluate_candidate
from .intake import build_intake
from .reporting import tagged, write_bytes
from .search_space import build_space


def _campaign_id(resp: dict) -> str:
    return str(resp.get("campaign_id") or resp.get("id") or resp.get("campaign", {}).get("id"))


def _status(campaign: dict) -> str:
    data = campaign.get("campaign", campaign)
    return str(data.get("status", "")).lower()


def _suggestions(payload) -> list[dict]:
    if isinstance(payload, list):
        return payload
    for key in ("suggestions", "data", "candidates", "items"):
        value = payload.get(key) if isinstance(payload, dict) else None
        if isinstance(value, list):
            return value
    return []


def _suggestion_id(s: dict) -> str | None:
    return s.get("suggestion_id") or s.get("id")


def _params(s: dict) -> dict:
    p = s.get("parameter_values") or s.get("parameters") or s.get("candidate") or {}
    return {"topology": str(p["topology"]), "node": str(p["node"]), "edge": str(p["edge"])}


def _maybe_resume(client: BoMcpClient, campaign_id: str) -> None:
    status = _status(client.get_campaign(campaign_id))
    if status == "paused":
        client.lifecycle(campaign_id, action="resume")
        tagged("EVENT", f"resumed campaign {campaign_id}")
    elif status == "completed":
        client.lifecycle(campaign_id, action="reopen")
        tagged("EVENT", f"reopened completed campaign {campaign_id}")


def run(args) -> str:
    artifact_dir = Path(args.artifact_dir) / time.strftime("%Y%m%d_%H%M%S")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    log_path = artifact_dir / "run.log"
    evaluations_path = artifact_dir / "evaluations.jsonl"
    tagged("EVENT", f"artifacts={artifact_dir} log={log_path}")

    space = build_space(args.node_limit_per_topology, args.edge_limit)
    (artifact_dir / "candidate_space.json").write_text(json.dumps(space, indent=2, sort_keys=True))
    tagged("EVENT", f"candidate space: {len(space['topologies'])} topologies, {len(space['nodes'])} nodes, {len(space['edges'])} edges")
    if space["excluded_topologies"]:
        tagged("ALERT", f"excluded exact-single-node topologies: {space['excluded_topologies']}")

    client = BoMcpClient.from_env(timeout_s=args.client_timeout_s)
    if args.campaign_id:
        campaign_id = args.campaign_id
        _maybe_resume(client, campaign_id)
    else:
        intake = build_intake(
            space,
            name=args.campaign_name,
            batch_size=args.batch_size,
            total_budget=args.total_budget,
            initial_design_size=args.initial_design_size,
        )
        (artifact_dir / "campaign_intake.json").write_text(json.dumps(intake, indent=2, sort_keys=True))
        validation = client.validate_intake(intake)
        (artifact_dir / "validation.json").write_text(json.dumps(validation, indent=2, sort_keys=True))
        if not validation.get("valid", False):
            tagged("ALERT", f"intake invalid: {validation.get('errors')}")
            raise RuntimeError("BO-MCP intake validation failed")
        key = client.make_idempotency_key("xe-kr-mof", str(uuid.uuid4()))
        created = client.create_campaign(intake, idempotency_key=key)
        campaign_id = _campaign_id(created)
        tagged("EVENT", f"created campaign {campaign_id}")

    successes = 0
    last_heartbeat = time.monotonic()
    stop_file = Path(args.stop_file)

    while successes < args.max_evaluations:
        if stop_file.exists():
            tagged("EVENT", f"stop file {stop_file} detected; deleting marker and shutting down")
            stop_file.unlink()
            break
        if time.monotonic() - last_heartbeat >= args.heartbeat_s:
            tagged("HEARTBEAT", f"campaign={campaign_id} completed_this_invocation={successes}")
            last_heartbeat = time.monotonic()

        decision = client.next_action(campaign_id)
        action = decision.get("action")
        if action != "bo_generate_suggestions":
            tagged("EVENT", f"BO next_action={action}; stopping invocation")
            break

        pending = client.query_suggestions(campaign_id, status_filter="pending", limit=args.batch_size)
        suggestions = pending[: args.batch_size]
        if not suggestions:
            try:
                suggestions = _suggestions(client.generate_suggestions(campaign_id, batch_size=args.batch_size, timeout_s=args.generate_timeout_s))
            except BoMcpOperationError as exc:
                tagged("EVENT", f"suggestion generation stopped: {exc}")
                break
            except BoMcpClientError:
                suggestions = client.query_suggestions(campaign_id, status_filter="pending", limit=args.batch_size)
                if not suggestions:
                    raise
        if not suggestions:
            tagged("EVENT", "no suggestions returned; stopping invocation")
            break

        for suggestion in suggestions:
            if successes >= args.max_evaluations:
                break
            sid = _suggestion_id(suggestion)
            params = _params(suggestion)
            tagged("EVENT", f"evaluating suggestion={sid} params={params}")
            result = evaluate_candidate(params, space=space, artifact_dir=artifact_dir)
            append_jsonl(evaluations_path, {"campaign_id": campaign_id, "suggestion_id": sid, **result})
            row = {
                "suggestion_id": sid,
                "parameter_values": params,
                "objective_values": result["objectives"],
                "metadata": {"conditions": params, "notes": result["notes"][:800]},
            }
            key = client.make_idempotency_key("xe-kr-result", campaign_id, str(sid or uuid.uuid4()))
            client.submit_results(campaign_id, results=[row], idempotency_key=key, force=True)
            successes += 1
            metrics = result.get("metrics", {})
            tagged("RESULT", f"{result['name']} ok={result['ok']} objectives={result['objectives']} metrics={metrics}")

    try:
        data, content_type = client.export_campaign(campaign_id, fmt="csv")
        write_bytes(artifact_dir / "campaign_export.csv", data)
        tagged("EVENT", f"exported campaign csv ({content_type})")
    except Exception as exc:
        tagged("ALERT", f"best-effort export failed: {type(exc).__name__}: {exc}")

    try:
        final_status = _status(client.get_campaign(campaign_id))
        if args.terminate_on_exit:
            client.lifecycle(campaign_id, action="terminate")
            tagged("EVENT", f"terminated campaign {campaign_id}")
        elif final_status == "running":
            client.lifecycle(campaign_id, action="pause")
            tagged("EVENT", f"paused campaign {campaign_id}; resume with --campaign-id {campaign_id}")
        else:
            tagged("EVENT", f"campaign {campaign_id} left status={final_status}")
    except Exception as exc:
        tagged("ALERT", f"best-effort lifecycle cleanup failed: {type(exc).__name__}: {exc}")

    logfire.info("xe_kr_mof_bo invocation finished", campaign_id=campaign_id, artifact_dir=str(artifact_dir))
    tagged("EVENT", f"done campaign_id={campaign_id} completed_this_invocation={successes}")
    return campaign_id
