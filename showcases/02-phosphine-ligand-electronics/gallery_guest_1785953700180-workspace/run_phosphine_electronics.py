from __future__ import annotations

import argparse

import logfire
from grafico.core.logfire_config import configure_logfire

try:
    configure_logfire(console=False)
except TypeError:
    configure_logfire()
logfire.instrument_requests()

from phosphine_electronics.campaign import run  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="BO-MCP + Gráfico PySCF finite phosphine electronic-tuning campaign")
    p.add_argument("--campaign-id", default="", help="Resume/reopen an existing BO-MCP campaign id")
    p.add_argument("--campaign-name", default="phosphine_electronics_finite_mobo", help="Name for a new campaign")
    p.add_argument("--artifact-dir", default="", help="Optional artifact directory; default is artifacts/phosphine_electronics_<UTC>")
    p.add_argument("--stop-file", default="STOP", help="Stop marker checked before suggestion generation")
    p.add_argument("--poll-s", type=float, default=180.0, help="Sleep interval between BO batches (keep 120-300 for monitored runs)")
    p.add_argument("--heartbeat-s", type=float, default=1800.0, help="Tagged liveness interval")
    p.add_argument("--warm-start-size", type=int, default=8, help="Script-selected initial ligand count")
    p.add_argument("--batch-size", type=int, default=2, help="BO suggestion batch size")
    p.add_argument("--max-bo-batches", type=int, default=10, help="Per-invocation cap on BO-guided batches after warm start")
    p.add_argument("--eval-workers", type=int, default=2, help="Threaded parallel evaluations per batch")
    p.add_argument("--client-timeout-s", type=float, default=120.0, help="BO-MCP client request timeout")
    p.add_argument("--suggestion-timeout-s", type=float, default=900.0, help="BO-MCP suggestion-generation timeout")
    p.add_argument("--pyscf-timeout-s", type=float, default=1800.0, help="Per-ligand Gráfico PySCF workflow timeout")
    p.add_argument("--geometry-max-steps", type=int, default=100, help="Maximum geometry-optimization steps exposed to PySCF workflow")
    p.add_argument("--synthetic-evaluator", action="store_true", help="Smoke-test only: replace PySCF with deterministic finite surrogate")
    p.add_argument("--pyscf-smoke-only", action="store_true", help="Run one real PySCF evaluator call and exit without BO-MCP")
    p.add_argument("--pyscf-smoke-candidate", default="P_0001", help="Candidate id for --pyscf-smoke-only")
    p.add_argument("--terminate-on-exit", action="store_true", help="Terminate instead of pausing at the end; intended for smoke tests only")
    return p


if __name__ == "__main__":
    run(build_parser().parse_args())
