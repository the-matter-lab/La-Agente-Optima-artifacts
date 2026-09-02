from __future__ import annotations

import argparse
import warnings

import logfire
from grafico.core.logfire_config import configure_logfire

warnings.filterwarnings("ignore")
configure_logfire(console=False)
configure_logfire(console=False)
logfire.instrument_requests()

from xe_kr_mof_bo.campaign import run


def parse_args():
    p = argparse.ArgumentParser(description="BO-MCP/BayBE PORMAKE MOF Xe/Kr proxy optimization")
    p.add_argument("--campaign-id", default=None, help="Resume/reopen an existing BO-MCP campaign id")
    p.add_argument("--campaign-name", default="xe-kr-pormake-mof-baybe")
    p.add_argument("--artifact-dir", default="xe_kr_mof_bo_artifacts")
    p.add_argument("--stop-file", default="STOP")
    p.add_argument("--heartbeat-s", type=float, default=1800.0)
    p.add_argument("--client-timeout-s", type=float, default=120.0)
    p.add_argument("--generate-timeout-s", type=float, default=900.0)
    p.add_argument("--total-budget", type=int, default=30, help="Immutable BO campaign max observations")
    p.add_argument("--batch-size", type=int, default=3, help="BO suggestions per iteration")
    p.add_argument("--initial-design-size", type=int, default=9, help="Initial design size inside BO-MCP")
    p.add_argument("--max-evaluations", type=int, default=30, help="Per-invocation evaluation budget")
    p.add_argument("--node-limit-per-topology", type=int, default=6)
    p.add_argument("--edge-limit", type=int, default=10)
    p.add_argument("--terminate-on-exit", action="store_true", help="Terminate instead of pausing; useful for bounded smoke tests")
    return p.parse_args()


if __name__ == "__main__":
    run(parse_args())
