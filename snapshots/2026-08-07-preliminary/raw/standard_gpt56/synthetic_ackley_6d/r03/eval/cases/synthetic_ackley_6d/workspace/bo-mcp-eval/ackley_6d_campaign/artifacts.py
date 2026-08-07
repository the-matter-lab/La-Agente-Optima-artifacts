import json
import logging
from pathlib import Path


def artifact_paths(campaign_id: str) -> tuple[Path, Path]:
    directory = Path("artifacts") / "ackley_6d" / campaign_id
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "results.jsonl", directory / "run.log"


def configure_file_log(path: Path) -> None:
    logging.basicConfig(
        filename=path,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        force=True,
    )


def append_result(path: Path, row: dict) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")


def emit_result(row: dict) -> None:
    print(f"[RESULT] {json.dumps(row, sort_keys=True, allow_nan=False)}", flush=True)
