"""Campaign orchestration for 6D Ackley BO via BO-MCP."""

import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from domains.bo_mcp.client import BoMcpClient, BoMcpClientError, BoMcpOperationError

from ackley_6d_bo.evaluation import AckleyEvaluator
from ackley_6d_bo.intake import build_campaign_intake
from ackley_6d_bo.search_space import PARAM_NAMES, RAW_RESPONSE_MAX, RAW_RESPONSE_MIN, surface_response


class AckleyCampaign:
    """Orchestrates the BO-MCP campaign for 6D Ackley optimization."""

    def __init__(
        self,
        campaign_id: Optional[str] = None,
        results_dir: Optional[Path] = None,
        max_evaluations: int = 60,
        poll_interval: float = 180.0,
        heartbeat_interval: float = 1800.0,
        stop_file: Optional[Path] = None,
    ):
        """Initialize campaign orchestrator.

        Args:
            campaign_id: Existing campaign ID to resume, or None to create new
            results_dir: Directory for result artifacts
            max_evaluations: Maximum evaluations for this invocation (CLI budget)
            poll_interval: Seconds between next_action polls
            heartbeat_interval: Seconds between heartbeat logs
            stop_file: Path to stop file; if exists, pause gracefully
        """
        self.campaign_id = campaign_id
        self.results_dir = results_dir or Path("ackley_6d_results")
        self.max_evaluations = max_evaluations
        self.poll_interval = poll_interval
        self.heartbeat_interval = heartbeat_interval
        self.stop_file = stop_file or Path("STOP")

        self.client = BoMcpClient.from_env()
        self.evaluator = AckleyEvaluator(self.results_dir)
        self.evaluations_this_run = 0
        self.last_heartbeat = time.time()

        # Ensure results dir exists
        self.results_dir.mkdir(parents=True, exist_ok=True)

    def _log_event(self, msg: str) -> None:
        """Print tagged event line."""
        print(f"[EVENT] {msg}", flush=True)

    def _log_alert(self, msg: str) -> None:
        """Print tagged alert line."""
        print(f"[ALERT] {msg}", flush=True)

    def _log_result(self, msg: str) -> None:
        """Print tagged result line."""
        print(f"[RESULT] {msg}", flush=True)

    def _log_heartbeat(self, msg: str) -> None:
        """Print tagged heartbeat line."""
        print(f"[HEARTBEAT] {msg}", flush=True)

    def _check_stop_file(self) -> bool:
        """Check if stop file exists; if so, delete it and return True."""
        if self.stop_file.exists():
            self._log_event(f"Stop file {self.stop_file} detected; deleting and pausing")
            self.stop_file.unlink()
            return True
        return False

    def _maybe_heartbeat(self) -> None:
        """Log heartbeat if interval elapsed."""
        now = time.time()
        if now - self.last_heartbeat >= self.heartbeat_interval:
            self._log_heartbeat(f"Campaign {self.campaign_id} running; evaluations this run: {self.evaluations_this_run}")
            self.last_heartbeat = now

    def create_campaign(self, intake: Dict[str, Any]) -> str:
        """Create a new BO-MCP campaign."""
        self._log_event("Creating new campaign")
        idempotency_key = str(uuid.uuid4())
        try:
            response = self.client.create_campaign(intake, idempotency_key=idempotency_key)
        except (BoMcpClientError, BoMcpOperationError) as e:
            self._log_alert(f"Campaign creation failed: {e}")
            raise

        if not response.get("success"):
            errors = response.get("errors", ["Unknown error"])
            self._log_alert(f"Campaign creation rejected: {errors}")
            raise RuntimeError(f"Campaign creation failed: {errors}")

        campaign_id = response["campaign_id"]
        self._log_event(f"Created campaign {campaign_id}")
        return campaign_id

    def run_optimization_loop(self) -> None:
        """Run the main BO optimization loop."""
        self._log_event(f"Starting optimization loop (max {self.max_evaluations} evaluations this run)")

        while self.evaluations_this_run < self.max_evaluations:
            self._maybe_heartbeat()

            # Check stop file at top of loop
            if self._check_stop_file():
                self._pause_campaign()
                return

            # Ask server for next action
            try:
                decision = self.client.next_action(self.campaign_id)
            except (BoMcpClientError, BoMcpOperationError) as e:
                self._log_alert(f"next_action failed: {e}")
                raise

            action = decision.get("action")
            self._log_event(f"Server action: {action}")

            if action != "bo_generate_suggestions":
                self._log_event(f"Campaign not ready for suggestions (action={action}); pausing")
                self._pause_campaign()
                return

            # Generate suggestions
            try:
                suggestion_response = self.client.generate_suggestions(
                    self.campaign_id, batch_size=1
                )
            except (BoMcpClientError, BoMcpOperationError) as e:
                self._log_alert(f"generate_suggestions failed: {e}")
                raise

            suggestions = suggestion_response.get("suggestions", [])
            if not suggestions:
                self._log_alert("No suggestions returned; pausing")
                self._pause_campaign()
                return

            # Evaluate each suggestion
            for sugg in suggestions:
                if self.evaluations_this_run >= self.max_evaluations:
                    self._log_event("Reached evaluation budget for this run")
                    break

                if self._check_stop_file():
                    self._pause_campaign()
                    return

                suggestion_id = sugg["suggestion_id"]
                parameter_values = sugg["parameter_values"]

                self._log_event(f"Evaluating suggestion {suggestion_id}")

                # Evaluate
                result = self.evaluator.evaluate(suggestion_id, parameter_values)
                self.evaluations_this_run += 1

                # Log result
                status = result["status"]
                if status == "success":
                    surface = result["objective_values"]["surface_response"]
                    raw = result["raw_response"]
                    params_str = ", ".join(f"{k}={v:.6f}" for k, v in parameter_values.items())
                    self._log_result(
                        f"eval={result['evaluation_index']} surface={surface:.6f} raw={raw:.6f} [{params_str}]"
                    )
                else:
                    reason = result["failure_reason"]
                    self._log_alert(f"eval={result['evaluation_index']} FAILED: {reason}")

                # Submit result to BO-MCP (only successful evaluations with finite values)
                submission_payload = self.evaluator.to_submission_payload(result)
                if submission_payload is not None:
                    idempotency_key = str(uuid.uuid4())
                    try:
                        submit_response = self.client.submit_results(
                            self.campaign_id,
                            results=[submission_payload],
                            idempotency_key=idempotency_key,
                        )
                    except (BoMcpClientError, BoMcpOperationError) as e:
                        self._log_alert(f"submit_results failed: {e}")
                        raise

                    if not submit_response.get("success"):
                        self._log_alert(f"Result submission rejected: {submit_response.get('errors')}")
                        # Continue anyway - the server may have accepted it
                else:
                    # Failed evaluation (duplicate, error) - mark suggestion as failed in BO-MCP
                    try:
                        self.client.update_suggestion_status(suggestion_id, status="failed")
                    except (BoMcpClientError, BoMcpOperationError) as e:
                        self._log_alert(f"update_suggestion_status failed for {suggestion_id}: {e}")

            # Check if we should continue after batch
            if self.evaluations_this_run >= self.max_evaluations:
                self._log_event("Reached evaluation budget; pausing")
                self._pause_campaign()
                return

        # Loop ended naturally
        self._pause_campaign()

    def _pause_campaign(self) -> None:
        """Pause the campaign."""
        self._log_event(f"Pausing campaign {self.campaign_id}")
        try:
            self.client.lifecycle(self.campaign_id, action="pause")
        except (BoMcpClientError, BoMcpOperationError) as e:
            self._log_alert(f"Pause failed: {e}")

    def finalize_and_report(self) -> Dict[str, Any]:
        """Fetch all results and generate final report."""
        self._log_event("Fetching final results for reporting")

        try:
            results = self.client.get_results(self.campaign_id)
        except (BoMcpClientError, BoMcpOperationError) as e:
            self._log_alert(f"get_results failed: {e}")
            results = []

        # Also get local artifact for complete record
        local_results = self._load_local_results()

        # Merge: prefer local (has raw_response), supplement with server
        all_results = self._merge_results(local_results, results)

        # Generate report
        report = self._generate_report(all_results)

        # Write report artifact
        report_path = self.results_dir / "final_report.json"
        import json
        with report_path.open("w") as f:
            json.dump(report, f, indent=2)

        self._log_event(f"Final report written to {report_path}")

        # Print summary to stdout
        self._print_summary(report)

        return report

    def _load_local_results(self) -> List[Dict[str, Any]]:
        """Load results from local JSONL artifact."""
        artifact_path = self.results_dir / "evaluations.jsonl"
        if not artifact_path.exists():
            return []

        results = []
        import json
        with artifact_path.open() as f:
            for line in f:
                line = line.strip()
                if line:
                    results.append(json.loads(line))
        return results

    def _merge_results(
        self,
        local: List[Dict[str, Any]],
        server: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Merge local and server results, preferring local for raw_response."""
        # Index local by suggestion_id
        local_by_id = {r["suggestion_id"]: r for r in local}
        server_by_id = {r["suggestion_id"]: r for r in server}

        # Union of all suggestion_ids
        all_ids = set(local_by_id.keys()) | set(server_by_id.keys())

        merged = []
        for sid in all_ids:
            if sid in local_by_id:
                merged.append(local_by_id[sid])
            else:
                merged.append(server_by_id[sid])

        # Sort by evaluation_index
        merged.sort(key=lambda r: r.get("evaluation_index", 0))
        return merged

    def _generate_report(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate final report from all results."""
        successful = [r for r in results if r.get("status") == "success"]
        failed = [r for r in results if r.get("status") != "success"]

        # Find best
        best_result = None
        best_surface = -float("inf")

        for r in successful:
            surface = r["objective_values"]["surface_response"]
            if surface > best_surface:
                best_surface = surface
                best_result = r

        # Build candidate table
        candidate_table = []
        for r in results:
            row = {
                "evaluation_index": r.get("evaluation_index"),
                "suggestion_id": r.get("suggestion_id"),
                "parameter_values": r.get("parameter_values", {}),
                "objective_values": r.get("objective_values", {}),
                "status": r.get("status"),
                "failure_reason": r.get("failure_reason"),
                "raw_response": r.get("raw_response"),
            }
            candidate_table.append(row)

        if best_result:
            best_params = best_result["parameter_values"]
            best_raw = best_result["raw_response"]
        else:
            best_params = {}
            best_raw = None

        return {
            "campaign_id": self.campaign_id,
            "best_normalized_coordinates": best_params,
            "best_raw_response": best_raw,
            "best_surface_response": best_surface if best_result else None,
            "successful_evaluations": len(successful),
            "attempted_evaluations": len(results),
            "failed_evaluations": len(failed),
            "candidate_table": candidate_table,
        }

    def _print_summary(self, report: Dict[str, Any]) -> None:
        """Print summary to stdout."""
        print("\n" + "=" * 60)
        print("FINAL REPORT")
        print("=" * 60)
        print(f"Campaign ID: {report['campaign_id']}")
        print(f"Best surface_response: {report['best_surface_response']:.6f}")
        print(f"Best raw_response: {report['best_raw_response']:.6f}")
        print(f"Best normalized coordinates:")
        for name in PARAM_NAMES:
            val = report['best_normalized_coordinates'].get(name, 0.0)
            print(f"  {name}: {val:.6f}")
        print(f"Successful evaluations: {report['successful_evaluations']}")
        print(f"Attempted evaluations: {report['attempted_evaluations']}")
        print(f"Failed evaluations: {report['failed_evaluations']}")
        print("\nCandidate Table:")
        print("-" * 100)
        header = f"{'Idx':>4} | {'surface':>10} | {'raw':>10} | {'status':>8} | params"
        print(header)
        print("-" * 100)
        for row in report["candidate_table"]:
            idx = row["evaluation_index"] or 0
            surf = row["objective_values"].get("surface_response")
            raw = row["raw_response"]
            status = row["status"]
            surf_str = f"{surf:.6f}" if surf is not None else "N/A"
            raw_str = f"{raw:.6f}" if raw is not None else "N/A"
            params_str = ", ".join(f"{k}={v:.4f}" for k, v in row["parameter_values"].items())
            print(f"{idx:>4} | {surf_str:>10} | {raw_str:>10} | {status:>8} | {params_str}")
        print("-" * 100)

        # Required single-line output for main agent
        print(f"BO_MCP_CAMPAIGN_ID={report['campaign_id']}")


def run_campaign(
    campaign_id: Optional[str] = None,
    results_dir: Optional[str] = None,
    max_evaluations: int = 60,
    poll_interval: float = 180.0,
    heartbeat_interval: float = 1800.0,
    stop_file: Optional[str] = None,
    random_seed: int = 42,
    initial_design_size: int = 10,
) -> Dict[str, Any]:
    """Run the Ackley 6D BO campaign.

    Args:
        campaign_id: Existing campaign ID to resume (None = create new)
        results_dir: Directory for artifacts
        max_evaluations: Max evaluations this invocation
        poll_interval: Seconds between next_action calls
        heartbeat_interval: Seconds between heartbeats
        stop_file: Path to stop file
        random_seed: Campaign RNG seed
        initial_design_size: Initial design size

    Returns:
        Final report dictionary
    """
    results_path = Path(results_dir) if results_dir else Path("ackley_6d_results")
    stop_path = Path(stop_file) if stop_file else Path("STOP")

    campaign = AckleyCampaign(
        campaign_id=campaign_id,
        results_dir=results_path,
        max_evaluations=max_evaluations,
        poll_interval=poll_interval,
        heartbeat_interval=heartbeat_interval,
        stop_file=stop_path,
    )

    if campaign_id is None:
        # Create new campaign
        intake = build_campaign_intake(random_seed=random_seed, initial_design_size=initial_design_size)
        campaign.campaign_id = campaign.create_campaign(intake)
    else:
        campaign._log_event(f"Resuming campaign {campaign_id}")

    try:
        campaign.run_optimization_loop()
    finally:
        report = campaign.finalize_and_report()

    return report