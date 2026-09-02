from __future__ import annotations

import csv
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
CANDIDATE_CSV = PACKAGE_DIR / "candidate_table.csv"


def load_candidates(path: Path = CANDIDATE_CSV) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def candidate_index(path: Path = CANDIDATE_CSV) -> dict[str, dict[str, str]]:
    return {row["candidate_id"]: row for row in load_candidates(path)}


def categories(path: Path = CANDIDATE_CSV) -> list[str]:
    return [row["candidate_id"] for row in load_candidates(path)]


def find_by_groups(rows: list[dict[str, str]], groups: tuple[str, str, str]) -> dict[str, str]:
    wanted = sorted(groups)
    for row in rows:
        if sorted([row["R1"], row["R2"], row["R3"]]) == wanted:
            return row
    raise KeyError(groups)


def choose_warm_start(rows: list[dict[str, str]], n: int = 8) -> list[dict[str, str]]:
    requested = [
        ("Me", "Me", "Me"),
        ("Me", "Me", "Ph"),
        ("Me", "Ph", "Ph"),
        ("Ph", "Ph", "Ph"),
        ("tBu", "tBu", "Ph"),
        ("Cy", "Cy", "Cy"),
        ("pOMePh", "pOMePh", "pOMePh"),
        ("pCF3Ph", "pCF3Ph", "pCF3Ph"),
    ]
    picked: list[dict[str, str]] = []
    seen: set[str] = set()
    for triple in requested:
        row = find_by_groups(rows, triple)
        if row["candidate_id"] not in seen:
            picked.append(row)
            seen.add(row["candidate_id"])
        if len(picked) >= n:
            break
    if len(picked) < n:
        for row in rows:
            if row["candidate_id"] not in seen:
                picked.append(row)
                seen.add(row["candidate_id"])
            if len(picked) >= n:
                break
    return picked


def warm_start_rationale(row: dict[str, str]) -> str:
    labels = {row["R1"], row["R2"], row["R3"]}
    if labels == {"Me"}:
        return "small, strongly donating alkyl baseline"
    if labels == {"Ph"}:
        return "aryl-rich lower-donor/benchmarked steric baseline"
    if "tBu" in labels:
        return "bulky alkyl point probing excessive steric demand"
    if "Cy" in labels:
        return "bulky saturated alkyl donor without aryl pi withdrawal"
    if "pOMePh" in labels:
        return "electron-rich aryl donor-side boundary"
    if "pCF3Ph" in labels:
        return "electron-poor aryl stability-side boundary"
    return "mixed alkyl/aryl interpolation near the expected target region"
