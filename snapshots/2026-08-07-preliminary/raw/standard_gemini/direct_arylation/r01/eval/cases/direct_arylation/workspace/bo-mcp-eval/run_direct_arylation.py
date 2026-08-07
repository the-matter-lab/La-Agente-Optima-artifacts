#!/usr/bin/env python
"""
Run entrypoint script for the direct arylation BO-MCP campaign.
"""
import sys
import argparse
import logfire
from grafico.core.logfire_config import configure_logfire

# Configure Logfire and instrument requests
configure_logfire()
logfire.instrument_requests()

from direct_arylation.campaign import run_campaign_loop

def main():
    parser = argparse.ArgumentParser(description="Run direct arylation BO-MCP campaign.")
    parser.add_argument(
        "--campaign-id",
        type=str,
        default=None,
        help="Optional campaign ID to resume an existing campaign."
    )
    parser.add_argument(
        "--stop-file",
        type=str,
        default="STOP",
        help="Path to the stop file to check for graceful shutdown."
    )
    parser.add_argument(
        "--poll-s",
        type=int,
        default=180,
        help="Polling interval in seconds between iterations."
    )
    parser.add_argument(
        "--heartbeat-s",
        type=int,
        default=1800,
        help="Heartbeat interval in seconds."
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=60,
        help="Maximum attempted evaluations budget."
    )
    parser.add_argument(
        "--results-file",
        type=str,
        default="direct_arylation_results.json",
        help="Path to the local JSON results file."
    )
    
    args = parser.parse_args()
    
    try:
        run_campaign_loop(
            campaign_id=args.campaign_id,
            stop_file=args.stop_file,
            poll_s=args.poll_s,
            heartbeat_s=args.heartbeat_s,
            max_attempts=args.max_attempts,
            results_file=args.results_file
        )
    except Exception as e:
        print(f"[ALERT] Campaign execution failed: {e}", file=sys.stderr, flush=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
