from __future__ import annotations

import argparse
from pathlib import Path

import logfire
from grafico.core.logfire_config import configure_logfire

from robochemflex_yield_only_bo.recreate import DEFAULT_EXPORT, run

configure_logfire()
logfire.instrument_requests()


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare/create a yield-only BO-MCP campaign seeded from 20 valid prior RoboChemFlex results.")
    parser.add_argument("--source-export", type=Path, default=DEFAULT_EXPORT)
    parser.add_argument("--artifact-dir", type=Path, default=None)
    parser.add_argument("--campaign-name", default=None)
    parser.add_argument("--campaign-id", default=None, help="Existing empty yield-only BO campaign to seed instead of creating one.")
    parser.add_argument("--expected-seed-count", type=int, default=20)
    parser.add_argument("--bo-timeout-s", type=float, default=300.0)
    parser.add_argument("--run-nonce", default=None)
    parser.add_argument("--validate-intake", action=argparse.BooleanOptionalAction, default=False, help="Call BO-MCP validate_intake only; safe read/preflight mutation-free validation.")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Write preflight artifacts only. Default.")
    parser.add_argument("--execute-create-seed", dest="dry_run", action="store_false", help="Create/seed BO-MCP campaign; still requires --confirm-create-seed.")
    parser.add_argument("--confirm-create-seed", action="store_true", help="Required with --execute-create-seed. Does not touch RoboFlex hardware.")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
