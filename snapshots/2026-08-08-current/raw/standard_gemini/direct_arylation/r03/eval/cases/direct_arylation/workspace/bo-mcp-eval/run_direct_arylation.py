#!/usr/bin/env python
import sys
import argparse
import logging
from direct_arylation.campaign import run_campaign


def main() -> None:
    # Ensure stdout is unbuffered so monitor-friendly tags are printed immediately
    sys.stdout.reconfigure(line_buffering=True)

    parser = argparse.ArgumentParser(
        description="Run or resume the Direct Arylation BO-MCP campaign."
    )
    parser.add_argument(
        "--campaign-id",
        type=str,
        default=None,
        help="Optional campaign ID to resume or query.",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=60,
        help="Maximum number of evaluation attempts (default: 60).",
    )
    parser.add_argument(
        "--poll-s",
        type=int,
        default=180,
        help="Polling interval in seconds between loop iterations (default: 180).",
    )
    parser.add_argument(
        "--heartbeat-s",
        type=int,
        default=1800,
        help="Heartbeat interval in seconds (default: 1800).",
    )
    parser.add_argument(
        "--stop-file",
        type=str,
        default="STOP",
        help="Path to the stop file for graceful shutdown (default: STOP).",
    )
    parser.add_argument(
        "--log-file",
        type=str,
        default="campaign_run.log",
        help="Path to the log file on disk (default: campaign_run.log).",
    )

    args = parser.parse_args()

    # Configure logging to write to disk
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(args.log_file, mode="a"),
        ],
    )

    # Run the campaign
    try:
        run_campaign(
            campaign_id=args.campaign_id,
            max_attempts=args.max_attempts,
            poll_s=args.poll_s,
            heartbeat_s=args.heartbeat_s,
            stop_file=args.stop_file,
        )
    except Exception as e:
        print(f"[ALERT] Campaign execution failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
