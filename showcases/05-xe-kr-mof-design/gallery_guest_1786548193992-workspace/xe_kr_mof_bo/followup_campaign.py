from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

import logfire
from domains.bo_mcp.client import BoMcpClient, BoMcpClientError, BoMcpOperationError

from .campaign import _campaign_id, _maybe_resume, _params, _status, _suggestion_id, _suggestions
from .evaluation import append_jsonl, evaluate_candidate
from .followup_intake import build_followup_intake
from .refined_space import build_refined_space, decode_candidate
from .reporting import tagged, write_bytes


def _candidate_id(suggestion: dict) -> str:
    p = suggestion.get("parameter_values") or suggestion.get("parameters") or suggestion.get("candidate") or {}
    return str(p["candidate_id"])


def _seed_payload(space: dict, seed_limit: int) -> list[dict]:
    seeds = space["seed_rows"] if seed_limit < 0 else space["seed_rows"][:seed_limit]
    rows = []
    for seed in seeds:
        src = seed["source_row"]
        decoded = decode_candidate(seed["candidate_id"])
        rows.append(
            {
                "parameter_values": {"candidate_id": seed["candidate_id"]},
                "objective_values": src["objectives"],
                "metadata": {
                    "conditions": decoded,
                    "notes": f"historical seed from prior Xe/Kr campaign: {src.get('name', seed['candidate_id'])}",
                },
            }
        )
    return rows


def run(args) -> str:
    artifact_dir = Path(args.artifact_dir) / time.strftime("%Y%m%d_%H%M%S")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    evaluations_path = artifact_dir / "evaluations.jsonl"
    tagged("EVENT", f"artifacts={artifact_dir} log={artifact_dir / 'run.log'}")

    space = build_refined_space(
        args.prior_artifact_dir,
        node_limit_per_topology=args.node_limit_per_topology,
        edge_limit=args.edge_limit,
        min_seed_balance=args.min_seed_balance,
    )
    (artifact_dir / "refined_candidate_space.json").write_text(json.dumps(space, indent=2, sort_keys=True))
    tagged(
        "EVENT",
        f"refined space: {len(space['candidate_ids'])} compatible candidate_id triples; "
        f"prior ok/total={space['prior_success_count']}/{space['prior_total_count']}",
    )

    client = BoMcpClient.from_env(timeout_s=args.client_timeout_s)
    if args.campaign_id:
        campaign_id = args.campaign_id
        _maybe_resume(client, campaign_id)
    else:
        seed_rows = _seed_payload(space, args.seed_limit)
        intake = build_followup_intake(
            space,
            name=args.campaign_name,
            batch_size=args.batch_size,
            new_budget=args.new_budget,
            seed_count=len(seed_rows),
        )
        (artifact_dir / "campaign_intake.json").write_text(json.dumps(intake, indent=2, sort_keys=True))
        validation = client.validate_intake(intake)
        (artifact_dir / "validation.json").write_text(json.dumps(validation, indent=2, sort_keys=True))
        if not validation.get("valid", False):
            tagged("ALERT", f"intake invalid: {validation.get('errors')}")
            raise RuntimeError("BO-MCP intake validation failed")
        created = client.create_campaign(intake, idempotency_key=client.make_idempotency_key("xe-kr-followup", str(uuid.uuid4())))
        campaign_id = _campaign_id(created)
        tagged("EVENT", f"created follow-up campaign {campaign_id}")
        if seed_rows:
            key = client.make_idempotency_key("xe-kr-followup-seeds", campaign_id, str(len(seed_rows)))
            client.submit_results(campaign_id, results=seed_rows, idempotency_key=key, force=True)
            tagged("EVENT", f"seeded {len(seed_rows)} historical compatible results from {args.prior_artifact_dir}")

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
        if decision.get("action") != "bo_generate_suggestions":
            tagged("EVENT", f"BO next_action={decision.get('action')}; stopping invocation")
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
            candidate_id = _candidate_id(suggestion)
            decoded = decode_candidate(candidate_id)
            tagged("EVENT", f"evaluating suggestion={sid} candidate_id={candidate_id}")
            result = evaluate_candidate(decoded, space={"topologies": space["topologies"], "compatible_nodes": {k: [{"id": n} for n in v] for k, v in space["compatible_nodes"].items()}, "edges": space["edges"]}, artifact_dir=artifact_dir)
            append_jsonl(evaluations_path, {"campaign_id": campaign_id, "suggestion_id": sid, "candidate_id": candidate_id, **result})
            row = {
                "suggestion_id": sid,
                "parameter_values": {"candidate_id": candidate_id},
                "objective_values": result["objectives"],
                "metadata": {"conditions": decoded, "notes": result["notes"][:800]},
            }
            key = client.make_idempotency_key("xe-kr-followup-result", campaign_id, str(sid or uuid.uuid4()))
            client.submit_results(campaign_id, results=[row], idempotency_key=key, force=True)
            successes += 1
            tagged("RESULT", f"{candidate_id} -> {result['name']} ok={result['ok']} objectives={result['objectives']} metrics={result.get('metrics', {})}")

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

    logfire.info("xe_kr_mof_bo follow-up invocation finished", campaign_id=campaign_id, artifact_dir=str(artifact_dir))
    tagged("EVENT", f"done campaign_id={campaign_id} completed_this_invocation={successes}")
    return campaign_id
