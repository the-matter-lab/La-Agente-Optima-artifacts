#!/usr/bin/env python
import os
import sys
import argparse
import logging
import logfire

# Add /app to PYTHONPATH so we can import domains and grafico
sys.path.insert(0, "/app")

from grafico.core.logfire_config import configure_logfire
from domains.bo_mcp.client import BoMcpClient
from synthetic_ackley_6d.campaign import run_campaign_loop

def main():
    parser = argparse.ArgumentParser(
        description="Run 6D Ackley Synthetic Optimization Campaign"
    )
    parser.add_argument(
        "--campaign-id",
        type=str,
        default=os.getenv("BO_MCP_CAMPAIGN_ID"),
        help="Campaign ID to resume/reopen. If not provided, a new campaign is created."
    )
    parser.add_argument(
        "--poll-s",
        type=int,
        default=180,
        help="Polling interval in seconds (default: 180)"
    )
    parser.add_argument(
        "--heartbeat-s",
        type=int,
        default=1800,
        help="Heartbeat interval in seconds (default: 1800)"
    )
    parser.add_argument(
        "--stop-file",
        type=str,
        default="STOP",
        help="Path to the stop file for graceful shutdown (default: STOP)"
    )
    parser.add_argument(
        "--artifact-dir",
        type=str,
        default="artifacts",
        help="Directory to save results artifacts (default: artifacts)"
    )
    parser.add_argument(
        "--budget",
        type=int,
        default=60,
        help="Total evaluation budget (default: 60)"
    )
    args = parser.parse_args()

    # Configure Logfire and request instrumentation
    configure_logfire()
    logfire.instrument_requests()

    # Configure file logging for everything else
    log_file = "campaign.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, mode="a"),
        ]
    )

    # Ensure stdout is unbuffered
    sys.stdout.reconfigure(line_buffering=True)

    # Check environment variables
    api_url = os.getenv("BO_MCP_API_URL")
    api_key = os.getenv("BO_MCP_API_KEY")
    if not api_url or not api_key:
        print("[ALERT] Missing required environment variables BO_MCP_API_URL or BO_MCP_API_KEY.")
        sys.exit(1)

    # Initialize BO-MCP client
    try:
        client = BoMcpClient.from_env()
    except Exception as e:
        print(f"[ALERT] Failed to initialize BoMcpClient: {e}")
        sys.exit(1)

    # Run campaign loop
    try:
        run_campaign_loop(
            client=client,
            campaign_id=args.campaign_id,
            poll_s=args.poll_s,
            heartbeat_s=args.heartbeat_s,
            stop_file=args.stop_file,
            artifact_dir=args.artifact_dir,
            budget=args.budget,
        )
    except KeyboardInterrupt:
        print("[EVENT] Campaign execution interrupted by user.")
        sys.exit(0)
    except Exception as e:
        print(f"[ALERT] Campaign execution failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
