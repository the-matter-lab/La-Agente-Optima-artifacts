"""Main campaign orchestration for 6D Ackley optimization.

Cache-buster nonce: 87fe1294-416b-4ab4-8491-0d8cb2c43c23
"""

import os
import sys
import time
from pathlib import Path
from typing import Any

import logfire

from ackley_6d_campaign.campaign.bo_client import BoMcpClient
from ackley_6d_campaign.evaluation.objective import evaluate_ackley, get_optimum
from ackley_6d_campaign.results.artifact import ResultRow, ResultsArtifact
from ackley_6d_campaign.search_space.intake import build_intake, intake_to_dict, MARKER, CAMPAIGN_NAME

# Campaign configuration
MAX_OBSERVATIONS = 60


class AckleyCampaign:
    """Orchestrates the 6D Ackley BO-MCP campaign."""

    def __init__(
        self,
        client: BoMcpClient,
        artifact_path: Path,
        campaign_id: str | None = None,
        poll_interval: float = 180.0,
        heartbeat_interval: float = 1800.0,
        stop_file: Path | None = None,
    ):
        self.client = client
        self.artifact_path = artifact_path
        self.campaign_id = campaign_id
        self.poll_interval = poll_interval
        self.heartbeat_interval = heartbeat_interval
        self.stop_file = stop_file or Path("STOP")
        self.artifact = ResultsArtifact(artifact_path)
        self.last_heartbeat = time.time()
        self.evaluation_index = self.artifact.get_last_evaluation_index()

    def _check_stop_file(self) -> bool:
        """Check if stop file exists. If so, remove it and return True."""
        if self.stop_file.exists():
            logfire.info("Stop file detected, stopping campaign", stop_file=str(self.stop_file))
            print(f"[EVENT] Stop file detected at {self.stop_file}, stopping campaign")
            self.stop_file.unlink()
            return True
        return False

    def _heartbeat(self):
        """Print heartbeat if interval elapsed."""
        now = time.time()
        if now - self.last_heartbeat >= self.heartbeat_interval:
            print(f"[HEARTBEAT] Campaign {self.campaign_id} running, "
                  f"evaluations: {self.artifact.get_attempted_count()}/{MAX_OBSERVATIONS}, "
                  f"successful: {self.artifact.get_successful_count()}")
            self.last_heartbeat = now

    def _evaluate_suggestion(self, suggestion_id: str, params: dict[str, Any]) -> ResultRow:
        """Evaluate a single suggestion using the deterministic Ackley function."""
        self.evaluation_index += 1
        eval_idx = self.evaluation_index

        logfire.info("Evaluating suggestion", suggestion_id=suggestion_id, index=eval_idx)

        try:
            # Evaluate objective
            obj_values = evaluate_ackley(params)
            raw_response = obj_values["raw_response"]
            surface_response = obj_values["surface_response"]

            result = ResultRow(
                evaluation_index=eval_idx,
                parameter_values=params,
                objective_values={"surface_response": surface_response},
                status="success",
                raw_response=raw_response,
                suggestion_id=suggestion_id,
            )
            print(f"[RESULT] eval={eval_idx} suggestion={suggestion_id} "
                  f"surface_response={surface_response:.6f} raw_response={raw_response:.6f} "
                  f"params={params}")
            return result

        except Exception as e:
            logfire.error("Evaluation failed", suggestion_id=suggestion_id, error=str(e))
            print(f"[ALERT] eval={eval_idx} suggestion={suggestion_id} FAILED: {e}")
            result = ResultRow(
                evaluation_index=eval_idx,
                parameter_values=params,
                objective_values={"surface_response": float("nan")},
                status="failed",
                failure_reason=str(e),
                suggestion_id=suggestion_id,
            )
            return result

    def _submit_results(self, results: list[ResultRow]):
        """Submit results to BO-MCP."""
        payload = []
        for r in results:
            payload.append({
                "suggestion_id": r.suggestion_id,
                "parameter_values": r.parameter_values,
                "objective_values": r.objective_values,
            })

        response = self.client.submit_results(self.campaign_id, payload)
        if not response.success:
            logfire.error("Result submission failed", errors=response.errors)
            print(f"[ALERT] Result submission failed: {response.errors}")
            raise RuntimeError(f"Result submission failed: {response.errors}")

        logfire.info("Results submitted", result_ids=response.result_ids)
        for r in results:
            self.artifact.add_row(r)

    def run_iteration(self) -> bool:
        """Run one BO iteration: generate suggestions, evaluate, submit.

        Returns True if campaign should continue, False if done/stopped.
        """
        self._heartbeat()

        if self._check_stop_file():
            return False

        # Check budget
        attempted = self.artifact.get_attempted_count()
        if attempted >= MAX_OBSERVATIONS:
            print(f"[EVENT] Budget exhausted: {attempted}/{MAX_OBSERVATIONS} evaluations")
            return False

        # Generate suggestions
        print(f"[EVENT] Generating suggestions (attempted: {attempted}/{MAX_OBSERVATIONS})")
        suggest_response = self.client.generate_suggestions(self.campaign_id)

        if not suggest_response.success:
            errors = suggest_response.errors
            print(f"[ALERT] Suggestion generation failed: {errors}")

            # Check for budget exceeded or stopping criteria
            if any("budget" in e.lower() or "exceeded" in e.lower() or "stopping" in e.lower() for e in errors):
                print("[EVENT] Stopping criteria met")
                return False

            # Other errors - continue to next iteration after logging
            time.sleep(self.poll_interval)
            return True

        suggestions = suggest_response.suggestions
        if not suggestions:
            print("[EVENT] No suggestions generated, campaign may be complete")
            return False

        print(f"[EVENT] Received {len(suggestions)} suggestion(s)")

        # Evaluate each suggestion
        results_to_submit = []
        for suggestion in suggestions:
            # Check budget again before each evaluation
            if self.artifact.get_attempted_count() >= MAX_OBSERVATIONS:
                print(f"[EVENT] Budget reached during batch evaluation")
                break

            # Check for duplicate (should not happen with BO-MCP but safety check)
            params = suggestion.parameter_values
            point = tuple(params.get(f"x_{i}", 0.0) for i in range(1, 7))
            if point in self.artifact.get_evaluated_points():
                print(f"[ALERT] Duplicate point detected, skipping: {params}")
                self.evaluation_index += 1
                result = ResultRow(
                    evaluation_index=self.evaluation_index,
                    parameter_values=params,
                    objective_values={"surface_response": float("nan")},
                    status="skipped_duplicate",
                    failure_reason="Duplicate parameter values",
                    suggestion_id=suggestion.suggestion_id,
                )
                results_to_submit.append(result)
                continue

            # Evaluate
            result = self._evaluate_suggestion(suggestion.suggestion_id, params)
            results_to_submit.append(result)

        # Submit all results
        if results_to_submit:
            self._submit_results(results_to_submit)

        return True

    def initialize_campaign(self) -> str:
        """Create or resume campaign. Returns campaign_id."""
        if self.campaign_id:
            # Resume existing campaign
            print(f"[EVENT] Resuming campaign {self.campaign_id}")
            campaign = self.client.get_campaign(self.campaign_id)
            # Verify marker in name
            campaign_name = campaign.get("name", "")
            if MARKER not in campaign_name:
                raise ValueError(f"Campaign {self.campaign_id} does not contain required marker {MARKER}")
            return self.campaign_id

        # Create new campaign
        print(f"[EVENT] Creating new campaign: {CAMPAIGN_NAME}")
        intake = build_intake(max_observations=MAX_OBSERVATIONS)
        intake_dict = intake_to_dict(intake)

        response = self.client.create_campaign(intake_dict)
        if not response.success:
            raise RuntimeError(f"Campaign creation failed: {response.errors}")

        self.campaign_id = response.campaign_id
        print(f"[EVENT] Campaign created: {self.campaign_id}")
        print(f"BO_MCP_CAMPAIGN_ID={self.campaign_id}")
        return self.campaign_id

    def run(self) -> str:
        """Run the campaign loop."""
        self.initialize_campaign()

        print(f"[EVENT] Starting optimization loop (max {MAX_OBSERVATIONS} evaluations)")
        print(f"BO_MCP_CAMPAIGN_ID={self.campaign_id}")

        iteration = 0
        while True:
            iteration += 1
            print(f"\n[EVENT] === Iteration {iteration} ===")

            try:
                continue_campaign = self.run_iteration()
                if not continue_campaign:
                    break
            except KeyboardInterrupt:
                print("\n[EVENT] Interrupted by user")
                break
            except Exception as e:
                logfire.exception("Iteration failed")
                print(f"[ALERT] Iteration failed: {e}")
                # Continue to next iteration unless budget exhausted
                if self.artifact.get_attempted_count() >= MAX_OBSERVATIONS:
                    break
                time.sleep(self.poll_interval)

        # Final summary
        self.artifact.print_summary()
        print(f"\nBO_MCP_CAMPAIGN_ID={self.campaign_id}")
        return self.campaign_id


def run_campaign(
    campaign_id: str | None = None,
    artifact_dir: str = "artifacts",
    poll_interval: float = 180.0,
    heartbeat_interval: float = 1800.0,
    stop_file: str = "STOP",
) -> str:
    """Entry point for running the campaign."""
    # Setup paths
    artifact_path = Path(artifact_dir) / "results.csv"
    stop_path = Path(stop_file)

    # Create client
    client = BoMcpClient.from_env()

    # Run campaign
    campaign = AckleyCampaign(
        client=client,
        artifact_path=artifact_path,
        campaign_id=campaign_id,
        poll_interval=poll_interval,
        heartbeat_interval=heartbeat_interval,
        stop_file=stop_path,
    )

    try:
        return campaign.run()
    finally:
        client.close()