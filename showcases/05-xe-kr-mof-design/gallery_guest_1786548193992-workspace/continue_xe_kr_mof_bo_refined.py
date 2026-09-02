from __future__ import annotations

import argparse
import warnings

import logfire
from grafico.core.logfire_config import configure_logfire

warnings.filterwarnings("ignore")
configure_logfire(console=False)
logfire.instrument_requests()

from xe_kr_mof_bo.followup_campaign import run


def parse_args():
    p = argparse.ArgumentParser(description="Refined BO-MCP/BayBE Xe/Kr PORMAKE MOF follow-up campaign")
    p.add_argument("--campaign-id", default=None, help="Resume/reopen an existing follow-up BO-MCP campaign id")
    p.add_argument("--campaign-name", default="xe-kr-pormake-mof-baybe-refined-50")
    p.add_argument("--prior-artifact-dir", default="xe_kr_mof_bo_artifacts/20260812_154010")
    p.add_argument("--artifact-dir", default="xe_kr_mof_bo_refined_artifacts")
    p.add_argument("--stop-file", default="STOP")
    p.add_argument("--heartbeat-s", type=float, default=1800.0)
    p.add_argument("--client-timeout-s", type=float, default=120.0)
    p.add_argument("--generate-timeout-s", type=float, default=900.0)
    p.add_argument("--new-budget", type=int, default=50, help="New evaluations after historical seeds")
    p.add_argument("--batch-size", type=int, default=5, help="BO suggestions per iteration")
    p.add_argument("--max-evaluations", type=int, default=50, help="Per-invocation new evaluation budget")
    p.add_argument("--seed-limit", type=int, default=-1, help="Historical successful seeds to submit; -1 means all")
    p.add_argument("--node-limit-per-topology", type=int, default=6)
    p.add_argument("--edge-limit", type=int, default=18)
    p.add_argument("--min-seed-balance", type=float, default=0.0)
    p.add_argument("--terminate-on-exit", action="store_true", help="Terminate instead of pausing; useful for bounded smoke tests")
    return p.parse_args()


if __name__ == "__main__":
    run(parse_args())
