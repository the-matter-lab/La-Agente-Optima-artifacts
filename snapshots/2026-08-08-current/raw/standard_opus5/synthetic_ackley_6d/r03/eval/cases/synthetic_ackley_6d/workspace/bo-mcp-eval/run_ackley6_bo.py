#!/usr/bin/env python3
"""CLI entrypoint for the Ackley-6 BO-MCP campaign (BayBE backend).

Campaign marker: akg-eval-2a04c50f6e2f4a42952ebc5cbc96b431
Nonce:           c02de9f3-c0fa-4590-bebf-d77d7aa55ad1
"""

import argparse

import logfire
from grafico.core.logfire_config import configure_logfire

configure_logfire()
logfire.instrument_requests()

from ackley6_bo.campaign import run  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Ackley-6 synthetic BO-MCP campaign")
    parser.add_argument("--campaign-id", default=None, help="resume/continue an existing campaign")
    parser.add_argument("--max-evals", type=int, default=60, help="attempted evaluations this invocation")
    parser.add_argument("--poll-s", type=float, default=180.0, help="wait between server polls when idle")
    parser.add_argument("--heartbeat-s", type=float, default=1800.0, help="liveness print interval")
    parser.add_argument("--stop-file", default="STOP", help="graceful-stop marker file")
    parser.add_argument("--artifact-base", default="artifacts/ackley6_bo", help="artifact root directory")
    parser.add_argument("--eval-timeout-s", type=float, default=60.0, help="per-candidate timeout")
    parser.add_argument(
        "--diagnostics-verbosity",
        default="none",
        choices=["none", "minimal", "standard", "detailed"],
        help="final BO-MCP diagnostics detail; cold-compute costs minutes on a grown campaign (default: skip)",
    )
    args = parser.parse_args()

    logfire.info("ackley6_bo start {args}", args=vars(args))
    run(
        campaign_id=args.campaign_id,
        max_evals=args.max_evals,
        poll_s=args.poll_s,
        heartbeat_s=args.heartbeat_s,
        stop_file=args.stop_file,
        artifact_base=args.artifact_base,
        eval_timeout_s=args.eval_timeout_s,
        diagnostics_verbosity=args.diagnostics_verbosity,
    )


if __name__ == "__main__":
    main()
