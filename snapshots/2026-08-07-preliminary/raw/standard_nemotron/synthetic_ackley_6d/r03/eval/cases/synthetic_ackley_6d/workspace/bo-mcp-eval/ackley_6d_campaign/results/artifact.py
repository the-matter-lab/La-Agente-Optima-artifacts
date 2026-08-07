"""Results handling and artifact writing for 6D Ackley campaign.

Cache-buster nonce: 87fe1294-416b-4ab4-8491-0d8cb2c43c23
"""

import csv
import json
from pathlib import Path
from typing import Any

import logfire


class ResultRow:
    """Single result row for the campaign artifact."""

    def __init__(
        self,
        evaluation_index: int,
        parameter_values: dict[str, float],
        objective_values: dict[str, float],
        status: str,
        failure_reason: str | None = None,
        raw_response: float | None = None,
        suggestion_id: str | None = None,
    ):
        self.evaluation_index = evaluation_index
        self.parameter_values = parameter_values
        self.objective_values = objective_values
        self.status = status
        self.failure_reason = failure_reason
        self.raw_response = raw_response
        self.suggestion_id = suggestion_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "evaluation_index": self.evaluation_index,
            "parameter_values": self.parameter_values,
            "objective_values": self.objective_values,
            "status": self.status,
            "failure_reason": self.failure_reason,
            "raw_response": self.raw_response,
            "suggestion_id": self.suggestion_id,
        }

    def to_csv_row(self) -> list[Any]:
        return [
            self.evaluation_index,
            json.dumps(self.parameter_values),
            json.dumps(self.objective_values),
            self.status,
            self.failure_reason or "",
            self.raw_response if self.raw_response is not None else "",
            self.suggestion_id or "",
        ]


class ResultsArtifact:
    """Manages the results artifact file."""

    CSV_HEADERS = [
        "evaluation_index",
        "parameter_values",
        "objective_values",
        "status",
        "failure_reason",
        "raw_response",
        "suggestion_id",
    ]

    def __init__(self, path: Path):
        self.path = path
        self.rows: list[ResultRow] = []
        self._load_existing()

    def _load_existing(self):
        """Load existing results from artifact file if it exists."""
        if self.path.exists():
            with open(self.path, "r") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    self.rows.append(
                        ResultRow(
                            evaluation_index=int(row["evaluation_index"]),
                            parameter_values=json.loads(row["parameter_values"]),
                            objective_values=json.loads(row["objective_values"]),
                            status=row["status"],
                            failure_reason=row["failure_reason"] or None,
                            raw_response=float(row["raw_response"]) if row["raw_response"] else None,
                            suggestion_id=row["suggestion_id"] or None,
                        )
                    )
            logfire.info("Loaded existing results", count=len(self.rows), path=str(self.path))

    def add_row(self, row: ResultRow):
        """Add a result row and persist to disk."""
        self.rows.append(row)
        self._write_all()

    def _write_all(self):
        """Write all rows to CSV."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(self.CSV_HEADERS)
            for row in self.rows:
                writer.writerow(row.to_csv_row())

    def get_evaluated_points(self) -> set[tuple[float, ...]]:
        """Get set of already-evaluated parameter tuples to avoid duplicates."""
        points = set()
        for row in self.rows:
            if row.status == "success":
                point = tuple(row.parameter_values[f"x_{i}"] for i in range(1, 7))
                points.add(point)
        return points

    def get_last_evaluation_index(self) -> int:
        """Get the last evaluation index used."""
        if not self.rows:
            return 0
        return max(row.evaluation_index for row in self.rows)

    def get_successful_count(self) -> int:
        """Get count of successful evaluations."""
        return sum(1 for row in self.rows if row.status == "success")

    def get_attempted_count(self) -> int:
        """Get total count of attempted evaluations."""
        return len(self.rows)

    def get_best_result(self) -> ResultRow | None:
        """Get the best successful result by surface_response."""
        successful = [row for row in self.rows if row.status == "success"]
        if not successful:
            return None
        return max(successful, key=lambda r: r.objective_values.get("surface_response", -float("inf")))

    def print_summary(self):
        """Print a summary of results."""
        best = self.get_best_result()
        successful = self.get_successful_count()
        attempted = self.get_attempted_count()

        print("\n" + "=" * 60)
        print("CAMPAIGN RESULTS SUMMARY")
        print("=" * 60)
        print(f"Attempted evaluations: {attempted}")
        print(f"Successful evaluations: {successful}")
        print(f"Failed evaluations: {attempted - successful}")

        if best:
            print(f"\nBest result (evaluation #{best.evaluation_index}):")
            print(f"  surface_response: {best.objective_values['surface_response']:.6f}")
            print(f"  raw_response: {best.raw_response:.6f}")
            print(f"  Coordinates:")
            for i in range(1, 7):
                print(f"    x_{i} = {best.parameter_values[f'x_{i}']:.6f}")

        print("\nAll evaluated candidates:")
        print("-" * 100)
        header = f"{'Idx':>4} | {'surface_response':>16} | {'raw_response':>12} | {'Status':>8} | Coordinates"
        print(header)
        print("-" * 100)
        for row in self.rows:
            coords = " ".join(f"x_{i}={row.parameter_values[f'x_{i}']:.4f}" for i in range(1, 7))
            sr = row.objective_values.get("surface_response", float("nan"))
            rr = row.raw_response if row.raw_response is not None else float("nan")
            print(f"{row.evaluation_index:>4} | {sr:>16.6f} | {rr:>12.6f} | {row.status:>8} | {coords}")
        print("=" * 60)