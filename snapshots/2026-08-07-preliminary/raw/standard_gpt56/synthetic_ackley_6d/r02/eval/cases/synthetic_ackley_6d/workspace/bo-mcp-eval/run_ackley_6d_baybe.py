#!/usr/bin/env python3
import argparse
import os
from pathlib import Path

import logfire
from grafico.core.logfire_config import configure_logfire

configure_logfire()
logfire.instrument_requests()

from ackley_6d_baybe.campaign import run_campaign


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the owned 6D Ackley BayBE campaign.")
    parser.add_argument("--campaign-id")
    parser.add_argument("--max-attempts", type=int, default=60)
    parser.add_argument("--poll-s", type=int, default=180)
    parser.add_argument("--heartbeat-s", type=int, default=1800)
    parser.add_argument("--stop-file", type=Path, default=Path("STOP"))
    parser.add_argument("--artifact-root", type=Path, default=Path("artifacts/ackley_6d_baybe"))
    return parser.parse_args()


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    run_campaign(parse_args())
